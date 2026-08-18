from app.services.guest import _split_display_name, next_guest_username


def test_next_guest_username_starts_at_0001() -> None:
    assert next_guest_username(set()) == "guest0001"


def test_next_guest_username_skips_taken() -> None:
    assert next_guest_username({"guest0001", "guest0002", "alice"}) == "guest0003"


def test_next_guest_username_exhausted() -> None:
    taken = {f"guest{i:04d}" for i in range(1, 10_000)}
    try:
        next_guest_username(taken)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "taken" in str(exc)


def test_split_display_name_empty() -> None:
    assert _split_display_name(None) == (None, None)
    assert _split_display_name("  ") == (None, None)


def test_split_display_name_one_and_two_parts() -> None:
    assert _split_display_name("Ada") == ("Ada", None)
    assert _split_display_name("Ada Lovelace") == ("Ada", "Lovelace")
    assert _split_display_name("Ada King Lovelace") == ("Ada", "King Lovelace")
