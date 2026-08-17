from uuid import uuid4

from app.integrations.freeradius.sync import render_clients_config
from app.models.entities import RadiusClient
from app.services.clients import find_address_conflict


def make_client(**overrides) -> RadiusClient:
    defaults = dict(
        id=uuid4(),
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


def test_clients_from_several_labs_are_rendered_together() -> None:
    # One FreeRADIUS instance serves every lab, so its clients file must hold
    # all of them — rendering one lab would drop the others' NAS devices.
    rendered = render_clients_config(
        [
            make_client(name="lab-a-switch", ip_address="192.168.1.10"),
            make_client(name="lab-b-wlc", ip_address="192.168.1.11"),
        ]
    )
    assert "lab-a-switch" in rendered
    assert "lab-b-wlc" in rendered


class TestDuplicateAddresses:
    """Two client blocks for one address make FreeRADIUS refuse to start, which
    takes down authentication for every lab — so the render never emits them."""

    def test_only_the_first_client_for_an_address_is_rendered(self) -> None:
        rendered = render_clients_config(
            [
                make_client(name="first-nas", ip_address="10.0.0.1"),
                make_client(name="second-nas", ip_address="10.0.0.1"),
            ]
        )
        assert "first-nas" in rendered
        assert "second-nas" not in rendered
        assert rendered.count("ipaddr = 10.0.0.1") == 1

    def test_addresses_are_compared_without_case_or_padding(self) -> None:
        rendered = render_clients_config(
            [
                make_client(name="first-nas", ip_address="2001:DB8::1"),
                make_client(name="second-nas", ip_address=" 2001:db8::1 "),
            ]
        )
        assert "second-nas" not in rendered

    def test_a_disabled_duplicate_does_not_displace_the_enabled_client(self) -> None:
        rendered = render_clients_config(
            [
                make_client(name="disabled-nas", ip_address="10.0.0.1", enabled=False),
                make_client(name="enabled-nas", ip_address="10.0.0.1"),
            ]
        )
        assert "enabled-nas" in rendered
        assert "disabled-nas" not in rendered


class TestFindAddressConflict:
    def test_reports_the_client_that_already_owns_the_address(self) -> None:
        existing = make_client(name="lab-switch", ip_address="10.0.0.1")
        assert find_address_conflict([existing], "10.0.0.1") is existing

    def test_a_free_address_has_no_conflict(self) -> None:
        existing = make_client(ip_address="10.0.0.1")
        assert find_address_conflict([existing], "10.0.0.2") is None

    def test_a_disabled_client_does_not_hold_its_address(self) -> None:
        existing = make_client(ip_address="10.0.0.1", enabled=False)
        assert find_address_conflict([existing], "10.0.0.1") is None

    def test_editing_a_client_does_not_conflict_with_itself(self) -> None:
        existing = make_client(ip_address="10.0.0.1")
        assert find_address_conflict([existing], "10.0.0.1", exclude_id=existing.id) is None

    def test_a_conflict_is_found_across_labs(self) -> None:
        # FreeRADIUS matches by source address alone, so labs cannot each claim
        # the same NAS address.
        existing = make_client(lab_id=uuid4(), name="other-lab-nas", ip_address="10.0.0.1")
        assert find_address_conflict([existing], "10.0.0.1") is existing

    def test_padding_and_case_still_conflict(self) -> None:
        existing = make_client(ip_address="2001:db8::1")
        assert find_address_conflict([existing], " 2001:DB8::1 ") is existing
