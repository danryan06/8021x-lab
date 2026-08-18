"""step-ca adapter — talks to a running Smallstep CA over HTTP.

Default labs stay on the openssl adapter. Point ``CA_ADAPTER=step-ca`` and
``STEP_CA_URL`` at a step-ca (often ``https://step-ca:9000``) to issue EAP-TLS
client certs from that CA instead.

Issuance uses ``POST /1.0/sign`` with a provisioner one-time token
(``STEP_CA_TOKEN``, from ``step ca token <identity>``). Tokens are typically
single-use; generate a fresh one per issue, or keep using openssl for the
in-Compose path.

See ``services/ca/README.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx

from app.config import get_settings
from app.integrations.ca.base import CaInfo, IssuedCert
from app.validation import validate_identity

settings = get_settings()


class StepCaAdapter:
    """Smallstep step-ca HTTP adapter for labs that already run step-ca."""

    def _lab_dir(self, lab_id: UUID) -> Path:
        path = Path(settings.ca_data_dir) / str(lab_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "certs").mkdir(exist_ok=True)
        (path / "private").mkdir(exist_ok=True)
        return path

    def _require_url(self) -> str:
        url = (settings.step_ca_url or "").rstrip("/")
        if not url:
            raise NotImplementedError(
                "CA_ADAPTER=step-ca requires STEP_CA_URL (e.g. https://step-ca:9000). "
                "Use CA_ADAPTER=openssl for the built-in lab CA."
            )
        return url

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._require_url(), verify=settings.step_ca_verify_tls, timeout=20)

    def root_cert_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "certs" / "root.crt"

    def client_cert_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{validate_identity(identity)}.crt"

    def client_key_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "private" / f"{validate_identity(identity)}.key"

    def client_p12_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{validate_identity(identity)}.p12"

    def crl_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "crl.pem"

    def ensure_root(self, lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> CaInfo:
        cert_path = self.root_cert_path(lab_id)
        if not cert_path.exists():
            with self._client() as client:
                response = client.get("/root")
                response.raise_for_status()
            cert_path.write_text(response.text, encoding="utf-8")
        pem = cert_path.read_text(encoding="utf-8")
        subject = _subject_from_pem(pem) or f"/CN={common_name}"
        return CaInfo(
            name=common_name,
            subject=subject,
            storage_ref=str(cert_path),
            not_before=datetime.now(UTC),
            not_after=datetime.now(UTC) + timedelta(days=3650),
        )

    def ensure_intermediate(
        self, lab_id: UUID, common_name: str = "802.1X Lab Intermediate CA"
    ) -> CaInfo:
        """step-ca already issues from its own intermediate; expose the issuer PEM."""
        self.ensure_root(lab_id)
        raise NotImplementedError(
            "step-ca manages its own issuer. Client certificates come from POST /1.0/sign; "
            "there is no separate lab-created intermediate."
        )

    def issue_client_cert(self, lab_id: UUID, identity: str, days: int = 365) -> IssuedCert:
        validate_identity(identity)
        self.ensure_root(lab_id)
        token = (settings.step_ca_token or "").strip()
        if not token:
            raise NotImplementedError(
                "CA_ADAPTER=step-ca requires STEP_CA_TOKEN from "
                "`step ca token <identity> --provisioner <name>`. "
                "Tokens are usually single-use."
            )
        lab_dir = self._lab_dir(lab_id)
        key_path = lab_dir / "private" / f"{identity}.key"
        csr_path = lab_dir / "certs" / f"{identity}.csr"
        cert_path = lab_dir / "certs" / f"{identity}.crt"
        subject = f"/CN={identity}"
        _run_openssl(
            [
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key_path),
                "-out",
                str(csr_path),
                "-subj",
                subject,
            ]
        )
        csr_pem = csr_path.read_text(encoding="utf-8")
        with self._client() as client:
            response = client.post("/1.0/sign", json={"csr": csr_pem, "ott": token})
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"step-ca refused to sign ({response.status_code}): {response.text[:300]}"
                ) from exc
        payload = response.json()
        cert_pem = payload.get("crt") or payload.get("cert") or ""
        if not cert_pem:
            raise RuntimeError("step-ca /1.0/sign returned no certificate")
        cert_path.write_text(cert_pem, encoding="utf-8")
        issuer_pem = payload.get("ca") or self.root_cert_path(lab_id).read_text(encoding="utf-8")
        chain_path = lab_dir / "certs" / "chain.pem"
        chain_path.write_text(cert_pem + issuer_pem, encoding="utf-8")
        p12_path = lab_dir / "certs" / f"{identity}.p12"
        _run_openssl(
            [
                "pkcs12",
                "-export",
                "-inkey",
                str(key_path),
                "-in",
                str(cert_path),
                "-certfile",
                str(chain_path),
                "-out",
                str(p12_path),
                "-passout",
                "pass:",
            ]
        )
        now = datetime.now(UTC)
        return IssuedCert(
            subject=subject,
            issuer=_subject_from_pem(issuer_pem) or "step-ca",
            serial=_serial_from_pem(cert_pem) or "unknown",
            storage_ref=str(cert_path),
            not_before=now,
            not_after=now + timedelta(days=days),
            cert_pem=cert_pem,
        )

    def revoke(self, lab_id: UUID, cert_ref: str) -> None:
        token = (settings.step_ca_token or "").strip()
        if not token:
            raise NotImplementedError("STEP_CA_TOKEN is required to revoke via step-ca")
        serial = _serial_from_file(Path(cert_ref))
        with self._client() as client:
            response = client.post(
                "/1.0/revoke",
                json={"serial": serial, "ott": token, "passive": True},
            )
            response.raise_for_status()

    def generate_crl(self, lab_id: UUID) -> Path:
        raise NotImplementedError(
            "step-ca CRL export is not wired in this adapter. Use CA_ADAPTER=openssl "
            "for lab CRL demos, or fetch the CRL from your step-ca instance."
        )


def _run_openssl(args: list[str]) -> None:
    import subprocess

    subprocess.run(["openssl", *args], check=True, capture_output=True)


def _subject_from_pem(pem: str) -> str | None:
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=True) as handle:
        handle.write(pem)
        handle.flush()
        try:
            out = subprocess.check_output(
                ["openssl", "x509", "-in", handle.name, "-noout", "-subject"],
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
    value = out.strip()
    if "=" in value:
        value = value.split("=", 1)[1].strip()
    return value or None


def _serial_from_pem(pem: str) -> str | None:
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=True) as handle:
        handle.write(pem)
        handle.flush()
        try:
            out = subprocess.check_output(
                ["openssl", "x509", "-in", handle.name, "-noout", "-serial"],
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
    return out.strip().split("=")[-1]


def _serial_from_file(path: Path) -> str:
    import subprocess

    out = subprocess.check_output(
        ["openssl", "x509", "-in", str(path), "-noout", "-serial"],
        text=True,
    )
    return out.strip().split("=")[-1]
