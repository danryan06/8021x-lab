from __future__ import annotations

import csv
import io
import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.freeradius.sql_sync import delete_user_from_radcheck, sync_user_to_radcheck
from app.models.entities import RadiusUser, UserStatus
from app.schemas.entities import (
    GeneratedUserCredential,
    GenerateUsersRequest,
    GenerateUsersResponse,
    RadiusUserCreate,
    RadiusUserUpdate,
)
from app.security import hash_password, nt_hash_password

FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Casey",
    "Morgan",
    "Riley",
    "Avery",
    "Quinn",
    "Cameron",
    "Jamie",
    "Drew",
    "Sam",
    "Chris",
    "Pat",
    "Lee",
    "Dana",
    "Jesse",
    "Kelly",
    "Robin",
    "Shawn",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Clark",
]

DEPARTMENTS = [
    "Engineering",
    "Sales",
    "Finance",
    "IT",
    "Human Resources",
    "Marketing",
    "Operations",
    "Facilities",
    "Legal",
    "Support",
]

# Short memorable words for lab passwords (easy to type during demos).
PASSWORD_WORDS = [
    "apple",
    "river",
    "cloud",
    "maple",
    "ocean",
    "tiger",
    "coral",
    "frost",
    "amber",
    "cedar",
    "pine",
    "stone",
    "flame",
    "grove",
    "haven",
    "ivory",
    "jade",
    "kite",
    "lunar",
    "mist",
    "nova",
    "orbit",
    "pearl",
    "quest",
    "ridge",
    "sable",
    "tide",
    "ultra",
    "vale",
    "willow",
]


def list_users(db: Session, lab_id: UUID | None = None) -> list[RadiusUser]:
    stmt = select(RadiusUser).order_by(RadiusUser.username)
    if lab_id:
        stmt = stmt.where(RadiusUser.lab_id == lab_id)
    return list(db.scalars(stmt).all())


def get_user(db: Session, user_id: UUID) -> RadiusUser | None:
    return db.get(RadiusUser, user_id)


