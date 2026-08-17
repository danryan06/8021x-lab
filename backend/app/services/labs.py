from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Lab
from app.schemas.entities import LabCreate, LabUpdate
from app.services import wireless as wireless_service


def list_labs(db: Session) -> list[Lab]:
    return list(db.scalars(select(Lab).order_by(Lab.name)).all())


def get_lab(db: Session, lab_id: UUID) -> Lab | None:
    return db.get(Lab, lab_id)


def find_name_conflict(labs: list[Lab], name: str, exclude_id: UUID | None = None) -> Lab | None:
    """Return the lab already using this name, ignoring case and padding."""
    wanted = (name or "").strip().casefold()
    if not wanted:
        return None
    for lab in labs:
        if lab.id == exclude_id:
            continue
        if (lab.name or "").strip().casefold() == wanted:
            return lab
    return None


def _name_taken_error(name: str) -> ValueError:
    return ValueError(
        f"A lab named “{name.strip()}” already exists — pick another name, or select that "
        "lab instead of creating a new one."
    )


def _assert_name_is_free(db: Session, name: str, exclude_id: UUID | None = None) -> None:
    """Lab names are unique in the database; report that as a message, not a 500."""
    if find_name_conflict(list_labs(db), name, exclude_id):
        raise _name_taken_error(name)


def create_lab(db: Session, payload: LabCreate) -> Lab:
    _assert_name_is_free(db, payload.name)
    lab = Lab(
        name=payload.name,
        description=payload.description,
        settings=wireless_service.normalize_settings(payload.settings)
        or {"wired": True, "wireless": True},
    )
    db.add(lab)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two requests can pass the check above at once; the constraint is the
        # real arbiter, so translate it into the same explanation.
        db.rollback()
        raise _name_taken_error(payload.name) from exc
    db.refresh(lab)
    return lab


def update_lab(db: Session, lab: Lab, payload: LabUpdate) -> Lab:
    data = payload.model_dump(exclude_unset=True)
    if data.get("settings") is not None:
        data["settings"] = wireless_service.normalize_settings(data["settings"])
    if data.get("name"):
        _assert_name_is_free(db, data["name"], exclude_id=lab.id)
    for field, value in data.items():
        setattr(lab, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _name_taken_error(data.get("name") or lab.name) from exc
    db.refresh(lab)
    return lab


def delete_lab(db: Session, lab: Lab) -> None:
    db.delete(lab)
    db.commit()
