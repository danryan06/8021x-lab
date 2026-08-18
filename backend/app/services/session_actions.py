"""Originate CoA / Disconnect-Request toward a NAS or the lab CoA sink."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.freeradius.coa import (
    RADCLIENT_COA,
    RADCLIENT_DISCONNECT,
    CoaResult,
    build_coa_request,
    run_coa,
)
from app.integrations.freeradius.coa_sink import get_runtime_sink
from app.integrations.freeradius.mab import mac_radius_usernames
from app.integrations.freeradius.reply_attributes import render_policy_attributes
from app.models.entities import AuthenticationEvent, AuthzPolicy, Endpoint
from app.services import clients as client_service
from app.services import endpoints as endpoint_service
from app.services import policies as policy_service

settings = get_settings()

SINK_NAME = "Lab CoA sink"


@dataclass
class SessionActionOutcome:
    action: str
    identity: str
    calling_station_id: str
    nas_name: str
    used_lab_sink: bool
    attributes_sent: dict
    last_seen_nas_ip: str | None
    note: str
    coa: CoaResult
    policy_name: str | None = None
    policy_id: UUID | None = None


@dataclass
class SessionActionTarget:
    id: UUID | None
    name: str
    host: str
    port: int
    kind: str
    device_type: str | None
    enabled: bool
    note: str | None = None


@dataclass
class SessionActionTargets:
    sink: SessionActionTarget
    clients: list[SessionActionTarget] = field(default_factory=list)
    sink_listening: bool = False


def list_targets(db: Session, lab_id: UUID) -> SessionActionTargets:
    sink_runtime = get_runtime_sink()
    sink_host = sink_runtime.host if sink_runtime else settings.coa_sink_host
    sink_port = sink_runtime.port if sink_runtime else settings.coa_port
    listening = sink_runtime is not None
    sink = SessionActionTarget(
        id=None,
        name=SINK_NAME,
        host=sink_host,
        port=sink_port,
        kind="sink",
        device_type=None,
        enabled=True,
        note=(
            "In-process RADIUS responder on the backend loopback. It ACKs CoA and "
            "Disconnect so you can see the exchange without a switch. It does not "
            "drop a real session."
            if listening
            else "The lab CoA sink is not listening — check backend logs, or send "
            "to a registered RADIUS client that has dynamic authorization enabled."
        ),
    )
    nas_targets = [
        SessionActionTarget(
            id=client.id,
            name=client.name,
            host=client.ip_address,
            port=settings.coa_port,
            kind="nas",
            device_type=client.device_type,
            enabled=client.enabled,
            note="Sends UDP 3799 to this client's address using its shared secret.",
        )
        for client in client_service.list_clients(db, lab_id)
    ]
    return SessionActionTargets(sink=sink, clients=nas_targets, sink_listening=listening)


def last_seen_nas_ip(db: Session, endpoint: Endpoint) -> str | None:
    """NAS-IP-Address from the most recent auth event for this MAC, if any."""
    names = mac_radius_usernames(endpoint.mac_address)
    event = db.scalar(
        select(AuthenticationEvent)
        .where(AuthenticationEvent.identity.in_(names))
        .where(AuthenticationEvent.nas_ip.isnot(None))
        .order_by(AuthenticationEvent.timestamp.desc())
        .limit(1)
    )
    return event.nas_ip if event else None


def _resolve_endpoint(db: Session, endpoint_id: UUID) -> Endpoint:
    endpoint = endpoint_service.get_endpoint(db, endpoint_id)
    if not endpoint:
        raise LookupError("Endpoint not found")
    return endpoint


def _resolve_client(
    db: Session, lab_id: UUID, client_id: UUID | None
) -> tuple[str, int, str, str, bool]:
    """Return (host, port, secret, name, used_lab_sink)."""
    if client_id is None:
        sink = get_runtime_sink()
        host = sink.host if sink else settings.coa_sink_host
        port = sink.port if sink else settings.coa_port
        return host, port, settings.freeradius_lab_secret, SINK_NAME, True

    client = client_service.get_client(db, client_id)
    if not client:
        raise LookupError("RADIUS client not found")
    if client.lab_id != lab_id:
        raise ValueError("RADIUS client does not belong to this lab")
    if not client.enabled:
        raise ValueError("RADIUS client is disabled")
    return client.ip_address, settings.coa_port, client.shared_secret, client.name, False


def _resolve_policy(
    db: Session, endpoint: Endpoint, policy_id: UUID | None
) -> AuthzPolicy | None:
    chosen = policy_id or endpoint.authz_policy_id
    if not chosen:
        return None
    policy = policy_service.get_policy(db, chosen)
    if not policy:
        raise LookupError("Authorization policy not found")
    if policy.lab_id != endpoint.lab_id:
        raise ValueError("Authorization policy does not belong to this lab")
    return policy


def _attributes_from_policy(policy: AuthzPolicy | None) -> dict[str, str]:
    if policy is None or not policy.enabled:
        return {}
    rendered = render_policy_attributes(
        vlan=policy.vlan,
        role=policy.role,
        extra=policy.reply_attributes or {},
    )
    return {item.name: item.value for item in rendered}


def _note(
    *,
    action: str,
    used_lab_sink: bool,
    result: str,
    policy: AuthzPolicy | None,
    extra: dict[str, str],
    last_nas: str | None,
    nas_name: str,
    failure_reason: str | None,
) -> str:
    if result == "ack" and used_lab_sink:
        verb = "drop the matching session" if action == "disconnect" else "re-authorize it"
        kind = "Disconnect" if action == "disconnect" else "CoA"
        base = f"Lab CoA sink ACKed the {kind}-Request. A real NAS would {verb}."
        if action == "coa" and not extra:
            base += " No VLAN/role was attached — assign an authorization policy to push one."
        elif action == "coa" and policy:
            base += f" Pushed policy '{policy.name}'."
        return base
    if result == "ack":
        verb = "asked to drop the session" if action == "disconnect" else "asked to apply new policy"
        return f"{nas_name} ACKed — it {verb}."
    hint = f" Last MAB/802.1X for this MAC came from {last_nas}." if last_nas else ""
    return (failure_reason or f"{nas_name} did not ACK.") + hint


def send_session_action(
    db: Session,
    *,
    action: str,
    endpoint_id: UUID,
    client_id: UUID | None = None,
    policy_id: UUID | None = None,
) -> SessionActionOutcome:
    if action not in {RADCLIENT_COA, RADCLIENT_DISCONNECT}:
        raise ValueError("action must be 'coa' or 'disconnect'")

    endpoint = _resolve_endpoint(db, endpoint_id)
    host, port, secret, nas_name, used_sink = _resolve_client(db, endpoint.lab_id, client_id)
    policy = _resolve_policy(db, endpoint, policy_id) if action == RADCLIENT_COA else None
    extra = _attributes_from_policy(policy) if action == RADCLIENT_COA else {}
    identity = endpoint.mac_address
    request = build_coa_request(
        identity,
        calling_station_id=identity,
        nas_ip=None if used_sink else host,
        extra=extra,
    )
    coa = run_coa(
        action,
        request,
        nas_host=host,
        nas_port=port,
        shared_secret=secret,
    )
    last_nas = last_seen_nas_ip(db, endpoint)
    sent = {"User-Name": identity, "Calling-Station-Id": identity}
    sent.update(extra)
    return SessionActionOutcome(
        action=action,
        identity=identity,
        calling_station_id=identity,
        nas_name=nas_name,
        used_lab_sink=used_sink,
        attributes_sent=sent,
        last_seen_nas_ip=last_nas,
        note=_note(
            action=action,
            used_lab_sink=used_sink,
            result=coa.result,
            policy=policy,
            extra=extra,
            last_nas=last_nas,
            nas_name=nas_name,
            failure_reason=coa.failure_reason,
        ),
        coa=coa,
        policy_name=policy.name if policy else None,
        policy_id=policy.id if policy else None,
    )
