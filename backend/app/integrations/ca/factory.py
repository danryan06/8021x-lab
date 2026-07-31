from app.config import get_settings
from app.integrations.ca.base import CertificateAuthorityAdapter
from app.integrations.ca.openssl_adapter import OpenSslLocalCaAdapter
from app.integrations.ca.step_ca import StepCaAdapter


def get_ca_adapter() -> CertificateAuthorityAdapter:
    adapter = get_settings().ca_adapter.lower()
    if adapter == "step-ca" or adapter == "stepca":
        return StepCaAdapter()
    return OpenSslLocalCaAdapter()
