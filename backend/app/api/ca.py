"""CA routes for lab root + client certificate issue/download (EAP-TLS path)."""

from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.config import get_settings
from app.db import get_db
from app.integrations.ca import get_ca_adapter
from app.integrations.ca.openssl_adapter import OpenSslLocalCaAdapter
from app.integrations.freeradius.tls_trust import publish_lab_ca, publish_lab_crl
from app.models.entities import (
    Certificate,
    CertificateAuthority,
    CertStatus,
    CertType,
)
from app.services.certificates import effective_cert_status, sweep_expired_certificates
from app.validation import IDENTITY_PATTERN

router = APIRouter(prefix="/ca", tags=["certificate-authority"])


class EnsureRootRequest(BaseModel):
    lab_id: UUID
    common_name: str = Field(default="802.1X Lab Root CA")


class IssueCertRequest(BaseModel):
    lab_id: UUID
    identity: str = Field(min_length=1, max_length=128, pattern=IDENTITY_PATTERN)
    days: int = Field(default=365, ge=1, le=3650)


class RevokeCertRequest(BaseModel):
    lab_id: UUID
    certificate_id: UUID


class CertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    subject: str
    issuer: str | None
    serial: str | None
    cert_type: CertType
    status: CertStatus
    not_before: datetime | None
    not_after: datetime | None
    created_at: datetime
    # Convenience identity (CN) parsed from subject for the UI.
    identity: str | None = None
    download_bundle: str | None = None
    download_p12: str | None = None


class AuthorityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    subject: str
    adapter: str
    created_at: datetime


class CertificateInventory(BaseModel):
    authority: AuthorityRead | None
    crl_available: bool
    crl_enforced: bool
    certificates: list[CertificateRead]


def _adapter() -> OpenSslLocalCaAdapter:
    adapter = get_ca_adapter()
    if not isinstance(adapter, OpenSslLocalCaAdapter):
        raise HTTPException(status_code=501, detail="Active CA adapter does not support file export")
    return adapter


