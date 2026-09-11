"""Acceptance tests for the 413 input-cap signal (TASK-D3).

The gateway's payload-too-large response must report the cap of the *requested
model*, never the provider-wide ``max()`` placeholder (262144). Three things are
pinned here:

1. A request whose model has a hard ``confirmed`` cap reports that model's cap when
   the ingress 413 fires — the value a client can plan against.
2. A model without a ``confirmed`` cap falls back to the b2 rule (passthrough or the
   operator byte limit), never to an invented ``max()`` number.
3. The reported number is always unit-labelled so ``tokens`` (a model cap) can
   never be mistaken for ``bytes`` (the operator body limit).

``_payload_too_large_response`` and ``_resolve_advertised_input_limit`` carry the
logic; ``_sniff_requested_model`` recovers the id from an oversized body that was
rejected before it could be parsed, so the endpoint can pass that id through.
"""

from __future__ import annotations

import json

import pytest

import faigate.main as main
from faigate import provider_catalog

# --------------------------------------------------------------------------- #
# Criterion 1 — a model-cap overrun reports that model's cap
# --------------------------------------------------------------------------- #


def _use_bundled_catalog(monkeypatch) -> None:
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)


def test_resolve_reports_the_requested_models_cap(monkeypatch) -> None:
    _use_bundled_catalog(monkeypatch)
    limit, estimated = main._resolve_advertised_input_limit("claude-opus-4-6")

    assert limit == 1000000
    assert estimated is False


def test_413_reports_the_requested_models_cap(monkeypatch) -> None:
    _use_bundled_catalog(monkeypatch)
    resp = main._payload_too_large_response("too large", model_id="claude-opus-4-6")

    payload = json.loads(resp.body)
    assert payload["type"] == "payload_too_large"
    assert payload["limit"] == 1000000
    assert resp.headers["x-faigate-request-limit"] == "1000000"


# --------------------------------------------------------------------------- #
# Criterion 2 — no confirmed cap: b2 rule, no max()
# --------------------------------------------------------------------------- #


def test_no_confirmed_cap_produces_no_invented_max() -> None:
    resp = main._payload_too_large_response("too large", model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["type"] == "payload_too_large"
    assert "limit" not in payload
    assert "x-faigate-request-limit" not in resp.headers


def test_unknown_model_resolves_to_none() -> None:
    limit, estimated = main._resolve_advertised_input_limit("provider/unknown-model")

    assert limit is None
    assert estimated is False


# --------------------------------------------------------------------------- #
# Criterion 3 — the unit is still labelled
# --------------------------------------------------------------------------- #


def test_confirmed_cap_is_labelled_tokens(monkeypatch) -> None:
    _use_bundled_catalog(monkeypatch)
    resp = main._payload_too_large_response("too large", model_id="claude-opus-4-6")

    payload = json.loads(resp.body)
    assert payload["limit"] == 1000000
    assert payload["unit"] == "tokens"


def test_byte_limit_mode_is_labelled_bytes(monkeypatch) -> None:
    monkeypatch.setenv("FAIGATE_UNVERIFIED_CAP_MODE", "byte_limit")

    class _Cfg:
        security = {"max_json_body_bytes": 524288}

    monkeypatch.setattr(main, "_config", _Cfg(), raising=False)

    resp = main._payload_too_large_response("too large", model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["limit"] == 524288
    assert payload["unit"] == "bytes"

    monkeypatch.delenv("FAIGATE_UNVERIFIED_CAP_MODE", raising=False)


def test_explicit_limit_override_is_labelled_tokens() -> None:
    resp = main._payload_too_large_response("too large", limit=4096, model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["limit"] == 4096
    assert payload["unit"] == "tokens"


# --------------------------------------------------------------------------- #
# Model sniffing from an oversized body
# --------------------------------------------------------------------------- #


def test_sniff_recovers_model_from_oversized_body() -> None:
    raw = b'{"model":"claude-opus-4-6","messages":[{"role":"user","content":"x"}]}'

    assert main._sniff_requested_model(raw) == "claude-opus-4-6"


def test_sniff_returns_none_without_model() -> None:
    assert main._sniff_requested_model(b'{"messages":[{"role":"user","content":"x"}]}') is None
    assert main._sniff_requested_model(b"") is None
    assert main._sniff_requested_model(b"\x00\xff\xfe not json") is None


def test_sniffed_model_flows_into_the_413(monkeypatch) -> None:
    _use_bundled_catalog(monkeypatch)
    raw = b'{"model":"claude-opus-4-6","messages":[]}'
    model_id = main._sniff_requested_model(raw)

    resp = main._payload_too_large_response("too large", model_id=model_id)

    payload = json.loads(resp.body)
    assert payload["limit"] == 1000000
    assert payload["unit"] == "tokens"


# --------------------------------------------------------------------------- #
# Criterion 4 — the catalog is the source of truth, the hardcoded map is a fallback
# --------------------------------------------------------------------------- #


def test_hardcoded_fallback_cap_is_unconfirmed() -> None:
    """A cap resolved exclusively from the hardcoded map is ``unconfirmed``.

    The test checks *origin*: when a model id exists only in
    ``_MODEL_INPUT_CAPS`` and not in the catalog's ``model_caps`` block, the
    returned fact must carry ``unconfirmed`` evidence.  A sentinel key that the
    catalog will never contain is used so the assertion stays stable regardless
    of which real model ids graduate from the hardcoded map to the catalog.
    """
    sentinel = "__test_sentinel_hardcoded_only__"
    original_caps = provider_catalog._MODEL_INPUT_CAPS
    provider_catalog._MODEL_INPUT_CAPS = {**original_caps, sentinel: 1000000}
    try:
        fact = provider_catalog.get_model_input_cap_fact(sentinel)
        assert fact is not None
        assert fact["max_input_tokens"] == 1000000
        assert fact["evidence"]["level"] == "unconfirmed", (
            f"hardcoded-only sentinel returned level {fact['evidence']['level']!r}; "
            "a value from _MODEL_INPUT_CAPS must always be unconfirmed"
        )
    finally:
        provider_catalog._MODEL_INPUT_CAPS = original_caps


def test_catalog_sourced_cap_is_confirmed(monkeypatch) -> None:
    _use_bundled_catalog(monkeypatch)
    fact = provider_catalog.get_model_input_cap_fact("claude-opus-4-6")

    assert fact is not None
    assert fact["max_input_tokens"] == 1000000
    assert fact["evidence"]["level"] == "confirmed"
    assert fact["evidence"]["source_url"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
