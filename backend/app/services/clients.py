from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.freeradius.sync import sync_radius_clients
from app.models.entities import RadiusClient
from app.schemas.entities import RadiusClientCreate, RadiusClientUpdate


def list_clients(db: Session, lab_id: UUID | None = None) -> list[RadiusClient]:
    stmt = select(RadiusClient).order_by(RadiusClient.name)
    if lab_id:
        stmt = stmt.where(RadiusClient.lab_id == lab_id)
    return list(db.scalars(stmt).all())


def get_client(db: Session, client_id: UUID) -> RadiusClient | None:
    return db.get(RadiusClient, client_id)


def create_client(db: Session, payload: RadiusClientCreate) -> RadiusClient:
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
    for field, value in payload.model_dump(exclude_unset=True).items():
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
