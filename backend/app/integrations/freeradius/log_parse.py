"""Parse FreeRADIUS linelog lines into authentication event fields.

Pinned format:
  DOT1X|%l|%{User-Name}|%{NAS-IP-Address}|%{EAP-Type}|%{reply:Packet-Type}|%{Module-Failure-Message}|%{Service-Type}|%{pairs:reply:}

Fields 8-9 (Service-Type, reply attributes) arrived with MAB in Phase 3 and are
optional, so events written by an older FreeRADIUS container still parse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.integrations.freeradius.reply_attributes import parse_attribute_pairs
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
    returned_attributes: dict = field(default_factory=dict)


def _map_method(eap_type: str, service_type: str = "") -> AuthMethod:
    value = (eap_type or "").strip().lower()
    # FreeRADIUS may emit names ("PEAP") or IANA numbers.
    if value in {"13", "eap-tls", "tls"} or "tls" in value:
        return AuthMethod.eap_tls
    if value in {"25", "26", "mschapv2", "peap"} or "peap" in value or "mschap" in value:
        return AuthMethod.peap
    if "mab" in value:
        return AuthMethod.mab
    # No EAP at all: a MAC lookup (Service-Type = Call-Check) is MAB.
    if "call-check" in (service_type or "").strip().lower():
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
    service_type = parts[7] if len(parts) > 7 else ""
    # The reply-attribute field can itself contain "|" inside a value, so keep
    # everything after field 8 rather than only the next segment.
    reply_pairs = "|".join(parts[8:]) if len(parts) > 8 else ""
    success = "Access-Accept" in packet_type
    try:
        # Prefer unix epoch (%l); also accept ISO-8601 / "YYYY-mm-dd HH:MM:SS".
        if ts.strip().isdigit():
            timestamp = datetime.fromtimestamp(int(ts.strip()), tz=UTC)
        else:
            normalized = ts.strip().replace("Z", "+00:00").replace(" ", "T", 1)
            timestamp = datetime.fromisoformat(normalized)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
    except ValueError:
        timestamp = datetime.now(UTC)

    return ParsedAuthLine(
        timestamp=timestamp,
        identity=identity or None,
        nas_ip=nas_ip or None,
        method=_map_method(eap_type, service_type),
        result=AuthResult.success if success else AuthResult.failure,
        failure_reason=None if success else (failure or "Authentication failed"),
        raw=line,
        # An Access-Reject grants no authorization. FreeRADIUS may still have
        # attributes staged in the reply list when linelog runs (a group lookup
        # ran before authentication failed), but they were never sent — recording
        # them would show a VLAN the NAS never received.
        returned_attributes=parse_attribute_pairs(reply_pairs) if success else {},
    )
