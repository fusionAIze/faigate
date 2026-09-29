"""Acceptance tests for model lifecycle extraction from probe data.

FAI-239-A: The provider catalog must carry lifecycle status sourced from the
same /models probe infrastructure established in FAI-238-A.  The recorded
response in ``tests/fixtures/models_probe/byteplus_models.json`` is the actual
BytePlus /models body captured on 2026-09-29; it carries 58 entries whose
statuses are reported by the provider itself: 28 unmarked (active), 17
``Retiring`` and 13 ``Shutdown``.  It must handle the BytePlus case where:

1. Per-model lifecycle status is extracted from the same probe as FAI-238-A
2. Short names (``name``) and versioned IDs (``id``) are both recorded when
   they differ, and the catalog says which one it means
3. Shutdown/retiring models remain visible and usable, not silently dropped
4. Duplicate short names with differing statuses are detected and reported
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "models_probe"

# The provider's own report for the recorded response.  Active is the bucket
# for the 28 entries BytePlus leaves unmarked.
REPORTED_ACTIVE = 28
REPORTED_RETIRING = 17
REPORTED_SHUTDOWN = 13
REPORTED_TOTAL = 58

# The concrete case from the FAI-239 finding: the catalog carried
# ``seed-1-8-251228`` while the provider marks it Retiring.
SEED_1_8_VERSIONED_ID = "seed-1-8-251228"

# The duplicate short name from the finding: one variant retiring, one active.
SEED_2_0_LITE_RETIRING = "seed-2-0-lite-260228"
SEED_2_0_LITE_ACTIVE = "seed-2-0-lite-260428"


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


def _ambiguous_entry(catalog: dict, model_id: str) -> dict:
    for entry in catalog["byteplus"]["ambiguous_names"]:
        if entry["model_id"] == model_id:
            return entry
    raise AssertionError(f"{model_id!r} is not reported as an ambiguous short name")


# --------------------------------------------------------------------------- #
# Criterion 1: lifecycle in the catalog, fed from the same probe as FAI-238-A
# --------------------------------------------------------------------------- #


def test_lifecycle_extracted_from_byteplus_probe() -> None:
    """Lifecycle status is extracted from the same BytePlus probe fixture
    that FAI-238-A uses for context-window probing."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)
    assert len(entries) == REPORTED_TOTAL, f"expected {REPORTED_TOTAL} entries, got {len(entries)}"

    # Every entry must carry model_id and status, and a status the provider
    # could actually have meant.
    for entry in entries:
        assert "model_id" in entry, f"Missing model_id in entry: {entry}"
        assert "status" in entry, f"Missing status in entry: {entry}"
        assert entry["status"] in ("Active", "Retiring", "Shutdown"), (
            f"Unexpected status {entry['status']!r} for {entry['model_id']!r}"
        )


def test_lifecycle_counts_match_report() -> None:
    """BytePlus reports 28 active, 17 Retiring, 13 Shutdown = 58 models."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})
    assert "byteplus" in catalog

    lc = catalog["byteplus"]["lifecycle"]
    assert lc["active"] == REPORTED_ACTIVE, f"Expected {REPORTED_ACTIVE} active, got {lc['active']}"
    assert lc["retiring"] == REPORTED_RETIRING, f"Expected {REPORTED_RETIRING} retiring, got {lc['retiring']}"
    assert lc["shutdown"] == REPORTED_SHUTDOWN, f"Expected {REPORTED_SHUTDOWN} shutdown, got {lc['shutdown']}"
    assert lc["total"] == REPORTED_TOTAL, f"Expected {REPORTED_TOTAL} total, got {lc['total']}"


def test_provider_omits_status_for_active_models_and_we_read_that_as_active() -> None:
    """BytePlus omits ``status`` for the models it has not marked; that is how
    it reports "active".  Such an entry keeps the reported bucket (Active) but
    is flagged as inferred, so the counts never invent a status silently and
    never leave a blank that would contradict the provider's own report."""
    data = _load_fixture("byteplus")

    # The provider really does omit the field on most entries.
    omitted = [m for m in data["data"] if "status" not in m]
    assert len(omitted) == REPORTED_ACTIVE, (
        f"expected {REPORTED_ACTIVE} entries with no status field, got {len(omitted)}"
    )

    inferred = next(e for e in _extract_model_lifecycles(data) if e.get("versioned_id") == SEED_2_0_LITE_ACTIVE)
    assert inferred["status"] == "Active"
    assert inferred["status_source"] == "inferred_absent", (
        "an absent status must be recorded as inferred, not as a reported fact"
    )

    # A status the provider actually sent is marked reported.
    reported = next(e for e in _extract_model_lifecycles(data) if e.get("versioned_id") == SEED_2_0_LITE_RETIRING)
    assert reported["status"] == "Retiring"
    assert reported["status_source"] == "reported"


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
    assert len(catalog["byteplus"]["models"]) == REPORTED_TOTAL


