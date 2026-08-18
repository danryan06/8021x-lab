"""In-process RADIUS CoA/Disconnect responder for Compose demos.

Access-Request travels NAS → FreeRADIUS (UDP 1812). CoA and Disconnect-Request
travel the other way: RADIUS → NAS (UDP 3799). Compose has no switch listening
on 3799, so a Disconnect aimed at a registered client times out. This sink
pretends to be that NAS on the backend loopback so the UI can show an ACK.

The packet codec is RFC 2865/5176: Response Authenticator is MD5 over the
response header, the request authenticator, the attributes, and the shared
secret. Message-Authenticator (RFC 3579) is included on every reply so
radclient will accept the packet.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# RFC 5176 packet codes. Access-Request (1) is intentionally absent: this
# process is a NAS stand-in, not an authentication server.
CODE_DISCONNECT_REQUEST = 40
CODE_DISCONNECT_ACK = 41
CODE_DISCONNECT_NAK = 42
CODE_COA_REQUEST = 43
CODE_COA_ACK = 44
CODE_COA_NAK = 45

ATTR_USER_NAME = 1
ATTR_REPLY_MESSAGE = 18
ATTR_CALLING_STATION_ID = 31
ATTR_MESSAGE_AUTHENTICATOR = 80
ATTR_ERROR_CAUSE = 101

# RFC 5176 Error-Cause: identity attributes were required and missing.
ERROR_CAUSE_MISSING_ATTRIBUTE = 404

HEADER_LEN = 20
_ZERO_AUTH = b"\x00" * 16

_ACK_CODES = {
    CODE_DISCONNECT_REQUEST: CODE_DISCONNECT_ACK,
    CODE_COA_REQUEST: CODE_COA_ACK,
}
_NAK_CODES = {
    CODE_DISCONNECT_REQUEST: CODE_DISCONNECT_NAK,
    CODE_COA_REQUEST: CODE_COA_NAK,
}

PACKET_NAMES = {
    CODE_DISCONNECT_REQUEST: "Disconnect-Request",
    CODE_DISCONNECT_ACK: "Disconnect-ACK",
    CODE_DISCONNECT_NAK: "Disconnect-NAK",
    CODE_COA_REQUEST: "CoA-Request",
    CODE_COA_ACK: "CoA-ACK",
    CODE_COA_NAK: "CoA-NAK",
}


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data, usedforsecurity=False).digest()


def encode_attribute(type_: int, value: bytes) -> bytes:
    length = 2 + len(value)
    if length > 255:
        raise ValueError(f"RADIUS attribute type {type_} is longer than 253 bytes")
    return bytes([type_, length]) + value


def encode_string(type_: int, value: str) -> bytes:
    return encode_attribute(type_, value.encode("utf-8"))


def encode_integer(type_: int, value: int) -> bytes:
    return encode_attribute(type_, value.to_bytes(4, "big"))


def encode_message_authenticator(value: bytes | None = None) -> bytes:
    blob = value if value is not None else _ZERO_AUTH
    if len(blob) != 16:
        raise ValueError("Message-Authenticator must be 16 octets")
    return encode_attribute(ATTR_MESSAGE_AUTHENTICATOR, blob)


@dataclass(frozen=True)
class RadiusAttribute:
    type: int
    value: bytes

    @property
    def text(self) -> str:
        return self.value.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class RadiusPacket:
    code: int
    identifier: int
    authenticator: bytes
    attributes: tuple[RadiusAttribute, ...]
    raw: bytes

    def first(self, type_: int) -> RadiusAttribute | None:
        for attribute in self.attributes:
            if attribute.type == type_:
                return attribute
        return None

    def text(self, type_: int) -> str | None:
        attribute = self.first(type_)
        return attribute.text if attribute else None


def parse_attributes(data: bytes) -> tuple[RadiusAttribute, ...]:
    attributes: list[RadiusAttribute] = []
    offset = 0
    while offset + 2 <= len(data):
        type_ = data[offset]
        length = data[offset + 1]
        if length < 2 or offset + length > len(data):
            break
        attributes.append(RadiusAttribute(type_, data[offset + 2 : offset + length]))
        offset += length
    return tuple(attributes)


def parse_packet(data: bytes) -> RadiusPacket | None:
    """Return a packet if `data` is a well-framed RADIUS datagram, else None."""
    if len(data) < HEADER_LEN:
        return None
    length = int.from_bytes(data[2:4], "big")
    if length < HEADER_LEN or length > len(data):
        return None
    body = data[:length]
    return RadiusPacket(
        code=body[0],
        identifier=body[1],
        authenticator=body[4:20],
        attributes=parse_attributes(body[20:]),
        raw=body,
    )


def _with_zeroed_message_authenticator(packet: bytes) -> bytes:
    """Copy of `packet` with any Message-Authenticator value set to zeros.

    HMAC-MD5 is computed over the packet as if the attribute were 16 zero
    octets (RFC 3579). Attributes after it are preserved.
    """
    if len(packet) < HEADER_LEN:
        return packet
    out = bytearray(packet)
    offset = HEADER_LEN
    while offset + 2 <= len(out):
        type_ = out[offset]
        length = out[offset + 1]
        if length < 2 or offset + length > len(out):
            break
        if type_ == ATTR_MESSAGE_AUTHENTICATOR and length == 18:
            out[offset + 2 : offset + 18] = _ZERO_AUTH
        offset += length
    return bytes(out)


def message_authenticator(
    packet: bytes,
    secret: bytes,
    *,
    hmac_authenticator: bytes | None = None,
) -> bytes:
    """HMAC-MD5 of the packet with Message-Authenticator zeroed (RFC 3579).

    For requests, the packet's Authenticator field is already the Request
    Authenticator. For responses, HMAC is computed with the *Request*
    Authenticator in that field — not the Response Authenticator — which is
    why radclient reports "invalid Message-Authenticator" if we HMAC the
    finished response packet as-is.
    """
    body = _with_zeroed_message_authenticator(packet)
    if hmac_authenticator is not None:
        if len(hmac_authenticator) != 16:
            raise ValueError("HMAC Authenticator must be 16 octets")
        body = body[:4] + hmac_authenticator + body[20:]
    return hmac.new(secret, body, hashlib.md5).digest()


def verify_message_authenticator(
    packet: bytes,
    secret: bytes,
    *,
    hmac_authenticator: bytes | None = None,
) -> bool:
    parsed = parse_packet(packet)
    if parsed is None:
        return False
    attribute = parsed.first(ATTR_MESSAGE_AUTHENTICATOR)
    if attribute is None or len(attribute.value) != 16:
        return False
    expected = message_authenticator(
        packet, secret, hmac_authenticator=hmac_authenticator
    )
    return hmac.compare_digest(attribute.value, expected)


def response_authenticator(
    code: int,
    identifier: int,
    request_authenticator: bytes,
    attributes: bytes,
    secret: bytes,
) -> bytes:
    length = HEADER_LEN + len(attributes)
    header = bytes([code, identifier]) + length.to_bytes(2, "big")
    return _md5(header + request_authenticator + attributes + secret)


def encode_request(
    code: int,
    identifier: int,
    request_authenticator: bytes,
    attributes: bytes,
    secret: bytes,
    *,
    with_message_authenticator: bool = True,
) -> bytes:
    """Build a CoA/Disconnect-Request. Request Authenticator is the caller's random 16 octets."""
    if len(request_authenticator) != 16:
        raise ValueError("Request Authenticator must be 16 octets")
    attrs = attributes
    if with_message_authenticator:
        attrs = attributes + encode_message_authenticator()
    length = HEADER_LEN + len(attrs)
    packet = bytes([code, identifier]) + length.to_bytes(2, "big") + request_authenticator + attrs
    if with_message_authenticator:
        packet = packet[:-16] + message_authenticator(packet, secret)
    return packet


