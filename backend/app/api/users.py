from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.schemas.entities import (
    GenerateUsersRequest,
    GenerateUsersResponse,
    RadiusUserCreate,
    RadiusUserRead,
    RadiusUserUpdate,
)
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[RadiusUserRead])
def list_users(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[RadiusUserRead]:
    return user_service.list_users(db, lab_id)


@router.post("", response_model=RadiusUserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: RadiusUserCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusUserRead:
    return user_service.create_user(db, payload)


@router.post("/generate", response_model=GenerateUsersResponse)
def generate_users(
    payload: GenerateUsersRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> GenerateUsersResponse:
    return user_service.generate_users(db, payload)


@router.get("/{user_id}", response_model=RadiusUserRead)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusUserRead:
    user = user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=RadiusUserRead)
def update_user(
    user_id: UUID,
    payload: RadiusUserUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusUserRead:
    user = user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user_service.update_user(db, user, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> None:
    user = user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user_service.delete_user(db, user)
