import pytest

from app.integrations.freeradius.failure_explain import explain_failure
from app.models.entities import AuthMethod, AuthResult


def test_success_returns_none() -> None:
    assert explain_failure(None, AuthMethod.peap, AuthResult.success) is None
    assert explain_failure("whatever", AuthMethod.peap, AuthResult.success) is None


@pytest.mark.parametrize(
    ("reason", "expected_summary_fragment"),
    [
        ("TLS Alert: unknown CA", "untrusted CA"),
        ("certificate has expired", "expired"),
        ("certificate revoked by CRL", "revoked"),
        ("mschap: MS-CHAP2-Response is incorrect", "MSCHAPv2"),
        ("rlm_sql: no such user / password", "Password"),
        ("Login incorrect: [alice] unknown user", "No matching user"),
    ],
)
def test_known_reasons_map_to_summary(reason: str, expected_summary_fragment: str) -> None:
    explanation = explain_failure(reason, AuthMethod.eap_tls, AuthResult.failure)
    assert explanation is not None
    assert expected_summary_fragment.lower() in explanation.summary.lower()
    assert explanation.hint


def test_generic_reject_uses_method_hint() -> None:
    eap = explain_failure("Authentication failed", AuthMethod.eap_tls, AuthResult.failure)
    peap = explain_failure(None, AuthMethod.peap, AuthResult.failure)
    assert eap is not None and "EAP-TLS" in eap.summary
    assert peap is not None and "PEAP" in peap.summary


def test_unrecognized_reason_is_surfaced() -> None:
    explanation = explain_failure("something weird happened", AuthMethod.unknown, AuthResult.failure)
    assert explanation is not None
    assert "something weird happened" in explanation.summary
