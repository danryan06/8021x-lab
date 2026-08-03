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
