from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Lab
from app.schemas.entities import LabCreate, LabUpdate
from app.services import wireless as wireless_service


def list_labs(db: Session) -> list[Lab]:
    return list(db.scalars(select(Lab).order_by(Lab.name)).all())


def get_lab(db: Session, lab_id: UUID) -> Lab | None:
    return db.get(Lab, lab_id)


def create_lab(db: Session, payload: LabCreate) -> Lab:
    lab = Lab(
        name=payload.name,
        description=payload.description,
        settings=wireless_service.normalize_settings(payload.settings)
        or {"wired": True, "wireless": True},
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return lab


def update_lab(db: Session, lab: Lab, payload: LabUpdate) -> Lab:
    data = payload.model_dump(exclude_unset=True)
    if data.get("settings") is not None:
        data["settings"] = wireless_service.normalize_settings(data["settings"])
    for field, value in data.items():
        setattr(lab, field, value)
    db.commit()
    db.refresh(lab)
    return lab


def delete_lab(db: Session, lab: Lab) -> None:
    db.delete(lab)
    db.commit()
