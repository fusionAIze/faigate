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
    from faigate.provider_catalog import extract_model_lifecycles as _f

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


def test_lifecycle_entries_carry_the_context_window_probe_field_path() -> None:
    """Criterion 1: the lifecycle probe is the same probe as FAI-238-A.

    Every lifecycle entry carries the provider's field path from the shared
    ``_PROBE_FIELD_PATHS`` table that the context-window probe reads through
    — the identifier of the same probe, not a parallel data source.
    """
    from faigate import provider_catalog as pc

    # (probe provider key, fixture stem) — the same recorded response is read
    # by both the lifecycle probe and the FAI-238-A context-window probe.
    cases = [
        ("byteplus", "byteplus"),
        ("deepseek-chat", "deepseek"),
        ("openrouter-fallback", "openrouter"),
        ("mistral", "mistral"),
    ]
    for provider_key, fixture in cases:
        data = _load_fixture(fixture)
        expected_path = pc._PROBE_FIELD_PATHS[provider_key]

        catalog = pc.build_provider_lifecycle_catalog({provider_key: data})
        entries = catalog[provider_key]["models"]
        assert entries, f"{provider_key}: expected lifecycle entries"
        for entry in entries:
            assert entry.get("field_path") == expected_path, (
                f"{provider_key}: lifecycle entry {entry.get('model_id')!r} must carry the "
                f"shared probe field path {expected_path!r}"
            )

        # The very same probe, read through the same path, yields the
        # context-window fact — the coupling is to the real probe, not a copy.
        evidence = pc.probe_context_window_evidence(provider_key, data)
        assert evidence.get("field_path") == expected_path
        assert evidence.get("level") == "confirmed"
        from faigate.capability_probe import extract_context_window

        assert extract_context_window(data, expected_path) == evidence["probed_value"]


def test_probe_field_paths_is_the_context_window_table() -> None:
    """The probe identifier the lifecycle entries carry is the one and only
    ``_PROBE_FIELD_PATHS`` table — the same identifier the context-window
    evidence block reports under ``field_path``."""
    from faigate import provider_catalog as pc

    data = _load_fixture("byteplus")
    evidence = pc.probe_context_window_evidence("byteplus", data)
    entry = pc.extract_lifecycle_probe(data)["entries"][0]

    assert evidence.get("field_path") == pc._PROBE_FIELD_PATHS["byteplus"]
    assert entry.get("field_path", pc.probed_field_path_for(entry, "byteplus")) == evidence["field_path"]


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


def test_ambiguous_name_states_which_version_is_meant() -> None:
    """Criterion 2: the catalog does not stop at 'ambiguous' — it says which
    concrete version an unversioned short name resolves to.

    The provider resolves ``seed-2-0-lite`` to its Active variant, so the
    ambiguous-name entry must name ``seed-2-0-lite-240701`` and record that the
    resolution came from the Active status.
    """
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    entry = catalog["byteplus"]["ambiguous_names"][0]
    assert entry["resolved_versioned_id"] == "seed-2-0-lite-240701", (
        f"the short name must resolve to its Active version, got {entry.get('resolved_versioned_id')!r}"
    )
    assert entry["resolved_by"] == "active_status"
    assert entry["resolution_note"], "the resolution must be explained"
    # The resolution must name the active version, not merely assert ambiguity.
    assert "seed-2-0-lite-240701" in entry["resolution_note"]
    # And it must NOT point at the retiring variant.
    assert "seed-2-0-lite-231201" not in entry["resolution_note"]


