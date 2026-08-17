"""Authorization reply attributes: render policies, read back what FreeRADIUS sent.

An `AuthzPolicy` is stored in friendly terms (VLAN id, role) plus an optional bag
of raw name/value pairs. FreeRADIUS only understands RADIUS attributes, so this
module is the single place that translates one into the other:

    vlan=20        → Tunnel-Type = VLAN
                     Tunnel-Medium-Type = IEEE-802
                     Tunnel-Private-Group-Id = 20
    role="guests"  → Filter-Id = guests

The rendered rows are written to `radreply` (per endpoint) / `radgroupreply`
(per user group) by `sql_sync`, and the same names are parsed back out of the
FreeRADIUS linelog / radclient output so the UI can show what the NAS received.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.validation import validate_attribute_name, validate_attribute_value

# Tagged tunnel attributes a switch/AP needs before it will move a port to a VLAN.
VLAN_TUNNEL_TYPE = "Tunnel-Type"
VLAN_TUNNEL_MEDIUM_TYPE = "Tunnel-Medium-Type"
VLAN_TUNNEL_GROUP_ID = "Tunnel-Private-Group-Id"
ROLE_ATTRIBUTE = "Filter-Id"

# Reply attributes that are either key material or protocol plumbing: never store
# or display them as "what the NAS received".
SENSITIVE_REPLY_ATTRIBUTES = {
    "eap-message",
    "message-authenticator",
    "ms-mppe-recv-key",
    "ms-mppe-send-key",
    "ms-mppe-encryption-policy",
    "ms-mppe-encryption-types",
    "proxy-state",
    "state",
}

# `%{pairs:reply:}` renders `Name = value, Name = "quoted value"`. Tunnel attributes
# may carry a tag (`Tunnel-Type:0`), which radclient prints and which must not be
# mistaken for the end of the previous value.
_PAIR_SPLIT = re.compile(r",\s*(?=[A-Za-z][A-Za-z0-9-]*(?::\d+)?\s*=)")

# Tag suffix on tunnel attributes; the tag groups attributes into one tunnel and
# carries no meaning for "what did the NAS receive".
_ATTRIBUTE_TAG = re.compile(r":\d+$")

# Common reply attributes, shown in the Advanced policy editor so the RADIUS
# names are visible rather than hidden behind lab jargon.
RADIUS_ATTRIBUTE_CATALOG: list[dict[str, str]] = [
    {
        "name": VLAN_TUNNEL_GROUP_ID,
        "label": "VLAN id or name",
        "example": "20",
        "description": "The VLAN the NAS should put the port/client into. Sent with "
        "Tunnel-Type and Tunnel-Medium-Type; the Simple editor fills all three for you.",
    },
    {
        "name": VLAN_TUNNEL_TYPE,
        "label": "Tunnel type",
        "example": "VLAN",
        "description": "Must be VLAN for dynamic VLAN assignment.",
    },
    {
        "name": VLAN_TUNNEL_MEDIUM_TYPE,
        "label": "Tunnel medium",
        "example": "IEEE-802",
        "description": "Must be IEEE-802 (Ethernet/802.11) for dynamic VLAN assignment.",
    },
    {
        "name": ROLE_ATTRIBUTE,
        "label": "Role / filter name",
        "example": "guest-acl",
        "description": "Names an ACL or role already defined on the switch/WLC. The most "
        "portable way to say “treat this session as X”.",
    },
    {
        "name": "Session-Timeout",
        "label": "Session timeout (seconds)",
        "example": "3600",
        "description": "How long the session may last before the NAS re-authenticates it.",
    },
    {
        "name": "Termination-Action",
        "label": "Termination action",
        "example": "RADIUS-Request",
        "description": "With Session-Timeout, asks the NAS to re-authenticate instead of "
        "dropping the session.",
    },
    {
        "name": "Idle-Timeout",
        "label": "Idle timeout (seconds)",
        "example": "600",
        "description": "Disconnect the session after this much inactivity.",
    },
    {
        "name": "Reply-Message",
        "label": "Reply message",
        "example": "Welcome to the lab VLAN",
        "description": "Free text returned with the decision. Handy for lab demos; most "
        "NAS devices only log it.",
    },
    {
        "name": "Cisco-AVPair",
        "label": "Cisco AV pair",
        "example": "device-traffic-class=voice",
        "description": "Vendor-specific attribute used by Cisco gear (dACLs, voice "
        "domain, redirect URLs).",
    },
]


@dataclass(frozen=True)
class ReplyAttribute:
    """One row as FreeRADIUS stores it in `radreply` / `radgroupreply`."""

    name: str
    op: str
    value: str


def render_policy_attributes(
    *,
    vlan: int | None = None,
    role: str | None = None,
    extra: dict | None = None,
) -> list[ReplyAttribute]:
    """Render a policy into the reply attributes FreeRADIUS should return.

    VLAN and role come first (they are what Simple mode edits), then any raw
    name/value pairs from Advanced mode. A raw pair that repeats a rendered name
    replaces it in place, so the Advanced editor always wins without producing
    two conflicting rows for the same attribute.
    """
    rendered: list[ReplyAttribute] = []
    if vlan is not None:
        if vlan < 1 or vlan > 4094:
            raise ValueError("VLAN id must be between 1 and 4094")
        rendered.append(ReplyAttribute(VLAN_TUNNEL_TYPE, "=", "VLAN"))
        rendered.append(ReplyAttribute(VLAN_TUNNEL_MEDIUM_TYPE, "=", "IEEE-802"))
        rendered.append(ReplyAttribute(VLAN_TUNNEL_GROUP_ID, "=", str(vlan)))
    if role and role.strip():
        value = validate_attribute_value(ROLE_ATTRIBUTE, role.strip())
        rendered.append(ReplyAttribute(ROLE_ATTRIBUTE, "=", value))

    for raw_name, raw_value in (extra or {}).items():
        name = validate_attribute_name(str(raw_name).strip())
        if raw_value is None:
            continue
        value = validate_attribute_value(name, str(raw_value).strip())
        if not value:
            continue
        attribute = ReplyAttribute(name, "=", value)
        replaced = False
        for index, existing in enumerate(rendered):
            if existing.name.lower() == name.lower():
                rendered[index] = attribute
                replaced = True
                break
        if not replaced:
            rendered.append(attribute)

    return rendered


def summarize_attributes(attributes: dict) -> str:
    """One-line, human-first summary used in status messages and event rows."""
    parts: list[str] = []
    for name, value in attributes.items():
        if name.lower() == VLAN_TUNNEL_GROUP_ID.lower():
            parts.append(f"VLAN {value}")
        elif name.lower() == ROLE_ATTRIBUTE.lower():
            parts.append(f"role {value}")
        elif name.lower() in {VLAN_TUNNEL_TYPE.lower(), VLAN_TUNNEL_MEDIUM_TYPE.lower()}:
            continue
        else:
            parts.append(f"{name}={value}")
    return " · ".join(parts)


def filter_returned_attributes(attributes: dict) -> dict:
    """Drop key material / protocol plumbing before an event is stored or shown."""
    clean: dict[str, str] = {}
    for name, value in attributes.items():
        if not name or name.lower() in SENSITIVE_REPLY_ATTRIBUTES:
            continue
        text = str(value)
        if len(text) > 253:
            continue
        clean[name] = text
    return clean


def parse_attribute_pairs(text: str) -> dict:
    """Parse a `Name = value, Name = "value"` list into a dict.

    Handles both FreeRADIUS `%{pairs:reply:}` output (linelog) and the attribute
    lines radclient prints for a reply.
    """
    result: dict[str, str] = {}
    for chunk in _PAIR_SPLIT.split((text or "").strip()):
        item = chunk.strip().strip(",").strip()
        if not item or "=" not in item:
            continue
        name, _, value = item.partition("=")
        name = _ATTRIBUTE_TAG.sub("", name.strip())
        if not name:
            continue
        value = value.strip().strip('"')
        result[name] = value
    return filter_returned_attributes(result)
