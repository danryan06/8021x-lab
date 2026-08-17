from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.integrations.freeradius.failure_explain import explain_failure
from app.models.entities import AuthenticationEvent, AuthMethod
from app.schemas.entities import AuthEventRead

router = APIRouter(prefix="/events", tags=["events"])


def _to_event_read(event: AuthenticationEvent) -> AuthEventRead:
    read = AuthEventRead.model_validate(event)
    explanation = explain_failure(event.failure_reason, event.method, event.result)
    if explanation is not None:
        read.failure_summary = explanation.summary
        read.failure_hint = explanation.hint
    return read


@router.get("", response_model=list[AuthEventRead])
def list_events(
    lab_id: UUID | None = Query(default=None),
    method: AuthMethod | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[AuthEventRead]:
    stmt = select(AuthenticationEvent).order_by(AuthenticationEvent.timestamp.desc()).limit(limit)
    if lab_id:
        stmt = stmt.where(AuthenticationEvent.lab_id == lab_id)
    if method:
        stmt = stmt.where(AuthenticationEvent.method == method)
    return [_to_event_read(event) for event in db.scalars(stmt).all()]
