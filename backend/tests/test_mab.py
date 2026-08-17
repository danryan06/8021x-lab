import pytest

from app.integrations.freeradius.mab import (
    DISABLED_ENDPOINT_REASON,
    UNKNOWN_MAC_REASON,
    build_mab_request,
    infer_mab_failure,
    mab_reject_reason,
    mac_radius_usernames,
    parse_reply_attributes,
)

ACCEPT_OUTPUT = """Sent Access-Request Id 169 from 0.0.0.0:42875 to 172.18.0.3:1812 length 134
\tUser-Name = "aa:bb:cc:dd:ee:ff"
\tService-Type = Call-Check
Received Access-Accept Id 169 from 172.18.0.3:1812 to 172.18.0.4:42875 length 49
\tTunnel-Type:0 = VLAN
\tTunnel-Medium-Type:0 = IEEE-802
\tTunnel-Private-Group-Id:0 = "40"
\tFilter-Id = "printer-acl"
"""

REJECT_OUTPUT = """Sent Access-Request Id 12 from 0.0.0.0:1234 to 172.18.0.3:1812 length 134
\tUser-Name = "de:ad:be:ef:00:01"
Received Access-Reject Id 12 from 172.18.0.3:1812 to 172.18.0.4:1234 length 20
"""


class TestMacRadiusUsernames:
    def test_covers_every_common_nas_spelling(self) -> None:
        assert mac_radius_usernames("aa:bb:cc:dd:ee:ff") == [
            "aa:bb:cc:dd:ee:ff",
            "AA:BB:CC:DD:EE:FF",
            "aa-bb-cc-dd-ee-ff",
            "AA-BB-CC-DD-EE-FF",
            "aabbccddeeff",
            "AABBCCDDEEFF",
        ]

    def test_canonical_form_is_first(self) -> None:
        assert mac_radius_usernames("AABB.CCDD.EEFF")[0] == "aa:bb:cc:dd:ee:ff"

    @pytest.mark.parametrize(
        "spelling",
        ["aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabb.ccdd.eeff", "AABBCCDDEEFF"],
    )
    def test_every_input_spelling_yields_the_same_set(self, spelling: str) -> None:
        assert mac_radius_usernames(spelling) == mac_radius_usernames("aa:bb:cc:dd:ee:ff")

    def test_entries_are_unique(self) -> None:
        usernames = mac_radius_usernames("11:11:11:11:11:11")
        assert len(usernames) == len(set(usernames))

    def test_invalid_mac_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            mac_radius_usernames("not-a-mac")


class TestBuildMabRequest:
    def test_mirrors_what_a_switch_sends_for_a_mab_port(self) -> None:
        request = build_mab_request("aa:bb:cc:dd:ee:ff")
        assert 'User-Name = "aa:bb:cc:dd:ee:ff"' in request
        assert 'User-Password = "aa:bb:cc:dd:ee:ff"' in request
        assert "Service-Type = Call-Check" in request
        assert 'Calling-Station-Id = "aa:bb:cc:dd:ee:ff"' in request
        assert "NAS-Port-Type = Ethernet" in request

    def test_nas_ip_is_included_only_when_known(self) -> None:
        assert "NAS-IP-Address" not in build_mab_request("aabbccddeeff")
        assert "NAS-IP-Address = 172.18.0.4" in build_mab_request("aabbccddeeff", nas_ip="172.18.0.4")

    def test_calling_station_id_keeps_the_canonical_mac(self) -> None:
        """The NAS reports the device MAC even when User-Name uses another spelling."""
        request = build_mab_request("AABBCCDDEEFF", calling_station_id="aa:bb:cc:dd:ee:ff")
        assert 'User-Name = "AABBCCDDEEFF"' in request
        assert 'Calling-Station-Id = "aa:bb:cc:dd:ee:ff"' in request

    def test_document_is_newline_terminated_for_radclient_stdin(self) -> None:
        assert build_mab_request("aabbccddeeff").endswith("\n")


class TestParseReplyAttributes:
    def test_reads_the_attributes_printed_after_access_accept(self) -> None:
        assert parse_reply_attributes(ACCEPT_OUTPUT) == {
            "Tunnel-Type": "VLAN",
            "Tunnel-Medium-Type": "IEEE-802",
            "Tunnel-Private-Group-Id": "40",
            "Filter-Id": "printer-acl",
        }

    def test_request_attributes_before_the_accept_are_ignored(self) -> None:
        assert "User-Name" not in parse_reply_attributes(ACCEPT_OUTPUT)
        assert "Service-Type" not in parse_reply_attributes(ACCEPT_OUTPUT)

    def test_reject_has_no_reply_attributes(self) -> None:
        assert parse_reply_attributes(REJECT_OUTPUT) == {}

    def test_empty_output(self) -> None:
        assert parse_reply_attributes("") == {}


class TestInferMabFailure:
    def test_reject(self) -> None:
        assert infer_mab_failure(REJECT_OUTPUT) == "RADIUS Access-Reject"

    def test_no_response(self) -> None:
        reason = infer_mab_failure("radclient: no reply from server for ID 1")
        assert reason is not None
        assert "No RADIUS response" in reason

    def test_challenge_is_called_out(self) -> None:
        reason = infer_mab_failure("Received Access-Challenge Id 3")
        assert reason is not None
        assert "Access-Challenge" in reason

    def test_accept_has_no_failure(self) -> None:
        assert infer_mab_failure(ACCEPT_OUTPUT) is None


class TestMabRejectReason:
    def test_unknown_mac(self) -> None:
        assert mab_reject_reason(registered=False, enabled=False) == UNKNOWN_MAC_REASON

    def test_disabled_endpoint(self) -> None:
        assert mab_reject_reason(registered=True, enabled=False) == DISABLED_ENDPOINT_REASON

    def test_enabled_endpoint_has_no_control_plane_reason(self) -> None:
        """An enabled MAC that still failed needs FreeRADIUS's own explanation."""
        assert mab_reject_reason(registered=True, enabled=True) is None