# --------------------------------------------------------------------------- #
# Criterion 2: name and versioned id — the catalog carries both and says which
# --------------------------------------------------------------------------- #


def test_versioned_id_recorded_when_present() -> None:
    """When a model's versioned id differs from its short name, both are
    recorded in the lifecycle entry."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)

    seed_entries = [e for e in entries if e["model_id"] == "seed-2-0-lite"]
    assert len(seed_entries) == 2, f"Expected 2 seed-2-0-lite entries, got {len(seed_entries)}"

    for entry in seed_entries:
        assert "versioned_id" in entry, f"seed-2-0-lite entry missing versioned_id: {entry}"
        # Each must have a versioned_id different from model_id
        assert entry["versioned_id"] != entry["model_id"], f"versioned_id should differ from model_id: {entry}"


def test_catalog_reports_versioned_id_vs_short_name() -> None:
    """The lifecycle catalog carries ``versioned_id`` alongside the short
    ``model_id`` so consumers can distinguish which concrete version is meant.

    Only the two entries whose provider ``id`` equals their ``name``
    (``deepseek-v3``, ``skylark-pro``) have no distinct versioned id.
    """
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    models = catalog["byteplus"]["models"]
    versioned = [m for m in models if "versioned_id" in m]
    assert len(versioned) == REPORTED_TOTAL - 2, (
        f"Expected {REPORTED_TOTAL - 2} models whose versioned id differs from the short name, got {len(versioned)}"
    )
    for entry in versioned:
        assert entry["versioned_id"] != entry["model_id"]


def test_short_name_is_ambiguous_flagged() -> None:
    """When a short name maps to multiple versioned IDs, ambiguous_names
    flags the conflict.  ``seed-2-0-lite`` is one of the groups the recorded
    response proves."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    ambiguous = catalog["byteplus"]["ambiguous_names"]
    assert ambiguous, "the recorded response contains duplicate short names; at least one group is expected"
    for group in ambiguous:
        assert len(group["entries"]) > 1, f"{group['model_id']!r} grouped without a duplicate"

    entry = _ambiguous_entry(catalog, "seed-2-0-lite")
    assert set(entry["statuses"]) == {"Active", "Retiring"}
    assert len(entry["entries"]) == 2
    # The note should explain the ambiguity
    assert "ambiguous" in entry["note"].lower()


def test_ambiguous_name_states_which_version_is_meant() -> None:
    """Criterion 2: the catalog does not stop at 'ambiguous' — it says which
    concrete version an unversioned short name resolves to.

    The provider resolves ``seed-2-0-lite`` to its active variant, so the
    ambiguous-name entry must name ``seed-2-0-lite-260428`` and record that the
    resolution came from the Active status.
    """
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    entry = _ambiguous_entry(catalog, "seed-2-0-lite")
    assert entry["resolved_versioned_id"] == SEED_2_0_LITE_ACTIVE, (
        f"the short name must resolve to its active version, got {entry.get('resolved_versioned_id')!r}"
    )
    assert entry["resolved_by"] == "active_status"
    assert entry["resolution_note"], "the resolution must be explained"
    # The resolution must name the active version, not merely assert ambiguity.
    assert SEED_2_0_LITE_ACTIVE in entry["resolution_note"]
    # And it must NOT point at the retiring variant.
    assert SEED_2_0_LITE_RETIRING not in entry["resolution_note"]


def test_ambiguous_resolution_falls_back_only_when_marked() -> None:
    """When no variant is Active and the sole Retiring variant is versioned,
    the fallback is named and explicitly marked as a fallback — never
    presented as an authoritative resolution."""
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    data = {
        "data": [
            {"name": "x-model", "id": "x-model-1", "status": "Shutdown"},
            {"name": "x-model", "id": "x-model-2", "status": "Retiring"},
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
            {"name": "y-model", "id": "y-model-1", "status": "Shutdown"},
            {"name": "y-model", "id": "y-model-2", "status": "Shutdown"},
        ]
    }
    entry = build_provider_lifecycle_catalog({"p": data})["p"]["ambiguous_names"][0]
    assert entry["resolved_versioned_id"] is None
    assert entry["resolved_by"] == ""
    assert "not decidable" in entry["resolution_note"]


