"""Acceptance tests for model lifecycle extraction from probe data.

FAI-239-A: The provider catalog must carry lifecycle status sourced from the
same /models probe infrastructure established in FAI-238-A, and must handle
the BytePlus case where:
1. Per-model lifecycle status is extracted from probe data
2. Short names (model_id) and versioned IDs are both recorded when they differ
3. Shutdown/retiring models remain visible and usable, not silently dropped
4. Duplicate short names with different statuses are detected and reported
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "models_probe"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}_models.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_model_lifecycles(models_data: dict) -> list[dict]:
    """Lazy import wrapper for RED PROOF compatibility."""
    from faigate.capability_probe import extract_model_lifecycles as _f

    return _f(models_data, status_field="status")


def _build_provider_lifecycle_catalog(probe_data: dict) -> dict:
    """Lazy import wrapper for RED PROOF compatibility."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog as _f

    return _f(probe_data)


# --------------------------------------------------------------------------- #
# Criterion 1: lifecycle im Katalog, gespeist aus derselben Probe wie FAI-238-A
# --------------------------------------------------------------------------- #


def test_lifecycle_extracted_from_byteplus_probe() -> None:
    """Lifecycle status is extracted from the same BytePlus probe fixture
    that FAI-238-A uses for context-window probing."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)
    assert len(entries) > 0, "Must extract lifecycle entries from probe data"

    # Every entry must carry model_id and status
    for entry in entries:
        assert "model_id" in entry, f"Missing model_id in entry: {entry}"
        assert "status" in entry, f"Missing status in entry: {entry}"
        assert entry["status"] in ("Active", "Retiring", "Shutdown"), (
            f"Unexpected status {entry['status']!r} for {entry['model_id']!r}"
        )


def test_lifecycle_counts_match_report() -> None:
    """BytePlus reports 28 Active, 17 Retiring, 13 Shutdown = 58 models."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})
    assert "byteplus" in catalog

    lc = catalog["byteplus"]["lifecycle"]
    assert lc["active"] == 28, f"Expected 28 active, got {lc['active']}"
    assert lc["retiring"] == 17, f"Expected 17 retiring, got {lc['retiring']}"
    assert lc["shutdown"] == 13, f"Expected 13 shutdown, got {lc['shutdown']}"
    assert lc["total"] == 58, f"Expected 58 total, got {lc['total']}"


def test_lifecycle_uses_same_fixture_as_context_window() -> None:
    """The lifecycle probe consumes the same fixture files as the context-window
    probe — no separate data source."""
    byteplus = _load_fixture("byteplus")
    deepseek = _load_fixture("deepseek")
    openrouter = _load_fixture("openrouter")
    mistral = _load_fixture("mistral")
    nvidia = _load_fixture("nvidia")

    # All must be processable by the lifecycle extractor
    for name, data in [
        ("byteplus", byteplus),
        ("deepseek", deepseek),
        ("openrouter", openrouter),
        ("mistral", mistral),
        ("nvidia", nvidia),
    ]:
        entries = _extract_model_lifecycles(data)
        assert isinstance(entries, list), f"{name}: expected list, got {type(entries)}"
        # Even providers without a status field produce entries (status="")
        assert len(entries) > 0, f"{name}: expected at least one entry"


def test_lifecycle_catalog_from_probe() -> None:
    """build_provider_lifecycle_catalog creates a lifecycle catalog from
    probe data, the same way build_probed_window_summary works for context
    windows."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    assert "byteplus" in catalog
    assert "models" in catalog["byteplus"]
    assert "lifecycle" in catalog["byteplus"]
    assert "ambiguous_names" in catalog["byteplus"]
    assert len(catalog["byteplus"]["models"]) == 58


# --------------------------------------------------------------------------- #
# Criterion 2: Name und versionierte ID — der Katalog führt beide
# --------------------------------------------------------------------------- #


def test_versioned_id_recorded_when_present() -> None:
    """When a model carries a versioned_id that differs from its model_id,
    both are recorded in the lifecycle entry."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)

    # Find the seed-2-0-lite entries — they have versioned_ids
    seed_entries = [e for e in entries if e["model_id"] == "seed-2-0-lite"]
    assert len(seed_entries) == 2, f"Expected 2 seed-2-0-lite entries, got {len(seed_entries)}"

    for entry in seed_entries:
        assert "versioned_id" in entry, f"seed-2-0-lite entry missing versioned_id: {entry}"
        # Each must have a versioned_id different from model_id
        assert entry["versioned_id"] != entry["model_id"], f"versioned_id should differ from model_id: {entry}"


def test_catalog_reports_versioned_id_vs_short_name() -> None:
    """The lifecycle catalog includes versioned_id alongside model_id so
    consumers can distinguish which concrete version is meant."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    models = catalog["byteplus"]["models"]
    versioned = [m for m in models if "versioned_id" in m]
    assert len(versioned) == 2, f"Expected exactly 2 versioned models (seed-2-0-lite x2), got {len(versioned)}"
    for entry in versioned:
        assert entry["versioned_id"] != entry["model_id"]


def test_short_name_is_ambiguous_flagged() -> None:
    """When a short name maps to multiple versioned IDs, ambiguous_names
    flags the conflict."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    ambiguous = catalog["byteplus"]["ambiguous_names"]
    assert len(ambiguous) == 1, f"Expected 1 ambiguous name group, got {len(ambiguous)}"
    entry = ambiguous[0]
    assert entry["model_id"] == "seed-2-0-lite"
    assert "Active" in entry["statuses"]
    assert "Retiring" in entry["statuses"]
    assert len(entry["entries"]) == 2

    # The note should explain the ambiguity
    assert "ambiguous" in entry["note"].lower()


