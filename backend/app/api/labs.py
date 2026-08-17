from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.schemas.entities import LabCreate, LabRead, LabUpdate, WirelessProfile
from app.services import labs as lab_service
from app.services import wireless as wireless_service

router = APIRouter(prefix="/labs", tags=["labs"])


@router.get("", response_model=list[LabRead])
def list_labs(db: Session = Depends(get_db), _admin=Depends(get_current_admin)) -> list[LabRead]:
    return lab_service.list_labs(db)


@router.post("", response_model=LabRead, status_code=status.HTTP_201_CREATED)
def create_lab(
    payload: LabCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> LabRead:
    try:
        return lab_service.create_lab(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{lab_id}", response_model=LabRead)
def get_lab(
    lab_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> LabRead:
    lab = lab_service.get_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    return lab


@router.patch("/{lab_id}", response_model=LabRead)
def update_lab(
    lab_id: UUID,
    payload: LabUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> LabRead:
    lab = lab_service.get_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    try:
        return lab_service.update_lab(db, lab, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{lab_id}/wireless-profile", response_model=LabRead)
def put_wireless_profile(
    lab_id: UUID,
    payload: WirelessProfile,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> LabRead:
    """Record the SSID a wireless flow set up, leaving other settings alone."""
    lab = lab_service.get_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    return wireless_service.set_profile(db, lab, payload)


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> None:
    lab = lab_service.get_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    lab_service.delete_lab(db, lab)
