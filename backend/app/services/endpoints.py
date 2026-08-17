"""Endpoints (MAC addresses) authenticated with MAB.

Mirrors the user service: create/update/delete, a bulk paste path, and a random
generator for demos. Every write syncs the endpoint into FreeRADIUS SQL, so a MAB
Access-Request for that MAC is answered from the next packet onward.
"""

from __future__ import annotations

import re
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.freeradius.mab import mac_radius_usernames
from app.integrations.freeradius.sql_sync import (
    delete_endpoint_from_radius,
    sync_endpoint_to_radius,
)
from app.models.entities import AuthzPolicy, Endpoint
from app.schemas.entities import (
    EndpointBulkCreate,
    EndpointCreate,
    EndpointRead,
    EndpointUpdate,
    GenerateEndpointsRequest,
)
from app.validation import normalize_mac

# Device classes that typically cannot run an 802.1X supplicant — the real-world
# reason MAB exists.
DEVICE_TYPES = [
    "printer",
    "ip-camera",
    "voip-phone",
    "badge-reader",
    "thermostat",
    "iot-sensor",
    "medical-device",
    "smart-tv",
]

_MAC_SPLIT = re.compile(r"[\s,;]+")


def choose_device_type(device_type: str | None, mixed: bool) -> str | None:
    """Pick the device type for one generated endpoint.

    An explicit `device_type` pins every endpoint to it; mixing only applies when
    the caller did not name one.
    """
    if device_type:
        return device_type
    if mixed:
        return secrets.choice(DEVICE_TYPES)
    return None


def list_endpoints(db: Session, lab_id: UUID | None = None) -> list[Endpoint]:
    stmt = select(Endpoint).order_by(Endpoint.mac_address)
    if lab_id:
        stmt = stmt.where(Endpoint.lab_id == lab_id)
    return list(db.scalars(stmt).all())


def get_endpoint(db: Session, endpoint_id: UUID) -> Endpoint | None:
    return db.get(Endpoint, endpoint_id)


def to_read(db: Session, endpoint: Endpoint) -> EndpointRead:
    read = EndpointRead.model_validate(endpoint)
    read.radius_usernames = mac_radius_usernames(endpoint.mac_address)
    if endpoint.authz_policy_id:
        policy = db.get(AuthzPolicy, endpoint.authz_policy_id)
        read.authz_policy_name = policy.name if policy else None
    return read


def parse_mac_list(text: str) -> tuple[list[str], list[str]]:
    """Normalize a pasted MAC list; returns (canonical MACs, per-entry errors).

    Duplicates within the paste collapse to one entry so a copied inventory list
    does not fail halfway through.
    """
    macs: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    for raw in _MAC_SPLIT.split(text or ""):
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            canonical = normalize_mac(candidate)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        macs.append(canonical)
    return macs, errors


def _existing_macs(db: Session, lab_id: UUID) -> set[str]:
    return {
        e.mac_address
        for e in db.scalars(select(Endpoint).where(Endpoint.lab_id == lab_id)).all()
    }


def _validate_policy(db: Session, lab_id: UUID, policy_id: UUID | None) -> None:
    if policy_id is None:
        return
    policy = db.get(AuthzPolicy, policy_id)
    if not policy or policy.lab_id != lab_id:
        raise ValueError("authorization policy not found in this lab")


