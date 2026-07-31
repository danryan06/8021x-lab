"""Seed a default lab for local development."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models.entities import Lab
from app.schemas.entities import LabCreate
from app.services.labs import create_lab


def main() -> None:
    with SessionLocal() as db:
        existing = db.scalar(select(Lab).where(Lab.name == "Default Lab"))
        if existing:
            print(f"Lab already exists: {existing.id}")
            return
        lab = create_lab(
            db,
            LabCreate(
                name="Default Lab",
                description="Starter lab for PEAP, EAP-TLS, and MAB experiments",
                settings={
                    "wired": True,
                    "wireless": True,
                    "simple_mode_default": True,
                },
            ),
        )
        print(f"Created lab: {lab.id}")


if __name__ == "__main__":
    main()
