import string

from app.services.users import _build_username, _generate_password, users_csv_template


class TestGeneratePassword:
    def test_easy_style_is_word_plus_three_digits(self) -> None:
        for _ in range(20):
            password = _generate_password("easy", length=12)
            digits = password[-3:]
            word = password[: -3]
            assert digits.isdigit()
            assert word.isalpha()

    def test_random_style_respects_length_and_charset(self) -> None:
        password = _generate_password("random", length=16)
        assert len(password) == 16
        allowed = set(string.ascii_letters + string.digits)
        assert set(password) <= allowed


class TestBuildUsername:
    def test_first_last(self) -> None:
        assert _build_username("first_last", "user", 3, "Ada", "Lovelace") == "ada.lovelace3"

    def test_flast(self) -> None:
        assert _build_username("flast", "user", 7, "Grace", "Hopper") == "ghopper7"

    def test_emailish(self) -> None:
        assert _build_username("emailish", "user", 1, "Alan", "Turing") == "alan.turing1@lab.local"

    def test_prefix_default(self) -> None:
        assert _build_username("prefix", "labuser", 4, None, None) == "labuser004"

    def test_names_are_slugged(self) -> None:
        assert _build_username("first_last", "user", 1, "Mary Jane", "O'Neil") == "maryjane.oneil1"


def test_csv_template_has_expected_header() -> None:
    header = users_csv_template().splitlines()[0]
    assert header.startswith("username,")
    for column in ("password", "first_name", "last_name", "department"):
        assert column in header
