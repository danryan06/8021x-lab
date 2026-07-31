"""Skeleton worker for FreeRADIUS linelog → authentication_events.

Phase 1 will run this as a long-lived process or asyncio task that tails
a mounted log file and persists ParsedAuthLine rows.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.freeradius.log_parse import parse_linelog_line
from app.models.entities import AuthenticationEvent

logger = logging.getLogger(__name__)


def ingest_line(db: Session, line: str, lab_id: UUID | None = None) -> AuthenticationEvent | None:
    parsed = parse_linelog_line(line)
    if not parsed:
        return None

    event = AuthenticationEvent(
        lab_id=lab_id,
        timestamp=parsed.timestamp,
        identity=parsed.identity,
        method=parsed.method,
        result=parsed.result,
        failure_reason=parsed.failure_reason,
        returned_attributes={},
        nas_ip=parsed.nas_ip,
        raw_ref=parsed.raw,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.debug("Ingested auth event for %s (%s)", event.identity, event.result)
    return event


def run_forever() -> None:
    raise NotImplementedError(
        "Auth log tailing is not wired in Phase 0. "
        "Use ingest_line() from tests or wire a file tail in Phase 1."
    )
