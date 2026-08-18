from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass
class CaInfo:
    name: str
    subject: str
    storage_ref: str
    not_before: datetime | None = None
    not_after: datetime | None = None


@dataclass
class IssuedCert:
    subject: str
    issuer: str
    serial: str
    storage_ref: str
    not_before: datetime
    not_after: datetime
    cert_pem: str | None = None


class CertificateAuthorityAdapter(Protocol):
    def ensure_root(self, lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> CaInfo: ...

    def issue_client_cert(self, lab_id: UUID, identity: str, days: int = 365) -> IssuedCert: ...

    def revoke(self, lab_id: UUID, cert_ref: str) -> None: ...

    def generate_crl(self, lab_id: UUID) -> Path: ...

    def ensure_intermediate(
        self, lab_id: UUID, common_name: str = "802.1X Lab Intermediate CA"
    ) -> CaInfo: ...
