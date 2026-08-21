"""Tests for OAuth token-health readiness states (FAI-203 class).

These assert that token validity / expiry / refresh-failure map to *named*
readiness states rather than collapsing into a single api-key-presence boolean.
"""

from faigate.oauth_readiness import (
    OAUTH_TOKEN_EXPIRED,
    OAUTH_TOKEN_MISSING,
    OAUTH_TOKEN_REFRESH_FAILED,
    OAUTH_TOKEN_VALID,
    oauth_readiness_block,
    oauth_token_ready,
    oauth_token_state,
)

_NOW = 1_800_000_000.0


def _token(expires_at=None, refresh_token="rt-123", **extra):
    t = {"access_token": "at-123", "refresh_token": refresh_token}
    if expires_at is not None:
        t["expires_at"] = expires_at
    t.update(extra)
    return t


def test_no_token_is_oauth_token_missing():
    assert oauth_token_state(None, now=_NOW) == OAUTH_TOKEN_MISSING
    assert oauth_token_ready(None, now=_NOW) is False


def test_valid_token_with_future_expiry_is_oauth_token_valid():
    token = _token(expires_at=_NOW + 3600)
    assert oauth_token_state(token, now=_NOW) == OAUTH_TOKEN_VALID
    assert oauth_token_ready(token, now=_NOW) is True


def test_token_without_expiry_metadata_is_valid_not_expired():
    # No expires_at -> assume still valid (matches TokenStore.is_expired).
    token = _token()
    assert oauth_token_state(token, now=_NOW) == OAUTH_TOKEN_VALID


def test_expired_token_with_refresh_token_but_no_failure_is_oauth_token_expired():
    token = _token(expires_at=_NOW - 1)
    assert oauth_token_state(token, now=_NOW) == OAUTH_TOKEN_EXPIRED
    assert oauth_token_ready(token, now=_NOW) is False


def test_expired_token_with_failed_refresh_is_oauth_token_refresh_failed():
    token = _token(expires_at=_NOW - 1)
    assert (
        oauth_token_state(token, refresh_failed=True, now=_NOW)
        == OAUTH_TOKEN_REFRESH_FAILED
    )


def test_expired_token_without_refresh_token_is_refresh_failed():
    token = _token(expires_at=_NOW - 1, refresh_token=None)
    assert (
        oauth_token_state(token, now=_NOW) == OAUTH_TOKEN_REFRESH_FAILED
    )


def test_ready_is_false_for_expiry_and_refresh_failure_and_missing():
    expired = oauth_token_ready(_token(expires_at=_NOW - 1), now=_NOW)
    failed = oauth_token_ready(
        _token(expires_at=_NOW - 1), refresh_failed=True, now=_NOW
    )
    missing = oauth_token_ready(None, now=_NOW)
    assert expired is False
    assert failed is False
    assert missing is False


def test_readiness_block_shape_is_stable_and_named():
    block = oauth_readiness_block(_token(expires_at=_NOW + 3600), now=_NOW)
    assert block == {"state": OAUTH_TOKEN_VALID, "ready": True}

    block = oauth_readiness_block(None, now=_NOW)
    assert block == {"state": OAUTH_TOKEN_MISSING, "ready": False}


def test_margin_treats_soon_to_expire_as_expired():
    # Default margin is 60s: a token expiring in 10s is already treated expired.
    token = _token(expires_at=_NOW + 10)
    assert oauth_token_state(token, now=_NOW) == OAUTH_TOKEN_EXPIRED
