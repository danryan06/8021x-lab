from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.models.entities import AuthenticationEvent
from app.schemas.entities import AuthEventRead

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[AuthEventRead])
def list_events(
    lab_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[AuthEventRead]:
    stmt = select(AuthenticationEvent).order_by(AuthenticationEvent.timestamp.desc()).limit(limit)
    if lab_id:
        stmt = stmt.where(AuthenticationEvent.lab_id == lab_id)
    return list(db.scalars(stmt).all())