def test_undecidable_note_is_consistent_with_the_statuses_it_describes() -> None:
    """Finding 3 regression: the undecidable note must describe *this*
    collision, not a canned sentence.

    Two Active variants cannot be resolved, but the note must not claim "No
    variant is Active" — that would be a false signal about the very material
    it is meant to describe.  The note must be consistent with ``statuses``
    for every undecidable shape.
    """
    from faigate.provider_catalog import build_provider_lifecycle_catalog

    # Two Active variants, neither versioned: undecidable, but Active exists.
    two_active = {
        "data": [
            {"name": "z-model", "id": "z-model", "status": "Active"},
            {"name": "z-model", "id": "z-model", "status": "Active"},
        ]
    }
    entry = build_provider_lifecycle_catalog({"p": two_active})["p"]["ambiguous_names"][0]
    assert entry["resolved_versioned_id"] is None
    assert entry["statuses"] == ["Active"]
    assert "no variant is active" not in entry["resolution_note"].lower(), (
        f"note contradicts the observed statuses {entry['statuses']}: {entry['resolution_note']!r}"
    )

    # The same claim must hold wherever the note is emitted: the note never
    # states a status is absent when the statuses list contains it.
    for data in (two_active,):
        for group in build_provider_lifecycle_catalog({"p": data})["p"]["ambiguous_names"]:
            note = group["resolution_note"].lower()
            for status in group["statuses"]:
                assert not (f"no {status.lower()} variant" in note or f"no variant is {status.lower()}" in note), (
                    f"note {group['resolution_note']!r} denies status {status!r} which it lists"
                )


# --------------------------------------------------------------------------- #
# Criterion 3: retired models stay visible and usable
# --------------------------------------------------------------------------- #


def test_shutdown_models_appear_in_catalog() -> None:
    """Models with Shutdown status are listed in the lifecycle catalog,
    not silently dropped."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    shutdown_models = catalog["byteplus"]["lifecycle"]["shutdown_models"]
    assert len(shutdown_models) == REPORTED_SHUTDOWN, (
        f"Expected {REPORTED_SHUTDOWN} shutdown models, got {len(shutdown_models)}"
    )
    assert "deepseek-r1" in shutdown_models, "deepseek-r1 should be listed as shutdown"
    assert "kimi-k2" in shutdown_models, "kimi-k2 should be listed as shutdown"


def test_retiring_models_appear_in_catalog() -> None:
    """Models with Retiring status are listed, not dropped."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    retiring_models = catalog["byteplus"]["lifecycle"]["retiring_models"]
    assert len(retiring_models) == REPORTED_RETIRING, (
        f"Expected {REPORTED_RETIRING} retiring models, got {len(retiring_models)}"
    )
    assert "seed-1-8" in retiring_models
    assert "gpt-oss-120b" in retiring_models


def test_concrete_finding_case_seed_1_8_251228_is_marked_retiring() -> None:
    """The FAI-239 finding's concrete case: the catalog carried
    ``seed-1-8-251228`` with no lifecycle at all.  The catalog must now carry
    it, marked Retiring, so the window between Retiring and Shutdown is
    visible instead of discovered when requests start failing."""
    data = _load_fixture("byteplus")
    catalog = _build_provider_lifecycle_catalog({"byteplus": data})

    entry = next(
        (m for m in catalog["byteplus"]["models"] if m.get("versioned_id") == SEED_1_8_VERSIONED_ID),
        None,
    )
    assert entry is not None, f"{SEED_1_8_VERSIONED_ID} must stay visible in the catalog, not be dropped"
    assert entry["status"] == "Retiring"
    assert entry["status_source"] == "reported"
    assert entry["model_id"] == "seed-1-8"
    assert SEED_1_8_VERSIONED_ID in catalog["byteplus"]["lifecycle"]["retiring_models"] or entry["versioned_id"] in [
        m.get("versioned_id") for m in catalog["byteplus"]["models"] if m["status"] == "Retiring"
    ]


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
            {"name": "a-model", "id": "a-model", "status": "Active"},
            {"name": "b-deprecated", "id": "b-deprecated", "status": "Deprecated"},
            {"name": "c-no-status", "id": "c-no-status"},
        ]
    }
    lc = build_provider_lifecycle_catalog({"p": data})["p"]["lifecycle"]

    # ``c-no-status`` has no reported status: it is read as inferred Active,
    # so it is not counted among the unknown, and the explicit ``Deprecated``
    # status is the one that stays visible as unknown.
    assert lc["unknown"] == 1
    assert "b-deprecated" in lc["unknown_models"]
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
# Criterion 4: the duplicate-entry case proven against the recorded response
# --------------------------------------------------------------------------- #


