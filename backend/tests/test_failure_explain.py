import pytest

from app.integrations.freeradius.failure_explain import explain_failure
from app.integrations.freeradius.mab import DISABLED_ENDPOINT_REASON, UNKNOWN_MAC_REASON
from app.models.entities import AuthMethod, AuthResult
from app.workers.auth_log_ingestion import _is_unattributed_reject


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
        (UNKNOWN_MAC_REASON, "not registered for MAB"),
        (DISABLED_ENDPOINT_REASON, "disabled"),
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


def test_generic_mab_reject_points_at_the_endpoint_list() -> None:
    explanation = explain_failure("Authentication failed", AuthMethod.mab, AuthResult.failure)
    assert explanation is not None
    assert "MAB" in explanation.summary
    assert "endpoint" in explanation.hint.lower()


def test_unrecognized_reason_is_surfaced() -> None:
    explanation = explain_failure("something weird happened", AuthMethod.unknown, AuthResult.failure)
    assert explanation is not None
    assert "something weird happened" in explanation.summary


class TestIsUnattributedReject:
    @pytest.mark.parametrize(
        "reason",
        [
            None,
            "",
            "   ",
            "Authentication failed",
            # What FreeRADIUS actually logs when nothing matched the MAC.
            "No Auth-Type found: rejecting the user via Post-Auth-Type = Reject",
        ],
    )
    def test_rejects_without_a_failing_module_are_unattributed(self, reason) -> None:
        assert _is_unattributed_reject(reason) is True

    @pytest.mark.parametrize(
        "reason",
        [
            "mschap: MS-CHAP2-Response is incorrect",
            "TLS Alert: unknown CA",
            "certificate revoked by CRL",
        ],
    )
    def test_real_module_failures_are_kept(self, reason: str) -> None:
        assert _is_unattributed_reject(reason) is False
