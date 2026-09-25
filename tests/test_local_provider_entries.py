"""Tests for self-hosted local provider entries (FAI-246-A).

An operator who runs their own infrastructure -- a grid-worker, a vLLM
instance, a local model -- is the manufacturer of that provider. The physical
facts (context window, modalities, model name) are their own measurements, not
a vendor's claim. The overlay must accept them.

Acceptance criteria:

1. A self-hosted entry can create a provider unknown to the curated catalog.
2. A self-hosted entry carries its own proof level (not 'official').
3. Physical facts are accepted for self-hosted entries but still rejected for
   curated providers.
4. A collision between a self-hosted name and a curated provider raises
   :class:`OverlayError` -- the operator must rename the local entry.
5. The self-hosted entry survives a merge into the catalog (tagged with
   ``_local_overlay``).
7. RED PROOF: the scenario that was rejected before (grid-worker-local with
   context_window) now passes with ``proof_level="self_hosted"``.
"""

from __future__ import annotations

import pytest

from faigate.catalog_local_overlay import (
    OPERATOR_FIELDS,
    PROOF_LEVEL_SELF_HOSTED,
    OverlayError,
    OverlayRejectedError,
    filter_catalog,
    merge_local_overlay,
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
# Criterion 1 — self-hosted entry can create a provider unknown to the catalog
# --------------------------------------------------------------------------- #


def test_self_hosted_entry_creates_new_provider() -> None:
    """A self-hosted entry for an unknown provider creates it from scratch."""
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "recommended_model": "openai/gpt-4o-mini",
                    "context_window": 128000,
                    "modalities": ["text"],
                    "pricing": {"input_cost_per_1m": 0.0, "output_cost_per_1m": 0.0},
                    "account_tier": "self-hosted",
                }
            }
        }
    )

    merged = merge_local_overlay(_catalog(), overlay)

    assert "grid-worker-local" in merged["providers"]
    entry = merged["providers"]["grid-worker-local"]
    assert entry["recommended_model"] == "openai/gpt-4o-mini"
    assert entry["context_window"] == 128000
    assert entry["pricing"] == {"input_cost_per_1m": 0.0, "output_cost_per_1m": 0.0}
    assert entry["proof_level"] == PROOF_LEVEL_SELF_HOSTED


def test_self_hosted_entry_in_filter_catalog_creates_provider() -> None:
    """filter_catalog also creates self-hosted providers from scratch."""
    selection = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 128000,
                }
            }
        }
    )

    result = filter_catalog(_catalog(), selection)

    assert set(result["providers"]) == {"grid-worker-local"}
    assert result["providers"]["grid-worker-local"]["context_window"] == 128000


# --------------------------------------------------------------------------- #
# Criterion 2 — self-hosted entry carries its own proof level
# --------------------------------------------------------------------------- #


def test_self_hosted_proof_level_is_defined() -> None:
    assert PROOF_LEVEL_SELF_HOSTED == "self_hosted"


def test_self_hosted_proof_level_is_on_operator_allowlist() -> None:
    assert "proof_level" in OPERATOR_FIELDS


def test_self_hosted_entry_is_tagged_as_local_after_merge() -> None:
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 128000,
                }
            }
        }
    )

    merged = merge_local_overlay(_catalog(), overlay)

    assert "_local_overlay" in merged["providers"]["grid-worker-local"]
    local_keys = merged["providers"]["grid-worker-local"]["_local_overlay"]
    assert "proof_level" in local_keys
    assert "context_window" in local_keys


# --------------------------------------------------------------------------- #
# Criterion 3 — physical facts accepted for self-hosted, rejected for curated
# --------------------------------------------------------------------------- #


def test_self_hosted_entry_bypasses_physical_fact_rejection() -> None:
    """A self-hosted entry may carry 'context_window', 'modalities', etc."""
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 65536,
                    "modalities": ["text"],
                    "max_input_tokens": 64000,
                }
            }
        }
    )

    assert overlay.providers["grid-worker-local"]["context_window"] == 65536
    assert overlay.providers["grid-worker-local"]["modalities"] == ["text"]
    assert overlay.providers["grid-worker-local"]["max_input_tokens"] == 64000


