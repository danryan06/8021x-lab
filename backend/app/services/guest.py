"""Guest / captive-portal analogue: short-lived users in a guest VLAN group.

A real controller does Central Web Auth (CWA): MAB on an open SSID, HTTP redirect
to a portal, then CoA into a guest VLAN. This lab cannot intercept that redirect,
so the Guest page *is* the portal — it creates a PEAP identity in the ``guests``
group and ensures an authorization policy that returns the guest VLAN.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuthzPolicy, RadiusUser
from app.schemas.entities import AuthzPolicyCreate, RadiusUserCreate
from app.services import policies as policy_service
from app.services import users as user_service

GUEST_GROUP = "guests"
GUEST_POLICY_NAME = "Guest VLAN"


def next_guest_username(existing: set[str]) -> str:
    for index in range(1, 10_000):
        name = f"guest{index:04d}"
        if name not in existing:
            return name
    raise ValueError("All guestNNNN usernames are taken in this lab")


def _usernames_in_lab(db: Session, lab_id: UUID) -> set[str]:
    rows = db.scalars(select(RadiusUser.username).where(RadiusUser.lab_id == lab_id)).all()
    return set(rows)


def ensure_guest_policy(
    db: Session,
    lab_id: UUID,
    *,
    vlan: int,
    role: str,
) -> tuple[AuthzPolicy, bool]:
    """Return the lab's guest policy, creating it if this is the first guest."""
    existing = db.scalar(
        select(AuthzPolicy).where(
            AuthzPolicy.lab_id == lab_id,
            AuthzPolicy.group_name == GUEST_GROUP,
        )
    )
    if existing:
        return existing, False
    created = policy_service.create_policy(
        db,
        AuthzPolicyCreate(
            lab_id=lab_id,
            name=GUEST_POLICY_NAME,
            vlan=vlan,
            role=role,
            group_name=GUEST_GROUP,
        ),
    )
    return created, True


def provision_guest(
    db: Session,
    lab_id: UUID,
    *,
    display_name: str | None,
    hours: int,
    vlan: int,
    role: str,
) -> tuple[RadiusUser, str, AuthzPolicy, bool]:
    """Create a short-lived PEAP guest and make sure their group has a VLAN policy.

    Returns the user, the plaintext password (shown once), the policy, and whether
    the policy was created in this call.
    """
    policy, policy_created = ensure_guest_policy(db, lab_id, vlan=vlan, role=role)
    username = next_guest_username(_usernames_in_lab(db, lab_id))
    password = user_service._generate_password("easy", 8)
    first, last = _split_display_name(display_name)
    user = user_service.create_user(
        db,
        RadiusUserCreate(
            lab_id=lab_id,
            username=username,
            password=password,
            first_name=first,
            last_name=last,
            department="Guest",
            groups=[GUEST_GROUP],
            expires_at=datetime.now(UTC) + timedelta(hours=hours),
        ),
    )
    return user, password, policy, policy_created


def _split_display_name(value: str | None) -> tuple[str | None, str | None]:
    text = (value or "").strip()
    if not text:
        return None, None
    parts = text.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]
