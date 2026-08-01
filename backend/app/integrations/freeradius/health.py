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
    udp_ok = _udp_reachable(host, port)
    parts.append(f"udp={host}:{port}:{'ok' if udp_ok else 'unreachable'}")

    detail = "; ".join(parts)
    if heartbeat_ok and udp_ok:
        return "ok", detail
    if heartbeat_ok or udp_ok:
        return "degraded", detail
    if clients_path.exists():
        return "configured", detail
    return "error", detail


def _udp_reachable(host: str, port: int, timeout: float = 1.5) -> bool:
    """Best-effort UDP reachability check (send empty datagram)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(b"\x00", (host, port))
            return True
        finally:
            sock.close()
    except OSError:
        return False
