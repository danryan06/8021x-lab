from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db import get_db
from app.schemas.entities import (
    EndpointBulkCreate,
    EndpointBulkResponse,
    EndpointCreate,
    EndpointRead,
    EndpointUpdate,
    GenerateEndpointsRequest,
    GenerateEndpointsResponse,
)
from app.services import endpoints as endpoint_service

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.get("", response_model=list[EndpointRead])
def list_endpoints(
    lab_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> list[EndpointRead]:
    return [
        endpoint_service.to_read(db, endpoint)
        for endpoint in endpoint_service.list_endpoints(db, lab_id)
    ]


@router.get("/device-types", response_model=list[str])
def list_device_types(_admin=Depends(get_current_admin)) -> list[str]:
    return endpoint_service.DEVICE_TYPES


@router.post("", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
def create_endpoint(
    payload: EndpointCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> EndpointRead:
    try:
        endpoint = endpoint_service.create_endpoint(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return endpoint_service.to_read(db, endpoint)


@router.post("/bulk", response_model=EndpointBulkResponse)
def bulk_create_endpoints(
    payload: EndpointBulkCreate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> EndpointBulkResponse:
    try:
        result = endpoint_service.bulk_create_endpoints(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EndpointBulkResponse(
        created=result["created"],
        skipped=result["skipped"],
        errors=result["errors"],
        endpoints=[endpoint_service.to_read(db, e) for e in result["endpoints"]],
    )


@router.post("/generate", response_model=GenerateEndpointsResponse)
def generate_endpoints(
    payload: GenerateEndpointsRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> GenerateEndpointsResponse:
    try:
        created = endpoint_service.generate_endpoints(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GenerateEndpointsResponse(
        created=len(created),
        endpoints=[endpoint_service.to_read(db, e) for e in created],
    )


@router.get("/{endpoint_id}", response_model=EndpointRead)
def get_endpoint(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> EndpointRead:
    endpoint = endpoint_service.get_endpoint(db, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint_service.to_read(db, endpoint)


@router.patch("/{endpoint_id}", response_model=EndpointRead)
def update_endpoint(
    endpoint_id: UUID,
    payload: EndpointUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> EndpointRead:
    endpoint = endpoint_service.get_endpoint(db, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    try:
        updated = endpoint_service.update_endpoint(db, endpoint, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return endpoint_service.to_read(db, updated)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> None:
    endpoint = endpoint_service.get_endpoint(db, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    endpoint_service.delete_endpoint(db, endpoint)
