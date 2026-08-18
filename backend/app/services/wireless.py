"""The wireless profile a lab carries: SSID, security mode, and its VLAN.

A lab's ``settings`` column is deliberately free-form, but the wireless profile
describes real radio configuration an operator will copy onto a controller, so
it is validated and normalized on the way in and lives under one known key.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.entities import Lab
from app.schemas.entities import WirelessProfile

SETTINGS_KEY = "wireless_profile"


def _readable(exc: ValidationError) -> str:
    """Pydantic's error list, flattened to one sentence an operator can act on."""
    parts = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", ()) if loc != "__root__")
        message = error.get("msg", "is not valid")
        message = message.removeprefix("Value error, ")
        parts.append(f"{field}: {message}" if field else message)
    return "; ".join(parts) or "wireless profile is not valid"


def parse_profile(data: Any) -> WirelessProfile:
    """Validate a raw wireless profile; raise ValueError with a readable reason."""
    if not isinstance(data, dict):
        raise ValueError("wireless_profile must be an object with an 'ssid'")
    try:
        return WirelessProfile.model_validate(data)
    except ValidationError as exc:
        raise ValueError(_readable(exc)) from exc


def normalize_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return lab settings with the wireless profile (if any) validated in place."""
    data = dict(settings or {})
    if SETTINGS_KEY not in data or data[SETTINGS_KEY] is None:
        return data
    data[SETTINGS_KEY] = parse_profile(data[SETTINGS_KEY]).model_dump()
    return data


def merge_profile(
    settings: dict[str, Any] | None, profile: WirelessProfile
) -> dict[str, Any]:
    """Set the wireless profile without disturbing the rest of a lab's settings."""
    data = dict(settings or {})
    data[SETTINGS_KEY] = profile.model_dump()
    return data


def read_profile(lab: Lab) -> WirelessProfile | None:
    raw = (lab.settings or {}).get(SETTINGS_KEY)
    if not raw:
        return None
    try:
        return parse_profile(raw)
    except ValueError:
        # A profile stored before a validation rule existed should not break the
        # lab it belongs to; the UI simply offers to set it again.
        return None


def set_profile(db: Session, lab: Lab, profile: WirelessProfile) -> Lab:
    lab.settings = merge_profile(lab.settings, profile)
    flag_modified(lab, "settings")
    db.commit()
    db.refresh(lab)
    return lab
