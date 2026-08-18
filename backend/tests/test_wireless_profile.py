from uuid import uuid4

import pytest

from app.models.entities import Lab
from app.schemas.entities import WirelessProfile
from app.services.labs import find_name_conflict
from app.services.wireless import (
    SETTINGS_KEY,
    merge_profile,
    normalize_settings,
    parse_profile,
    read_profile,
)
from app.validation import normalize_ssid


class TestNormalizeSsid:
    @pytest.mark.parametrize(
        "value",
        ["Lab-Corp", "Guest WiFi", "802.1X Lab", "eduroam", "x" * 32],
    )
    def test_accepts_ssids_a_radio_can_advertise(self, value: str) -> None:
        assert normalize_ssid(value) == value

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert normalize_ssid("  Lab-Corp  ") == "Lab-Corp"

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_requires_an_ssid(self, value: str | None) -> None:
        with pytest.raises(ValueError, match="required"):
            normalize_ssid(value)

    def test_rejects_more_than_32_characters(self) -> None:
        with pytest.raises(ValueError, match="32"):
            normalize_ssid("x" * 33)

    def test_limit_counts_bytes_not_characters(self) -> None:
        # 17 two-byte characters are 34 octets, so the SSID does not fit even
        # though it is shorter than 32 characters.
        with pytest.raises(ValueError, match="34 bytes"):
            normalize_ssid("é" * 17)

    @pytest.mark.parametrize("value", ["line\nbreak", "tab\there", "null\x00byte"])
    def test_rejects_control_characters(self, value: str) -> None:
        with pytest.raises(ValueError, match="control characters"):
            normalize_ssid(value)


class TestParseProfile:
    def test_defaults_to_wpa2_enterprise_with_no_vlan(self) -> None:
        profile = parse_profile({"ssid": "Lab-Corp"})
        assert profile == WirelessProfile(
            ssid="Lab-Corp", security="wpa2_enterprise", vlan=None, user_group=None
        )

    def test_keeps_a_full_profile(self) -> None:
        profile = parse_profile(
            {
                "ssid": " Lab-Corp ",
                "security": "wpa3_enterprise",
                "vlan": 20,
                "user_group": "staff",
            }
        )
        assert profile.ssid == "Lab-Corp"
        assert profile.security == "wpa3_enterprise"
        assert profile.vlan == 20
        assert profile.user_group == "staff"

    @pytest.mark.parametrize("data", [None, "Lab-Corp", ["Lab-Corp"], 42])
    def test_rejects_anything_that_is_not_an_object(self, data: object) -> None:
        with pytest.raises(ValueError, match="object"):
            parse_profile(data)

    def test_reports_the_field_that_failed(self) -> None:
        with pytest.raises(ValueError, match="ssid"):
            parse_profile({"ssid": ""})

    @pytest.mark.parametrize("vlan", [0, 4095, -1])
    def test_rejects_vlans_outside_the_802_1q_range(self, vlan: int) -> None:
        with pytest.raises(ValueError, match="vlan"):
            parse_profile({"ssid": "Lab-Corp", "vlan": vlan})

    def test_rejects_a_security_mode_the_lab_does_not_configure(self) -> None:
        with pytest.raises(ValueError, match="security"):
            parse_profile({"ssid": "Lab-Corp", "security": "wpa2_psk"})


class TestLabSettings:
    def test_settings_without_a_profile_pass_through_untouched(self) -> None:
        settings = {"wired": True, "wireless": True, "radius_target": {"mode": "auto"}}
        assert normalize_settings(settings) == settings

    def test_none_becomes_an_empty_document(self) -> None:
        assert normalize_settings(None) == {}

    def test_profile_is_normalized_in_place(self) -> None:
        result = normalize_settings({"medium": "wireless", SETTINGS_KEY: {"ssid": " Lab "}})
        assert result["medium"] == "wireless"
        assert result[SETTINGS_KEY] == {
            "ssid": "Lab",
            "security": "wpa2_enterprise",
            "vlan": None,
            "user_group": None,
        }

    def test_an_invalid_profile_is_rejected_before_it_is_stored(self) -> None:
        with pytest.raises(ValueError):
            normalize_settings({SETTINGS_KEY: {"ssid": "x" * 33}})

    def test_the_caller_settings_object_is_not_mutated(self) -> None:
        settings = {SETTINGS_KEY: {"ssid": " Lab "}}
        normalize_settings(settings)
        assert settings[SETTINGS_KEY] == {"ssid": " Lab "}

    def test_merge_keeps_other_settings(self) -> None:
        profile = WirelessProfile(ssid="Lab-Corp", vlan=20)
        merged = merge_profile({"radius_target": {"mode": "manual"}}, profile)
        assert merged["radius_target"] == {"mode": "manual"}
        assert merged[SETTINGS_KEY]["ssid"] == "Lab-Corp"
        assert merged[SETTINGS_KEY]["vlan"] == 20

    def test_merge_replaces_an_earlier_profile(self) -> None:
        first = merge_profile({}, WirelessProfile(ssid="Old-SSID"))
        second = merge_profile(first, WirelessProfile(ssid="New-SSID"))
        assert second[SETTINGS_KEY]["ssid"] == "New-SSID"


class TestFindNameConflict:
    def test_an_existing_name_is_reported(self) -> None:
        lab = Lab(id=uuid4(), name="Wireless lab")
        assert find_name_conflict([lab], "Wireless lab") is lab

    @pytest.mark.parametrize("name", ["  Wireless lab  ", "WIRELESS LAB", "wireless lab"])
    def test_case_and_padding_do_not_make_a_new_name(self, name: str) -> None:
        lab = Lab(id=uuid4(), name="Wireless lab")
        assert find_name_conflict([lab], name) is lab

    def test_a_free_name_has_no_conflict(self) -> None:
        assert find_name_conflict([Lab(id=uuid4(), name="Wireless lab")], "Wired lab") is None

    def test_renaming_a_lab_does_not_conflict_with_itself(self) -> None:
        lab = Lab(id=uuid4(), name="Wireless lab")
        assert find_name_conflict([lab], "Wireless lab", exclude_id=lab.id) is None


class TestReadProfile:
    def test_reads_back_what_was_merged(self) -> None:
        lab = Lab(name="Wireless lab", settings=merge_profile({}, WirelessProfile(ssid="Lab-Corp")))
        assert read_profile(lab).ssid == "Lab-Corp"

    @pytest.mark.parametrize(
        "settings",
        [None, {}, {"wired": True}, {SETTINGS_KEY: None}],
    )
    def test_a_lab_without_a_profile_reads_as_none(self, settings: dict | None) -> None:
        assert read_profile(Lab(name="Wired lab", settings=settings)) is None

    def test_a_profile_stored_before_a_rule_existed_does_not_break_the_lab(self) -> None:
        lab = Lab(name="Old lab", settings={SETTINGS_KEY: {"ssid": "x" * 40}})
        assert read_profile(lab) is None
