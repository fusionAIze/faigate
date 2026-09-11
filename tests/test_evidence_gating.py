"""Acceptance tests for evidence-gated input-cap enforcement (TASK-B2 + TASK-B3).

The catalog carries per-model input caps as facts tagged with ``evidence.level``
on the three-step scale ``unconfirmed < plausible < confirmed``. The gateway must
let that scale decide what a 413 may advertise:

* ``confirmed``     -> hard decision, the cap is exposed unchanged.
* ``plausible``  -> best-effort, the cap is exposed but flagged as an estimate.
* ``unconfirmed`` -> invisible: no 413 is produced from it, no number is
  invented in its place. Instead the request passes through to the provider,
  or falls back to the operator-configured byte limit, per
  ``FAIGATE_UNVERIFIED_CAP_MODE``.

These tests pin the two TASK-B2 criteria and the three TASK-B3 criteria around
``faigate.main._resolve_advertised_input_limit`` and
``faigate.main._payload_too_large_response``. The split itself is delegated to
``faigate.catalog_views.split_catalog_facts`` — there is no second piece of
view-splitting logic in the gateway.
"""

from __future__ import annotations

import json

import pytest

import faigate.main as main
from faigate import provider_catalog


def _fact(level: str, cap: int = 1000000) -> dict[str, object]:
    return {
        "max_input_tokens": cap,
        "evidence": {"level": level, "source_url": "https://example.test", "as_of": "2026-08-21"},
    }


# --------------------------------------------------------------------------- #
# TASK-B2 criterion 1 — unconfirmed produces no 413 from that cap
# --------------------------------------------------------------------------- #


def test_unconfirmed_cap_is_invisible(monkeypatch) -> None:
    monkeypatch.setattr(provider_catalog, "get_model_input_cap_fact", lambda model_id: _fact("unconfirmed"))

    limit, estimated = main._resolve_advertised_input_limit("some-model")

    assert limit is None
    assert estimated is False


def test_missing_cap_is_invisible() -> None:
    limit, estimated = main._resolve_advertised_input_limit("provider/not-a-binding-model")

    assert limit is None
    assert estimated is False


# --------------------------------------------------------------------------- #
# TASK-B2 criterion 2 — plausible is flagged to the client as an estimate
# --------------------------------------------------------------------------- #


def test_plausible_cap_is_flagged_as_estimate(monkeypatch) -> None:
    monkeypatch.setattr(provider_catalog, "get_model_input_cap_fact", lambda model_id: _fact("plausible", 200000))

    resp = main._payload_too_large_response("too large", model_id="some-model")

    payload = json.loads(resp.body)
    assert payload["limit"] == 200000
    assert payload.get("estimated") is True
    assert resp.headers["x-faigate-request-limit"] == "~200000"


# --------------------------------------------------------------------------- #
# TASK-B2 criterion 3 — confirmed acts unchanged
# --------------------------------------------------------------------------- #


def test_confirmed_cap_acts_unchanged(monkeypatch) -> None:
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)
    assert provider_catalog.get_model_max_input_tokens("claude-opus-4-6") == 1000000

    limit, estimated = main._resolve_advertised_input_limit("claude-opus-4-6")

    assert limit == 1000000
    assert estimated is False


def test_confirmed_cap_is_surfaced_without_estimate_flag(monkeypatch) -> None:
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)
    resp = main._payload_too_large_response("too large", model_id="claude-opus-4-6")

    payload = json.loads(resp.body)
    assert payload["limit"] == 1000000
    assert "estimated" not in payload
    assert resp.headers["x-faigate-request-limit"] == "1000000"


# --------------------------------------------------------------------------- #
# TASK-B3 criterion 1 — no max() placeholder in the 413 for a capped-less model
# --------------------------------------------------------------------------- #


