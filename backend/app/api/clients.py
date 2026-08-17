from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.schemas.entities import RadiusClientCreate, RadiusClientRead, RadiusClientUpdate
from app.services import clients as client_service

router = APIRouter(prefix="/clients", tags=["radius-clients"])


@router.get("", response_model=list[RadiusClientRead])
def list_clients(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[RadiusClientRead]:
    return client_service.list_clients(db, lab_id)


@router.post("", response_model=RadiusClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: RadiusClientCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusClientRead:
    try:
        return client_service.create_client(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{client_id}", response_model=RadiusClientRead)
def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusClientRead:
    client = client_service.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=RadiusClientRead)
def update_client(
    client_id: UUID,
    payload: RadiusClientUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> RadiusClientRead:
    client = client_service.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    try:
        return client_service.update_client(db, client, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> None:
    client = client_service.get_client(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client_service.delete_client(db, client)
