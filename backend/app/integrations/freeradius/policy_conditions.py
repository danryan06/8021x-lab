"""Time-of-day and NAS-scoped check items for authorization policies.

Reply attributes (VLAN, Filter-Id) say what the NAS should do *after* accept.
Check items say whether FreeRADIUS should accept at all: only during these
hours, only from this NAS. They are written to `radcheck` (MAB endpoints) and
`radgroupcheck` (user groups) next to `Auth-Type := Accept`.

FreeRADIUS `Login-Time` is a compact day+window string (`Wk0800-1700` =
weekdays 08:00–17:00). `NAS-IP-Address` is compared to the attribute on the
Access-Request — the same address a switch puts in the packet, which is why
the Auth Test MAB runner sends it.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError, field_validator

# Al/Any = every day, Wk = Mon–Fri, then two-letter days and optional ranges.
_DAY = r"(?:Any|Al|Wk|Mo|Tu|We|Th|Fr|Sa|Su)"
_LOGIN_TIME = re.compile(rf"^{_DAY}(?:-{_DAY})?(?:\d{{4}}-\d{{4}})?$", re.IGNORECASE)

# Presets shown in Simple mode; values are the FreeRADIUS strings themselves.
LOGIN_TIME_PRESETS: list[dict[str, str]] = [
    {"value": "", "label": "Any time"},
    {"value": "Wk0800-1700", "label": "Weekdays 08:00–17:00"},
    {"value": "Wk0800-1800", "label": "Weekdays 08:00–18:00"},
    {"value": "Sa-Su", "label": "Weekends"},
    {"value": "Al1800-0800", "label": "Evenings 18:00–08:00 (overnight)"},
]


class PolicyConditions(BaseModel):
    """Optional constraints stored on `AuthzPolicy.conditions`."""

    login_time: str | None = Field(default=None, max_length=32)
    nas_ip: str | None = Field(default=None, max_length=64)

    @field_validator("login_time")
    @classmethod
    def _login_time(cls, value: str | None) -> str | None:
        return validate_login_time(value)

    @field_validator("nas_ip")
    @classmethod
    def _nas_ip(cls, value: str | None) -> str | None:
        return validate_nas_ip(value)


@dataclass(frozen=True)
class CheckItem:
    """One row as FreeRADIUS stores it in `radcheck` / `radgroupcheck`."""

    name: str
    op: str
    value: str


def validate_login_time(value: str | None) -> str | None:
    """Normalize a FreeRADIUS Login-Time string, or None when unrestricted."""
    text = (value or "").strip()
    if not text:
        return None
    if not _LOGIN_TIME.fullmatch(text):
        raise ValueError(
            "login_time must be a FreeRADIUS Login-Time string such as Wk0800-1700 "
            "(weekdays 08:00–17:00), Sa-Su, or Al1800-0800"
        )
    days, _, window = _split_login_time(text)
    suffix = ""
    if window:
        start, end = window[:4], window[5:]
        _assert_hhmm(start)
        _assert_hhmm(end)
        suffix = f"{start}-{end}"
    return _canonical_days(days) + suffix


def _canonical_days(days: str) -> str:
    return "-".join(part[:1].upper() + part[1:].lower() for part in days.split("-"))


def _split_login_time(value: str) -> tuple[str, str, str]:
    match = re.match(r"^([A-Za-z]{2}(?:-[A-Za-z]{2})?)(\d{4}-\d{4})?$", value)
    if not match:
        return value, "", ""
    return match.group(1), "", match.group(2) or ""


def _assert_hhmm(hhmm: str) -> None:
    hour, minute = int(hhmm[:2]), int(hhmm[2:])
    if hour > 23 or minute > 59:
        raise ValueError("login_time hours must be 00–23 and minutes 00–59")


def validate_nas_ip(value: str | None) -> str | None:
    """One NAS address this policy is willing to answer, or None for any NAS."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        addr = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError("nas_ip must be a valid IPv4 or IPv6 address") from exc
    return str(addr)


def parse_policy_conditions(raw: dict | None) -> PolicyConditions:
    try:
        return PolicyConditions.model_validate(raw or {})
    except ValidationError as exc:
        parts: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", ()))
            message = error.get("msg") or "is not valid"
            parts.append(f"{loc}: {message}" if loc else message)
        raise ValueError("; ".join(parts) or "invalid policy conditions") from exc


def render_check_items(raw: dict | None) -> list[CheckItem]:
    """Check items FreeRADIUS should AND with Auth-Type / NT-Password."""
    conditions = parse_policy_conditions(raw)
    items: list[CheckItem] = []
    if conditions.login_time:
        items.append(CheckItem("Login-Time", "==", conditions.login_time))
    if conditions.nas_ip:
        items.append(CheckItem("NAS-IP-Address", "==", conditions.nas_ip))
    return items


def summarize_conditions(raw: dict | None) -> str:
    parts: list[str] = []
    for item in render_check_items(raw):
        if item.name == "Login-Time":
            parts.append(f"time {item.value}")
        elif item.name == "NAS-IP-Address":
            parts.append(f"NAS {item.value}")
        else:
            parts.append(f"{item.name}={item.value}")
    return " · ".join(parts)
