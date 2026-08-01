"""Run eapol_test against the lab FreeRADIUS from the backend container."""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def resolve_radius_host(host: str) -> str:
    """eapol_test requires a numeric IPv4 address (hostnames assert/fail)."""
    host = (host or "").strip()
    if not host:
        raise ValueError("RADIUS host is empty")
    try:
        socket.inet_pton(socket.AF_INET, host)
        return host
    except OSError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_DGRAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve RADIUS host {host!r}: {exc}") from exc
    if not infos:
        raise ValueError(f"No IPv4 address for RADIUS host {host!r}")
    return infos[0][4][0]


@dataclass
class EapolResult:
    success: bool
    exit_code: int
    output: str
    method: str
    identity: str
    radius_host: str
    radius_port: int
    shared_secret_hint: str
    failure_reason: str | None = None


def _find_eapol_bin() -> str:
    for name in ("eapol_test", "eapoltest"):
        path = shutil.which(name)
        if path:
            return path
    raise FileNotFoundError(
        "eapol_test/eapoltest not found in PATH. Install the eapoltest package in the backend image."
    )


def _ca_pem_path() -> Path:
    path = Path(settings.freeradius_ca_path)
    if path.exists() and path.stat().st_size > 0:
        return path
    raise FileNotFoundError(
        f"FreeRADIUS EAP CA not found at {path}. Is the freeradius service running?"
    )


