"""CA stub routes — models + adapter wiring; full UI in Phase 2."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_admin
from app.integrations.ca import get_ca_adapter

router = APIRouter(prefix="/ca", tags=["certificate-authority"])


class EnsureRootRequest(BaseModel):
    lab_id: UUID
    common_name: str = Field(default="802.1X Lab Root CA")


class IssueCertRequest(BaseModel):
    lab_id: UUID
    identity: str = Field(min_length=1, max_length=128)
    days: int = Field(default=365, ge=1, le=3650)


@router.post("/ensure-root")
def ensure_root(payload: EnsureRootRequest, _admin=Depends(get_current_admin)) -> dict:
    adapter = get_ca_adapter()
    info = adapter.ensure_root(payload.lab_id, payload.common_name)
    return {
        "name": info.name,
        "subject": info.subject,
        "storage_ref": info.storage_ref,
        "not_before": info.not_before,
        "not_after": info.not_after,
    }


@router.post("/issue-client")
def issue_client(payload: IssueCertRequest, _admin=Depends(get_current_admin)) -> dict:
    adapter = get_ca_adapter()
    try:
        cert = adapter.issue_client_cert(payload.lab_id, payload.identity, payload.days)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return {
        "subject": cert.subject,
        "issuer": cert.issuer,
        "serial": cert.serial,
        "storage_ref": cert.storage_ref,
        "not_before": cert.not_before,
        "not_after": cert.not_after,
    }