def test_seed_2_0_lite_duplicate_detected() -> None:
    """seed-2-0-lite appears twice in the recorded BytePlus /models response:
    once Retiring (versioned id seed-2-0-lite-260228) and once unmarked, i.e.
    active (versioned id seed-2-0-lite-260428).  Both are extracted and the
    ambiguity is reported."""
    data = _load_fixture("byteplus")
    entries = _extract_model_lifecycles(data)

    seed_entries = [e for e in entries if e["model_id"] == "seed-2-0-lite"]
    assert len(seed_entries) == 2, f"seed-2-0-lite should appear twice, got {len(seed_entries)} entries"

    active = [e for e in seed_entries if e["status"] == "Active"]
    retiring = [e for e in seed_entries if e["status"] == "Retiring"]
    assert len(active) == 1, f"Expected 1 active seed-2-0-lite, got {len(active)}"
    assert len(retiring) == 1, f"Expected 1 Retiring seed-2-0-lite, got {len(retiring)}"

    assert active[0].get("versioned_id") == SEED_2_0_LITE_ACTIVE
    assert active[0]["status_source"] == "inferred_absent"
    assert retiring[0].get("versioned_id") == SEED_2_0_LITE_RETIRING
    assert retiring[0]["status_source"] == "reported"


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
# RED PROOF — fails on 5f9376e with a real assertion
# --------------------------------------------------------------------------- #


def test_red_proof_byteplus_fixture_is_the_recorded_lifecycle_response() -> None:
    """RED PROOF: this test is collectable on both revisions — it imports
    only ``json`` and ``pathlib`` — and fails on 5f9376e with a real
    ``AssertionError``.

    On 5f9376e the BytePlus fixture held a single hand-set entry
    (``deepseek-v4-flash``) with no ``status`` field at all.  Against that
    revision the first assertion below fails with a genuine assertion about
    the recorded data — not an ImportError, not a collection error, not an
    AttributeError.
    """
    path = FIXTURES_DIR / "byteplus_models.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("data", [])

    assert len(data) == REPORTED_TOTAL, (
        f"RED PROOF: the recorded BytePlus response carries {len(data)} models, "
        f"expected {REPORTED_TOTAL}.  On 5f9376e the fixture held 1 model, so "
        "this fails there with a real assertion."
    )

    # The concrete lifecycle the finding names must be present in the data.
    seed = next((m for m in data if m.get("id") == SEED_1_8_VERSIONED_ID), None)
    assert seed is not None, (
        f"RED PROOF: {SEED_1_8_VERSIONED_ID} is absent from the recorded data; on 5f9376e it does not exist at all."
    )
    assert seed.get("status") == "Retiring", (
        f"RED PROOF: {SEED_1_8_VERSIONED_ID} carries status {seed.get('status')!r}, expected 'Retiring'."
    )


def test_red_proof_probe_reads_the_recorded_values_not_the_hand_set_one() -> None:
    """RED PROOF (behavioural): fails on 5f9376e with a real ``AssertionError``.

    ``probe_context_window_evidence`` already exists on 5f9376e, so this test
    is collectable there and fails only on its value: against the hand-set
    fixture of that revision the BytePlus probe returned 131072 for a single
    ``deepseek-v4-flash`` entry.  Against the recorded 2026-09-29 response the
    same probe reads the first entry's ``token_limits.context_window``
    (98304), and the first entry is a real BytePlus model id.  This is a real
    assertion about behaviour, not an import error.
    """
    from faigate.capability_probe import extract_context_window
    from faigate.provider_catalog import probe_context_window_evidence

    data = _load_fixture("byteplus")
    evidence = probe_context_window_evidence("byteplus", data)

    assert evidence["level"] == "confirmed"
    assert evidence["probed_value"] == 98304, (
        f"RED PROOF: probed {evidence['probed_value']!r}; 5f9376e's hand-set fixture yielded 131072 here."
    )
    assert extract_context_window(data, "token_limits.context_window") == evidence["probed_value"]
    assert data["data"][0]["id"] == "deepseek-r1-250120"
