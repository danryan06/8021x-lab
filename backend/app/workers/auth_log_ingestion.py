"""FreeRADIUS linelog → authentication_events worker."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.freeradius.log_parse import parse_linelog_line
from app.integrations.freeradius.mab import mab_reject_reason
from app.models.entities import AuthenticationEvent, AuthMethod, AuthResult, Endpoint, Lab, RadiusClient
from app.validation import normalize_mac

logger = logging.getLogger(__name__)
settings = get_settings()

# Rejects FreeRADIUS could not attribute to a failing module arrive with this
# placeholder; the control plane may know better (e.g. an unregistered MAC).
_GENERIC_FAILURES = {"", "authentication failed"}


def _resolve_lab_id(db: Session, nas_ip: str | None) -> UUID | None:
    if nas_ip:
        client = db.scalar(select(RadiusClient).where(RadiusClient.ip_address == nas_ip).limit(1))
        if client:
            return client.lab_id
    lab = db.scalar(select(Lab).order_by(Lab.created_at.asc()).limit(1))
    return lab.id if lab else None


def _explain_mab_reject(
    db: Session,
    lab_id: UUID | None,
    identity: str | None,
    failure_reason: str | None,
) -> str | None:
    """Replace a bare MAB reject with the reason from the lab's endpoint list."""
    if (failure_reason or "").strip().lower() not in _GENERIC_FAILURES:
        return failure_reason
    if not identity:
        return failure_reason
    try:
        mac = normalize_mac(identity)
    except ValueError:
        return failure_reason
    stmt = select(Endpoint).where(Endpoint.mac_address == mac)
    if lab_id:
        stmt = stmt.where(Endpoint.lab_id == lab_id)
    endpoint = db.scalar(stmt.limit(1))
    reason = mab_reject_reason(
        registered=endpoint is not None,
        enabled=bool(endpoint and endpoint.enabled),
    )
    return reason or failure_reason


def ingest_line(db: Session, line: str, lab_id: UUID | None = None) -> AuthenticationEvent | None:
    parsed = parse_linelog_line(line)
    if not parsed:
        return None

    resolved_lab = lab_id or _resolve_lab_id(db, parsed.nas_ip)
    failure_reason = parsed.failure_reason
    if parsed.method == AuthMethod.mab and parsed.result == AuthResult.failure:
        failure_reason = _explain_mab_reject(db, resolved_lab, parsed.identity, failure_reason)

    event = AuthenticationEvent(
        lab_id=resolved_lab,
        timestamp=parsed.timestamp,
        identity=parsed.identity,
        method=parsed.method,
        result=parsed.result,
        failure_reason=failure_reason,
        returned_attributes=parsed.returned_attributes,
        nas_ip=parsed.nas_ip,
        raw_ref=parsed.raw,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "Ingested auth event identity=%s result=%s method=%s",
        event.identity,
        event.result.value if event.result else None,
        event.method.value if event.method else None,
    )
    return event


def _follow(path: Path, poll_seconds: float = 0.5):
    """Yield new lines from a log file, waiting for the file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, 2)  # start at EOF (only new events after worker start)
        while True:
            line = handle.readline()
            if line:
                yield line
                continue
            # Handle log rotation / truncation.
            try:
                if path.exists() and handle.tell() > path.stat().st_size:
                    handle.seek(0)
            except OSError:
                pass
            time.sleep(poll_seconds)


def run_forever(log_path: str | None = None) -> None:
    path = Path(log_path or settings.freeradius_auth_log_path)
    logger.info("Starting auth log ingestion from %s", path)
    for line in _follow(path):
        try:
            with SessionLocal() as db:
                ingest_line(db, line)
        except Exception:
            logger.exception("Failed to ingest auth log line")


async def run_ingestion_task(stop_event: asyncio.Event | None = None) -> None:
    """Async wrapper used from FastAPI lifespan."""
    path = Path(settings.freeradius_auth_log_path)
    logger.info("Auth log ingestion task watching %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    loop = asyncio.get_running_loop()

    def _poll_once(offset: int) -> tuple[int, list[str]]:
        if not path.exists():
            return offset, []
        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            for line in handle:
                lines.append(line)
            new_offset = handle.tell()
            try:
                size = path.stat().st_size
                if new_offset > size:
                    new_offset = 0
            except OSError:
                pass
        return new_offset, lines

    # Start at EOF so historical noise is not re-ingested on restart.
    offset = path.stat().st_size if path.exists() else 0

    while True:
        if stop_event and stop_event.is_set():
            return
        offset, lines = await loop.run_in_executor(None, _poll_once, offset)
        for line in lines:
            try:
                with SessionLocal() as db:
                    ingest_line(db, line)
            except Exception:
                logger.exception("Failed to ingest auth log line")
        await asyncio.sleep(0.5)
