"""step-ca adapter stub — implemented in Phase 2."""

from __future__ import annotations

from uuid import UUID

from app.integrations.ca.base import CaInfo, IssuedCert


class StepCaAdapter:
    """Placeholder for Smallstep step-ca integration.

    Future work: provision a root/intermediate via the step-ca API,
    issue short-lived client certs for EAP-TLS, and sync trust material
    into FreeRADIUS.
    """

    def ensure_root(self, lab_id: UUID, common_name: str = "802.1X Lab Root CA") -> CaInfo:
        raise NotImplementedError(
            "StepCaAdapter is not implemented yet. Use CA_ADAPTER=openssl for Phase 0/1."
        )

    def issue_client_cert(self, lab_id: UUID, identity: str, days: int = 365) -> IssuedCert:
        raise NotImplementedError(
            "StepCaAdapter is not implemented yet. Use CA_ADAPTER=openssl for Phase 0/1."
        )

    def revoke(self, serial: str) -> None:
        raise NotImplementedError(
            "StepCaAdapter is not implemented yet. Use CA_ADAPTER=openssl for Phase 0/1."
        )
