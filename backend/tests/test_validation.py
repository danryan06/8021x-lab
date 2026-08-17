import pytest

from app.validation import (
    normalize_mac,
    validate_attribute_name,
    validate_attribute_value,
    validate_eapol_config_value,
    validate_identity,
)


class TestValidateIdentity:
    @pytest.mark.parametrize(
        "identity",
        ["alice", "alice.smith", "a1-b2_c3", "user@lab.local", "A", "0", "x" * 128],
    )
    def test_accepts_normal_identities(self, identity: str) -> None:
        assert validate_identity(identity) == identity

    @pytest.mark.parametrize(
        "identity",
        [
            "../../../etc/passwd",
            "a/b",
            "a\\b",
            "..",
            ".hidden",
            "-leading-dash",
            "_leading-underscore",
            "@lab",
            "",
            "x" * 129,
            "space name",
            'quote"name',
            "new\nline",
        ],
    )
    def test_rejects_unsafe_identities(self, identity: str) -> None:
        with pytest.raises(ValueError):
            validate_identity(identity)


class TestValidateEapolConfigValue:
    @pytest.mark.parametrize("value", ["S3cure!pass", "with spaces ok", "émoji✓", "'single'"])
    def test_accepts_quotable_values(self, value: str) -> None:
        assert validate_eapol_config_value("password", value) == value

    @pytest.mark.parametrize(
        "value",
        ['break"out', "back\\slash", "new\nline", "carriage\rreturn"],
    )
    def test_rejects_config_injection(self, value: str) -> None:
        with pytest.raises(ValueError):
            validate_eapol_config_value("password", value)


class TestNormalizeMac:
    @pytest.mark.parametrize(
        "value",
        [
            "aa:bb:cc:dd:ee:ff",
            "AA:BB:CC:DD:EE:FF",
            "aa-bb-cc-dd-ee-ff",
            "AA-BB-CC-DD-EE-FF",
            "aabb.ccdd.eeff",
            "AABB.CCDD.EEFF",
            "aabbccddeeff",
            "AABBCCDDEEFF",
            "  aa:bb:cc:dd:ee:ff  ",
            "aa:BB-cc.dd:EE-ff",
        ],
    )
    def test_every_accepted_spelling_maps_to_one_canonical_form(self, value: str) -> None:
        assert normalize_mac(value) == "aa:bb:cc:dd:ee:ff"

    def test_result_is_idempotent(self) -> None:
        once = normalize_mac("AABB.CCDD.EEFF")
        assert normalize_mac(once) == once

    def test_zero_mac_is_preserved(self) -> None:
        assert normalize_mac("000000000000") == "00:00:00:00:00:00"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "aa:bb:cc:dd:ee",
            "aa:bb:cc:dd:ee:ff:00",
            "aabbccddeef",
            "aabbccddeeffa",
            "zz:zz:zz:zz:zz:zz",
            "aa:bb:cc:dd:ee:gg",
            "not-a-mac",
            "aa bb cc dd ee ff ff",
        ],
    )
    def test_rejects_values_that_are_not_macs(self, value: str) -> None:
        with pytest.raises(ValueError):
            normalize_mac(value)

    def test_none_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="required"):
            normalize_mac(None)

    def test_error_message_lists_the_accepted_formats(self) -> None:
        with pytest.raises(ValueError, match="aa:bb:cc:dd:ee:ff"):
            normalize_mac("oops")


class TestValidateAttributeName:
    @pytest.mark.parametrize(
        "name",
        ["Filter-Id", "Tunnel-Private-Group-Id", "Cisco-AVPair", "Session-Timeout", "X", "a" * 64],
    )
    def test_accepts_dictionary_names(self, name: str) -> None:
        assert validate_attribute_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "   ",
            "-leading-dash",
            "1leading-digit",
            "with_underscore",
            "with space",
            "with:colon",
            "semi;colon",
            "quote\"name",
            "new\nline",
            "a" * 65,
        ],
    )
    def test_rejects_names_that_are_not_radius_attributes(self, name: str) -> None:
        with pytest.raises(ValueError):
            validate_attribute_name(name)

    def test_none_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_attribute_name(None)


class TestValidateAttributeValue:
    @pytest.mark.parametrize(
        "value",
        ["40", "guest-acl", "device-traffic-class=voice", "with spaces", "", "x" * 253],
    )
    def test_accepts_values_radclient_can_carry(self, value: str) -> None:
        assert validate_attribute_value("Filter-Id", value) == value

    @pytest.mark.parametrize("value", ['quote"injection', "new\nline", "carriage\rreturn"])
    def test_rejects_values_that_would_inject_extra_attributes(self, value: str) -> None:
        with pytest.raises(ValueError, match="double quotes or newlines"):
            validate_attribute_value("Filter-Id", value)

    def test_rejects_values_longer_than_a_radius_attribute(self) -> None:
        with pytest.raises(ValueError, match="253"):
            validate_attribute_value("Reply-Message", "x" * 254)

    def test_error_message_names_the_attribute(self) -> None:
        with pytest.raises(ValueError, match="Cisco-AVPair"):
            validate_attribute_value("Cisco-AVPair", 'bad"value')