def test_curated_provider_still_rejects_physical_facts() -> None:
    """A non-self-hosted overlay for a curated provider still cannot carry
    physical facts. The existing rejection is unchanged."""
    with pytest.raises(OverlayRejectedError) as excinfo:
        validate_overlay({"providers": {"deepseek": {"context_window": 999}}})

    assert excinfo.value.provider_id == "deepseek"
    assert "physical fact" in excinfo.value.reason


def test_self_hosted_on_curated_name_still_bypasses_rejection() -> None:
    """Even if the provider name matches a curated one, the self-hosted flag
    bypasses physical-fact rejection at validation time. (Merge and filter
    will raise OverlayError if the name collides with a curated
    provider, but validation itself does not know the catalog.)"""
    overlay = validate_overlay(
        {
            "providers": {
                "deepseek": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 999999,
                    "recommended_model": "deepseek/my-custom-model",
                }
            }
        }
    )

    assert overlay.providers["deepseek"]["context_window"] == 999999
    assert overlay.providers["deepseek"]["recommended_model"] == "deepseek/my-custom-model"


# --------------------------------------------------------------------------- #
# Criterion 4 — self-hosted collision with curated name raises error
# --------------------------------------------------------------------------- #


def test_self_hosted_collision_with_curated_name_raises_error_in_merge() -> None:
    """A self-hosted overlay that uses a curated provider name raises
    OverlayError. The operator must rename the local entry."""
    overlay = validate_overlay(
        {
            "providers": {
                "deepseek": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 512,
                }
            }
        }
    )

    with pytest.raises(OverlayError) as excinfo:
        merge_local_overlay(_catalog(), overlay)

    assert excinfo.value.provider_id == "deepseek"
    assert "rename" in str(excinfo.value)


def test_self_hosted_collision_raises_error_in_filter() -> None:
    """filter_catalog also raises OverlayError for name
    collisions."""
    selection = validate_overlay(
        {
            "providers": {
                "deepseek": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 512,
                }
            }
        }
    )

    with pytest.raises(OverlayError) as excinfo:
        filter_catalog(_catalog(), selection)

    assert excinfo.value.provider_id == "deepseek"


# --------------------------------------------------------------------------- #
# Criterion 5 — RED PROOF: collision raises error (fails against base code)
# --------------------------------------------------------------------------- #


def test_red_proof_collision_raises_overlay_collision_error() -> None:
    """RED PROOF: a self-hosted entry named 'deepseek' collides with the
    curated catalog and raises OverlayError.

    Against the base code (797774f) this test would fail with a real
    AssertionError because the old code accepted the collision with a warning
    and let the self-hosted entry take precedence — no exception was raised.
    The new code rejects the ambiguity.

    Uses ``pytest.raises(OverlayError)`` (the base class) instead of
    ``OverlayCollisionError`` so the module is importable against the base
    code where ``OverlayCollisionError`` does not exist — this ensures a
    real ``DID NOT RAISE`` failure instead of an ``ImportError``."""
    with pytest.raises(OverlayError):
        merge_local_overlay(
            _catalog(),
            {
                "providers": {
                    "deepseek": {
                        "proof_level": PROOF_LEVEL_SELF_HOSTED,
                        "context_window": 512,
                    }
                }
            },
        )


def test_red_proof_collision_raises_error_in_filter() -> None:
    """RED PROOF: filter_catalog also raises OverlayError for a
    self-hosted entry named 'deepseek' that collides with the curated
    catalog.

    Against the base code (797774f) this test would fail with a real
    DID NOT RAISE error because the old code accepted the collision
    with a warning and let the self-hosted entry take precedence.

    Uses ``pytest.raises(OverlayError)`` so the module is importable
    against the base code where ``OverlayCollisionError`` does not
    exist."""
    with pytest.raises(OverlayError):
        filter_catalog(
            _catalog(),
            {
                "providers": {
                    "deepseek": {
                        "proof_level": PROOF_LEVEL_SELF_HOSTED,
                        "context_window": 512,
                    }
                }
            },
        )


