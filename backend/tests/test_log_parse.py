from datetime import UTC, datetime

import pytest

from app.integrations.freeradius.log_parse import _map_method, parse_linelog_line
from app.models.entities import AuthMethod, AuthResult


class TestParseLinelogLine:
    def test_accept_line(self) -> None:
        line = "DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Accept|"
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.identity == "alice"
        assert parsed.nas_ip == "10.0.0.10"
        assert parsed.method is AuthMethod.peap
        assert parsed.result is AuthResult.success
        assert parsed.failure_reason is None
        assert parsed.timestamp == datetime.fromtimestamp(1754226000, tz=UTC)

    def test_reject_line_carries_failure_reason(self) -> None:
        line = "DOT1X|1754226000|bob|10.0.0.10|MSCHAPv2|Access-Reject|mschap: FAILED"
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.result is AuthResult.failure
        assert parsed.failure_reason == "mschap: FAILED"

    def test_reject_line_without_reason_gets_default(self) -> None:
        parsed = parse_linelog_line("DOT1X|1754226000|bob|10.0.0.10|PEAP|Access-Reject|")
        assert parsed is not None
        assert parsed.failure_reason == "Authentication failed"

    def test_iso_timestamp_accepted(self) -> None:
        parsed = parse_linelog_line("DOT1X|2026-08-03 12:00:00|c|1.2.3.4|TLS|Access-Accept|")
        assert parsed is not None
        assert parsed.timestamp == datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "random noise",
            "NOT-DOT1X|1|a|b|c|d|e",
            "DOT1X|too|few|fields",
        ],
    )
    def test_non_matching_lines_return_none(self, line: str) -> None:
        assert parse_linelog_line(line) is None


class TestMapMethod:
    @pytest.mark.parametrize(
        ("eap_type", "expected"),
        [
            ("PEAP", AuthMethod.peap),
            ("MSCHAPv2", AuthMethod.peap),
            ("25", AuthMethod.peap),
            ("26", AuthMethod.peap),
            ("TLS", AuthMethod.eap_tls),
            ("EAP-TLS", AuthMethod.eap_tls),
            ("13", AuthMethod.eap_tls),
            ("mab", AuthMethod.mab),
            ("", AuthMethod.unknown),
            ("GTC", AuthMethod.unknown),
        ],
    )
    def test_mapping(self, eap_type: str, expected: AuthMethod) -> None:
        assert _map_method(eap_type) is expected
