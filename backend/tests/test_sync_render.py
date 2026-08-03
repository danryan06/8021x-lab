from uuid import uuid4

from app.integrations.freeradius.sync import render_clients_config
from app.models.entities import RadiusClient


def make_client(**overrides) -> RadiusClient:
    defaults = dict(
        lab_id=uuid4(),
        name="lab-switch-1",
        ip_address="192.168.1.10",
        shared_secret="nas-secret",
        device_type="switch",
        enabled=True,
    )
    defaults.update(overrides)
    return RadiusClient(**defaults)


def test_renders_enabled_client_with_repo_template() -> None:
    rendered = render_clients_config([make_client()])
    assert 'client "lab-switch-1"' in rendered
    assert "ipaddr = 192.168.1.10" in rendered
    assert 'secret = "nas-secret"' in rendered


def test_disabled_clients_are_skipped() -> None:
    rendered = render_clients_config(
        [
            make_client(name="enabled-nas"),
            make_client(name="disabled-nas", enabled=False),
        ]
    )
    assert "enabled-nas" in rendered
    assert "disabled-nas" not in rendered


def test_empty_client_list_renders_no_client_blocks() -> None:
    rendered = render_clients_config([])
    assert 'client "' not in rendered
