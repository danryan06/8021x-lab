from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.services import guest as guest_service
from app.services import labs as lab_service

router = APIRouter(prefix="/guest", tags=["guest"])


class GuestProvisionRequest(BaseModel):
    lab_id: UUID
    display_name: str | None = Field(default=None, max_length=128)
    hours: int = Field(default=24, ge=1, le=720)
    vlan: int = Field(default=40, ge=1, le=4094)
    role: str = Field(default="guest-acl", min_length=1, max_length=128)


class GuestProvisionResponse(BaseModel):
    username: str
    password: str
    expires_at: datetime | None
    policy_name: str
    vlan: int | None
    role: str | None
    group_name: str
    policy_created: bool
    note: str


@router.post("/provision", response_model=GuestProvisionResponse, status_code=status.HTTP_201_CREATED)
def provision_guest(
    payload: GuestProvisionRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> GuestProvisionResponse:
    if lab_service.get_lab(db, payload.lab_id) is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    try:
        user, password, policy, policy_created = guest_service.provision_guest(
            db,
            payload.lab_id,
            display_name=payload.display_name,
            hours=payload.hours,
            vlan=payload.vlan,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GuestProvisionResponse(
        username=user.username,
        password=password,
        expires_at=user.expires_at,
        policy_name=policy.name,
        vlan=policy.vlan,
        role=policy.role,
        group_name=guest_service.GUEST_GROUP,
        policy_created=policy_created,
        note=(
            "This identity is a PEAP user in the guests group. A real captive portal "
            "would sit on an open SSID (MAB + HTTP redirect) and then CoA the session "
            "into this VLAN; here you create the guest and test PEAP or push CoA from Endpoints."
        ),
    )
