"""Mark lab certificates expired once `not_after` has passed.

The inventory already *displayed* expired certs by comparing dates on read, but
the row stayed `active` in the database. A sweep writes `status = expired` so
filters, counts, and later FreeRADIUS checks see the same thing the UI does.

Revoked stays revoked: expiry does not overwrite a CRL decision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Certificate, CertStatus


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def effective_cert_status(
    status: CertStatus,
    not_after: datetime | None,
    *,
    now: datetime | None = None,
) -> CertStatus:
    """Status the UI/API should show, including a not-yet-persisted expiry."""
    if status != CertStatus.active:
        return status
    expiry = as_utc(not_after)
    if expiry is None:
        return status
    clock = as_utc(now) or datetime.now(UTC)
    if expiry < clock:
        return CertStatus.expired
    return status


def sweep_expired_certificates(
    db: Session,
    *,
    now: datetime | None = None,
    lab_id: UUID | None = None,
) -> int:
    """Persist `expired` on active rows whose `not_after` is in the past.

    Returns how many rows were updated. Safe to call on every inventory list
    and once at API startup — a lab holds few certificates.
    """
    clock = as_utc(now) or datetime.now(UTC)
    stmt = select(Certificate).where(Certificate.status == CertStatus.active)
    if lab_id is not None:
        stmt = stmt.where(Certificate.lab_id == lab_id)
    changed = 0
    for row in db.scalars(stmt).all():
        if effective_cert_status(row.status, row.not_after, now=clock) == CertStatus.expired:
            row.status = CertStatus.expired
            changed += 1
    if changed:
        db.commit()
    return changed
