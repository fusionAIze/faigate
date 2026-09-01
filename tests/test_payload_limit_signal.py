"""The 413 must name the limit that actually rejected the request.

Byte-based rejections previously reported the provider token cap
(``limits.max_input_tokens``) instead of the byte limit that fired.

Measured against the running gateway (faigate 2.7.0, 2026-09-01), isolating the
two checks by sending few tokens in many bytes:

    body 1_000_000 B -> HTTP 200, prompt_tokens = 125071
    body 1_100_000 B -> HTTP 413, limit = 262144

The rejected request carried roughly 137k tokens — far below the advertised
262144 cap — so the wall it hit was security.max_json_body_bytes (1048576), not
the token cap. A caller who shrank to the advertised number would be shrinking
against a limit that never fired.

The response now carries the limit that actually fired, plus its unit.
"""

from __future__ import annotations

import json

from faigate.main import PayloadTooLargeError, _payload_too_large_response


def _body(resp):
    return json.loads(bytes(resp.body).decode("utf-8"))


def test_byte_rejection_reports_the_byte_limit():
    exc = PayloadTooLargeError("body too big", byte_limit=1_048_576)
    resp = _payload_too_large_response("Chat completion request is too large", exc=exc)
    body = _body(resp)
    assert resp.status_code == 413
    assert body["limit"] == 1_048_576
    assert body["limit_unit"] == "bytes"
    assert resp.headers["x-faigate-request-limit"] == "1048576"
    assert resp.headers["x-faigate-request-limit-unit"] == "bytes"


def test_explicit_token_limit_still_reports_tokens():
    resp = _payload_too_large_response("too many tokens", limit=262_144)
    body = _body(resp)
    assert body["limit"] == 262_144
    assert body["limit_unit"] == "tokens"
    assert resp.headers["x-faigate-request-limit-unit"] == "tokens"


def test_byte_limit_is_not_masked_by_the_token_cap():
    """The regression: a byte rejection must not advertise the token cap."""
    exc = PayloadTooLargeError("body too big", byte_limit=1_048_576)
    resp = _payload_too_large_response("Chat completion request is too large", exc=exc)
    body = _body(resp)
    assert body["limit"] != 262_144, "byte rejection reported the token cap"


def test_exception_without_byte_limit_falls_back_cleanly():
    resp = _payload_too_large_response("generic", exc=ValueError("boom"))
    body = _body(resp)
    assert body["type"] == "payload_too_large"
    if "limit" in body:
        assert body["limit_unit"] == "tokens"
