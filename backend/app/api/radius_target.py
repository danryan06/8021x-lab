"""Advertised RADIUS target (what NAS/AP devices should point at)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.services import radius_target as target_service

router = APIRouter(prefix="/radius-target", tags=["radius-target"])


class AddressCandidateRead(BaseModel):
    ip: str
    interface: str | None = None
    source: str
    likely_docker: bool = False
    is_private: bool = True


class RadiusTargetRead(BaseModel):
    lab_id: UUID | None
    mode: Literal["auto", "manual"]
    advertise_ip: str | None
    effective_ip: str | None
    auth_port: int
    acct_port: int
    shared_secret_hint: str
    lab_shared_secret: str
    candidates: list[AddressCandidateRead]
    nas_instructions: str
    warning: str | None = None
    auto_source: str | None = None


class RadiusTargetUpdate(BaseModel):
    lab_id: UUID | None = None
    mode: Literal["auto", "manual"] = "auto"
    advertise_ip: str | None = Field(default=None, max_length=64)
    auth_port: int | None = Field(default=None, ge=1, le=65535)
    acct_port: int | None = Field(default=None, ge=1, le=65535)


@router.get("", response_model=RadiusTargetRead)
def get_radius_target(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusTargetRead:
    return RadiusTargetRead.model_validate(target_service.build_radius_target(db, lab_id))


@router.put("", response_model=RadiusTargetRead)
def put_radius_target(
    payload: RadiusTargetUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusTargetRead:
    try:
        data = target_service.update_radius_target(
            db,
            lab_id=payload.lab_id,
            mode=payload.mode,
            advertise_ip=payload.advertise_ip,
            auth_port=payload.auth_port,
            acct_port=payload.acct_port,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RadiusTargetRead.model_validate(data)