def test_ambiguous_resolution_falls_back_only_when_marked() -> None:
    """When no variant is Active and the sole Retiring variant is versioned,
    the fallback is named and explicitly marked as a fallback — never
    presented as an authoritative resolution."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    data = {
        "data": [
            {"id": "x-model", "status": "Shutdown", "versioned_id": "x-model-1"},
            {"id": "x-model", "status": "Retiring", "versioned_id": "x-model-2"},
        ]
    }
    entry = build_provider_lifecycle_catalog({"p": data})["p"]["ambiguous_names"][0]
    assert entry["resolved_versioned_id"] == "x-model-2"
    assert entry["resolved_by"] == "retiring_status"


def test_ambiguous_resolution_is_none_when_undecidable() -> None:
    """When the resolution cannot be decided from the recorded response, the
    entry says so (``resolved_versioned_id is None``) instead of guessing."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    data = {
        "data": [
            {"id": "y-model", "status": "Shutdown"},
            {"id": "y-model", "status": "Shutdown"},
        ]
    }
    entry = build_provider_lifecycle_catalog({"p": data})["p"]["ambiguous_names"][0]
    assert entry["resolved_versioned_id"] is None
    assert entry["resolved_by"] == ""
    assert "not decidable" in entry["resolution_note"]


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
    """The total model count equals active + retiring + shutdown + unknown,
    proving no models are silently excluded."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    lc = catalog["byteplus"]["lifecycle"]
    assert lc["total"] == lc["active"] + lc["retiring"] + lc["shutdown"] + lc["unknown"], (
        f"Total {lc['total']} != {lc['active']} + {lc['retiring']} + {lc['shutdown']} + {lc['unknown']}"
    )


def test_unexpected_status_lands_in_a_visible_bucket() -> None:
    """Criterion 3: a status outside Active/Retiring/Shutdown must not fall
    into an invisible remainder while ``total`` counts it.

    A model with status ``Deprecated`` lands in ``unknown_models`` and its raw
    status is recorded, so total always equals the sum of the visible lists.
    """
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    data = {
        "data": [
            {"id": "a-model", "status": "Active"},
            {"id": "b-deprecated", "status": "Deprecated"},
            {"id": "c-no-status"},
        ]
    }
    lc = build_provider_lifecycle_catalog({"p": data})["p"]["lifecycle"]

    assert lc["unknown"] == 2
    assert "b-deprecated" in lc["unknown_models"]
    assert "c-no-status" in lc["unknown_models"], "a model with no status field must stay visible, not vanish"
    assert "Deprecated" in lc["unknown_statuses"]
    assert lc["total"] == lc["active"] + lc["retiring"] + lc["shutdown"] + lc["unknown"]
    assert set(lc["active_models"] + lc["retiring_models"] + lc["shutdown_models"] + lc["unknown_models"]) == {
        "a-model",
        "b-deprecated",
        "c-no-status",
    }


def test_empty_response_is_reported_not_dropped() -> None:
    """Criterion 3: a provider whose /models response is empty is reported as
    an observed state, not silently removed from the catalog."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    catalog = build_provider_lifecycle_catalog({"p": {"data": []}})
    assert "p" in catalog, "a supplied provider with an empty response must not vanish"
    assert catalog["p"]["probe_state"] == "empty_response"
    assert catalog["p"]["lifecycle"]
    assert catalog["p"]["lifecycle"]["total"] == 0


def test_no_status_field_provider_is_reported_not_dropped() -> None:
    """Criterion 3: a provider that returns models but no status field is
    reported with its observed state — it is not silently omitted and not
    mistaken for 'everything is healthy'."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    catalog = build_provider_lifecycle_catalog({"p": {"data": [{"id": "m1"}]}})
    assert "p" in catalog
    assert catalog["p"]["probe_state"] == "no_status_field"
    assert catalog["p"]["models"][0]["model_id"] == "m1"


def test_cli_probe_lifecycles_reports_missing_and_unusable_providers() -> None:
    """The CLI probe never turns an unprobed or unusable provider into silence:
    each requested provider is listed with the state it was observed in."""
    from faigate.provider_catalog import cli_probe_lifecycles

    catalog = cli_probe_lifecycles(
        ["byteplus", "nvidia", "not-configured"],
        recorded_responses={
            "byteplus": _load_fixture("byteplus"),
            "nvidia": _load_fixture("nvidia"),
        },
    )
    probe = catalog["_probe"]
    assert probe["states"]["byteplus"] == "measured"
    assert probe["states"]["nvidia"] == "no_status_field"
    assert probe["missing"] == ["not-configured"]
    assert probe["states"]["not-configured"] == "missing_recorded_response"
    # Every requested provider is accounted for one way or another.
    assert set(probe["states"]) == {"byteplus", "nvidia", "not-configured"}


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
# Guard: an empty candidate set must fail the check, not pass it
# --------------------------------------------------------------------------- #


def test_empty_candidate_set_fails_the_check_does_not_pass_silently() -> None:
    """A check that loops over an empty candidate set and reports 'no
    violations' is worthless.  The lifecycle probe therefore reports a
    failing status when it measured nothing, so a consumer can never read
    an empty run as a clean one."""
    from faigate.provider_catalog import cli_probe_lifecycles

    # Nothing recorded at all: an empty candidate set.
    empty = cli_probe_lifecycles(["p"], recorded_responses={})
    assert empty["_probe"]["status"] == "insufficient_evidence", (
        "an empty candidate set must fail the check, not pass it"
    )
    assert empty["_probe"]["measured"] == []

    # A provider that only returned models with no status was still measured
    # as empty: it must not count as a successful measurement either.
    unusable = cli_probe_lifecycles(["p"], recorded_responses={"p": {"data": [{"id": "m1"}]}})
    assert unusable["_probe"]["status"] == "insufficient_evidence"

    # The check passes only when there is a real candidate.
    measured = cli_probe_lifecycles(["p"], recorded_responses={"p": {"data": [{"id": "m1", "status": "Active"}]}})
    assert measured["_probe"]["status"] == "ok"
    assert measured["_probe"]["measured"] == ["p"]


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
