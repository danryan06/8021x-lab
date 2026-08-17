"""FreeRADIUS sync / status endpoints for the UI."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.integrations.freeradius.health import freeradius_health_detail
from app.integrations.freeradius.sql_sync import (
    sync_all_endpoints,
    sync_all_users,
    sync_authz_policy_groups,
)
from app.integrations.freeradius.sync import bootstrap_radius_runtime, sync_radius_clients
from app.integrations.freeradius.tls_trust import publish_lab_ca
from app.models.entities import Lab, RadiusClient

router = APIRouter(prefix="/freeradius", tags=["freeradius"])


class SyncResponse(BaseModel):
    users_synced: int
    clients_synced: int
    endpoints_synced: int = 0
    policies_synced: int = 0
    reload_requested: bool
    lab_ids: list[UUID] = Field(default_factory=list)
    detail: str


class FreeRadiusStatus(BaseModel):
    status: str
    detail: str


@router.get("/status", response_model=FreeRadiusStatus)
def freeradius_status(_admin=Depends(get_current_admin)) -> FreeRadiusStatus:
    status, detail = freeradius_health_detail()
    return FreeRadiusStatus(status=status, detail=detail)


@router.post("/sync", response_model=SyncResponse)
def sync_freeradius(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> SyncResponse:
    if lab_id:
        lab_ids = [lab_id]
        users = sync_all_users(db, lab_id)
        endpoints = sync_all_endpoints(db, lab_id)
        policies = sync_authz_policy_groups(db, lab_id)
        sync_radius_clients(db, lab_id)
        clients = len(
            list(db.scalars(select(RadiusClient).where(RadiusClient.lab_id == lab_id)).all())
        )
        try:
            publish_lab_ca(lab_id)
        except Exception:
            pass
    else:
        labs = list(db.scalars(select(Lab)).all())
        lab_ids = [lab.id for lab in labs]
        users = sync_all_users(db)
        endpoints = sync_all_endpoints(db)
        policies = sync_authz_policy_groups(db)
        bootstrap_radius_runtime(db)
        clients = len(list(db.scalars(select(RadiusClient)).all()))
        for lid in lab_ids:
            try:
                publish_lab_ca(lid)
            except Exception:
                pass

    return SyncResponse(
        users_synced=users,
        clients_synced=clients,
        endpoints_synced=endpoints,
        policies_synced=policies,
        reload_requested=True,
        lab_ids=lab_ids,
        detail=(
            "Synced users to radcheck, MAB endpoints to radcheck/radreply, group policies to "
            "radgroupreply, and clients to clients.dot1x.conf/nas; FreeRADIUS restarts "
            "automatically when client or trust config changed"
        ),
    )