def test_no_confirmed_cap_produces_no_invented_limit() -> None:
    resp = main._payload_too_large_response("too large", model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["type"] == "payload_too_large"
    assert "limit" not in payload
    assert "x-faigate-request-limit" not in resp.headers


def test_no_confirmed_cap_defaults_to_passthrough(monkeypatch) -> None:
    monkeypatch.delenv("FAIGATE_UNVERIFIED_CAP_MODE", raising=False)

    limit, estimated = main._resolve_advertised_input_limit("provider/unknown-model")

    assert limit is None
    assert main._unverified_cap_mode() == "passthrough"


# --------------------------------------------------------------------------- #
# TASK-B3 criterion 2 — the chosen path is configurable (passthrough / byte limit)
# --------------------------------------------------------------------------- #


def test_unverified_cap_mode_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("FAIGATE_UNVERIFIED_CAP_MODE", "byte_limit")
    assert main._unverified_cap_mode() == "byte_limit"

    monkeypatch.setenv("FAIGATE_UNVERIFIED_CAP_MODE", "passthrough")
    assert main._unverified_cap_mode() == "passthrough"


def test_byte_limit_mode_reports_operator_byte_limit(monkeypatch) -> None:
    monkeypatch.setenv("FAIGATE_UNVERIFIED_CAP_MODE", "byte_limit")

    class _Cfg:
        security = {"max_json_body_bytes": 524288}

    monkeypatch.setattr(main, "_config", _Cfg(), raising=False)

    resp = main._payload_too_large_response("too large", model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["limit"] == 524288
    assert "estimated" not in payload
    assert resp.headers["x-faigate-request-limit"] == "524288"

    monkeypatch.delenv("FAIGATE_UNVERIFIED_CAP_MODE", raising=False)


def test_explicit_limit_override_still_wins(monkeypatch) -> None:
    resp = main._payload_too_large_response("too large", limit=4096, model_id="provider/unknown-model")

    payload = json.loads(resp.body)
    assert payload["limit"] == 4096
    assert "estimated" not in payload


# --------------------------------------------------------------------------- #
# TASK-B3 criterion 3 — RED PROOF: the base advertised the placeholder 262144
# --------------------------------------------------------------------------- #


def test_base_advertised_the_262144_placeholder_is_replaced() -> None:
    """Pin that the provider-wide 262144 placeholder is gone from the 413 path.

    On the base commit the byte-rejection 413 surfaced ``limit == 262144`` (the
    ``max()`` over the flat provider floor) regardless of the model. After this
    change that invented number is never produced for a model without a hard
    ``confirmed`` cap: the limit is absent under ``passthrough`` and equals the
    operator byte limit under ``byte_limit``.
    """
    # No providers are consulted anymore: the placeholder aggregation path is gone.
    resp = main._payload_too_large_response("too large")

    payload = json.loads(resp.body)
    assert payload.get("limit") != 262144
    assert "limit" not in payload


def test_hardcoded_fallback_caps_are_unconfirmed() -> None:
    """Every hardcoded fallback cap is an ``unconfirmed`` fact, never ``confirmed``.

    The ``_MODEL_INPUT_CAPS`` map is an offline fallback with no per-value
    source, so it must not carry a stronger evidence label than the catalog. A
    sourced catalog fact is ``confirmed``; a hardcoded value without a source is the
    oldest unverified fact in the system and is labelled ``unconfirmed``.
    """
    for model_id in provider_catalog._MODEL_INPUT_CAPS:
        fact = provider_catalog.get_model_input_cap_fact(model_id)
        assert fact is not None, f"{model_id!r} must carry an evidence-tagged cap fact"
        assert fact["evidence"]["level"] == "unconfirmed"
        assert "source_url" not in fact["evidence"]
        assert fact["max_input_tokens"] == provider_catalog.get_model_max_input_tokens(model_id)


def test_unknown_model_cap_fact_is_none() -> None:
    assert provider_catalog.get_model_input_cap_fact("provider/not-a-binding-model") is None
    assert provider_catalog.get_model_input_cap_fact("") is None
    assert provider_catalog.get_model_input_cap_fact(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
