import pytest

from app.validation import validate_eapol_config_value, validate_identity


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
