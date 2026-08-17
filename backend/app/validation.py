"""Shared input-validation helpers for values that reach the filesystem or subprocesses."""

from __future__ import annotations

import re

# Certificate identities become file names (<identity>.crt/.key/.p12) and openssl
# subjects, so restrict them to a safe charset: no path separators, no dots-only
# names, no leading separator characters.
IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$"
_IDENTITY_RE = re.compile(IDENTITY_PATTERN)

# wpa_supplicant config values are written inside double quotes with no escaping
# mechanism, so quotes/backslashes/newlines would inject config directives.
_EAPOL_UNSAFE = re.compile(r'["\\\r\n]')

# RADIUS attribute names as they appear in FreeRADIUS dictionaries
# (Tunnel-Private-Group-Id, Filter-Id, Cisco-AVPair, …).
ATTRIBUTE_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9-]{0,63}$"
_ATTRIBUTE_NAME_RE = re.compile(ATTRIBUTE_NAME_PATTERN)

# radclient reads attributes from a line-based stdin document, so a value with a
# newline or quote would inject extra attributes into the request.
_ATTRIBUTE_VALUE_UNSAFE = re.compile(r'["\r\n]')


def validate_identity(identity: str) -> str:
    """Validate a certificate identity used in file paths; raise ValueError if unsafe."""
    if not _IDENTITY_RE.fullmatch(identity):
        raise ValueError(
            "identity must start with a letter or digit and may only contain "
            "letters, digits, '.', '_', '@' and '-' (max 128 characters)"
        )
    return identity


def validate_eapol_config_value(name: str, value: str) -> str:
    """Reject values that cannot be safely quoted in a wpa_supplicant config."""
    if _EAPOL_UNSAFE.search(value):
        raise ValueError(f'{name} must not contain double quotes, backslashes, or newlines')
    return value


def normalize_mac(value: str) -> str:
    """Return the canonical lab form of a MAC address: lowercase, colon-separated.

    Accepts the formats operators paste from switches, NIC labels, and inventory
    exports: ``aa:bb:cc:dd:ee:ff``, ``aa-bb-cc-dd-ee-ff``, ``aabb.ccdd.eeff``,
    ``AABBCCDDEEFF``, and mixed separators. One canonical form is stored so the
    same endpoint cannot be registered twice under two spellings.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("MAC address is required")
    hex_digits = re.sub(r"[\s:.-]", "", raw)
    if len(hex_digits) != 12 or not all(c in "0123456789abcdefABCDEF" for c in hex_digits):
        raise ValueError(
            f"{raw!r} is not a MAC address — expected 12 hex digits, e.g. "
            "aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, aabb.ccdd.eeff, or aabbccddeeff"
        )
    lowered = hex_digits.lower()
    return ":".join(lowered[i : i + 2] for i in range(0, 12, 2))


def validate_attribute_name(name: str) -> str:
    """Validate a RADIUS reply-attribute name before it reaches SQL / radclient."""
    if not _ATTRIBUTE_NAME_RE.fullmatch(name or ""):
        raise ValueError(
            f"{name!r} is not a valid RADIUS attribute name — use dictionary names such as "
            "Filter-Id or Tunnel-Private-Group-Id (letters, digits, and '-')"
        )
    return name


def validate_attribute_value(name: str, value: str) -> str:
    """Reject reply-attribute values that cannot be safely written to SQL/radclient."""
    if _ATTRIBUTE_VALUE_UNSAFE.search(value or ""):
        raise ValueError(f"value for {name} must not contain double quotes or newlines")
    if len(value or "") > 253:
        raise ValueError(f"value for {name} is longer than a RADIUS attribute allows (253 bytes)")
    return value
