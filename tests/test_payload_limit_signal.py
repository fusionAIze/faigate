"""Acceptance tests for the 413 input-cap signal (TASK-D3).

The gateway's payload-too-large response must report the cap of the *requested
model*, never the provider-wide ``max()`` placeholder (262144). Three things are
pinned here:

1. A request whose model has a hard ``belegt`` cap reports that model's cap when
   the ingress 413 fires — the value a client can plan against.
2. A model without a ``belegt`` cap falls back to the b2 rule (passthrough or the
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


def test_resolve_reports_the_requested_models_cap() -> None:
    limit, estimated = main._resolve_advertised_input_limit("deepseek-v4-flash")

    assert limit == 1000000
    assert estimated is False


def test_413_reports_the_requested_models_cap() -> None:
    resp = main._payload_too_large_response("too large", model_id="deepseek-v4-flash")

    payload = json.loads(resp.body)
    assert payload["type"] == "payload_too_large"
    assert payload["limit"] == 1000000
    assert resp.headers["x-faigate-request-limit"] == "1000000"


# --------------------------------------------------------------------------- #
# Criterion 2 — no belegt cap: b2 rule, no max()
# --------------------------------------------------------------------------- #


def test_no_belegt_cap_produces_no_invented_max() -> None:
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


def test_belegt_cap_is_labelled_tokens() -> None:
    resp = main._payload_too_large_response("too large", model_id="deepseek-v4-flash")

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
    raw = b'{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"x"}]}'

    assert main._sniff_requested_model(raw) == "deepseek-v4-flash"


def test_sniff_returns_none_without_model() -> None:
    assert main._sniff_requested_model(b'{"messages":[{"role":"user","content":"x"}]}') is None
    assert main._sniff_requested_model(b"") is None
    assert main._sniff_requested_model(b"\x00\xff\xfe not json") is None


def test_sniffed_model_flows_into_the_413() -> None:
    raw = b'{"model":"deepseek-v4-flash","messages":[]}'
    model_id = main._sniff_requested_model(raw)

    resp = main._payload_too_large_response("too large", model_id=model_id)

    payload = json.loads(resp.body)
    assert payload["limit"] == 1000000
    assert payload["unit"] == "tokens"


# --------------------------------------------------------------------------- #
# Criterion 4 — the curated caps are still the source of truth
# --------------------------------------------------------------------------- #


def test_deepseek_v4_flash_cap_is_belegt() -> None:
    fact = provider_catalog.get_model_input_cap_fact("deepseek-v4-flash")

    assert fact is not None
    assert fact["max_input_tokens"] == 1000000
    assert fact["evidence"]["level"] == "belegt"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
