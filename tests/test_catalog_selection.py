"""Tests for the catalog selection/filter mechanism (FAI-245-C).

An operator may configure a local selection that names which providers and
which operator fields should be visible. The selection:

1. Filters the catalog to only the named providers — any provider absent from
   the selection is dropped from the result.
2. Applies local overlay fields (``account_tier``, ``key_limits``, ``quota``)
   onto each selected provider.
3. Tags each provider entry that received local fields with a
   ``_local_overlay`` key so consumers can distinguish operator-bound facts.
4. Rejects physical facts the same way ``merge_local_overlay`` does.
"""

from __future__ import annotations

import pytest

from faigate.catalog_local_overlay import (
    OverlayRejectedError,
    filter_catalog,
    validate_overlay,
)


def _catalog() -> dict:
    return {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": {
            "deepseek": {
                "recommended_model": "deepseek/deepseek-v4-flash",
                "context_window": 128000,
                "modalities": ["text"],
                "pricing": {"input_cost_per_1m": 0.28, "output_cost_per_1m": 0.42},
            },
            "anthropic": {
                "recommended_model": "anthropic/claude-opus-4-7",
                "context_window": 200000,
                "pricing": {"input_cost_per_1m": 5.0, "output_cost_per_1m": 25.0},
            },
            "openai": {
                "recommended_model": "openai/gpt-4o",
                "context_window": 128000,
                "pricing": {"input_cost_per_1m": 2.5, "output_cost_per_1m": 10.0},
            },
        },
    }


# --------------------------------------------------------------------------- #
# Criterion 1 — providers absent from the selection are dropped
# --------------------------------------------------------------------------- #


def test_filter_drops_unselected_providers() -> None:
    selection = validate_overlay({"providers": {"deepseek": {"account_tier": "pro"}}})

    result = filter_catalog(_catalog(), selection)

    assert set(result["providers"]) == {"deepseek"}


def test_filter_keeps_selected_providers_with_catalog_facts() -> None:
    selection = validate_overlay({"providers": {"deepseek": {"account_tier": "pro"}, "openai": {}}})

    result = filter_catalog(_catalog(), selection)

    assert set(result["providers"]) == {"deepseek", "openai"}
    # Catalog facts survive for a provider with an empty overlay.
    assert result["providers"]["openai"]["context_window"] == 128000


def test_filter_with_empty_selection_returns_empty_providers() -> None:
    selection = validate_overlay({"providers": {}})

    result = filter_catalog(_catalog(), selection)

    assert result["providers"] == {}


def test_filter_handles_catalog_with_no_providers() -> None:
    empty_catalog = {"schema_version": "fusionaize-provider-catalog/v1.2", "providers": {}}
    selection = validate_overlay({"providers": {"deepseek": {"account_tier": "pro"}}})

    result = filter_catalog(empty_catalog, selection)

    assert result["providers"] == {"deepseek": {"account_tier": "pro", "_local_overlay": ["account_tier"]}}


# --------------------------------------------------------------------------- #
# Criterion 2 — local overlay fields are applied and tagged
# --------------------------------------------------------------------------- #


def test_local_overlay_fields_appear_in_filtered_output() -> None:
    selection = validate_overlay(
        {
            "providers": {
                "deepseek": {
                    "account_tier": "pro",
                    "quota": {"tokens_per_day": 500000},
                }
            }
        }
    )

    result = filter_catalog(_catalog(), selection)

    deepseek = result["providers"]["deepseek"]
    assert deepseek["account_tier"] == "pro"
    assert deepseek["quota"] == {"tokens_per_day": 500000}
    # Catalog facts still present
    assert deepseek["context_window"] == 128000


def test_local_overlay_field_names_are_tracked() -> None:
    selection = validate_overlay({"providers": {"deepseek": {"account_tier": "pro", "key_limits": {"rpm": 60}}}})

    result = filter_catalog(_catalog(), selection)

    assert result["providers"]["deepseek"]["_local_overlay"] == ["account_tier", "key_limits"]


def test_provider_without_local_fields_has_no_overlay_tag() -> None:
    selection = validate_overlay({"providers": {"deepseek": {}, "openai": {"account_tier": "free"}}})

    result = filter_catalog(_catalog(), selection)

    # deepseek has no overlay fields — no _local_overlay key.
    assert "_local_overlay" not in result["providers"]["deepseek"]
    # openai has overlay fields — _local_overlay is present.
    assert result["providers"]["openai"]["_local_overlay"] == ["account_tier"]


# --------------------------------------------------------------------------- #
# Criterion 3 — physical facts are rejected (same as merge_local_overlay)
# --------------------------------------------------------------------------- #


def test_physical_fact_in_selection_is_rejected() -> None:
    with pytest.raises(OverlayRejectedError) as excinfo:
        filter_catalog(
            _catalog(),
            {"providers": {"deepseek": {"context_window": 999}}},
        )

    assert excinfo.value.provider_id == "deepseek"
    assert excinfo.value.field_name == "context_window"


def test_unknown_field_in_selection_is_rejected() -> None:
    with pytest.raises(OverlayRejectedError) as excinfo:
        filter_catalog(
            _catalog(),
            {"providers": {"deepseek": {"banana": True}}},
        )

    assert "not on the operator-field allowlist" in excinfo.value.reason


def test_hand_built_local_overlay_cannot_smuggle_physical_fact() -> None:
    from faigate.catalog_local_overlay import LocalOverlay

    sneaky = LocalOverlay(providers={"deepseek": {"pricing": {"input_cost_per_1m": 0.01}}})

    with pytest.raises(OverlayRejectedError):
        filter_catalog(_catalog(), sneaky)


# --------------------------------------------------------------------------- #
# Criterion 4 — determinism
# --------------------------------------------------------------------------- #


def test_filter_is_deterministic_across_input_ordering() -> None:
    import json

    sel_a = {"providers": {"anthropic": {"account_tier": "team"}, "deepseek": {"account_tier": "pro"}}}
    sel_b = {"providers": {"deepseek": {"account_tier": "pro"}, "anthropic": {"account_tier": "team"}}}

    result_a = filter_catalog(_catalog(), sel_a)
    result_b = filter_catalog(_catalog(), sel_b)

    assert result_a == result_b
    assert json.dumps(result_a, sort_keys=True) == json.dumps(result_b, sort_keys=True)


def test_filter_output_providers_are_sorted() -> None:
    selection = validate_overlay({"providers": {"openai": {}, "anthropic": {}, "deepseek": {"account_tier": "pro"}}})

    result = filter_catalog(_catalog(), selection)

    assert list(result["providers"]) == sorted(result["providers"])


# --------------------------------------------------------------------------- #
# Criterion 5 — the original catalog is never mutated
# --------------------------------------------------------------------------- #


def test_filter_does_not_mutate_catalog() -> None:
    catalog = _catalog()
    selection = validate_overlay({"providers": {"deepseek": {"account_tier": "pro"}}})

    filter_catalog(catalog, selection)

    assert "account_tier" not in catalog["providers"]["deepseek"]
    assert "account_tier" not in catalog["providers"]