# --------------------------------------------------------------------------- #
# Criterion 3: Abgekündigte Modelle bleiben sichtbar und nutzbar
# --------------------------------------------------------------------------- #


def test_shutdown_models_appear_in_catalog() -> None:
    """Models with Shutdown status are listed in the lifecycle catalog,
    not silently dropped."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    shutdown_models = catalog["byteplus"]["lifecycle"]["shutdown_models"]
    assert len(shutdown_models) == 13, f"Expected 13 shutdown models, got {len(shutdown_models)}"
    assert "gpt-4" in shutdown_models, "gpt-4 should be listed as shutdown"
    assert "claude-2" in shutdown_models, "claude-2 should be listed as shutdown"


def test_retiring_models_appear_in_catalog() -> None:
    """Models with Retiring status are listed, not dropped."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    retiring_models = catalog["byteplus"]["lifecycle"]["retiring_models"]
    assert len(retiring_models) == 17, f"Expected 17 retiring models, got {len(retiring_models)}"
    assert "deepseek-v2" in retiring_models
    assert "llama-2-70b" in retiring_models


def test_total_includes_all_statuses() -> None:
    """The total model count equals active + retiring + shutdown,
    proving no models are silently excluded."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    lc = catalog["byteplus"]["lifecycle"]
    assert lc["total"] == lc["active"] + lc["retiring"] + lc["shutdown"], (
        f"Total {lc['total']} != {lc['active']} + {lc['retiring']} + {lc['shutdown']}"
    )


# --------------------------------------------------------------------------- #
# Criterion 4: Doppeleintrag-Fall an aufgezeichneten Antworten belegt
# --------------------------------------------------------------------------- #


def test_seed_2_0_lite_duplicate_detected() -> None:
    """seed-2-0-lite appears twice in the BytePlus /models response:
    once as Active (versioned_id seed-2-0-lite-240701) and once as
    Retiring (versioned_id seed-2-0-lite-231201). Both are extracted
    and the ambiguity is reported."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)

    seed_entries = [e for e in entries if e["model_id"] == "seed-2-0-lite"]
    assert len(seed_entries) == 2, f"seed-2-0-lite should appear twice, got {len(seed_entries)} entries"

    active = [e for e in seed_entries if e["status"] == "Active"]
    retiring = [e for e in seed_entries if e["status"] == "Retiring"]
    assert len(active) == 1, f"Expected 1 Active seed-2-0-lite, got {len(active)}"
    assert len(retiring) == 1, f"Expected 1 Retiring seed-2-0-lite, got {len(retiring)}"

    # Verify versioned_ids
    assert active[0].get("versioned_id") == "seed-2-0-lite-240701"
    assert retiring[0].get("versioned_id") == "seed-2-0-lite-231201"


def test_empty_probe_data_returns_empty_catalog() -> None:
    """An empty probe data dict produces an empty lifecycle catalog."""
    catalog = _build_provider_lifecycle_catalog({})
    assert catalog == {}


def test_none_probe_data_returns_empty_catalog() -> None:
    """None probe data produces an empty lifecycle catalog."""
    catalog = _build_provider_lifecycle_catalog(None)
    assert catalog == {}


def test_empty_data_list_returns_no_entries() -> None:
    """A /models response with an empty data array yields no entries."""
    entries = _extract_model_lifecycles({"data": []})
    assert entries == []


def test_non_dict_models_data_returns_empty() -> None:
    """Non-dict models_data returns an empty list."""
    entries = _extract_model_lifecycles(None)  # type: ignore[arg-type]
    assert entries == []


# --------------------------------------------------------------------------- #
# RED PROOF: empty candidate set must fail the test
# --------------------------------------------------------------------------- #


def test_empty_candidate_set_does_not_pass_silently() -> None:
    """A lifecycle extractor that receives an empty model list must
    return no entries.  A test that loops over an empty set and reports
    'no violations' is worthless — this guard asserts that the empty
    case actually produces an empty result, and the caller must check
    for emptiness rather than assume 'no violations means everything is
    fine'."""
    entries = _extract_model_lifecycles({"data": []})
    assert len(entries) == 0, "An empty model list must produce zero entries"
    # The real check: if a caller iterates over entries and finds none,
    # they must not conclude "all models are healthy" — they must report
    # that no data was available.  This test exists to enforce that the
    # extractor returns empty (not None, not a single entry with no
    # status) so the emptiness is detectable.


# --------------------------------------------------------------------------- #
# RED PROOF — scheitert auf 5f9376e mit echter Assertion
# --------------------------------------------------------------------------- #


def test_red_proof_byteplus_fixture_has_lifecycle() -> None:
    """RED PROOF: On the current branch the BytePlus fixture carries 58
    models with per-model lifecycle status.  On 5f9376e (the base merge)
    the fixture has a single model with no status field, so this test
    fails with a real ``AssertionError`` — not an ImportError, not a
    collection error.

    Uses only ``json`` and ``pathlib`` so it is collectable on both
    revisions.
    """
    path = FIXTURES_DIR / "byteplus_models.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data", [])
    assert len(data) >= 50, (
        f"RED PROOF: BytePlus fixture has only {len(data)} models; "
        "expected 58.  The old fixture (5f9376e) had 1 model — "
        "this test must fail there with a real assertion."
    )
    # Every model must carry a status field
    for entry in data:
        assert "status" in entry, (
            f"RED PROOF: model {entry.get('id', '?')} has no status field. "
            "The old fixture (5f9376e) had no status fields."
        )
        assert entry["status"] in ("Active", "Retiring", "Shutdown"), (
            f"RED PROOF: unexpected status {entry['status']!r}"
        )