def create_user(db: Session, payload: RadiusUserCreate) -> RadiusUser:
    user = RadiusUser(
        lab_id=payload.lab_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        nt_hash=nt_hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        department=payload.department,
        groups=payload.groups,
        status=payload.status,
        expires_at=payload.expires_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    sync_user_to_radcheck(db, user)
    return user


def update_user(db: Session, user: RadiusUser, payload: RadiusUserUpdate) -> RadiusUser:
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        user.nt_hash = nt_hash_password(payload.password)
    if payload.first_name is not None:
        user.first_name = payload.first_name or None
    if payload.last_name is not None:
        user.last_name = payload.last_name or None
    if payload.department is not None:
        user.department = payload.department or None
    if payload.groups is not None:
        user.groups = payload.groups
    if payload.status is not None:
        user.status = payload.status
    if payload.expires_at is not None:
        user.expires_at = payload.expires_at
    db.commit()
    db.refresh(user)
    sync_user_to_radcheck(db, user)
    return user


def delete_user(db: Session, user: RadiusUser) -> None:
    username = user.username
    db.delete(user)
    db.commit()
    delete_user_from_radcheck(db, username)


def _generate_password(style: str, length: int) -> str:
    if style == "easy":
        word = secrets.choice(PASSWORD_WORDS)
        digits = "".join(secrets.choice(string.digits) for _ in range(3))
        return f"{word}{digits}"
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _slug(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _build_username(
    style: str,
    prefix: str,
    index: int,
    first_name: str | None,
    last_name: str | None,
) -> str:
    first = _slug(first_name or "user")
    last = _slug(last_name or "demo")
    if style == "first_last":
        return f"{first}.{last}{index}"
    if style == "flast":
        return f"{first[:1]}{last}{index}"
    if style == "emailish":
        return f"{first}.{last}{index}@lab.local"
    return f"{prefix}{index:03d}"


def _pick_department(payload: GenerateUsersRequest) -> str | None:
    if not payload.include_department:
        return None
    if payload.randomize_department:
        return secrets.choice(DEPARTMENTS)
    return payload.department


def generate_users(db: Session, payload: GenerateUsersRequest) -> GenerateUsersResponse:
    credentials: list[GeneratedUserCredential] = []
    created_users: list[RadiusUser] = []

    existing = {
        u.username
        for u in db.scalars(select(RadiusUser).where(RadiusUser.lab_id == payload.lab_id)).all()
    }

    index = 1
    while len(created_users) < payload.count:
        first_name = secrets.choice(FIRST_NAMES) if payload.include_first_name else None
        last_name = secrets.choice(LAST_NAMES) if payload.include_last_name else None
        department = _pick_department(payload)
        groups = list(payload.groups) if payload.include_groups else []

        username = _build_username(
            payload.username_style,
            payload.prefix,
            index,
            first_name,
            last_name,
        )
        index += 1
        if username in existing:
            continue

        password = _generate_password(payload.password_style, payload.password_length)
        user = RadiusUser(
            lab_id=payload.lab_id,
            username=username,
            password_hash=hash_password(password),
            nt_hash=nt_hash_password(password),
            first_name=first_name,
            last_name=last_name,
            department=department,
            groups=groups,
            status=UserStatus.active,
        )
        db.add(user)
        created_users.append(user)
        credentials.append(
            GeneratedUserCredential(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                department=department,
                groups=groups,
            )
        )
        existing.add(username)

    db.commit()
    for user in created_users:
        db.refresh(user)
        sync_user_to_radcheck(db, user)

    return GenerateUsersResponse(
        created=len(created_users),
        users=created_users,
        credentials=credentials,
    )


def users_csv_template() -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "username",
            "password",
            "first_name",
            "last_name",
            "department",
            "groups",
            "status",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "username": "jsmith",
            "password": "apple123",
            "first_name": "Jordan",
            "last_name": "Smith",
            "department": "Engineering",
            "groups": "students;staff",
            "status": "active",
        }
    )
    return buffer.getvalue()


def import_users_csv(db: Session, lab_id: UUID, content: str) -> dict:
    reader = csv.DictReader(io.StringIO(content))
    required = {"username", "password"}
    if not reader.fieldnames or not required.issubset({f.strip() for f in reader.fieldnames}):
        raise ValueError("CSV must include username and password columns")

    existing = {
        u.username
        for u in db.scalars(select(RadiusUser).where(RadiusUser.lab_id == lab_id)).all()
    }
    created = 0
    skipped = 0
    errors: list[str] = []
    created_users: list[RadiusUser] = []

    for i, row in enumerate(reader, start=2):
        username = (row.get("username") or "").strip()
        password = (row.get("password") or "").strip()
        if not username or not password:
            errors.append(f"Row {i}: username and password are required")
            continue
        if username in existing:
            skipped += 1
            continue
        status_raw = (row.get("status") or "active").strip().lower()
        try:
            status = UserStatus(status_raw)
        except ValueError:
            status = UserStatus.active
        groups_raw = (row.get("groups") or "").strip()
        groups = [g.strip() for g in groups_raw.replace(",", ";").split(";") if g.strip()]
        user = RadiusUser(
            lab_id=lab_id,
            username=username,
            password_hash=hash_password(password),
            nt_hash=nt_hash_password(password),
            first_name=(row.get("first_name") or "").strip() or None,
            last_name=(row.get("last_name") or "").strip() or None,
            department=(row.get("department") or "").strip() or None,
            groups=groups,
            status=status,
        )
        db.add(user)
        created_users.append(user)
        existing.add(username)
        created += 1

    db.commit()
    for user in created_users:
        db.refresh(user)
        sync_user_to_radcheck(db, user)
    return {"created": created, "skipped": skipped, "errors": errors}
