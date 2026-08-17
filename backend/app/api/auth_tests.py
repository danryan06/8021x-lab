"""UI-driven authentication tests (PEAP / EAP-TLS via eapol_test, MAB via radclient)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.config import get_settings
from app.db import get_db
from app.integrations.ca import get_ca_adapter
from app.integrations.freeradius.eapol import resolve_radius_host, run_eap_tls_test, run_peap_test
from app.integrations.freeradius.mab import mab_reject_reason, run_mab_test
from app.integrations.freeradius.tls_trust import publish_lab_ca
from app.models.entities import AuthenticationEvent, AuthMethod, Endpoint, RadiusUser, UserStatus
from app.schemas.entities import AuthEventRead
from app.validation import IDENTITY_PATTERN, normalize_mac, validate_identity

router = APIRouter(prefix="/auth-tests", tags=["auth-tests"])
settings = get_settings()


class AuthTestRequest(BaseModel):
    lab_id: UUID
    method: Literal["peap", "eap_tls", "mab"] = "peap"
    user_id: UUID | None = None
    username: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=1, max_length=128)
    expect_reject: bool = False
    # When true, use an intentionally wrong password (negative PEAP test).
    wrong_password: bool = False
    # For EAP-TLS: identity whose cert was issued under the lab CA.
    cert_identity: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=IDENTITY_PATTERN
    )
    # For MAB: an endpoint from this lab, or any MAC typed by hand (negative test).
    endpoint_id: UUID | None = None
    mac_address: str | None = Field(default=None, min_length=12, max_length=32)
    # Which spelling of the MAC goes in User-Name (default: aa:bb:cc:dd:ee:ff).
    mac_username_format: str | None = Field(default=None, max_length=32)


class AuthTestContext(BaseModel):
    radius_host: str
    radius_port: int
    shared_secret_hint: str
    note: str


class AuthTestResponse(BaseModel):
    method: str
    identity: str
    result: str
    expected_reject: bool
    matched_expectation: bool
    failure_reason: str | None = None
    eapol_exit_code: int
    eapol_output: str
    radius: AuthTestContext
    event: AuthEventRead | None = None
    # Reply attributes the RADIUS server returned (VLAN, Filter-Id, …).
    returned_attributes: dict = Field(default_factory=dict)


@router.get("/context", response_model=AuthTestContext)
def auth_test_context(_admin=Depends(get_current_admin)) -> AuthTestContext:
    secret = settings.freeradius_lab_secret
    hint = f"{secret[:2]}…{secret[-2:]}" if len(secret) > 4 else "****"
    try:
        resolved = resolve_radius_host(settings.freeradius_host)
        host_display = f"{settings.freeradius_host} ({resolved})"
    except ValueError:
        host_display = settings.freeradius_host
    return AuthTestContext(
        radius_host=host_display,
        radius_port=settings.freeradius_auth_port,
        shared_secret_hint=f"{hint} (compose lab-docker-host)",
        note=(
            "UI tests run eapol_test (PEAP/EAP-TLS) or radclient (MAB) from the backend "
            "container against FreeRADIUS on the Compose network using the lab-docker-host "
            "shared secret. NAS clients you create are for real switches/APs; they are "
            "synced separately."
        ),
    )


@router.post("", response_model=AuthTestResponse)
def run_auth_test(
    payload: AuthTestRequest,
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
) -> AuthTestResponse:
    method = payload.method
    expect_reject = payload.expect_reject or payload.wrong_password
    test_started = time.time()
    reply_attributes: dict = {}

    if method == "mab":
        mac, endpoint = _resolve_endpoint(db, payload)
        identity = mac
        try:
            mab = run_mab_test(mac, username_format=payload.mac_username_format)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"MAB test failed to start: {exc}") from exc
        identity = mab.identity
        reply_attributes = mab.reply_attributes
        # radclient only reports "Access-Reject"; the lab knows *why* (unknown or
        # disabled MAC), so prefer that explanation when it has one.
        control_plane_reason = mab_reject_reason(
            registered=endpoint is not None,
            enabled=bool(endpoint and endpoint.enabled),
        )
        if not mab.success and control_plane_reason:
            mab.failure_reason = control_plane_reason
        # MabResult mirrors EapolResult's fields, so the shared tail below works.
        eapol = mab
    elif method == "peap":
        user = _resolve_user(db, payload)
        identity = user.username
        if payload.wrong_password:
            password = (payload.password or "wrong-password") + "!NOT!"
        else:
            if not payload.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="password is required for PEAP tests (plaintext is not stored)",
                )
            password = payload.password
        try:
            eapol = run_peap_test(identity, password)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PEAP test failed to start: {exc}") from exc
    else:
        identity = payload.cert_identity or payload.username
        if not identity:
            user = _resolve_user(db, payload)
            identity = user.username
        try:
            validate_identity(identity)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        adapter = get_ca_adapter()
        # Ensure material exists; issue if missing.
        lab_dir = Path(settings.ca_data_dir) / str(payload.lab_id)
        cert_path = lab_dir / "certs" / f"{identity}.crt"
        key_path = lab_dir / "private" / f"{identity}.key"
        if not cert_path.exists() or not key_path.exists():
            try:
                adapter.ensure_root(payload.lab_id)
                adapter.issue_client_cert(payload.lab_id, identity)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Failed to issue client certificate: {exc}"
                ) from exc
        # Publish lab CA into FreeRADIUS trust store before testing.
        restart_requested = publish_lab_ca(payload.lab_id)
        if restart_requested:
            # Wait for FreeRADIUS restart (ca_file trust updates need a full restart).
            time.sleep(6.0)
        try:
            eapol = run_eap_tls_test(identity, cert_path, key_path)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"EAP-TLS test failed to start: {exc}"
            ) from exc

    event = _wait_for_event(
        db, identity=identity, method=method, timeout=8.0, started_at=test_started
    )
    if event and event.returned_attributes and not reply_attributes:
        # PEAP/EAP-TLS: eapol_test does not print the reply list, so take the
        # attributes FreeRADIUS logged for this accept.
        reply_attributes = dict(event.returned_attributes)
    actual_success = eapol.success
    matched = (not actual_success) if expect_reject else actual_success
    result = "success" if actual_success else "failure"
    failure_reason = eapol.failure_reason
    if expect_reject and not actual_success:
        failure_reason = failure_reason or "Rejected as expected"
    elif expect_reject and actual_success:
        failure_reason = "Expected Access-Reject but received Accept"

    return AuthTestResponse(
        method=method,
        identity=identity,
        result=result,
        expected_reject=expect_reject,
        matched_expectation=matched,
        failure_reason=failure_reason,
        eapol_exit_code=eapol.exit_code,
        eapol_output=eapol.output,
        radius=AuthTestContext(
            radius_host=eapol.radius_host,
            radius_port=eapol.radius_port,
            shared_secret_hint=eapol.shared_secret_hint,
            note=(
                "Test executed inside Compose via radclient"
                if method == "mab"
                else "Test executed inside Compose via eapol_test"
            ),
        ),
        event=AuthEventRead.model_validate(event) if event else None,
        returned_attributes=reply_attributes,
    )


def _resolve_user(db: Session, payload: AuthTestRequest) -> RadiusUser:
    user: RadiusUser | None = None
    if payload.user_id:
        user = db.get(RadiusUser, payload.user_id)
    elif payload.username:
        user = db.scalar(
            select(RadiusUser).where(
                RadiusUser.lab_id == payload.lab_id,
                RadiusUser.username == payload.username,
            )
        )
    if not user:
        raise HTTPException(status_code=404, detail="Lab user not found")
    if user.lab_id != payload.lab_id:
        raise HTTPException(status_code=400, detail="User does not belong to the selected lab")
    if user.status != UserStatus.active and not payload.wrong_password:
        raise HTTPException(status_code=400, detail=f"User status is {user.status.value}")
    return user


def _resolve_endpoint(
    db: Session, payload: AuthTestRequest
) -> tuple[str, Endpoint | None]:
    """Resolve the MAC to test, plus its endpoint when the lab knows it.

    An unregistered MAC is allowed on purpose: typing one is how you demonstrate
    that MAB rejects an unknown device.
    """
    endpoint: Endpoint | None = None
    if payload.endpoint_id:
        endpoint = db.get(Endpoint, payload.endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")
        if endpoint.lab_id != payload.lab_id:
            raise HTTPException(
                status_code=400, detail="Endpoint does not belong to the selected lab"
            )
        return endpoint.mac_address, endpoint

    if not payload.mac_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mac_address or endpoint_id is required for MAB tests",
        )
    try:
        mac = normalize_mac(payload.mac_address)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    endpoint = db.scalar(
        select(Endpoint).where(
            Endpoint.lab_id == payload.lab_id,
            Endpoint.mac_address == mac,
        )
    )
    return mac, endpoint


def _wait_for_event(
    db: Session,
    *,
    identity: str,
    method: str,
    timeout: float,
    started_at: float,
) -> AuthenticationEvent | None:
    """Poll briefly for the linelog-ingested event matching this test.

    Only events with a timestamp at or after the test start are considered, so a
    stale event from an earlier test (or an unrelated real auth) for the same
    identity is never attributed to this run. Linelog timestamps have one-second
    resolution, so allow 2s of clock slack.
    """
    deadline = time.monotonic() + timeout
    method_enum = {
        "peap": AuthMethod.peap,
        "eap_tls": AuthMethod.eap_tls,
        "mab": AuthMethod.mab,
    }.get(method, AuthMethod.unknown)
    earliest_ts = started_at - 2.0
    while time.monotonic() < deadline:
        db.expire_all()
        latest = db.scalar(
            select(AuthenticationEvent)
            .where(AuthenticationEvent.identity == identity)
            .order_by(AuthenticationEvent.timestamp.desc())
            .limit(1)
        )
        if (
            latest
            and latest.method in {method_enum, AuthMethod.unknown}
            and latest.timestamp.timestamp() >= earliest_ts
        ):
            return latest
        time.sleep(0.4)
    return None
