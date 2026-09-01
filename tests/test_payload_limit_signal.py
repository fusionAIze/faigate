"""The 413 must name the limit that actually rejected the request.

Byte-based rejections previously reported the provider token cap
(``limits.max_input_tokens``), so a caller who shrank the request to that many
tokens still failed: 262144 tokens do not fit in 1 MiB. The response now carries
the limit that fired, plus its unit.
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
