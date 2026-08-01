"""Local openssl-based CA adapter for lab use."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.integrations.ca.base import CaInfo, IssuedCert

settings = get_settings()


class OpenSslLocalCaAdapter:
    def _lab_dir(self, lab_id: UUID) -> Path:
        path = Path(settings.ca_data_dir) / str(lab_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "certs").mkdir(exist_ok=True)
        (path / "private").mkdir(exist_ok=True)
        return path

    def root_cert_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "certs" / "root.crt"

    def root_key_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "private" / "root.key"

    def client_cert_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{identity}.crt"

    def client_key_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "private" / f"{identity}.key"

    def client_p12_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{identity}.p12"

    def ensure_root(self, lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> CaInfo:
        lab_dir = self._lab_dir(lab_id)
        key_path = lab_dir / "private" / "root.key"
        cert_path = lab_dir / "certs" / "root.crt"
        subject = f"/CN={common_name}"

        if not cert_path.exists():
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(key_path),
                    "-out",
                    str(cert_path),
                    "-days",
                    "3650",
                    "-subj",
                    subject,
                ],
                check=True,
                capture_output=True,
            )

        return CaInfo(
            name=common_name,
            subject=subject,
            storage_ref=str(cert_path),
            not_before=datetime.now(UTC),
            not_after=datetime.now(UTC) + timedelta(days=3650),
        )

    def issue_client_cert(self, lab_id: UUID, identity: str, days: int = 365) -> IssuedCert:
        self.ensure_root(lab_id)
        lab_dir = self._lab_dir(lab_id)
        key_path = lab_dir / "private" / f"{identity}.key"
        csr_path = lab_dir / "certs" / f"{identity}.csr"
        cert_path = lab_dir / "certs" / f"{identity}.crt"
        root_key = lab_dir / "private" / "root.key"
        root_cert = lab_dir / "certs" / "root.crt"
        subject = f"/CN={identity}"

        subprocess.run(
            [
                "openssl",
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
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(csr_path),
                "-CA",
                str(root_cert),
                "-CAkey",
                str(root_key),
                "-CAcreateserial",
                "-out",
                str(cert_path),
                "-days",
                str(days),
            ],
            check=True,
            capture_output=True,
        )

        # Lab-friendly PKCS#12 (empty passphrase) for Windows/macOS import demos.
        p12_path = lab_dir / "certs" / f"{identity}.p12"
        subprocess.run(
            [
                "openssl",
                "pkcs12",
                "-export",
                "-inkey",
                str(key_path),
                "-in",
                str(cert_path),
                "-certfile",
                str(root_cert),
                "-out",
                str(p12_path),
                "-passout",
                "pass:",
            ],
            check=True,
            capture_output=True,
        )

        serial = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_path), "-noout", "-serial"],
            text=True,
        ).strip().split("=")[-1]

        pem = cert_path.read_text(encoding="utf-8")
        now = datetime.now(UTC)
        return IssuedCert(
            subject=subject,
            issuer="/CN=802.1X Lab Root CA",
            serial=serial,
            storage_ref=str(cert_path),
            not_before=now,
            not_after=now + timedelta(days=days),
            cert_pem=pem,
        )

    def revoke(self, serial: str) -> None:
        # Phase 2+: maintain a CRL. Lab records intent only.
        _ = serial
        return None
