"""Sync control-plane identities/clients into FreeRADIUS SQL tables.

Source of truth: `radius_users` / `radius_clients`.
FreeRADIUS reads: `radcheck` (NT-Password) and `nas` (optional SQL clients).
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.entities import RadiusClient, RadiusUser, UserStatus

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _nas_shortname(client: RadiusClient) -> str:
    base = _SAFE_NAME.sub("_", client.name).strip("_") or "client"
    return f"{base}_{str(client.id).split('-')[0]}"


def sync_user_to_radcheck(db: Session, user: RadiusUser) -> None:
    """Upsert/delete the FreeRADIUS radcheck NT-Password row for a lab user."""
    db.execute(text("DELETE FROM radcheck WHERE username = :u"), {"u": user.username})
    db.execute(text("DELETE FROM radusergroup WHERE username = :u"), {"u": user.username})

    if user.status != UserStatus.active or not user.nt_hash:
        db.commit()
        logger.info("Removed FreeRADIUS SQL credentials for user id=%s", user.id)
        return

    # Never log nt_hash / password material.
    db.execute(
        text(
            "INSERT INTO radcheck (username, attribute, op, value) "
            "VALUES (:u, 'NT-Password', ':=', :v)"
        ),
        {"u": user.username, "v": user.nt_hash},
    )
    for group in user.groups or []:
        if not isinstance(group, str) or not group:
            continue
        db.execute(
            text(
                "INSERT INTO radusergroup (username, groupname, priority) "
                "VALUES (:u, :g, 1)"
            ),
            {"u": user.username, "g": group},
        )
    db.commit()
    logger.info("Synced FreeRADIUS SQL credentials for user id=%s", user.id)


def delete_user_from_radcheck(db: Session, username: str) -> None:
    db.execute(text("DELETE FROM radcheck WHERE username = :u"), {"u": username})
    db.execute(text("DELETE FROM radusergroup WHERE username = :u"), {"u": username})
    db.commit()
    logger.info("Deleted FreeRADIUS SQL rows for username=%s", username)


def sync_client_to_nas(db: Session, client: RadiusClient) -> None:
    """Upsert/delete a row in FreeRADIUS `nas` (read_clients = yes)."""
    shortname = _nas_shortname(client)
    db.execute(text("DELETE FROM nas WHERE shortname = :s"), {"s": shortname})

    if not client.enabled:
        db.commit()
        logger.info("Removed FreeRADIUS NAS row for client id=%s", client.id)
        return

    db.execute(
        text(
            "INSERT INTO nas (nasname, shortname, type, secret, description) "
            "VALUES (:nasname, :shortname, :type, :secret, :description)"
        ),
        {
            "nasname": client.ip_address,
            "shortname": shortname,
            "type": client.device_type or "other",
            "secret": client.shared_secret,
            "description": f"lab={client.lab_id}",
        },
    )
    db.commit()
    logger.info("Synced FreeRADIUS NAS row for client id=%s", client.id)


def delete_client_from_nas(db: Session, client: RadiusClient) -> None:
    shortname = _nas_shortname(client)
    db.execute(text("DELETE FROM nas WHERE shortname = :s"), {"s": shortname})
    db.commit()
    logger.info("Deleted FreeRADIUS NAS row for client id=%s", client.id)


def sync_all_users(db: Session, lab_id: UUID | None = None) -> int:
    stmt = select(RadiusUser)
    if lab_id:
        stmt = stmt.where(RadiusUser.lab_id == lab_id)
    users = list(db.scalars(stmt).all())
    for user in users:
        sync_user_to_radcheck(db, user)
    return len(users)


def sync_all_clients_to_nas(db: Session, lab_id: UUID | None = None) -> int:
    stmt = select(RadiusClient)
    if lab_id:
        stmt = stmt.where(RadiusClient.lab_id == lab_id)
    clients = list(db.scalars(stmt).all())
    # Rebuild NAS rows owned by this sync (description marker lab=<uuid>).
    if lab_id:
        db.execute(text("DELETE FROM nas WHERE description = :d"), {"d": f"lab={lab_id}"})
        db.commit()
    for client in clients:
        sync_client_to_nas(db, client)
    return len(clients)
