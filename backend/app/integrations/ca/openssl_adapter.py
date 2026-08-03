"""Local openssl-based CA adapter for lab use.

Issuance goes through ``openssl ca`` (not ``x509 -req``) so every certificate is
tracked in a per-lab CA database (``index.txt`` + ``newcerts/``). That database
is what makes real revocation and CRL generation possible.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.integrations.ca.base import CaInfo, IssuedCert
from app.validation import validate_identity

settings = get_settings()


class OpenSslLocalCaAdapter:
    def _lab_dir(self, lab_id: UUID) -> Path:
        path = Path(settings.ca_data_dir) / str(lab_id)
        path.mkdir(parents=True, exist_ok=True)
        (path / "certs").mkdir(exist_ok=True)
        (path / "private").mkdir(exist_ok=True)
        (path / "db" / "newcerts").mkdir(parents=True, exist_ok=True)
        return path

    def root_cert_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "certs" / "root.crt"

    def root_key_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "private" / "root.key"

    def client_cert_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{validate_identity(identity)}.crt"

    def client_key_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "private" / f"{validate_identity(identity)}.key"

    def client_p12_path(self, lab_id: UUID, identity: str) -> Path:
        return self._lab_dir(lab_id) / "certs" / f"{validate_identity(identity)}.p12"

    def crl_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "crl.pem"

    def _openssl_cnf_path(self, lab_id: UUID) -> Path:
        return self._lab_dir(lab_id) / "openssl.cnf"

    def _write_ca_config(self, lab_id: UUID) -> Path:
        """(Re)create the CA database scaffolding and openssl.cnf for this lab."""
        lab_dir = self._lab_dir(lab_id)
        db_dir = lab_dir / "db"
        index = db_dir / "index.txt"
        if not index.exists():
            index.touch()
        # unique_subject=no lets us re-issue for the same identity (the download
        # and auth-test flows re-issue on demand).
        (db_dir / "index.txt.attr").write_text("unique_subject = no\n", encoding="utf-8")
        serial = db_dir / "serial"
        if not serial.exists():
            serial.write_text("1000\n", encoding="utf-8")
        crlnumber = db_dir / "crlnumber"
        if not crlnumber.exists():
            crlnumber.write_text("1000\n", encoding="utf-8")

        cnf = lab_dir / "openssl.cnf"
        cnf.write_text(_OPENSSL_CNF_TEMPLATE.format(dir=lab_dir), encoding="utf-8")
        return cnf

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
        # Ensure the CA database exists even for labs created before this change.
        self._write_ca_config(lab_id)

        return CaInfo(
            name=common_name,
            subject=_read_subject(cert_path) or subject,
            storage_ref=str(cert_path),
            not_before=datetime.now(UTC),
            not_after=datetime.now(UTC) + timedelta(days=3650),
        )

    def issue_client_cert(self, lab_id: UUID, identity: str, days: int = 365) -> IssuedCert:
        validate_identity(identity)
        self.ensure_root(lab_id)
        lab_dir = self._lab_dir(lab_id)
        key_path = lab_dir / "private" / f"{identity}.key"
        csr_path = lab_dir / "certs" / f"{identity}.csr"
        cert_path = lab_dir / "certs" / f"{identity}.crt"
        root_cert = lab_dir / "certs" / "root.crt"
        cnf = self._openssl_cnf_path(lab_id)
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
        # Sign via `openssl ca` so the cert is recorded in the CA database and
        # can later be revoked / listed in the CRL.
        subprocess.run(
            [
                "openssl",
                "ca",
                "-batch",
                "-config",
                str(cnf),
                "-in",
                str(csr_path),
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

        serial = _read_serial(cert_path)
        pem = cert_path.read_text(encoding="utf-8")
        not_before, not_after = _read_validity(cert_path)
        now = datetime.now(UTC)
        return IssuedCert(
            subject=subject,
            issuer=_read_subject(root_cert) or "/CN=802.1X Lab Root CA",
            serial=serial,
            storage_ref=str(cert_path),
            not_before=not_before or now,
            not_after=not_after or (now + timedelta(days=days)),
            cert_pem=pem,
        )

    def revoke(self, lab_id: UUID, cert_ref: str) -> None:
        """Revoke an issued certificate (by its on-disk path) and refresh the CRL."""
        cert_path = Path(cert_ref)
        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate not found for revocation: {cert_path}")
        cnf = self._openssl_cnf_path(lab_id)
        if not cnf.exists():
            self._write_ca_config(lab_id)
        subprocess.run(
            ["openssl", "ca", "-config", str(cnf), "-revoke", str(cert_path)],
            check=True,
            capture_output=True,
        )
        self.generate_crl(lab_id)

    def generate_crl(self, lab_id: UUID) -> Path:
        """(Re)generate the CRL for this lab from its CA database."""
        cnf = self._openssl_cnf_path(lab_id)
        if not cnf.exists():
            self._write_ca_config(lab_id)
        crl_path = self.crl_path(lab_id)
        subprocess.run(
            ["openssl", "ca", "-config", str(cnf), "-gencrl", "-out", str(crl_path)],
            check=True,
            capture_output=True,
        )
        return crl_path


def _read_serial(cert_path: Path) -> str:
    out = subprocess.check_output(
        ["openssl", "x509", "-in", str(cert_path), "-noout", "-serial"], text=True
    )
    return out.strip().split("=")[-1]


def _read_subject(cert_path: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_path), "-noout", "-subject"], text=True
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    value = out.strip()
    # openssl may print "subject=CN = X" (3.x) or "subject= /CN=X" (1.x).
    if "=" in value:
        value = value.split("=", 1)[1].strip()
    return value or None


def _read_validity(cert_path: Path) -> tuple[datetime | None, datetime | None]:
    try:
        out = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_path), "-noout", "-dates"], text=True
        )
    except (subprocess.CalledProcessError, OSError):
        return None, None
    not_before = not_after = None
    for line in out.splitlines():
        key, _, raw = line.partition("=")
        parsed = _parse_openssl_date(raw.strip())
        if key == "notBefore":
            not_before = parsed
        elif key == "notAfter":
            not_after = parsed
    return not_before, not_after


def _parse_openssl_date(value: str) -> datetime | None:
    # e.g. "Aug  3 12:00:00 2026 GMT"
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


_OPENSSL_CNF_TEMPLATE = """\
[ ca ]
default_ca = CA_default

[ CA_default ]
dir               = {dir}
database          = {dir}/db/index.txt
new_certs_dir     = {dir}/db/newcerts
serial            = {dir}/db/serial
crlnumber         = {dir}/db/crlnumber
certificate       = {dir}/certs/root.crt
private_key       = {dir}/private/root.key
default_md        = sha256
default_days      = 365
default_crl_days  = 30
policy            = policy_any
unique_subject    = no
x509_extensions   = client_ext

[ policy_any ]
commonName              = supplied
countryName             = optional
stateOrProvinceName     = optional
organizationName        = optional
organizationalUnitName  = optional
emailAddress            = optional

[ client_ext ]
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
"""
