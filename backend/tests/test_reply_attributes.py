import pytest

from app.integrations.freeradius.reply_attributes import (
    filter_returned_attributes,
    parse_attribute_pairs,
    render_policy_attributes,
    summarize_attributes,
)


def as_pairs(attributes) -> list[tuple[str, str]]:
    return [(a.name, a.value) for a in attributes]


class TestRenderPolicyAttributes:
    def test_vlan_renders_the_tunnel_triplet_in_order(self) -> None:
        assert as_pairs(render_policy_attributes(vlan=20)) == [
            ("Tunnel-Type", "VLAN"),
            ("Tunnel-Medium-Type", "IEEE-802"),
            ("Tunnel-Private-Group-Id", "20"),
        ]

    def test_role_renders_filter_id(self) -> None:
        assert as_pairs(render_policy_attributes(role="guest-acl")) == [
            ("Filter-Id", "guest-acl")
        ]

    def test_vlan_and_role_together(self) -> None:
        assert as_pairs(render_policy_attributes(vlan=40, role="printer-acl")) == [
            ("Tunnel-Type", "VLAN"),
            ("Tunnel-Medium-Type", "IEEE-802"),
            ("Tunnel-Private-Group-Id", "40"),
            ("Filter-Id", "printer-acl"),
        ]

    def test_empty_policy_renders_nothing(self) -> None:
        assert render_policy_attributes() == []

    def test_all_rows_use_the_assignment_operator(self) -> None:
        rendered = render_policy_attributes(vlan=10, role="r", extra={"Idle-Timeout": "600"})
        assert {a.op for a in rendered} == {"="}

    def test_extra_attributes_are_appended(self) -> None:
        rendered = render_policy_attributes(
            vlan=10, extra={"Session-Timeout": "3600", "Reply-Message": "hello"}
        )
        assert as_pairs(rendered)[-2:] == [
            ("Session-Timeout", "3600"),
            ("Reply-Message", "hello"),
        ]

    def test_extra_attribute_overrides_rendered_name_in_place(self) -> None:
        """Advanced mode wins, but must not produce two rows for one attribute."""
        rendered = render_policy_attributes(
            vlan=20, extra={"Tunnel-Private-Group-Id": "corp-vlan"}
        )
        assert as_pairs(rendered) == [
            ("Tunnel-Type", "VLAN"),
            ("Tunnel-Medium-Type", "IEEE-802"),
            ("Tunnel-Private-Group-Id", "corp-vlan"),
        ]

    def test_override_match_is_case_insensitive(self) -> None:
        rendered = render_policy_attributes(role="a", extra={"filter-id": "b"})
        assert as_pairs(rendered) == [("filter-id", "b")]

    def test_blank_role_and_empty_values_are_dropped(self) -> None:
        rendered = render_policy_attributes(role="   ", extra={"Filter-Id": "  ", "X-Y": None})
        assert rendered == []

    @pytest.mark.parametrize("vlan", [0, -1, 4095, 9999])
    def test_vlan_out_of_range_is_rejected(self, vlan: int) -> None:
        with pytest.raises(ValueError, match="VLAN id"):
            render_policy_attributes(vlan=vlan)

    @pytest.mark.parametrize("name", ["Bad Name", "-leading", "with_underscore", "", "a" * 65])
    def test_invalid_attribute_names_are_rejected(self, name: str) -> None:
        with pytest.raises(ValueError):
            render_policy_attributes(extra={name: "x"})

    @pytest.mark.parametrize("value", ['quote"injection', "new\nline", "carriage\rreturn"])
    def test_unsafe_attribute_values_are_rejected(self, value: str) -> None:
        with pytest.raises(ValueError):
            render_policy_attributes(extra={"Filter-Id": value})

    def test_oversized_attribute_value_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="253"):
            render_policy_attributes(extra={"Reply-Message": "x" * 254})


class TestSummarizeAttributes:
    def test_vlan_and_role_are_named_in_plain_language(self) -> None:
        summary = summarize_attributes(
            {
                "Tunnel-Type": "VLAN",
                "Tunnel-Medium-Type": "IEEE-802",
                "Tunnel-Private-Group-Id": "40",
                "Filter-Id": "printer-acl",
            }
        )
        assert summary == "VLAN 40 · role printer-acl"

    def test_other_attributes_keep_their_radius_name(self) -> None:
        assert summarize_attributes({"Session-Timeout": "3600"}) == "Session-Timeout=3600"

    def test_empty_input(self) -> None:
        assert summarize_attributes({}) == ""


class TestFilterReturnedAttributes:
    @pytest.mark.parametrize(
        "name",
        [
            "MS-MPPE-Recv-Key",
            "ms-mppe-send-key",
            "EAP-Message",
            "State",
            "Proxy-State",
            # A successful EAP exchange derives these; they are session keys.
            "EAP-MSK",
            "EAP-EMSK",
            "EAP-Session-Id",
            # Echoed from the request, not an authorization decision.
            "User-Name",
        ],
    )
    def test_key_material_and_plumbing_is_dropped(self, name: str) -> None:
        assert filter_returned_attributes({name: "secret", "Filter-Id": "ok"}) == {
            "Filter-Id": "ok"
        }

    def test_oversized_values_are_dropped(self) -> None:
        assert filter_returned_attributes({"Reply-Message": "x" * 300}) == {}

    def test_values_are_stringified(self) -> None:
        assert filter_returned_attributes({"Session-Timeout": 3600}) == {
            "Session-Timeout": "3600"
        }


class TestParseAttributePairs:
    def test_linelog_pairs(self) -> None:
        text = (
            'Tunnel-Type = VLAN, Tunnel-Medium-Type = IEEE-802, '
            'Tunnel-Private-Group-Id = "40", Filter-Id = "printer-acl"'
        )
        assert parse_attribute_pairs(text) == {
            "Tunnel-Type": "VLAN",
            "Tunnel-Medium-Type": "IEEE-802",
            "Tunnel-Private-Group-Id": "40",
            "Filter-Id": "printer-acl",
        }

    def test_tagged_tunnel_attributes_lose_the_tag(self) -> None:
        """radclient prints `Tunnel-Type:0`; the tag is grouping, not an attribute name."""
        text = (
            'Tunnel-Type:0 = VLAN, Tunnel-Medium-Type:0 = IEEE-802, '
            'Tunnel-Private-Group-Id:0 = "40", Filter-Id = "printer-acl"'
        )
        assert parse_attribute_pairs(text) == {
            "Tunnel-Type": "VLAN",
            "Tunnel-Medium-Type": "IEEE-802",
            "Tunnel-Private-Group-Id": "40",
            "Filter-Id": "printer-acl",
        }

    def test_value_containing_a_comma_is_kept_whole(self) -> None:
        assert parse_attribute_pairs('Reply-Message = "hello, world", Filter-Id = r') == {
            "Reply-Message": "hello, world",
            "Filter-Id": "r",
        }

    def test_value_containing_an_equals_sign_is_kept_whole(self) -> None:
        assert parse_attribute_pairs('Cisco-AVPair = "device-traffic-class=voice"') == {
            "Cisco-AVPair": "device-traffic-class=voice"
        }

    def test_sensitive_attributes_are_filtered(self) -> None:
        text = "MS-MPPE-Recv-Key = 0xdead, Filter-Id = ok"
        assert parse_attribute_pairs(text) == {"Filter-Id": "ok"}

    @pytest.mark.parametrize("text", ["", "   ", "no-equals-sign", None])
    def test_empty_or_unparseable_input(self, text) -> None:
        assert parse_attribute_pairs(text) == {}
