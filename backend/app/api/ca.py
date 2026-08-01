"""CA routes for lab root + client certificate issue/download (EAP-TLS path)."""

from __future__ import annotations

import zipfile
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.integrations.ca import get_ca_adapter
from app.integrations.ca.openssl_adapter import OpenSslLocalCaAdapter
from app.integrations.freeradius.tls_trust import publish_lab_ca
from app.models.entities import (
    Certificate,
    CertificateAuthority,
    CertStatus,
    CertType,
)

router = APIRouter(prefix="/ca", tags=["certificate-authority"])


class EnsureRootRequest(BaseModel):
    lab_id: UUID
    common_name: str = Field(default="802.1X Lab Root CA")


class IssueCertRequest(BaseModel):
    lab_id: UUID
    identity: str = Field(min_length=1, max_length=128)
    days: int = Field(default=365, ge=1, le=3650)


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
    identity: str = Query(..., min_length=1, max_length=128),
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
    identity: str = Query(..., min_length=1, max_length=128),
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
