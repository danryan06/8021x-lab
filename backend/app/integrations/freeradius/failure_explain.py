"""Turn raw FreeRADIUS failure text into a friendly summary + remediation hint.

Used by the Events and Auth Test surfaces so operators see plain-language
explanations instead of only the raw Module-Failure-Message.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.entities import AuthMethod, AuthResult


@dataclass
class FailureExplanation:
    summary: str
    hint: str


# Ordered (substring -> explanation); first match wins. Substrings are matched
# case-insensitively against the raw failure reason.
_RULES: list[tuple[str, FailureExplanation]] = [
    (
        "unknown ca",
        FailureExplanation(
            "Client certificate signed by an untrusted CA",
            "Publish the lab CA into the FreeRADIUS trust store (Sync to FreeRADIUS) "
            "so the client's issuer is trusted.",
        ),
    ),
    (
        "self signed",
        FailureExplanation(
            "Client presented a self-signed certificate",
            "Issue the client certificate from the lab CA instead of using a self-signed cert.",
        ),
    ),
    (
        "certificate has expired",
        FailureExplanation(
            "Client certificate has expired",
            "Re-issue the client certificate; the presented one is past its notAfter date.",
        ),
    ),
    (
        "expired",
        FailureExplanation(
            "Certificate or credential expired",
            "Re-issue the client certificate or reset the user's password/expiry.",
        ),
    ),
    (
        "certificate revoked",
        FailureExplanation(
            "Client certificate was revoked",
            "This certificate is on the CRL. Issue a new certificate for the identity.",
        ),
    ),
    (
        "revoked",
        FailureExplanation(
            "Client certificate was revoked",
            "This certificate is on the CRL. Issue a new certificate for the identity.",
        ),
    ),
    (
        "mschap",
        FailureExplanation(
            "PEAP/MSCHAPv2 password rejected",
            "Confirm the user's password and that it was synced to FreeRADIUS (radcheck NT-Password).",
        ),
    ),
    (
        "password",
        FailureExplanation(
            "Password did not match",
            "Confirm the user's password; for PEAP the NT-Password must be synced to radcheck.",
        ),
    ),
    (
        "unknown user",
        FailureExplanation(
            "No matching user in FreeRADIUS",
            "Create the user in this lab and Sync to FreeRADIUS so radcheck has the identity.",
        ),
    ),
    (
        "no configuration",
        FailureExplanation(
            "No matching user in FreeRADIUS",
            "Create the user in this lab and Sync to FreeRADIUS so radcheck has the identity.",
        ),
    ),
]


def explain_failure(
    failure_reason: str | None,
    method: AuthMethod | None = None,
    result: AuthResult | None = None,
) -> FailureExplanation | None:
    """Return a friendly explanation, or None for successful/unclassified events."""
    if result is not None and result != AuthResult.failure:
        return None

    text = (failure_reason or "").strip().lower()
    for needle, explanation in _RULES:
        if needle in text:
            return explanation

    if not text or text == "authentication failed":
        # Generic reject with no detail: give a method-appropriate starting point.
        if method == AuthMethod.eap_tls:
            return FailureExplanation(
                "EAP-TLS authentication was rejected",
                "Check that the client certificate is issued by a trusted lab CA and not "
                "expired or revoked, and that the lab CA is published to FreeRADIUS.",
            )
        if method == AuthMethod.peap:
            return FailureExplanation(
                "PEAP authentication was rejected",
                "Verify the username/password and that the user is synced to FreeRADIUS.",
            )
        return FailureExplanation(
            "Authentication was rejected",
            "Open the event detail or FreeRADIUS logs for the specific reason.",
        )

    # Unrecognized but present reason: surface it as the summary with a generic hint.
    return FailureExplanation(
        failure_reason.strip() if failure_reason else "Authentication was rejected",
        "See the FreeRADIUS logs for more detail on this failure.",
    )
