"""Change of Authorization and Disconnect-Request, originated toward a NAS.

Authentication is NAS → RADIUS (Access-Request on UDP 1812). Session control is
the reverse: the RADIUS side sends Disconnect-Request (drop this session) or
CoA-Request (apply a new VLAN/role) to the NAS on UDP 3799. This module builds
those packets as radclient documents and runs radclient from the backend
container, the same pattern as the MAB test runner.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.integrations.freeradius.eapol import _secret_hint, _trim_output, resolve_radius_host
from app.integrations.freeradius.reply_attributes import (
    VLAN_TUNNEL_MEDIUM_TYPE,
    VLAN_TUNNEL_TYPE,
    parse_attribute_pairs,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# radclient's second argument selects the RADIUS packet type.
RADCLIENT_DISCONNECT = "disconnect"
RADCLIENT_COA = "coa"

_REPLY_MARKERS = (
    "Disconnect-ACK",
    "Disconnect-NAK",
    "CoA-ACK",
    "CoA-NAK",
)

# Dictionary names radclient knows; quoting them makes it treat them as strings.
_UNQUOTED_DICTIONARY = {
    (VLAN_TUNNEL_TYPE.lower(), "vlan"),
    (VLAN_TUNNEL_MEDIUM_TYPE.lower(), "ieee-802"),
}


@dataclass
class CoaResult:
    success: bool
    result: str
    packet_type: str | None
    exit_code: int
    output: str
    nas_ip: str
    nas_port: int
    shared_secret_hint: str
    attributes_returned: dict = field(default_factory=dict)
    failure_reason: str | None = None


def _find_radclient_bin() -> str:
    path = shutil.which("radclient")
    if path:
        return path
    raise FileNotFoundError(
        "radclient not found in PATH. Install the freeradius-utils package in the backend image."
    )


def format_radclient_pair(name: str, value: str) -> str:
    """One `Name = value` line, quoted unless radclient's dictionary should see it."""
    if any(char in value for char in "\r\n"):
        raise ValueError(f"{name} contains a newline")
    if (name.lower(), value.lower()) in _UNQUOTED_DICTIONARY:
        return f"{name} = {value}"
    if value.isdecimal():
        return f"{name} = {value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{name} = "{escaped}"'


def build_coa_request(
    username: str,
    *,
    calling_station_id: str | None = None,
    nas_ip: str | None = None,
    extra: dict | None = None,
) -> str:
    """Build the radclient attribute document for one CoA or Disconnect-Request.

    RFC 5176 identifies the session with User-Name and/or Calling-Station-Id (the
    endpoint MAC, for MAB). Extra pairs are the authorization attributes a
    CoA-Request pushes — VLAN tunnel attributes, Filter-Id, and anything else
    the policy rendered.
    """
    if not username or not username.strip():
        raise ValueError("User-Name is required for CoA/Disconnect")
    lines = [format_radclient_pair("User-Name", username.strip())]
    station = (calling_station_id or username).strip()
    if station:
        lines.append(format_radclient_pair("Calling-Station-Id", station))
    if nas_ip:
        lines.append(f"NAS-IP-Address = {nas_ip}")
    for raw_name, raw_value in (extra or {}).items():
        name = str(raw_name).strip()
        if not name or raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        lines.append(format_radclient_pair(name, value))
    return "\n".join(lines) + "\n"


def parse_coa_reply(output: str) -> tuple[str | None, dict]:
    """Packet type and attributes radclient printed after `Received …-ACK/NAK`."""
    packet_type: str | None = None
    collecting = False
    pairs: list[str] = []
    for line in output.splitlines():
        matched = next((marker for marker in _REPLY_MARKERS if f"Received {marker}" in line), None)
        if matched:
            packet_type = matched
            collecting = True
            pairs = []
            continue
        if not collecting:
            continue
        if not line.startswith((" ", "\t")):
            if line.strip():
                collecting = False
            continue
        item = line.strip()
        if "=" in item:
            pairs.append(item)
    return packet_type, parse_attribute_pairs(", ".join(pairs)) if pairs else {}


def infer_coa_failure(output: str, packet_type: str | None) -> str | None:
    if packet_type and packet_type.endswith("-ACK"):
        return None
    if packet_type and packet_type.endswith("-NAK"):
        return (
            f"NAS sent {packet_type} — the session was not found, dynamic authorization "
            "is not enabled, or an attribute was rejected"
        )
    lowered = output.lower()
    if "no reply" in lowered or "no response" in lowered:
        return (
            "No CoA response — the NAS is not listening on UDP 3799 (dynamic "
            "authorization). In Compose, send to the lab CoA sink."
        )
    return None


def run_coa(
    action: str,
    request: str,
    *,
    nas_host: str,
    nas_port: int | None = None,
    shared_secret: str | None = None,
    timeout_seconds: int = 20,
) -> CoaResult:
    """Send a CoA-Request or Disconnect-Request with radclient and report ACK/NAK."""
    if action not in {RADCLIENT_COA, RADCLIENT_DISCONNECT}:
        raise ValueError(f"action must be {RADCLIENT_COA!r} or {RADCLIENT_DISCONNECT!r}")

    host = resolve_radius_host(nas_host)
    port = nas_port or settings.coa_port
    secret = shared_secret or settings.freeradius_lab_secret
    radclient = _find_radclient_bin()

    cmd = [radclient, "-x", "-t", "3", "-r", "1", f"{host}:{port}", action, secret]
    logger.info("Running radclient %s host=%s:%s", action, host, port)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=request,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return CoaResult(
            success=False,
            result="timeout",
            packet_type=None,
            exit_code=124,
            output=_trim_output(output),
            nas_ip=host,
            nas_port=port,
            shared_secret_hint=_secret_hint(secret),
            failure_reason=f"radclient timed out after {timeout_seconds}s",
        )

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    packet_type, returned = parse_coa_reply(output)
    if packet_type and packet_type.endswith("-ACK"):
        result = "ack"
        success = True
    elif packet_type and packet_type.endswith("-NAK"):
        result = "nak"
        success = False
    else:
        no_reply = infer_coa_failure(output, packet_type)
        result = "timeout" if no_reply and "No CoA response" in no_reply else "error"
        success = False
    failure_reason = None if success else infer_coa_failure(output, packet_type)
    if not success and failure_reason is None:
        failure_reason = f"radclient exit={proc.returncode}"

    logger.info(
        "radclient %s finished result=%s packet=%s elapsed=%.1fs",
        action,
        result,
        packet_type,
        time.monotonic() - started,
    )
    return CoaResult(
        success=success,
        result=result,
        packet_type=packet_type,
        exit_code=proc.returncode,
        output=_trim_output(output),
        nas_ip=host,
        nas_port=port,
        shared_secret_hint=_secret_hint(secret),
        attributes_returned=returned,
        failure_reason=failure_reason,
    )
