"""OAuth token-health readiness states (closing the FAI-203 class of failure).

FAI-203 class = a green readout that checks only presence (api-key set /
endpoint reachable) while ignoring the real health of the credential.  For
OAuth-wrapped providers the credential is a bearer token that expires and can
fail to refresh.  This module maps ``TokenStore`` state into **named** readiness
states so an operator can tell ``oauth_token_valid`` from
``oauth_token_expired`` or ``oauth_token_refresh_failed`` without grepping
runtime logs.

The classifier is pure and side-effect free: it only reads a token dict plus an
optional "was a refresh attempted and did it fail" flag.  It never mutates the
store and never performs a network refresh.  Refresh behaviour stays in
``faigate/oauth/token_store.py``; this module only *labels* the resulting
state.
"""

from __future__ import annotations

import time
from typing import Any

# Named readiness states (additive to the existing api-key check in
# ``ProviderBackend.request_readiness``).  These names are the public contract.
OAUTH_TOKEN_VALID = "oauth_token_valid"
OAUTH_TOKEN_EXPIRED = "oauth_token_expired"
OAUTH_TOKEN_REFRESH_FAILED = "oauth_token_refresh_failed"
OAUTH_TOKEN_MISSING = "oauth_token_missing"
OAUTH_TOKEN_NO_EXPIRY = "oauth_token_no_expiry"

# States that must *not* read green: a missing, expired, or un-refreshable
# token means the route cannot carry live OAuth traffic even if an api_key
# string happens to be present.
_UNHEALTHY_STATES = frozenset(
    {
        OAUTH_TOKEN_EXPIRED,
        OAUTH_TOKEN_REFRESH_FAILED,
        OAUTH_TOKEN_MISSING,
    }
)

_DEFAULT_MARGIN_SECONDS = 60


def _expired(token: dict[str, Any], margin_seconds: int, now: float) -> bool:
    """Return True when a token has expiry metadata in the past (with margin)."""
    expires_at = token.get("expires_at")
    if expires_at is None:
        return False
    try:
        return now >= (float(expires_at) - margin_seconds)
    except (TypeError, ValueError):
        # A malformed ``expires_at`` is not "valid forever": treat it as
        # expired so operators are not shown a false green.
        return True


def oauth_token_state(
    token: dict[str, Any] | None,
    *,
    refresh_failed: bool = False,
    margin_seconds: int = _DEFAULT_MARGIN_SECONDS,
    now: float | None = None,
) -> str:
    """Label an OAuth provider's token health with one named state.

    Args:
        token: The token dict from ``TokenStore.get(provider)``, or ``None``
            when the provider has no stored token yet.
        refresh_failed: Whether the most recent refresh attempt failed (or no
            refresh token was available for an expired token).  Callers that
            observe a ``refresh_if_needed`` -> ``False`` on an expired token
            pass ``True``.
        margin_seconds: Expiry safety margin, matching ``TokenStore.is_expired``.
        now: Clock for tests; defaults to ``time.time``.

    Returns:
        One of ``OAUTH_TOKEN_*`` constants.
    """
    if now is None:
        now = time.time()

    if not token:
        return OAUTH_TOKEN_MISSING

    expired = _expired(token, margin_seconds, now)

    if not expired:
        return OAUTH_TOKEN_VALID

    # Expired. Refresh is only possible when a refresh token exists; a failure
    # (or an expired token with no refresh token) is the refresh-failed family.
    has_refresh_token = bool(token.get("refresh_token"))
    if refresh_failed or not has_refresh_token:
        return OAUTH_TOKEN_REFRESH_FAILED

    return OAUTH_TOKEN_EXPIRED


def oauth_token_ready(
    token: dict[str, Any] | None,
    *,
    refresh_failed: bool = False,
    margin_seconds: int = _DEFAULT_MARGIN_SECONDS,
    now: float | None = None,
) -> bool:
    """Return whether the OAuth token is healthy enough to carry live traffic."""
    state = oauth_token_state(
        token,
        refresh_failed=refresh_failed,
        margin_seconds=margin_seconds,
        now=now,
    )
    return state not in _UNHEALTHY_STATES


def oauth_readiness_block(
    token: dict[str, Any] | None,
    *,
    refresh_failed: bool = False,
    margin_seconds: int = _DEFAULT_MARGIN_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Return the additive readiness sub-block wired into the health readout.

    Shape is intentionally small and stable: ``state`` is the named state and
    ``ready`` is a boolean the readiness surface may fold into its existing
    ``status``/``reason`` without replacing the api-key check.
    """
    state = oauth_token_state(
        token,
        refresh_failed=refresh_failed,
        margin_seconds=margin_seconds,
        now=now,
    )
    return {
        "state": state,
        "ready": state not in _UNHEALTHY_STATES,
    }