def run_peap_test(
    identity: str,
    password: str,
    *,
    radius_host: str | None = None,
    radius_port: int | None = None,
    shared_secret: str | None = None,
    timeout_seconds: int = 30,
) -> EapolResult:
    host = resolve_radius_host(radius_host or settings.freeradius_host)
    port = radius_port or settings.freeradius_auth_port
    secret = shared_secret or settings.freeradius_lab_secret
    ca_pem = _ca_pem_path()
    eapol = _find_eapol_bin()

    with tempfile.TemporaryDirectory(prefix="dot1x-peap-") as tmp:
        conf_path = Path(tmp) / "peap.conf"
        # Point ca_cert at a copy inside tmp so relative paths stay simple.
        ca_copy = Path(tmp) / "ca.pem"
        ca_copy.write_text(ca_pem.read_text(encoding="utf-8"), encoding="utf-8")
        conf_path.write_text(
            "\n".join(
                [
                    "network={",
                    "  key_mgmt=WPA-EAP",
                    "  eap=PEAP",
                    f'  identity="{identity}"',
                    f'  password="{password}"',
                    '  phase2="auth=MSCHAPV2"',
                    f'  ca_cert="{ca_copy}"',
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return _run_eapol(
            eapol=eapol,
            conf_path=conf_path,
            host=host,
            port=port,
            secret=secret,
            method="peap",
            identity=identity,
            timeout_seconds=timeout_seconds,
        )


def run_eap_tls_test(
    identity: str,
    client_cert: Path,
    private_key: Path,
    *,
    radius_host: str | None = None,
    radius_port: int | None = None,
    shared_secret: str | None = None,
    timeout_seconds: int = 45,
) -> EapolResult:
    host = resolve_radius_host(radius_host or settings.freeradius_host)
    port = radius_port or settings.freeradius_auth_port
    secret = shared_secret or settings.freeradius_lab_secret
    ca_pem = _ca_pem_path()
    eapol = _find_eapol_bin()

    if not client_cert.exists() or not private_key.exists():
        raise FileNotFoundError("Client certificate or private key missing for EAP-TLS test")

    with tempfile.TemporaryDirectory(prefix="dot1x-eaptls-") as tmp:
        conf_path = Path(tmp) / "eap-tls.conf"
        ca_copy = Path(tmp) / "ca.pem"
        cert_copy = Path(tmp) / "client.pem"
        key_copy = Path(tmp) / "client.key"
        ca_copy.write_text(ca_pem.read_text(encoding="utf-8"), encoding="utf-8")
        cert_copy.write_text(client_cert.read_text(encoding="utf-8"), encoding="utf-8")
        key_copy.write_text(private_key.read_text(encoding="utf-8"), encoding="utf-8")
        conf_path.write_text(
            "\n".join(
                [
                    "network={",
                    "  key_mgmt=WPA-EAP",
                    "  eap=TLS",
                    f'  identity="{identity}"',
                    f'  client_cert="{cert_copy}"',
                    f'  private_key="{key_copy}"',
                    f'  ca_cert="{ca_copy}"',
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return _run_eapol(
            eapol=eapol,
            conf_path=conf_path,
            host=host,
            port=port,
            secret=secret,
            method="eap_tls",
            identity=identity,
            timeout_seconds=timeout_seconds,
        )


def _run_eapol(
    *,
    eapol: str,
    conf_path: Path,
    host: str,
    port: int,
    secret: str,
    method: str,
    identity: str,
    timeout_seconds: int,
) -> EapolResult:
    cmd = [
        eapol,
        "-c",
        str(conf_path),
        "-a",
        host,
        "-p",
        str(port),
        "-s",
        secret,
        "-r",
        "1",
    ]
    # Never log the shared secret or password-bearing config path contents.
    logger.info("Running eapol_test method=%s identity=%s host=%s:%s", method, identity, host, port)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return EapolResult(
            success=False,
            exit_code=124,
            output=_trim_output(output),
            method=method,
            identity=identity,
            radius_host=host,
            radius_port=port,
            shared_secret_hint=_secret_hint(secret),
            failure_reason=f"eapol_test timed out after {timeout_seconds}s",
        )

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    success = proc.returncode == 0 or "SUCCESS" in output
    failure_reason = None
    if not success:
        failure_reason = _infer_failure(output) or f"eapol_test exit={proc.returncode}"

    logger.info(
        "eapol_test finished method=%s identity=%s success=%s elapsed=%.1fs",
        method,
        identity,
        success,
        time.monotonic() - started,
    )
    return EapolResult(
        success=success,
        exit_code=proc.returncode,
        output=_trim_output(output),
        method=method,
        identity=identity,
        radius_host=host,
        radius_port=port,
        shared_secret_hint=_secret_hint(secret),
        failure_reason=failure_reason,
    )


def _secret_hint(secret: str) -> str:
    if len(secret) <= 4:
        return "****"
    return f"{secret[:2]}…{secret[-2:]} (lab compose secret)"


def _redact_secrets(output: str) -> str:
    """Strip password material from eapol_test debug dumps before returning to UI/API."""
    lines = output.splitlines()
    redacted: list[str] = []
    skip_hex = 0
    for line in lines:
        lower = line.lower()
        if "password - hexdump" in lower or lower.strip().startswith("password -"):
            redacted.append("password - hexdump_ascii: [REDACTED]")
            skip_hex = 2
            continue
        if skip_hex > 0 and (line.startswith("     ") or line.startswith("\t")):
            skip_hex -= 1
            continue
        skip_hex = 0
        redacted.append(line)
    return "\n".join(redacted)


def _trim_output(output: str, limit: int = 4000) -> str:
    text = _redact_secrets(output).strip()
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n…\n" + text[-limit // 2 :]


def _infer_failure(output: str) -> str | None:
    lowered = output.lower()
    if "password" in lowered and ("fail" in lowered or "reject" in lowered):
        return "MSCHAPv2 password rejected"
    if "certificate" in lowered and ("unknown" in lowered or "untrusted" in lowered):
        return "TLS certificate not trusted"
    if "expired" in lowered:
        return "Certificate expired"
    if "access-reject" in lowered or "radius rejected" in lowered:
        return "RADIUS Access-Reject"
    if "timeout" in lowered or "timed out" in lowered:
        return "RADIUS timeout"
    if "no radius" in lowered:
        return "No RADIUS response"
    return None
