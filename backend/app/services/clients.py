from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.freeradius.sync import client_address, sync_radius_clients
from app.models.entities import RadiusClient
from app.schemas.entities import RadiusClientCreate, RadiusClientUpdate


def find_address_conflict(
    clients: list[RadiusClient],
    address: str,
    exclude_id: UUID | None = None,
) -> RadiusClient | None:
    """Return the enabled client that already answers for this address, if any."""
    wanted = (address or "").strip().lower()
    if not wanted:
        return None
    for client in clients:
        if not client.enabled or client.id == exclude_id:
            continue
        if client_address(client) == wanted:
            return client
    return None


def _assert_address_is_free(
    db: Session,
    address: str,
    lab_id: UUID,
    exclude_id: UUID | None = None,
) -> None:
    """FreeRADIUS matches a request to a client by source address alone, and
    refuses to start if two clients claim one address — so a second entry for an
    address is rejected here rather than breaking the next restart."""
    existing = find_address_conflict(list_clients(db), address, exclude_id)
    if not existing:
        return
    where = "in this lab" if existing.lab_id == lab_id else "in another lab"
    raise ValueError(
        f"{address} is already registered as '{existing.name}' {where}. FreeRADIUS "
        "identifies a NAS by its source address, so an address can only have one "
        "client — edit or reuse that one, or disable it first."
    )


def list_clients(db: Session, lab_id: UUID | None = None) -> list[RadiusClient]:
    stmt = select(RadiusClient).order_by(RadiusClient.name)
    if lab_id:
        stmt = stmt.where(RadiusClient.lab_id == lab_id)
    return list(db.scalars(stmt).all())


def get_client(db: Session, client_id: UUID) -> RadiusClient | None:
    return db.get(RadiusClient, client_id)


def create_client(db: Session, payload: RadiusClientCreate) -> RadiusClient:
    if payload.enabled:
        _assert_address_is_free(db, payload.ip_address, payload.lab_id)
    client = RadiusClient(
        lab_id=payload.lab_id,
        name=payload.name,
        ip_address=payload.ip_address,
        shared_secret=payload.shared_secret,
        device_type=payload.device_type,
        enabled=payload.enabled,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    sync_radius_clients(db, payload.lab_id)
    return client


def update_client(db: Session, client: RadiusClient, payload: RadiusClientUpdate) -> RadiusClient:
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("enabled", client.enabled):
        _assert_address_is_free(
            db,
            fields.get("ip_address", client.ip_address),
            client.lab_id,
            exclude_id=client.id,
        )
    for field, value in fields.items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    sync_radius_clients(db, client.lab_id)
    return client


def delete_client(db: Session, client: RadiusClient) -> None:
    lab_id = client.lab_id
    db.delete(client)
    db.commit()
    sync_radius_clients(db, lab_id)