def encode_response(
    code: int,
    identifier: int,
    request_authenticator: bytes,
    attributes: bytes,
    secret: bytes,
    *,
    with_message_authenticator: bool = True,
) -> bytes:
    attrs = attributes
    if with_message_authenticator:
        attrs = attributes + encode_message_authenticator()
    length = HEADER_LEN + len(attrs)
    header = bytes([code, identifier]) + length.to_bytes(2, "big")
    resp_auth = response_authenticator(code, identifier, request_authenticator, attrs, secret)
    packet = header + resp_auth + attrs
    if with_message_authenticator:
        packet = packet[:-16] + message_authenticator(
            packet, secret, hmac_authenticator=request_authenticator
        )
    return packet


def verify_response_authenticator(
    packet: bytes, request_authenticator: bytes, secret: bytes
) -> bool:
    parsed = parse_packet(packet)
    if parsed is None:
        return False
    attrs = _with_zeroed_message_authenticator(packet)[HEADER_LEN:]
    expected = response_authenticator(
        parsed.code, parsed.identifier, request_authenticator, attrs, secret
    )
    return hmac.compare_digest(parsed.authenticator, expected)


def build_coa_response(data: bytes, secret: bytes | str) -> bytes | None:
    """Turn a CoA/Disconnect-Request into an ACK (or NAK if no identity).

    Returns None for short/unknown packets so a stray datagram is ignored
    rather than answered with a RADIUS header.
    """
    secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
    request = parse_packet(data)
    if request is None or request.code not in _ACK_CODES:
        return None

    has_identity = bool(request.text(ATTR_USER_NAME) or request.text(ATTR_CALLING_STATION_ID))
    if has_identity:
        code = _ACK_CODES[request.code]
        name = PACKET_NAMES[request.code]
        attributes = encode_string(ATTR_REPLY_MESSAGE, f"lab CoA sink: {name} accepted")
    else:
        code = _NAK_CODES[request.code]
        attributes = encode_integer(ATTR_ERROR_CAUSE, ERROR_CAUSE_MISSING_ATTRIBUTE)
        attributes += encode_string(
            ATTR_REPLY_MESSAGE,
            "lab CoA sink: User-Name or Calling-Station-Id is required",
        )

    return encode_response(code, request.identifier, request.authenticator, attributes, secret_bytes)


