import asyncio
import os
import shutil
import socket

import pytest

from app.integrations.freeradius.coa import (
    build_coa_request,
    format_radclient_pair,
    infer_coa_failure,
    parse_coa_reply,
    run_coa,
)
from app.integrations.freeradius.coa_sink import (
    ATTR_CALLING_STATION_ID,
    ATTR_ERROR_CAUSE,
    ATTR_REPLY_MESSAGE,
    ATTR_USER_NAME,
    CODE_COA_ACK,
    CODE_COA_REQUEST,
    CODE_DISCONNECT_ACK,
    CODE_DISCONNECT_NAK,
    CODE_DISCONNECT_REQUEST,
    ERROR_CAUSE_MISSING_ATTRIBUTE,
    build_coa_response,
    encode_request,
    encode_string,
    parse_packet,
    start_coa_sink,
    stop_coa_sink,
    verify_message_authenticator,
    verify_response_authenticator,
)

SECRET = b"testing123"

ACK_OUTPUT = """Sent Disconnect-Request Id 12 from 0.0.0.0:45123 to 127.0.0.1:3799 length 59
\tUser-Name = "aa:bb:cc:dd:ee:ff"
\tCalling-Station-Id = "aa:bb:cc:dd:ee:ff"
Received Disconnect-ACK Id 12 from 127.0.0.1:3799 to 0.0.0.0:45123 length 48
\tReply-Message = "lab CoA sink: Disconnect-Request accepted"
"""

NAK_OUTPUT = """Sent CoA-Request Id 3 from 0.0.0.0:9 to 10.0.0.1:3799 length 40
\tUser-Name = "aa:bb:cc:dd:ee:ff"
Received CoA-NAK Id 3 from 10.0.0.1:3799 to 0.0.0.0:9 length 26
\tError-Cause = Missing-Attribute
"""

TIMEOUT_OUTPUT = "radclient: no reply from server for ID 1"


class TestFormatRadclientPair:
    def test_quotes_mac_usernames(self) -> None:
        assert format_radclient_pair("User-Name", "aa:bb:cc:dd:ee:ff") == (
            'User-Name = "aa:bb:cc:dd:ee:ff"'
        )

    def test_leaves_vlan_dictionary_names_unquoted(self) -> None:
        assert format_radclient_pair("Tunnel-Type", "VLAN") == "Tunnel-Type = VLAN"
        assert format_radclient_pair("Tunnel-Medium-Type", "IEEE-802") == (
            "Tunnel-Medium-Type = IEEE-802"
        )

    def test_leaves_decimal_vlan_ids_unquoted(self) -> None:
        assert format_radclient_pair("Tunnel-Private-Group-Id", "40") == (
            "Tunnel-Private-Group-Id = 40"
        )

    def test_quotes_and_escapes_filter_id(self) -> None:
        assert format_radclient_pair("Filter-Id", 'guest "acl"') == (
            'Filter-Id = "guest \\"acl\\""'
        )

    def test_rejects_newlines(self) -> None:
        with pytest.raises(ValueError):
            format_radclient_pair("Filter-Id", "a\nb")


class TestBuildCoaRequest:
    def test_identifies_the_session_by_mac(self) -> None:
        request = build_coa_request("aa:bb:cc:dd:ee:ff")
        assert 'User-Name = "aa:bb:cc:dd:ee:ff"' in request
        assert 'Calling-Station-Id = "aa:bb:cc:dd:ee:ff"' in request
        assert request.endswith("\n")

    def test_includes_nas_ip_only_when_known(self) -> None:
        assert "NAS-IP-Address" not in build_coa_request("aa:bb:cc:dd:ee:ff")
        assert "NAS-IP-Address = 10.0.0.1" in build_coa_request(
            "aa:bb:cc:dd:ee:ff", nas_ip="10.0.0.1"
        )

    def test_appends_policy_attributes_for_coa(self) -> None:
        request = build_coa_request(
            "aa:bb:cc:dd:ee:ff",
            extra={
                "Tunnel-Type": "VLAN",
                "Tunnel-Medium-Type": "IEEE-802",
                "Tunnel-Private-Group-Id": "40",
                "Filter-Id": "printer-acl",
            },
        )
        assert "Tunnel-Type = VLAN" in request
        assert "Tunnel-Medium-Type = IEEE-802" in request
        assert "Tunnel-Private-Group-Id = 40" in request
        assert 'Filter-Id = "printer-acl"' in request

    def test_empty_username_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_coa_request("  ")


class TestParseCoaReply:
    def test_reads_ack_and_reply_message(self) -> None:
        packet_type, attrs = parse_coa_reply(ACK_OUTPUT)
        assert packet_type == "Disconnect-ACK"
        assert attrs["Reply-Message"] == "lab CoA sink: Disconnect-Request accepted"

    def test_request_attributes_are_ignored(self) -> None:
        _, attrs = parse_coa_reply(ACK_OUTPUT)
        assert "User-Name" not in attrs

    def test_nak(self) -> None:
        packet_type, attrs = parse_coa_reply(NAK_OUTPUT)
        assert packet_type == "CoA-NAK"
        assert attrs["Error-Cause"] == "Missing-Attribute"

    def test_empty(self) -> None:
        assert parse_coa_reply("") == (None, {})


