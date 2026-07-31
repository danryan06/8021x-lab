from __future__ import annotations

import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import RadiusUser, UserStatus
from app.schemas.entities import (
    GenerateUsersRequest,
    GenerateUsersResponse,
    GeneratedUserCredential,
    RadiusUserCreate,
    RadiusUserUpdate,
)
from app.security import hash_password


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
        groups=payload.groups,
        status=payload.status,
        expires_at=payload.expires_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: RadiusUser, payload: RadiusUserUpdate) -> RadiusUser:
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.groups is not None:
        user.groups = payload.groups
    if payload.status is not None:
        user.status = payload.status
    if payload.expires_at is not None:
        user.expires_at = payload.expires_at
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: RadiusUser) -> None:
    db.delete(user)
    db.commit()


def _random_password(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_users(db: Session, payload: GenerateUsersRequest) -> GenerateUsersResponse:
    credentials: list[GeneratedUserCredential] = []
    created_users: list[RadiusUser] = []

    existing = {
        u.username
        for u in db.scalars(
            select(RadiusUser).where(RadiusUser.lab_id == payload.lab_id)
        ).all()
    }

    i = 1
    while len(created_users) < payload.count:
        username = f"{payload.prefix}{i:03d}"
        i += 1
        if username in existing:
            continue
        password = _random_password(payload.password_length)
        user = RadiusUser(
            lab_id=payload.lab_id,
            username=username,
            password_hash=hash_password(password),
            groups=payload.groups,
            status=UserStatus.active,
        )
        db.add(user)
        created_users.append(user)
        credentials.append(GeneratedUserCredential(username=username, password=password))
        existing.add(username)

    db.commit()
    for user in created_users:
        db.refresh(user)

    return GenerateUsersResponse(
        created=len(created_users),
        users=created_users,
        credentials=credentials,
    )
