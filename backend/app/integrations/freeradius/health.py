"""Probe FreeRADIUS health from the shared runtime volume + optional UDP reachability."""

from __future__ import annotations

import socket
import time
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def freeradius_health_detail() -> tuple[str, str]:
    """Return (status, detail) for the FreeRADIUS component.

    status: ok | degraded | error | configured
    """
    runtime = Path(settings.freeradius_config_dir)
    status_path = runtime / "health.status"
    clients_path = runtime / "clients.dot1x.conf"
    ca_path = Path(settings.freeradius_ca_path)
    parts: list[str] = []

    heartbeat_ok = False
    if status_path.exists():
        try:
            age = time.time() - status_path.stat().st_mtime
            text = status_path.read_text(encoding="utf-8", errors="replace").strip() or "unknown"
            parts.append(f"heartbeat={text} age={age:.0f}s")
            heartbeat_ok = age <= settings.freeradius_health_max_age_seconds
        except OSError as exc:
            parts.append(f"heartbeat_error={exc}")
    else:
        parts.append("heartbeat=missing")

    if clients_path.exists():
        parts.append("clients_conf=present")
    else:
        parts.append("clients_conf=missing")

    if ca_path.exists() and ca_path.stat().st_size > 0:
        parts.append("eap_ca=present")
    else:
        parts.append("eap_ca=missing")

    host = settings.freeradius_host
    port = settings.freeradius_auth_port
    resolvable = _host_resolvable(host)
    parts.append(f"target={host}:{port}:{'resolvable' if resolvable else 'unresolvable'}")

    # The heartbeat file written by the FreeRADIUS entrypoint is the authoritative
    # liveness signal. A UDP sendto() "probe" always succeeds on a connectionless
    # socket regardless of whether anything is listening, so it must never be
    # allowed to upgrade the status.
    detail = "; ".join(parts)
    if heartbeat_ok:
        return ("ok", detail) if resolvable else ("degraded", detail)
    if status_path.exists():
        # Heartbeat present but stale — the container stopped updating it.
        return "degraded", detail
    if clients_path.exists():
        return "configured", detail
    return "error", detail


def _host_resolvable(host: str) -> bool:
    """Informational DNS/addressing check for the configured RADIUS target."""
    try:
        socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_DGRAM)
        return True
    except OSError:
        return False
