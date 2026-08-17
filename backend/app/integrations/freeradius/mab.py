"""MAC Authentication Bypass (MAB): how a MAC becomes a RADIUS identity, and a
test runner that sends a real MAB Access-Request from the backend container.

MAB is what a switch falls back to for devices that cannot speak 802.1X (printers,
cameras, badge readers). The NAS puts the device's MAC in `User-Name` and asks
FreeRADIUS whether that MAC is allowed on the network. There is no secret and no
EAP exchange, which is why MAB is weak authentication: whoever can spell the MAC
can be the device.

Two details make this work against real hardware:

* **Username spelling.** Vendors send the MAC in different formats
  (`aabbccddeeff`, `AA-BB-CC-DD-EE-FF`, `aa:bb:cc:dd:ee:ff`, …), so an endpoint is
  registered in FreeRADIUS under every common spelling of its canonical MAC.
* **No password to check.** The registered `radcheck` row is
  `Auth-Type := Accept`, so a known MAC is accepted whatever the NAS puts in
  `User-Password` — which is exactly the MAB trust model.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field

from app.config import get_settings

# Shared with the eapol_test runner: identical redaction/trimming rules for
# subprocess output that is handed back to the UI.
from app.integrations.freeradius.eapol import _secret_hint, _trim_output, resolve_radius_host
from app.integrations.freeradius.reply_attributes import parse_attribute_pairs
from app.validation import normalize_mac

logger = logging.getLogger(__name__)
settings = get_settings()

# Separator + case combinations seen in real NAS Access-Requests. Cisco IOS sends
# bare hex, Cisco WLC / Juniper / Meraki use colons, Windows tooling uses hyphens.
_MAC_USERNAME_SEPARATORS = (":", "-", "")


def mac_radius_usernames(mac: str) -> list[str]:
    """Every `User-Name` spelling a NAS might use for this MAC (canonical first)."""
    canonical = normalize_mac(mac)
    hex_digits = canonical.replace(":", "")
    pairs = [hex_digits[i : i + 2] for i in range(0, 12, 2)]
    usernames: list[str] = []
    for separator in _MAC_USERNAME_SEPARATORS:
        lower = separator.join(pairs)
        for value in (lower, lower.upper()):
            if value not in usernames:
                usernames.append(value)
    return usernames


UNKNOWN_MAC_REASON = (
    "Unknown MAC address — no endpoint is registered for this MAC in the lab, "
    "so FreeRADIUS had nothing to authorize"
)
DISABLED_ENDPOINT_REASON = (
    "Endpoint is disabled — the MAC is registered in the lab but not synced to FreeRADIUS"
)


def mab_reject_reason(*, registered: bool, enabled: bool) -> str | None:
    """Why a MAB attempt was rejected, from the control plane's point of view.

    FreeRADIUS rejects an unknown MAC with no `Module-Failure-Message` (there is no
    module to fail — nothing matched), so the useful explanation has to come from
    the lab's own endpoint list.
    """
    if not registered:
        return UNKNOWN_MAC_REASON
    if not enabled:
        return DISABLED_ENDPOINT_REASON
    return None


@dataclass
class MabResult:
    success: bool
    exit_code: int
    output: str
    identity: str
    radius_host: str
    radius_port: int
    shared_secret_hint: str
    reply_attributes: dict = field(default_factory=dict)
    failure_reason: str | None = None


def _find_radclient_bin() -> str:
    path = shutil.which("radclient")
    if path:
        return path
    raise FileNotFoundError(
        "radclient not found in PATH. Install the freeradius-utils package in the backend image."
    )


def _local_source_ip(host: str, port: int) -> str | None:
    """Address FreeRADIUS will see this request come from (for NAS-IP-Address)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((host, port))
            return probe.getsockname()[0]
    except OSError:
        return None


