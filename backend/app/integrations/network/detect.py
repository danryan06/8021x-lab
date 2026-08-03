"""Detect IPv4 addresses suitable for advertising as a RADIUS target."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

_DOCKER_IFACE = re.compile(r"^(docker|br-|veth|cni|flannel|virbr|lxc)", re.I)


@dataclass
class AddressCandidate:
    ip: str
    interface: str | None
    source: str
    likely_docker: bool
    is_private: bool


def _is_dockerish(iface: str | None, ip: str) -> bool:
    if iface and _DOCKER_IFACE.search(iface):
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 192.168/16 is also common on LANs — only treat 172.16/12 as docker-likely.
    return addr in ipaddress.ip_network("172.16.0.0/12")


def _from_ip_cmd() -> list[AddressCandidate]:
    try:
        proc = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:
        return []

    found: list[AddressCandidate] = []
    for line in proc.stdout.splitlines():
        # Example: "2: eth0    inet 10.0.0.5/24 brd ... scope global ..."
        parts = line.split()
        if len(parts) < 4 or parts[2] != "inet":
            continue
        iface = parts[1].rstrip(":")
        cidr = parts[3]
        ip = cidr.split("/", 1)[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
            continue
        found.append(
            AddressCandidate(
                ip=ip,
                interface=iface,
                source="interface",
                likely_docker=_is_dockerish(iface, ip),
                is_private=addr.is_private,
            )
        )
    return found


def _from_udp_probe() -> AddressCandidate | None:
    """Best-effort primary outbound IPv4 (may be a container bridge IP)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.connect(("1.1.1.1", 80))
        ip = sock.getsockname()[0]
        sock.close()
    except OSError:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_unspecified:
        return None
    return AddressCandidate(
        ip=ip,
        interface=None,
        source="default_route",
        likely_docker=_is_dockerish(None, ip),
        is_private=addr.is_private,
    )


def _from_host_ip_file(path: str) -> AddressCandidate | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        raw = file_path.read_text(encoding="utf-8").strip().split()[0]
        addr = ipaddress.ip_address(raw)
    except (OSError, ValueError, IndexError):
        return None
    if addr.version != 4 or addr.is_loopback or addr.is_unspecified:
        return None
    return AddressCandidate(
        ip=str(addr),
        interface=None,
        source="host_ip_file",
        likely_docker=False,
        is_private=addr.is_private,
    )


def _from_env() -> AddressCandidate | None:
    # Read via Settings so a value in .env works for non-Docker runs too
    # (pydantic-settings loads .env without exporting to os.environ).
    raw = (get_settings().radius_advertise_ip or "").strip()
    if not raw:
        return None
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if addr.version != 4 or addr.is_loopback or addr.is_unspecified:
        return None
    return AddressCandidate(
        ip=str(addr),
        interface=None,
        source="env",
        likely_docker=False,
        is_private=addr.is_private,
    )


def detect_address_candidates(host_ip_file: str | None = None) -> list[AddressCandidate]:
    """Return unique IPv4 candidates, preferred first."""
    ordered: list[AddressCandidate] = []
    seen: set[str] = set()

    def add(candidate: AddressCandidate | None) -> None:
        if not candidate or candidate.ip in seen:
            return
        seen.add(candidate.ip)
        ordered.append(candidate)

    add(_from_env())
    if host_ip_file:
        add(_from_host_ip_file(host_ip_file))
    for item in _from_ip_cmd():
        add(item)
    add(_from_udp_probe())

    # Prefer non-docker private LAN addresses for auto selection ordering.
    ordered.sort(
        key=lambda c: (
            0 if c.source in {"env", "host_ip_file"} else 1,
            1 if c.likely_docker else 0,
            0 if c.is_private else 1,
            c.ip,
        )
    )
    return ordered


def pick_auto_ip(candidates: list[AddressCandidate]) -> str | None:
    if not candidates:
        return None
    for c in candidates:
        if c.source in {"env", "host_ip_file"}:
            return c.ip
    for c in candidates:
        if not c.likely_docker:
            return c.ip
    return candidates[0].ip
