"""Sync control-plane identities/clients/endpoints into FreeRADIUS SQL tables.

Source of truth: `radius_users` / `radius_clients` / `endpoints` / `authz_policies`.
FreeRADIUS reads:

| Control plane | FreeRADIUS SQL |
|---------------|----------------|
| `radius_users` | `radcheck` (NT-Password) + `radusergroup` |
| `radius_clients` | `nas` (mirror; clients load from the rendered file) |
| `endpoints` (MAB) | `radcheck` (`Auth-Type := Accept`) + `radreply` |
| `authz_policies` | `radreply` (per endpoint) / `radgroupreply` (per user group); `Login-Time` / `NAS-IP-Address` as `radcheck` / `radgroupcheck` |

`rlm_sql` queries these tables per request, so endpoint/policy changes apply to
the next Access-Request with no reload — unlike clients.conf, which FreeRADIUS
only reads at startup.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.integrations.freeradius.mab import mac_radius_usernames
from app.integrations.freeradius.policy_conditions import render_check_items
from app.integrations.freeradius.reply_attributes import render_policy_attributes
from app.models.entities import AuthzPolicy, Endpoint, RadiusClient, RadiusUser, UserStatus

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


def _policy_reply_rows(policy: AuthzPolicy | None) -> list[tuple[str, str, str]]:
    """Rendered (attribute, op, value) rows for a policy, or none when disabled."""
    if policy is None or not policy.enabled:
        return []
    attributes = render_policy_attributes(
        vlan=policy.vlan,
        role=policy.role,
        extra=policy.reply_attributes or {},
    )
    return [(a.name, a.op, a.value) for a in attributes]


def _policy_check_rows(policy: AuthzPolicy | None) -> list[tuple[str, str, str]]:
    """Login-Time / NAS-IP-Address check items, or none when the policy is off."""
    if policy is None or not policy.enabled:
        return []
    return [(item.name, item.op, item.value) for item in render_check_items(policy.conditions)]


def _delete_endpoint_rows(db: Session, usernames: list[str]) -> None:
    for username in usernames:
        db.execute(
            text(
                "DELETE FROM radcheck WHERE username = :u AND attribute IN "
                "('Auth-Type', 'Login-Time', 'NAS-IP-Address')"
            ),
            {"u": username},
        )
        db.execute(text("DELETE FROM radreply WHERE username = :u"), {"u": username})


def sync_endpoint_to_radius(db: Session, endpoint: Endpoint) -> list[str]:
    """Register (or unregister) one MAB endpoint in FreeRADIUS SQL.

    Writes `Auth-Type := Accept` to `radcheck` for every spelling of the MAC a NAS
    might send, plus the endpoint's authorization policy as `radreply` rows.
    Returns the RADIUS usernames now registered (empty when disabled).
    """
    usernames = mac_radius_usernames(endpoint.mac_address)
    _delete_endpoint_rows(db, usernames)

    if not endpoint.enabled:
        db.commit()
        logger.info("Removed FreeRADIUS MAB rows for endpoint id=%s (disabled)", endpoint.id)
        return []

    policy = (
        db.get(AuthzPolicy, endpoint.authz_policy_id) if endpoint.authz_policy_id else None
    )
    reply_rows = _policy_reply_rows(policy)
    check_rows = _policy_check_rows(policy)
    for username in usernames:
        # MAB has no secret: a known MAC is accepted regardless of User-Password.
        db.execute(
            text(
                "INSERT INTO radcheck (username, attribute, op, value) "
                "VALUES (:u, 'Auth-Type', ':=', 'Accept')"
            ),
            {"u": username},
        )
        for name, op, value in check_rows:
            db.execute(
                text(
                    "INSERT INTO radcheck (username, attribute, op, value) "
                    "VALUES (:u, :a, :o, :v)"
                ),
                {"u": username, "a": name, "o": op, "v": value},
            )
        for name, op, value in reply_rows:
            db.execute(
                text(
                    "INSERT INTO radreply (username, attribute, op, value) "
                    "VALUES (:u, :a, :o, :v)"
                ),
                {"u": username, "a": name, "o": op, "v": value},
            )
    db.commit()
    logger.info(
        "Synced FreeRADIUS MAB rows for endpoint id=%s (%s usernames, %s reply attributes, %s checks)",
        endpoint.id,
        len(usernames),
        len(reply_rows),
        len(check_rows),
    )
    return usernames


def delete_endpoint_from_radius(db: Session, mac_address: str) -> None:
    _delete_endpoint_rows(db, mac_radius_usernames(mac_address))
    db.commit()
    logger.info("Deleted FreeRADIUS MAB rows for endpoint mac=%s", mac_address)


def sync_all_endpoints(db: Session, lab_id: UUID | None = None) -> int:
    stmt = select(Endpoint)
    if lab_id:
        stmt = stmt.where(Endpoint.lab_id == lab_id)
    endpoints = list(db.scalars(stmt).all())
    for endpoint in endpoints:
        sync_endpoint_to_radius(db, endpoint)
    return len(endpoints)


def sync_authz_policy_groups(db: Session, lab_id: UUID | None = None) -> int:
    """Push group-bound authorization policies into `radgroupreply`.

    Users carry group names (`radusergroup`), so binding a policy to a group is how
    a successful PEAP/EAP-TLS login picks up VLAN/role attributes.
    """
    stmt = select(AuthzPolicy).where(AuthzPolicy.group_name.isnot(None))
    if lab_id:
        stmt = stmt.where(AuthzPolicy.lab_id == lab_id)
    policies = list(db.scalars(stmt).all())
    synced = 0
    for policy in policies:
        group = (policy.group_name or "").strip()
        if not group:
            continue
        db.execute(text("DELETE FROM radgroupreply WHERE groupname = :g"), {"g": group})
        db.execute(
            text(
                "DELETE FROM radgroupcheck WHERE groupname = :g AND attribute IN "
                "('Login-Time', 'NAS-IP-Address')"
            ),
            {"g": group},
        )
        for name, op, value in _policy_reply_rows(policy):
            db.execute(
                text(
                    "INSERT INTO radgroupreply (groupname, attribute, op, value) "
                    "VALUES (:g, :a, :o, :v)"
                ),
                {"g": group, "a": name, "o": op, "v": value},
            )
        for name, op, value in _policy_check_rows(policy):
            db.execute(
                text(
                    "INSERT INTO radgroupcheck (groupname, attribute, op, value) "
                    "VALUES (:g, :a, :o, :v)"
                ),
                {"g": group, "a": name, "o": op, "v": value},
            )
        synced += 1
    db.commit()
    if synced:
        logger.info("Synced %s group-bound authorization policies to radgroupreply", synced)
    return synced


def delete_group_reply(db: Session, group_name: str) -> None:
    group = (group_name or "").strip()
    if not group:
        return
    db.execute(text("DELETE FROM radgroupreply WHERE groupname = :g"), {"g": group})
    db.execute(
        text(
            "DELETE FROM radgroupcheck WHERE groupname = :g AND attribute IN "
            "('Login-Time', 'NAS-IP-Address')"
        ),
        {"g": group},
    )
    db.commit()
    logger.info("Deleted radgroupreply/radgroupcheck rows for group=%s", group)


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
