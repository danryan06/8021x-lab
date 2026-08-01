"""Resolve and persist the advertised RADIUS target address for NAS devices."""

from __future__ import annotations

import ipaddress
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.integrations.network.detect import detect_address_candidates, pick_auto_ip
from app.models.entities import Lab

settings = get_settings()

SETTINGS_KEY = "radius_target"


def _lab_target_settings(lab: Lab) -> dict[str, Any]:
    raw = lab.settings or {}
    value = raw.get(SETTINGS_KEY) or {}
    return value if isinstance(value, dict) else {}


def get_or_default_lab(db: Session, lab_id: UUID | None = None) -> Lab | None:
    if lab_id:
        return db.get(Lab, lab_id)
    return db.scalar(select(Lab).order_by(Lab.created_at.asc()).limit(1))


def build_radius_target(db: Session, lab_id: UUID | None = None) -> dict[str, Any]:
    lab = get_or_default_lab(db, lab_id)
    stored = _lab_target_settings(lab) if lab else {}
    mode = stored.get("mode") if stored.get("mode") in {"auto", "manual"} else "auto"
    auth_port = int(stored.get("auth_port") or settings.radius_advertise_auth_port)
    acct_port = int(stored.get("acct_port") or settings.radius_advertise_acct_port)
    manual_ip = (stored.get("advertise_ip") or "").strip() or None
    if manual_ip:
        try:
            ipaddress.ip_address(manual_ip)
        except ValueError:
            manual_ip = None

    candidates = detect_address_candidates(settings.radius_host_ip_file)
    auto_ip = pick_auto_ip(candidates)
    effective_ip = manual_ip if mode == "manual" and manual_ip else auto_ip

    warning = None
    if not effective_ip:
        warning = (
            "No advertise IP detected yet. Set one manually, or ensure the host has a DHCP/LAN "
            "address and restart after bootstrap writes host-ip."
        )
    elif mode == "auto" and candidates:
        chosen = next((c for c in candidates if c.ip == effective_ip), None)
        if chosen and chosen.likely_docker:
            warning = (
                "Auto-detected address looks like a Docker/bridge IP. For a real NAS, set a "
                "manual LAN IP (or re-run bootstrap on the host so RADIUS_ADVERTISE_IP / host-ip "
                "is populated from DHCP)."
            )

    return {
        "lab_id": lab.id if lab else None,
        "mode": mode,
        "advertise_ip": manual_ip,
        "effective_ip": effective_ip,
        "auth_port": auth_port,
        "acct_port": acct_port,
        "shared_secret_hint": _secret_hint(settings.freeradius_lab_secret),
        "lab_shared_secret": settings.freeradius_lab_secret,
        "candidates": [
            {
                "ip": c.ip,
                "interface": c.interface,
                "source": c.source,
                "likely_docker": c.likely_docker,
                "is_private": c.is_private,
            }
            for c in candidates
        ],
        "nas_instructions": (
            f"On your switch/WLC/AP, set RADIUS server to {effective_ip or '<lab-ip>'}"
            f":{auth_port} (acct {acct_port}). Then add a RADIUS Client in this lab whose IP/CIDR "
            "matches the NAS source address and shared secret."
        ),
        "warning": warning,
        "auto_source": next(
            (c.source for c in candidates if c.ip == auto_ip),
            None,
        ),
    }


def update_radius_target(
    db: Session,
    *,
    lab_id: UUID | None,
    mode: str,
    advertise_ip: str | None,
    auth_port: int | None = None,
    acct_port: int | None = None,
) -> dict[str, Any]:
    lab = get_or_default_lab(db, lab_id)
    if not lab:
        raise ValueError("No lab found — create a lab first")

    if mode not in {"auto", "manual"}:
        raise ValueError("mode must be 'auto' or 'manual'")

    cleaned_ip: str | None = None
    if advertise_ip is not None:
        cleaned = advertise_ip.strip()
        if cleaned:
            try:
                addr = ipaddress.ip_address(cleaned)
            except ValueError as exc:
                raise ValueError("advertise_ip must be a valid IPv4/IPv6 address") from exc
            if addr.version != 4:
                raise ValueError("advertise_ip must be IPv4 for RADIUS NAS targeting")
            cleaned_ip = str(addr)

    if mode == "manual" and not cleaned_ip:
        raise ValueError("advertise_ip is required when mode is manual")

    settings_obj = dict(lab.settings or {})
    current = _lab_target_settings(lab)
    next_settings = {
        "mode": mode,
        "advertise_ip": cleaned_ip if mode == "manual" else current.get("advertise_ip"),
        "auth_port": int(auth_port or current.get("auth_port") or settings.radius_advertise_auth_port),
        "acct_port": int(acct_port or current.get("acct_port") or settings.radius_advertise_acct_port),
    }
    if mode == "auto":
        # Keep last manual IP as a convenience preset, but effective IP comes from detection.
        next_settings["advertise_ip"] = cleaned_ip or current.get("advertise_ip")

    settings_obj[SETTINGS_KEY] = next_settings
    lab.settings = settings_obj
    flag_modified(lab, "settings")
    db.add(lab)
    db.commit()
    db.refresh(lab)
    return build_radius_target(db, lab.id)


def _secret_hint(secret: str) -> str:
    if len(secret) <= 4:
        return "****"
    return f"{secret[:2]}…{secret[-2:]}"
