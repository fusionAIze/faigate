"""Acceptance tests for the local operator overlay (TASK-D6).

Operator-bound facts -- quota, account tier, key-bound limits -- belong to
the operator's account, not to a repository. ``faigate.catalog_local_overlay``
keeps them in a gitignored local file with the same shape as the catalog and
merges them in memory.

The three TASK-D6 criteria pinned here:

1. Operator facts take effect locally and never appear in a repo.
2. An overlay that tries to override a physical fact is *rejected*.
3. The merge is deterministic and covered by these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faigate.catalog_local_overlay import (
    DEFAULT_OVERLAY_PATH,
    OPERATOR_FIELDS,
    OverlayError,
    OverlayRejectedError,
    load_overlay,
    merge_local_overlay,
    overlay_path,
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
        },
    }


# --------------------------------------------------------------------------- #
# Criterion 1 — operator facts take effect, and stay local
# --------------------------------------------------------------------------- #


def test_operator_facts_are_merged_into_their_provider() -> None:
    overlay = validate_overlay(
        {
            "providers": {
                "deepseek": {
                    "account_tier": "pro",
                    "quota": {"tokens_per_day": 500000},
                    "key_limits": {"requests_per_minute": 60},
                }
            }
        }
    )

    merged = merge_local_overlay(_catalog(), overlay)
    deepseek = merged["providers"]["deepseek"]

    assert deepseek["account_tier"] == "pro"
    assert deepseek["quota"] == {"tokens_per_day": 500000}
    assert deepseek["key_limits"] == {"requests_per_minute": 60}


def test_default_overlay_path_is_outside_any_repo_checkout() -> None:
    # The default lives under the user cache directory, so it is runtime
    # state and can never be committed from a checkout.
    assert "catalog-local-overlay" in DEFAULT_OVERLAY_PATH.name
    assert ".cache" in DEFAULT_OVERLAY_PATH.parts


def test_overlay_path_env_override_is_respected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "operator-overlay.json"
    monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(custom))

    assert overlay_path() == custom
    assert ".cache" not in overlay_path().parts


def test_load_missing_overlay_is_empty_not_an_error(tmp_path: Path) -> None:
    overlay = load_overlay(tmp_path / "does-not-exist.json")

    assert overlay.is_empty()
    assert overlay.providers == {}


def test_load_local_overlay_from_disk(tmp_path: Path) -> None:
    target = tmp_path / "local.json"
    target.write_text(
        json.dumps({"providers": {"deepseek": {"account_tier": "free"}}}),
        encoding="utf-8",
    )

    overlay = load_overlay(target)

    assert overlay.providers == {"deepseek": {"account_tier": "free"}}
    assert overlay.source == str(target)


def test_overlay_does_not_leak_into_the_catalog_input() -> None:
    catalog = _catalog()
    overlay = validate_overlay({"providers": {"deepseek": {"account_tier": "pro"}}})

    merged = merge_local_overlay(catalog, overlay)

    # The original catalog mapping is untouched; the overlay only exists in
    # the returned copy.
    assert "account_tier" not in catalog["providers"]["deepseek"]
    assert merged["providers"]["deepseek"]["account_tier"] == "pro"
    assert merged is not catalog


# --------------------------------------------------------------------------- #
# Criterion 2 — a physical-fact override is rejected, not silently dropped
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "field_name",
    ["context_window", "modalities", "pricing", "max_input_tokens"],
)
def test_physical_fact_override_is_rejected(field_name: str) -> None:
    with pytest.raises(OverlayRejectedError) as excinfo:
        validate_overlay({"providers": {"deepseek": {field_name: 123}}})

    error = excinfo.value
    assert error.provider_id == "deepseek"
    assert error.field_name == field_name
    assert "physical fact" in error.reason


def test_rejection_happens_at_merge_time_for_raw_mappings() -> None:
    with pytest.raises(OverlayRejectedError):
        merge_local_overlay(_catalog(), {"providers": {"deepseek": {"context_window": 999}}})


def test_unknown_field_is_rejected_as_not_allowlisted() -> None:
    with pytest.raises(OverlayRejectedError) as excinfo:
        validate_overlay({"providers": {"deepseek": {"banana": True}}})

    assert "not on the operator-field allowlist" in excinfo.value.reason


def test_hand_built_overlay_cannot_smuggle_a_physical_fact_past_validation() -> None:
    from faigate.catalog_local_overlay import LocalOverlay

    sneaky = LocalOverlay(providers={"deepseek": {"context_window": 999999}})

    with pytest.raises(OverlayRejectedError):
        merge_local_overlay(_catalog(), sneaky)


def test_non_mapping_provider_entry_is_rejected() -> None:
    with pytest.raises(OverlayRejectedError):
        validate_overlay({"providers": {"deepseek": ["account_tier"]}})


def test_invalid_json_raises_overlay_error(tmp_path: Path) -> None:
    target = tmp_path / "broken.json"
    target.write_text("{ not json", encoding="utf-8")

    with pytest.raises(OverlayError):
        load_overlay(target)


def test_allowlist_is_the_documented_operator_field_set() -> None:
    assert OPERATOR_FIELDS == ("account_tier", "key_limits", "quota")
    # No physical fact may appear on the allowlist.
    assert "context_window" not in OPERATOR_FIELDS
    assert "pricing" not in OPERATOR_FIELDS


# --------------------------------------------------------------------------- #
# Criterion 3 — the merge is deterministic
# --------------------------------------------------------------------------- #


def test_merge_is_deterministic_across_input_ordering() -> None:
    overlay_a = {
        "providers": {
            "anthropic": {"account_tier": "team"},
            "deepseek": {"account_tier": "pro", "quota": {"tokens_per_day": 1}},
        }
    }
    overlay_b = {
        "providers": {
            "deepseek": {"quota": {"tokens_per_day": 1}, "account_tier": "pro"},
            "anthropic": {"account_tier": "team"},
        }
    }

    merged_a = merge_local_overlay(_catalog(), overlay_a)
    merged_b = merge_local_overlay(_catalog(), overlay_b)

    assert merged_a == merged_b
    assert json.dumps(merged_a, sort_keys=True) == json.dumps(merged_b, sort_keys=True)


def test_merge_output_provider_order_is_sorted() -> None:
    overlay = {"providers": {"deepseek": {"account_tier": "pro"}}}

    merged = merge_local_overlay(_catalog(), overlay)

    assert list(merged["providers"]) == sorted(merged["providers"])


def test_merge_of_empty_overlay_preserves_catalog_providers() -> None:
    catalog = _catalog()

    merged = merge_local_overlay(catalog, {"providers": {}})

    assert set(merged["providers"]) == set(catalog["providers"])
    assert merged["providers"]["deepseek"]["context_window"] == 128000


def test_overlay_can_add_a_provider_absent_from_the_catalog() -> None:
    merged = merge_local_overlay(
        _catalog(),
        {"providers": {"local-worker": {"account_tier": "self-hosted"}}},
    )

    assert merged["providers"]["local-worker"] == {"account_tier": "self-hosted"}