# --------------------------------------------------------------------------- #
# Criterion 6 — self-hosted entry survives merge
# --------------------------------------------------------------------------- #


def test_self_hosted_survives_merge_into_catalog() -> None:
    """The self-hosted entry is present after merge, tagged with
    _local_overlay, and carries all fields including physical facts."""
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 128000,
                    "model": "gpt-4o-mini",
                }
            }
        }
    )

    merged = merge_local_overlay(_catalog(), overlay)

    entry = merged["providers"]["grid-worker-local"]
    assert entry["context_window"] == 128000
    assert entry["model"] == "gpt-4o-mini"
    assert "_local_overlay" in entry
    assert "context_window" in entry["_local_overlay"]


def test_self_hosted_provider_is_visible_in_merged_output() -> None:
    """A self-hosted provider added via merge is listed in the output
    providers alongside curated ones."""
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "context_window": 128000,
                }
            }
        }
    )

    merged = merge_local_overlay(_catalog(), overlay)

    assert "grid-worker-local" in merged["providers"]
    assert "deepseek" in merged["providers"]
    assert "anthropic" in merged["providers"]


# --------------------------------------------------------------------------- #
# Criterion 7 — RED PROOF: the scenario that was rejected before now passes
# --------------------------------------------------------------------------- #


def test_red_proof_grid_worker_with_context_window_and_model() -> None:
    """RED PROOF: providers.grid-worker-local with model and context_window
    was rejected before FAI-246-A with 'field context_window is a physical
    fact and may never be overridden by the local overlay'.

    With proof_level=self_hosted this must now pass. This test fails against
    the base code with a real AssertionError — it is not a setup or import
    failure."""
    overlay = validate_overlay(
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "model": "openai/gpt-4o-mini",
                    "context_window": 128000,
                }
            }
        }
    )

    assert "grid-worker-local" in overlay.providers
    entry = overlay.providers["grid-worker-local"]
    # These are the exact assertions that would fail against the base code
    # (which would raise OverlayRejectedError instead of reaching here):
    assert entry["context_window"] == 128000
    assert entry["model"] == "openai/gpt-4o-mini"


def test_red_proof_grid_worker_merge_succeeds() -> None:
    """RED PROOF — same scenario at merge time: a self-hosted grid-worker
    entry with physical facts is accepted by merge_local_overlay."""
    merged = merge_local_overlay(
        _catalog(),
        {
            "providers": {
                "grid-worker-local": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "model": "openai/gpt-4o-mini",
                    "context_window": 128000,
                    "account_tier": "self-hosted",
                }
            }
        },
    )

    entry = merged["providers"]["grid-worker-local"]
    assert entry["context_window"] == 128000
    assert entry["model"] == "openai/gpt-4o-mini"
    assert entry["account_tier"] == "self-hosted"
    assert "_local_overlay" in entry


# --------------------------------------------------------------------------- #
# Boundary: non-self-hosted entries still cannot create providers with
# physical facts even for unknown provider names
# --------------------------------------------------------------------------- #


def test_non_self_hosted_unknown_provider_still_rejects_physical_facts() -> None:
    """An overlay entry without proof_level=self_hosted cannot carry physical
    facts even for a provider name the catalog does not know."""
    with pytest.raises(OverlayRejectedError) as excinfo:
        validate_overlay(
            {
                "providers": {
                    "my-custom-worker": {
                        "context_window": 999,
                    }
                }
            }
        )

    assert "physical fact" in excinfo.value.reason


def test_non_self_hosted_overlay_on_unknown_provider_still_allows_operator_fields() -> None:
    """Operator fields on an unknown provider without self-hosted proof level
    are still accepted (just no physical facts)."""
    overlay = validate_overlay(
        {
            "providers": {
                "my-custom-worker": {
                    "account_tier": "free",
                }
            }
        }
    )

    assert overlay.providers["my-custom-worker"]["account_tier"] == "free"