def create_endpoint(db: Session, payload: EndpointCreate) -> Endpoint:
    mac = normalize_mac(payload.mac_address)
    _validate_policy(db, payload.lab_id, payload.authz_policy_id)
    if mac in _existing_macs(db, payload.lab_id):
        raise ValueError(f"{mac} is already registered in this lab")
    endpoint = Endpoint(
        lab_id=payload.lab_id,
        mac_address=mac,
        description=payload.description,
        device_type=payload.device_type,
        authz_policy_id=payload.authz_policy_id,
        enabled=payload.enabled,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    sync_endpoint_to_radius(db, endpoint)
    return endpoint


def update_endpoint(db: Session, endpoint: Endpoint, payload: EndpointUpdate) -> Endpoint:
    previous_mac = endpoint.mac_address
    if payload.mac_address is not None:
        mac = normalize_mac(payload.mac_address)
        if mac != previous_mac and mac in _existing_macs(db, endpoint.lab_id):
            raise ValueError(f"{mac} is already registered in this lab")
        endpoint.mac_address = mac
    if payload.description is not None:
        endpoint.description = payload.description
    if payload.device_type is not None:
        endpoint.device_type = payload.device_type
    if payload.authz_policy_id is not None:
        _validate_policy(db, endpoint.lab_id, payload.authz_policy_id)
        endpoint.authz_policy_id = payload.authz_policy_id
    if payload.clear_authz_policy:
        endpoint.authz_policy_id = None
    if payload.enabled is not None:
        endpoint.enabled = payload.enabled
    db.commit()
    db.refresh(endpoint)

    if endpoint.mac_address != previous_mac:
        delete_endpoint_from_radius(db, previous_mac)
    sync_endpoint_to_radius(db, endpoint)
    return endpoint


def delete_endpoint(db: Session, endpoint: Endpoint) -> None:
    mac = endpoint.mac_address
    db.delete(endpoint)
    db.commit()
    delete_endpoint_from_radius(db, mac)


def bulk_create_endpoints(db: Session, payload: EndpointBulkCreate) -> dict:
    macs, errors = parse_mac_list(payload.mac_addresses)
    _validate_policy(db, payload.lab_id, payload.authz_policy_id)
    existing = _existing_macs(db, payload.lab_id)
    created: list[Endpoint] = []
    skipped = 0

    for mac in macs:
        if mac in existing:
            skipped += 1
            continue
        endpoint = Endpoint(
            lab_id=payload.lab_id,
            mac_address=mac,
            description=payload.description,
            device_type=payload.device_type,
            authz_policy_id=payload.authz_policy_id,
            enabled=payload.enabled,
        )
        db.add(endpoint)
        created.append(endpoint)
        existing.add(mac)

    db.commit()
    for endpoint in created:
        db.refresh(endpoint)
        sync_endpoint_to_radius(db, endpoint)
    return {"created": len(created), "skipped": skipped, "errors": errors, "endpoints": created}


def random_mac(oui: str = "02:1a:2b") -> str:
    """Random MAC under a fixed vendor prefix (OUI), padded from the prefix given.

    Accepts a partial prefix in any accepted MAC format (`02:1a:2b`, `021a`, …) and
    fills the remaining octets randomly.
    """
    prefix = re.sub(r"[^0-9a-fA-F]", "", oui or "").lower()
    if len(prefix) > 12:
        raise ValueError("OUI prefix is longer than a MAC address")
    if len(prefix) % 2:
        prefix = prefix[:-1]
    if not prefix:
        prefix = "021a2b"
    remaining = 12 - len(prefix)
    suffix = "".join(secrets.choice("0123456789abcdef") for _ in range(remaining))
    return normalize_mac(prefix + suffix)


def generate_endpoints(db: Session, payload: GenerateEndpointsRequest) -> list[Endpoint]:
    _validate_policy(db, payload.lab_id, payload.authz_policy_id)
    existing = _existing_macs(db, payload.lab_id)
    created: list[Endpoint] = []

    attempts = 0
    while len(created) < payload.count and attempts < payload.count * 20:
        attempts += 1
        mac = random_mac(payload.oui)
        if mac in existing:
            continue
        existing.add(mac)
        device_type = choose_device_type(payload.device_type, payload.mixed_device_types)
        index = len(created) + 1
        endpoint = Endpoint(
            lab_id=payload.lab_id,
            mac_address=mac,
            description=f"Generated {device_type or 'endpoint'} {index}",
            device_type=device_type,
            authz_policy_id=payload.authz_policy_id,
            enabled=payload.enabled,
        )
        db.add(endpoint)
        created.append(endpoint)

    db.commit()
    for endpoint in created:
        db.refresh(endpoint)
        sync_endpoint_to_radius(db, endpoint)
    return created
