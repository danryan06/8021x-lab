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
        assert parsed.raw == line

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

    def test_pre_phase3_lines_still_parse_without_attributes(self) -> None:
        parsed = parse_linelog_line("DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Accept|")
        assert parsed is not None
        assert parsed.returned_attributes == {}


class TestParseMabLines:
    MAB_ACCEPT = (
        "DOT1X|1754226000|aa:bb:cc:dd:ee:ff|172.18.0.4||Access-Accept||Call-Check|"
        'Tunnel-Type = VLAN, Tunnel-Medium-Type = IEEE-802, '
        'Tunnel-Private-Group-Id = "40", Filter-Id = "printer-acl"'
    )

    def test_call_check_without_eap_type_is_mab(self) -> None:
        parsed = parse_linelog_line(self.MAB_ACCEPT)
        assert parsed is not None
        assert parsed.method is AuthMethod.mab
        assert parsed.identity == "aa:bb:cc:dd:ee:ff"
        assert parsed.result is AuthResult.success

    def test_returned_attributes_are_parsed(self) -> None:
        parsed = parse_linelog_line(self.MAB_ACCEPT)
        assert parsed is not None
        assert parsed.returned_attributes == {
            "Tunnel-Type": "VLAN",
            "Tunnel-Medium-Type": "IEEE-802",
            "Tunnel-Private-Group-Id": "40",
            "Filter-Id": "printer-acl",
        }

    def test_mab_reject_keeps_method_and_failure(self) -> None:
        line = "DOT1X|1754226000|de:ad:be:ef:00:01|172.18.0.4||Access-Reject||Call-Check|"
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.method is AuthMethod.mab
        assert parsed.result is AuthResult.failure
        assert parsed.failure_reason == "Authentication failed"

    def test_reject_records_no_attributes_even_when_the_reply_list_has_some(self) -> None:
        """A group lookup can stage attributes before auth fails; they were never sent."""
        line = (
            "DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Reject|mschap: FAILED||"
            'Tunnel-Type = VLAN, Tunnel-Private-Group-Id = "20"'
        )
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.result is AuthResult.failure
        assert parsed.returned_attributes == {}

    def test_eap_type_wins_over_service_type(self) -> None:
        """A PEAP request that also carries Service-Type must not be logged as MAB."""
        line = "DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Accept||Framed-User|"
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.method is AuthMethod.peap

    def test_pipe_inside_an_attribute_value_does_not_truncate_the_list(self) -> None:
        line = (
            "DOT1X|1754226000|aa:bb:cc:dd:ee:ff|172.18.0.4||Access-Accept||Call-Check|"
            'Reply-Message = "a|b", Filter-Id = "r"'
        )
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.returned_attributes == {"Reply-Message": "a|b", "Filter-Id": "r"}

    def test_key_material_is_never_stored_on_the_event(self) -> None:
        line = (
            "DOT1X|1754226000|alice|10.0.0.10|PEAP|Access-Accept|||"
            "MS-MPPE-Recv-Key = 0xdeadbeef, Filter-Id = \"corp\""
        )
        parsed = parse_linelog_line(line)
        assert parsed is not None
        assert parsed.returned_attributes == {"Filter-Id": "corp"}


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

    @pytest.mark.parametrize(
        ("service_type", "expected"),
        [
            ("Call-Check", AuthMethod.mab),
            ("call-check", AuthMethod.mab),
            ("Framed-User", AuthMethod.unknown),
            ("", AuthMethod.unknown),
        ],
    )
    def test_service_type_identifies_mab_when_there_is_no_eap(
        self, service_type: str, expected: AuthMethod
    ) -> None:
        assert _map_method("", service_type) is expected
