"""Parse FreeRADIUS linelog lines into authentication event fields.

Pinned format (Phase 1 will configure FreeRADIUS to emit this):
  DOT1X|%{timestamp}|%{User-Name}|%{NAS-IP-Address}|%{EAP-Type}|%{reply:Packet-Type}|%{Module-Failure-Message}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.entities import AuthMethod, AuthResult


@dataclass
class ParsedAuthLine:
    timestamp: datetime
    identity: str | None
    nas_ip: str | None
    method: AuthMethod
    result: AuthResult
    failure_reason: str | None
    raw: str


def _map_method(eap_type: str) -> AuthMethod:
    value = (eap_type or "").strip().lower()
    # FreeRADIUS may emit names ("PEAP") or IANA numbers.
    if value in {"13", "eap-tls", "tls"} or "tls" in value:
        return AuthMethod.eap_tls
    if value in {"25", "26", "mschapv2", "peap"} or "peap" in value or "mschap" in value:
        return AuthMethod.peap
    if "mab" in value:
        return AuthMethod.mab
    return AuthMethod.unknown


def parse_linelog_line(line: str) -> ParsedAuthLine | None:
    line = line.strip()
    if not line.startswith("DOT1X|"):
        return None
    parts = line.split("|")
    if len(parts) < 7:
        return None

    _, ts, identity, nas_ip, eap_type, packet_type, failure = parts[:7]
    success = "Access-Accept" in packet_type
    try:
        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        timestamp = datetime.now(UTC)

    return ParsedAuthLine(
        timestamp=timestamp,
        identity=identity or None,
        nas_ip=nas_ip or None,
        method=_map_method(eap_type),
        result=AuthResult.success if success else AuthResult.failure,
        failure_reason=None if success else (failure or "Authentication failed"),
        raw=line,
    )
