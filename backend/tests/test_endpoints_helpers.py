import pytest

from app.services.endpoints import (
    DEVICE_TYPES,
    choose_device_type,
    parse_mac_list,
    random_mac,
)
from app.validation import normalize_mac


class TestParseMacList:
    def test_accepts_every_supported_format_in_one_paste(self) -> None:
        macs, errors = parse_mac_list(
            "aa:bb:cc:dd:ee:ff\n11-22-33-44-55-66\n1122.3344.5567\nAABBCCDDEE01"
        )
        assert errors == []
        assert macs == [
            "aa:bb:cc:dd:ee:ff",
            "11:22:33:44:55:66",
            "11:22:33:44:55:67",
            "aa:bb:cc:dd:ee:01",
        ]

    @pytest.mark.parametrize("separator", ["\n", ", ", ";", " ", "\r\n", "\t"])
    def test_entries_may_be_separated_any_way_an_export_does_it(self, separator: str) -> None:
        macs, errors = parse_mac_list(separator.join(["aabbccddeeff", "112233445566"]))
        assert errors == []
        assert macs == ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]

    def test_duplicates_within_one_paste_collapse(self) -> None:
        macs, errors = parse_mac_list("aa:bb:cc:dd:ee:ff\nAABBCCDDEEFF\naabb.ccdd.eeff")
        assert macs == ["aa:bb:cc:dd:ee:ff"]
        assert errors == []

    def test_bad_entries_are_reported_without_losing_the_good_ones(self) -> None:
        macs, errors = parse_mac_list("aabbccddeeff\nnope\n112233445566\nzz:zz:zz:zz:zz:zz")
        assert macs == ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]
        assert len(errors) == 2

    @pytest.mark.parametrize("text", ["", "   ", "\n\n", None])
    def test_empty_input_is_not_an_error(self, text) -> None:
        assert parse_mac_list(text) == ([], [])


class TestRandomMac:
    def test_default_oui_is_used(self) -> None:
        assert random_mac().startswith("02:1a:2b:")

    def test_generated_mac_is_canonical(self) -> None:
        mac = random_mac()
        assert normalize_mac(mac) == mac

    @pytest.mark.parametrize("oui", ["02:1a:2b", "021a2b", "02-1a-2b", "021A2B"])
    def test_prefix_is_accepted_in_any_format(self, oui: str) -> None:
        assert random_mac(oui).startswith("02:1a:2b:")

    def test_shorter_and_longer_prefixes_are_honoured(self) -> None:
        assert random_mac("02").startswith("02:")
        assert random_mac("02:1a:2b:3c:4d").startswith("02:1a:2b:3c:4d:")

    def test_odd_length_prefix_drops_the_half_octet(self) -> None:
        assert random_mac("021a2").startswith("02:1a:")

    @pytest.mark.parametrize("oui", ["", "   ", None])
    def test_blank_prefix_falls_back_to_the_default(self, oui) -> None:
        assert random_mac(oui).startswith("02:1a:2b:")

    def test_prefix_longer_than_a_mac_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="longer than a MAC"):
            random_mac("00:11:22:33:44:55:66")

    def test_generates_distinct_addresses(self) -> None:
        assert len({random_mac() for _ in range(50)}) > 40


def test_device_types_are_devices_that_cannot_do_8021x() -> None:
    assert "printer" in DEVICE_TYPES
    assert all(t == t.lower() and " " not in t for t in DEVICE_TYPES)


class TestChooseDeviceType:
    def test_explicit_type_wins_over_the_mixing_default(self) -> None:
        assert choose_device_type("voip-phone", mixed=True) == "voip-phone"

    def test_explicit_type_is_used_when_not_mixing(self) -> None:
        assert choose_device_type("printer", mixed=False) == "printer"

    def test_mixing_picks_from_the_lab_device_list(self) -> None:
        picks = {choose_device_type(None, mixed=True) for _ in range(60)}
        assert picks <= set(DEVICE_TYPES)
        assert len(picks) > 1

    def test_no_type_and_no_mixing_leaves_it_unset(self) -> None:
        assert choose_device_type(None, mixed=False) is None
