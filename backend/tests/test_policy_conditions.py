import pytest

from app.integrations.freeradius.policy_conditions import (
    parse_policy_conditions,
    render_check_items,
    summarize_conditions,
    validate_login_time,
    validate_nas_ip,
)


class TestValidateLoginTime:
    def test_empty_is_unrestricted(self) -> None:
        assert validate_login_time(None) is None
        assert validate_login_time("  ") is None

    def test_weekdays_window(self) -> None:
        assert validate_login_time("wk0800-1700") == "Wk0800-1700"

    def test_weekend_range(self) -> None:
        assert validate_login_time("sa-su") == "Sa-Su"

    def test_overnight_wraps_midnight(self) -> None:
        assert validate_login_time("Al1800-0800") == "Al1800-0800"

    def test_rejects_unknown_tokens(self) -> None:
        with pytest.raises(ValueError, match="Login-Time"):
            validate_login_time("Never")

    def test_rejects_impossible_hours(self) -> None:
        with pytest.raises(ValueError, match="hours"):
            validate_login_time("Wk2500-1700")


class TestValidateNasIp:
    def test_empty_is_any_nas(self) -> None:
        assert validate_nas_ip("") is None

    def test_normalizes_ipv4(self) -> None:
        assert validate_nas_ip(" 10.0.0.1 ") == "10.0.0.1"

    def test_rejects_hostnames(self) -> None:
        with pytest.raises(ValueError, match="nas_ip"):
            validate_nas_ip("switch.lab")


class TestRenderCheckItems:
    def test_unrestricted_policy_has_no_checks(self) -> None:
        assert render_check_items({}) == []
        assert render_check_items(None) == []

    def test_login_time_and_nas_become_check_items(self) -> None:
        items = render_check_items({"login_time": "Wk0800-1700", "nas_ip": "10.0.0.1"})
        assert [(i.name, i.op, i.value) for i in items] == [
            ("Login-Time", "==", "Wk0800-1700"),
            ("NAS-IP-Address", "==", "10.0.0.1"),
        ]

    def test_summary_is_human_first(self) -> None:
        assert summarize_conditions({"login_time": "Wk0800-1700", "nas_ip": "10.0.0.1"}) == (
            "time Wk0800-1700 · NAS 10.0.0.1"
        )

    def test_invalid_payload_is_a_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_policy_conditions({"login_time": "nope"})
