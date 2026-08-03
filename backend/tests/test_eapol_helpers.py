import pytest

from app.integrations.freeradius.eapol import (
    _infer_failure,
    _redact_secrets,
    _trim_output,
    resolve_radius_host,
)


class TestResolveRadiusHost:
    def test_numeric_ipv4_passthrough(self) -> None:
        assert resolve_radius_host("10.1.2.3") == "10.1.2.3"

    def test_localhost_resolves_to_ipv4(self) -> None:
        assert resolve_radius_host("localhost") == "127.0.0.1"

    @pytest.mark.parametrize("host", ["", "   "])
    def test_empty_host_rejected(self, host: str) -> None:
        with pytest.raises(ValueError):
            resolve_radius_host(host)


class TestRedactSecrets:
    def test_password_hexdump_removed(self) -> None:
        output = "\n".join(
            [
                "EAP: status",
                "password - hexdump_ascii(len=11):",
                "     53 33 63 75 72 65 21 70 61 73 73   S3cure!pass",
                "     00 00                                          ..",
                "CTRL-EVENT-EAP-SUCCESS",
            ]
        )
        redacted = _redact_secrets(output)
        assert "S3cure!pass" not in redacted
        assert "53 33" not in redacted
        assert "[REDACTED]" in redacted
        assert "CTRL-EVENT-EAP-SUCCESS" in redacted

    def test_normal_output_untouched(self) -> None:
        output = "line one\nline two"
        assert _redact_secrets(output) == output


def test_trim_output_keeps_head_and_tail() -> None:
    text = "HEAD " + ("x" * 10000) + " TAIL"
    trimmed = _trim_output(text, limit=1000)
    assert len(trimmed) < len(text)
    assert trimmed.startswith("HEAD")
    assert trimmed.endswith("TAIL")
    assert "…" in trimmed


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("MSCHAPV2: password failed", "MSCHAPv2 password rejected"),
        ("TLS: certificate unknown ca", "TLS certificate not trusted"),
        ("certificate has expired", "Certificate expired"),
        ("received Access-Reject", "RADIUS Access-Reject"),
        ("EAPOL test timed out", "RADIUS timeout"),
        ("no radius response received", "No RADIUS response"),
        ("all good", None),
    ],
)
def test_infer_failure(output: str, expected: str | None) -> None:
    assert _infer_failure(output) == expected