def build_mab_request(
    username: str,
    *,
    password: str | None = None,
    calling_station_id: str | None = None,
    nas_ip: str | None = None,
) -> str:
    """Build the radclient attribute document for one MAB Access-Request.

    Mirrors what a switch sends for a MAB port: the MAC as both `User-Name` and
    `User-Password`, `Service-Type = Call-Check` to mark it as a MAC lookup rather
    than a user login, and `Calling-Station-Id` carrying the endpoint MAC.
    """
    lines = [
        f'User-Name = "{username}"',
        f'User-Password = "{password if password is not None else username}"',
        "Service-Type = Call-Check",
        f'Calling-Station-Id = "{calling_station_id or username}"',
        "NAS-Port-Type = Ethernet",
        "NAS-Port = 1",
    ]
    if nas_ip:
        lines.append(f"NAS-IP-Address = {nas_ip}")
    return "\n".join(lines) + "\n"


def run_mab_test(
    mac: str,
    *,
    username_format: str | None = None,
    password: str | None = None,
    radius_host: str | None = None,
    radius_port: int | None = None,
    shared_secret: str | None = None,
    timeout_seconds: int = 20,
) -> MabResult:
    """Send a MAB Access-Request with radclient and report the decision + reply.

    `username_format` picks which spelling of the MAC goes in `User-Name` (default:
    the canonical `aa:bb:cc:dd:ee:ff`), so the UI can demonstrate that a switch
    sending bare hex authenticates the same endpoint.
    """
    canonical = normalize_mac(mac)
    identity = canonical
    if username_format:
        available = {u.lower(): u for u in mac_radius_usernames(canonical)}
        chosen = available.get(username_format.lower())
        if not chosen:
            raise ValueError(f"{username_format!r} is not a known MAC username format")
        identity = chosen

    host = resolve_radius_host(radius_host or settings.freeradius_host)
    port = radius_port or settings.freeradius_auth_port
    secret = shared_secret or settings.freeradius_lab_secret
    radclient = _find_radclient_bin()

    request = build_mab_request(
        identity,
        password=password,
        calling_station_id=canonical,
        nas_ip=_local_source_ip(host, port),
    )

    cmd = [radclient, "-x", "-t", "3", "-r", "1", f"{host}:{port}", "auth", secret]
    logger.info("Running radclient MAB test identity=%s host=%s:%s", identity, host, port)
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
        return MabResult(
            success=False,
            exit_code=124,
            output=_trim_output(output),
            identity=identity,
            radius_host=host,
            radius_port=port,
            shared_secret_hint=_secret_hint(secret),
            failure_reason=f"radclient timed out after {timeout_seconds}s",
        )

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    # radclient exits 0 for any answered request, so the packet type in the
    # output — not the exit code — is what decides accept vs reject.
    success = "Received Access-Accept" in output
    reply_attributes = parse_reply_attributes(output) if success else {}
    failure_reason = None
    if not success:
        failure_reason = infer_mab_failure(output) or f"radclient exit={proc.returncode}"

    logger.info(
        "radclient MAB test finished identity=%s success=%s elapsed=%.1fs",
        identity,
        success,
        time.monotonic() - started,
    )
    return MabResult(
        success=success,
        exit_code=proc.returncode,
        output=_trim_output(output),
        identity=identity,
        radius_host=host,
        radius_port=port,
        shared_secret_hint=_secret_hint(secret),
        reply_attributes=reply_attributes,
        failure_reason=failure_reason,
    )


def parse_reply_attributes(output: str) -> dict:
    """Pull the reply attributes radclient printed after `Received Access-Accept`."""
    collecting = False
    pairs: list[str] = []
    for line in output.splitlines():
        if "Received Access-Accept" in line:
            collecting = True
            continue
        if not collecting:
            continue
        if not line.startswith((" ", "\t")):
            # radclient indents reply attributes; anything else ends the block.
            if line.strip():
                break
            continue
        item = line.strip()
        if "=" in item:
            pairs.append(item)
    return parse_attribute_pairs(", ".join(pairs))


def infer_mab_failure(output: str) -> str | None:
    lowered = output.lower()
    if "received access-reject" in lowered:
        return "RADIUS Access-Reject"
    if "no reply from server" in lowered or "no response" in lowered:
        return "No RADIUS response — is FreeRADIUS running and is this source a known client?"
    if "received access-challenge" in lowered:
        return "RADIUS Access-Challenge (MAB expects a straight Accept/Reject)"
    return None