class CoaSinkProtocol(asyncio.DatagramProtocol):
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.transport: asyncio.DatagramTransport | None = None
        self.requests_handled = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        reply = build_coa_response(data, self.secret)
        if reply is None:
            logger.debug("CoA sink ignored %s-byte datagram from %s", len(data), addr)
            return
        self.requests_handled += 1
        parsed = parse_packet(data)
        code_name = PACKET_NAMES.get(parsed.code, str(parsed.code)) if parsed else "unknown"
        logger.info("CoA sink answering %s from %s:%s", code_name, addr[0], addr[1])
        if self.transport is not None:
            self.transport.sendto(reply, addr)


@dataclass
class CoaSink:
    transport: asyncio.DatagramTransport
    protocol: CoaSinkProtocol
    host: str
    port: int
    secret_hint: str


_runtime: CoaSink | None = None


def get_runtime_sink() -> CoaSink | None:
    return _runtime


def _secret_hint(secret: str) -> str:
    if len(secret) <= 4:
        return "****"
    return f"{secret[:2]}…{secret[-2:]}"


async def start_coa_sink(
    *,
    host: str | None = None,
    port: int | None = None,
    secret: str | None = None,
    register: bool = True,
) -> CoaSink:
    """Bind the UDP sink. `port=0` asks the OS for an ephemeral port (tests)."""
    global _runtime
    bind_host = host if host is not None else settings.coa_sink_host
    bind_port = settings.coa_port if port is None else port
    shared = secret if secret is not None else settings.freeradius_lab_secret
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: CoaSinkProtocol(shared),
        local_addr=(bind_host, bind_port),
    )
    sockname = transport.get_extra_info("sockname")
    bound_host, bound_port = sockname[0], int(sockname[1])
    sink = CoaSink(
        transport=transport,
        protocol=protocol,
        host=bound_host,
        port=bound_port,
        secret_hint=_secret_hint(shared),
    )
    if register:
        _runtime = sink
    logger.info("Lab CoA sink listening on %s:%s", bound_host, bound_port)
    return sink


async def stop_coa_sink(sink: CoaSink | None) -> None:
    global _runtime
    if sink is None:
        return
    sink.transport.close()
    if _runtime is sink:
        _runtime = None
    await asyncio.sleep(0)
