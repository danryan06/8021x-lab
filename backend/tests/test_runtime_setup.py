from pathlib import Path

import pytest

from app import runtime_setup


def test_backend_root_contains_alembic_ini() -> None:
    assert (runtime_setup.BACKEND_ROOT / "alembic.ini").is_file()
    assert (runtime_setup.BACKEND_ROOT / "alembic").is_dir()


def test_apply_schema_upgrades_to_head(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_upgrade(cfg, revision: str) -> None:
        seen["ini"] = cfg.config_file_name
        seen["script"] = cfg.get_main_option("script_location")
        seen["revision"] = revision

    monkeypatch.setattr("alembic.command.upgrade", fake_upgrade)
    runtime_setup.apply_schema()
    assert seen["revision"] == "head"
    assert Path(seen["ini"]).name == "alembic.ini"
    assert Path(seen["script"]).name == "alembic"


def test_prepare_database_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky() -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("db starting")

    monkeypatch.setattr(runtime_setup, "apply_schema", flaky)
    runtime_setup.prepare_database(retries=5, delay_seconds=0)
    assert calls["n"] == 3


def test_prepare_database_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fail() -> None:
        raise ConnectionError("down")

    monkeypatch.setattr(runtime_setup, "apply_schema", always_fail)
    with pytest.raises(RuntimeError, match="failed after"):
        runtime_setup.prepare_database(retries=2, delay_seconds=0)


def test_main_skips_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKIP_SCHEMA_SETUP", "1")
    called = {"prepare": False}

    def boom() -> None:
        called["prepare"] = True
        raise AssertionError("should not run")

    monkeypatch.setattr(runtime_setup, "prepare_database", boom)
    runtime_setup.main()
    assert called["prepare"] is False
