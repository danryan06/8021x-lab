from app.security import hash_password, nt_hash_password, verify_password


def test_nt_hash_known_vector() -> None:
    # Canonical MD4(UTF-16LE("password")) test vector.
    assert nt_hash_password("password") == "0x8846F7EAEE8FB117AD06BDD830B7586C"


def test_nt_hash_format() -> None:
    value = nt_hash_password("S3cure!pass")
    assert value.startswith("0x")
    assert len(value) == 34  # 0x + 32 hex chars
    assert value[2:] == value[2:].upper()


def test_bcrypt_round_trip() -> None:
    hashed = hash_password("lab-password")
    assert hashed != "lab-password"
    assert verify_password("lab-password", hashed)
    assert not verify_password("wrong", hashed)
