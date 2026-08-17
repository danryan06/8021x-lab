from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.integrations.freeradius.reply_attributes import RADIUS_ATTRIBUTE_CATALOG
from app.schemas.entities import (
    AttributeCatalogEntry,
    AuthzPolicyCreate,
    AuthzPolicyRead,
    AuthzPolicyUpdate,
)
from app.services import policies as policy_service

router = APIRouter(prefix="/authz-policies", tags=["authz-policies"])


@router.get("", response_model=list[AuthzPolicyRead])
def list_policies(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[AuthzPolicyRead]:
    return [
        policy_service.to_read(db, policy)
        for policy in policy_service.list_policies(db, lab_id)
    ]


@router.get("/attribute-catalog", response_model=list[AttributeCatalogEntry])
def attribute_catalog(_admin=Depends(get_current_admin)) -> list[AttributeCatalogEntry]:
    """Common RADIUS reply attributes, shown by the Advanced policy editor."""
    return [AttributeCatalogEntry(**entry) for entry in RADIUS_ATTRIBUTE_CATALOG]


@router.post("", response_model=AuthzPolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: AuthzPolicyCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> AuthzPolicyRead:
    try:
        policy = policy_service.create_policy(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return policy_service.to_read(db, policy)


@router.get("/{policy_id}", response_model=AuthzPolicyRead)
def get_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> AuthzPolicyRead:
    policy = policy_service.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Authorization policy not found")
    return policy_service.to_read(db, policy)


@router.patch("/{policy_id}", response_model=AuthzPolicyRead)
def update_policy(
    policy_id: UUID,
    payload: AuthzPolicyUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> AuthzPolicyRead:
    policy = policy_service.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Authorization policy not found")
    try:
        updated = policy_service.update_policy(db, policy, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return policy_service.to_read(db, updated)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> None:
    policy = policy_service.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Authorization policy not found")
    policy_service.delete_policy(db, policy)