@router.post("/ensure-root")
def ensure_root(
    payload: EnsureRootRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> dict:
    adapter = get_ca_adapter()
    info = adapter.ensure_root(payload.lab_id, payload.common_name)
    _upsert_ca_row(db, payload.lab_id, info.name, info.subject, info.storage_ref)
    try:
        publish_lab_ca(payload.lab_id, payload.common_name)
        freeradius_trust = "published"
    except Exception as exc:
        freeradius_trust = f"publish_failed: {exc}"
    return {
        "name": info.name,
        "subject": info.subject,
        "storage_ref": info.storage_ref,
        "not_before": info.not_before,
        "not_after": info.not_after,
        "freeradius_trust": freeradius_trust,
        "download_pem": f"/api/ca/root.pem?lab_id={payload.lab_id}",
    }


@router.post("/issue-client")
def issue_client(
    payload: IssueCertRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> dict:
    adapter = get_ca_adapter()
    try:
        root = adapter.ensure_root(payload.lab_id)
        _upsert_ca_row(db, payload.lab_id, root.name, root.subject, root.storage_ref)
        cert = adapter.issue_client_cert(payload.lab_id, payload.identity, payload.days)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Certificate issue failed: {exc}") from exc

    ca_row = db.scalar(
        select(CertificateAuthority)
        .where(CertificateAuthority.lab_id == payload.lab_id)
        .order_by(CertificateAuthority.created_at.desc())
        .limit(1)
    )
    row = Certificate(
        lab_id=payload.lab_id,
        authority_id=ca_row.id if ca_row else None,
        subject=cert.subject,
        issuer=cert.issuer,
        serial=cert.serial,
        cert_type=CertType.client,
        status=CertStatus.active,
        not_before=cert.not_before,
        not_after=cert.not_after,
        storage_ref=cert.storage_ref,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    try:
        publish_lab_ca(payload.lab_id)
        freeradius_trust = "published"
    except Exception as exc:
        freeradius_trust = f"publish_failed: {exc}"

    return {
        "id": str(row.id),
        "subject": cert.subject,
        "issuer": cert.issuer,
        "serial": cert.serial,
        "storage_ref": cert.storage_ref,
        "not_before": cert.not_before,
        "not_after": cert.not_after,
        "freeradius_trust": freeradius_trust,
        "download_pem_bundle": (
            f"/api/ca/client-bundle?lab_id={payload.lab_id}&identity={payload.identity}"
        ),
        "download_p12": (
            f"/api/ca/client.p12?lab_id={payload.lab_id}&identity={payload.identity}"
        ),
    }


@router.get("/certificates", response_model=CertificateInventory)
def list_certificates(
    lab_id: UUID = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> CertificateInventory:
    authority = db.scalar(
        select(CertificateAuthority)
        .where(CertificateAuthority.lab_id == lab_id)
        .order_by(CertificateAuthority.created_at.desc())
        .limit(1)
    )
    sweep_expired_certificates(db, lab_id=lab_id)
    rows = list(
        db.scalars(
            select(Certificate)
            .where(Certificate.lab_id == lab_id)
            .order_by(Certificate.created_at.desc())
        ).all()
    )
    adapter = get_ca_adapter()
    crl_available = False
    if isinstance(adapter, OpenSslLocalCaAdapter):
        crl_available = adapter.crl_path(lab_id).exists()

    return CertificateInventory(
        authority=authority,
        crl_available=crl_available,
        crl_enforced=get_settings().freeradius_enforce_crl,
        certificates=[_to_certificate_read(row) for row in rows],
    )


@router.post("/revoke", response_model=CertificateRead)
def revoke_certificate(
    payload: RevokeCertRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> CertificateRead:
    row = db.get(Certificate, payload.certificate_id)
    if not row or row.lab_id != payload.lab_id:
        raise HTTPException(status_code=404, detail="Certificate not found in this lab")
    if row.status == CertStatus.revoked:
        return _to_certificate_read(row)
    if not row.storage_ref:
        raise HTTPException(status_code=400, detail="Certificate has no stored material to revoke")

    adapter = _adapter()
    try:
        adapter.revoke(payload.lab_id, row.storage_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Revocation failed: {exc}") from exc

    row.status = CertStatus.revoked
    db.commit()
    db.refresh(row)

    try:
        publish_lab_crl(payload.lab_id)
    except Exception:
        # CRL published best-effort; DB state is already authoritative.
        pass
    return _to_certificate_read(row)


@router.get("/crl.pem")
def download_crl(
    lab_id: UUID = Query(...),
    _admin=Depends(get_current_admin),
) -> Response:
    adapter = _adapter()
    path = adapter.crl_path(lab_id)
    if not path.exists():
        adapter.generate_crl(lab_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="CRL not available for this lab")
    return Response(
        content=path.read_bytes(),
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f'attachment; filename="lab-{lab_id}-crl.pem"'},
    )


@router.get("/root.pem")
def download_root_pem(
    lab_id: UUID = Query(...),
    _admin=Depends(get_current_admin),
) -> Response:
    adapter = _adapter()
    adapter.ensure_root(lab_id)
    path = adapter.root_cert_path(lab_id)
    return Response(
        content=path.read_bytes(),
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f'attachment; filename="lab-{lab_id}-root.pem"'},
    )


@router.get("/client.p12")
def download_client_p12(
    lab_id: UUID = Query(...),
    identity: str = Query(..., min_length=1, max_length=128, pattern=IDENTITY_PATTERN),
    _admin=Depends(get_current_admin),
) -> Response:
    adapter = _adapter()
    path = adapter.client_p12_path(lab_id, identity)
    if not path.exists():
        adapter.ensure_root(lab_id)
        adapter.issue_client_cert(lab_id, identity)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Client PKCS#12 not found")
    return Response(
        content=path.read_bytes(),
        media_type="application/x-pkcs12",
        headers={"Content-Disposition": f'attachment; filename="{identity}.p12"'},
    )


@router.get("/client-bundle")
def download_client_bundle(
    lab_id: UUID = Query(...),
    identity: str = Query(..., min_length=1, max_length=128, pattern=IDENTITY_PATTERN),
    _admin=Depends(get_current_admin),
) -> StreamingResponse:
    adapter = _adapter()
    cert = adapter.client_cert_path(lab_id, identity)
    key = adapter.client_key_path(lab_id, identity)
    root = adapter.root_cert_path(lab_id)
    p12 = adapter.client_p12_path(lab_id, identity)
    if not cert.exists() or not key.exists():
        adapter.ensure_root(lab_id)
        adapter.issue_client_cert(lab_id, identity)
    if not root.exists() or not cert.exists() or not key.exists():
        raise HTTPException(status_code=404, detail="Certificate material not found")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{identity}.crt", cert.read_text(encoding="utf-8"))
        zf.writestr(f"{identity}.key", key.read_text(encoding="utf-8"))
        zf.writestr("lab-root.pem", root.read_text(encoding="utf-8"))
        if p12.exists():
            zf.writestr(f"{identity}.p12", p12.read_bytes())
        readme = (
            "802.1X Lab EAP-TLS bundle\n"
            f"identity={identity}\n"
            "Import the .p12 (empty passphrase) on the client, or use .crt/.key with eapol_test.\n"
            "Trust lab-root.pem as the RADIUS client CA; trust the FreeRADIUS server CA separately "
            "for server authentication in lab tests.\n"
        )
        zf.writestr("README.txt", readme)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{identity}-eap-tls.zip"'},
    )


def _identity_from_subject(subject: str) -> str | None:
    # Subjects are stored as "/CN=<identity>" (openssl 1.x) or "CN = <identity>".
    for token in subject.replace("/", ",").split(","):
        token = token.strip()
        upper = token.upper()
        if upper.startswith("CN=") or upper.startswith("CN ="):
            return token.split("=", 1)[1].strip()
    return None


def _to_certificate_read(row: Certificate) -> CertificateRead:
    status = effective_cert_status(row.status, row.not_after)

    identity = _identity_from_subject(row.subject)
    download_bundle = download_p12 = None
    if row.cert_type == CertType.client and identity:
        download_bundle = f"/api/ca/client-bundle?lab_id={row.lab_id}&identity={identity}"
        download_p12 = f"/api/ca/client.p12?lab_id={row.lab_id}&identity={identity}"

    return CertificateRead(
        id=row.id,
        lab_id=row.lab_id,
        subject=row.subject,
        issuer=row.issuer,
        serial=row.serial,
        cert_type=row.cert_type,
        status=status,
        not_before=row.not_before,
        not_after=row.not_after,
        created_at=row.created_at,
        identity=identity,
        download_bundle=download_bundle,
        download_p12=download_p12,
    )


def _upsert_ca_row(
    db: Session,
    lab_id: UUID,
    name: str,
    subject: str,
    storage_ref: str | None,
) -> CertificateAuthority:
    existing = db.scalar(
        select(CertificateAuthority).where(
            CertificateAuthority.lab_id == lab_id,
            CertificateAuthority.name == name,
        )
    )
    if existing:
        existing.subject = subject
        existing.storage_ref = storage_ref
        db.commit()
        db.refresh(existing)
        return existing
    row = CertificateAuthority(
        lab_id=lab_id,
        name=name,
        subject=subject,
        adapter="openssl",
        storage_ref=storage_ref,
        profiles={},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
