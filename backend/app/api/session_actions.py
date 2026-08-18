"""Per-endpoint CoA / Disconnect-Request (RADIUS session control)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.services import session_actions as session_action_service

router = APIRouter(prefix="/session-actions", tags=["session-actions"])


class SessionActionRequest(BaseModel):
    action: Literal["disconnect", "coa"]
    endpoint_id: UUID
    # None = lab CoA sink (loopback UDP 3799 in the backend container).
    client_id: UUID | None = None
    # CoA only: override which authorization policy to push. Default is the
    # endpoint's attached policy.
    policy_id: UUID | None = None


class SessionActionTargetRead(BaseModel):
    id: UUID | None = None
    name: str
    host: str
    port: int
    kind: str
    device_type: str | None = None
    enabled: bool
    note: str | None = None


class SessionActionTargetsRead(BaseModel):
    sink: SessionActionTargetRead
    clients: list[SessionActionTargetRead] = Field(default_factory=list)
    sink_listening: bool = False


class SessionActionResponse(BaseModel):
    action: str
    result: str
    packet_type: str | None = None
    identity: str
    calling_station_id: str
    nas_ip: str
    nas_port: int
    nas_name: str
    used_lab_sink: bool
    shared_secret_hint: str
    attributes_sent: dict = Field(default_factory=dict)
    attributes_returned: dict = Field(default_factory=dict)
    output: str
    failure_reason: str | None = None
    last_seen_nas_ip: str | None = None
    policy_name: str | None = None
    note: str


@router.get("/targets", response_model=SessionActionTargetsRead)
def list_targets(
    lab_id: UUID = Query(...),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> SessionActionTargetsRead:
    targets = session_action_service.list_targets(db, lab_id)
    return SessionActionTargetsRead(
        sink=SessionActionTargetRead(
            id=targets.sink.id,
            name=targets.sink.name,
            host=targets.sink.host,
            port=targets.sink.port,
            kind=targets.sink.kind,
            device_type=targets.sink.device_type,
            enabled=targets.sink.enabled,
            note=targets.sink.note,
        ),
        clients=[
            SessionActionTargetRead(
                id=client.id,
                name=client.name,
                host=client.host,
                port=client.port,
                kind=client.kind,
                device_type=client.device_type,
                enabled=client.enabled,
                note=client.note,
            )
            for client in targets.clients
        ],
        sink_listening=targets.sink_listening,
    )


@router.post("", response_model=SessionActionResponse)
def run_session_action(
    payload: SessionActionRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> SessionActionResponse:
    try:
        outcome = session_action_service.send_session_action(
            db,
            action=payload.action,
            endpoint_id=payload.endpoint_id,
            client_id=payload.client_id,
            policy_id=payload.policy_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session action failed to start: {exc}",
        ) from exc

    coa = outcome.coa
    return SessionActionResponse(
        action=outcome.action,
        result=coa.result,
        packet_type=coa.packet_type,
        identity=outcome.identity,
        calling_station_id=outcome.calling_station_id,
        nas_ip=coa.nas_ip,
        nas_port=coa.nas_port,
        nas_name=outcome.nas_name,
        used_lab_sink=outcome.used_lab_sink,
        shared_secret_hint=coa.shared_secret_hint,
        attributes_sent=outcome.attributes_sent,
        attributes_returned=coa.attributes_returned,
        output=coa.output,
        failure_reason=coa.failure_reason,
        last_seen_nas_ip=outcome.last_seen_nas_ip,
        policy_name=outcome.policy_name,
        note=outcome.note,
    )