class TestInferCoaFailure:
    def test_ack_has_no_failure(self) -> None:
        assert infer_coa_failure(ACK_OUTPUT, "Disconnect-ACK") is None

    def test_nak_explains_the_packet(self) -> None:
        reason = infer_coa_failure(NAK_OUTPUT, "CoA-NAK")
        assert reason is not None
        assert "CoA-NAK" in reason

    def test_timeout_points_at_the_sink(self) -> None:
        reason = infer_coa_failure(TIMEOUT_OUTPUT, None)
        assert reason is not None
        assert "lab CoA sink" in reason


class TestSinkCodec:
    def test_acks_disconnect_with_identity(self) -> None:
        request = encode_request(
            CODE_DISCONNECT_REQUEST,
            7,
            os.urandom(16),
            encode_string(ATTR_USER_NAME, "aa:bb:cc:dd:ee:ff"),
            SECRET,
        )
        reply = build_coa_response(request, SECRET)
        assert reply is not None
        parsed = parse_packet(reply)
        assert parsed is not None
        assert parsed.code == CODE_DISCONNECT_ACK
        assert parsed.identifier == 7
        assert verify_response_authenticator(reply, parse_packet(request).authenticator, SECRET)
        assert verify_message_authenticator(reply, SECRET)
        assert "Disconnect-Request accepted" in (parsed.text(ATTR_REPLY_MESSAGE) or "")

    def test_acks_coa_identified_by_calling_station(self) -> None:
        request = encode_request(
            CODE_COA_REQUEST,
            1,
            os.urandom(16),
            encode_string(ATTR_CALLING_STATION_ID, "aa:bb:cc:dd:ee:ff"),
            SECRET,
        )
        reply = build_coa_response(request, SECRET)
        parsed = parse_packet(reply)
        assert parsed is not None
        assert parsed.code == CODE_COA_ACK

    def test_naks_request_without_identity(self) -> None:
        request = encode_request(
            CODE_DISCONNECT_REQUEST,
            2,
            os.urandom(16),
            b"",
            SECRET,
        )
        reply = build_coa_response(request, SECRET)
        parsed = parse_packet(reply)
        assert parsed is not None
        assert parsed.code == CODE_DISCONNECT_NAK
        error = parsed.first(ATTR_ERROR_CAUSE)
        assert error is not None
        assert int.from_bytes(error.value, "big") == ERROR_CAUSE_MISSING_ATTRIBUTE

    def test_ignores_short_and_unknown_packets(self) -> None:
        assert build_coa_response(b"\x00" * 8, SECRET) is None
        # Access-Request (code 1) is not CoA.
        garbage = bytes([1, 0, 0, 20]) + os.urandom(16)
        assert build_coa_response(garbage, SECRET) is None


class TestSinkUdp:
    def test_round_trip_on_an_ephemeral_port(self) -> None:
        async def _run() -> None:
            sink = await start_coa_sink(
                host="127.0.0.1", port=0, secret="testing123", register=False
            )
            try:
                request_auth = os.urandom(16)
                request = encode_request(
                    CODE_DISCONNECT_REQUEST,
                    9,
                    request_auth,
                    encode_string(ATTR_USER_NAME, "de:ad:be:ef:00:01"),
                    SECRET,
                )

                def _exchange() -> bytes:
                    # Blocking recv must not run on the event loop: the sink is an
                    # asyncio protocol on that loop and would never see the datagram.
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(2)
                    try:
                        sock.sendto(request, ("127.0.0.1", sink.port))
                        data, _addr = sock.recvfrom(4096)
                    finally:
                        sock.close()
                    return data

                data = await asyncio.to_thread(_exchange)
                parsed = parse_packet(data)
                assert parsed is not None
                assert parsed.code == CODE_DISCONNECT_ACK
                assert verify_response_authenticator(data, request_auth, SECRET)
            finally:
                await stop_coa_sink(sink)

        asyncio.run(_run())


@pytest.mark.skipif(shutil.which("radclient") is None, reason="radclient not installed")
class TestRadclientAgainstSink:
    def test_disconnect_is_acked(self) -> None:
        async def _run() -> None:
            sink = await start_coa_sink(
                host="127.0.0.1", port=0, secret="testing123", register=False
            )
            try:
                request = build_coa_request("aa:bb:cc:dd:ee:ff")
                result = await asyncio.to_thread(
                    run_coa,
                    "disconnect",
                    request,
                    nas_host="127.0.0.1",
                    nas_port=sink.port,
                    shared_secret="testing123",
                )
                assert result.result == "ack"
                assert result.packet_type == "Disconnect-ACK"
                assert result.success
            finally:
                await stop_coa_sink(sink)

        asyncio.run(_run())

    def test_coa_is_acked(self) -> None:
        async def _run() -> None:
            sink = await start_coa_sink(
                host="127.0.0.1", port=0, secret="testing123", register=False
            )
            try:
                request = build_coa_request(
                    "aa:bb:cc:dd:ee:ff",
                    extra={"Tunnel-Type": "VLAN", "Tunnel-Private-Group-Id": "40"},
                )
                result = await asyncio.to_thread(
                    run_coa,
                    "coa",
                    request,
                    nas_host="127.0.0.1",
                    nas_port=sink.port,
                    shared_secret="testing123",
                )
                assert result.result == "ack"
                assert result.packet_type == "CoA-ACK"
            finally:
                await stop_coa_sink(sink)

        asyncio.run(_run())
