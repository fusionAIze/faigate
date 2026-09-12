"""Regression test for the five-seat Council benchmark (FAI-208 / P0 gate).

This test does NOT hit the live service. It exercises the deterministic,
catalog-only assertions of the benchmark in recorded mode: five distinct
seats resolve to five distinct answering models, per-provider limits + the 413
cap are read programmatically from the catalog (never hardcoded), and the
substitution-table premise check holds. It is the regression gate that re-runs
green after any catalog/limits change.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_PATH = REPO_ROOT / "faigate_v2_research" / "five-seat-benchmark.py"
RESULT_PATH = REPO_ROOT / "faigate_v2_research" / "five-seat-benchmark-result.json"


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("five_seat_benchmark", BENCH_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["five_seat_benchmark"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_catalog_limits_are_read_programmatically():
    """AC-2: per-provider limits + 413 cap come from the catalog, not literals.

    Two distinct bands are involved and the test must keep them distinct:

    * the per-*provider* band, ``providers[*].limits.max_input_tokens``, read by
      ``read_limits_from_catalog`` — a provider-wide placeholder;
    * the per-*model* band, the catalog's top-level ``model_caps`` block, whose
      entries carry an ``evidence.level``. This is the band the live 413
      actually advertises, via ``faigate.main._resolve_advertised_input_limit``.

    ``read_limits_from_catalog`` derives ``max_cap`` as ``max(per-provider
    caps)`` whenever ``faigate.main._max_input_token_cap`` is unimportable —
    which it is in this tree. Asserting ``max_cap in per_provider.values()``
    would therefore be a tautology (the max of a set is in the set) and could
    never fail. The guarantee guarded here is the real provenance rule: a
    seat's advertised cap is a positive integer drawn from the evidence-tagged
    model-cap band, and each seat's provider lane declares its own positive cap.
    """
    bench = _load_benchmark_module()
    reading = bench.read_limits_from_catalog()

    # The cap must resolve to a positive integer read from provider limits.
    assert reading.max_cap is not None
    assert reading.max_cap > 0
    declared = reading.provider_caps()
    # The catalog owns the 413 band: every provider that a five-seat request
    # can resolve to must declare its cap programmatically. Seat client-IDs map
    # to provider keys as follows (deepseek-v4-pro is served by the
    # deepseek-reasoner provider lane).
    seat_provider_keys = (
        "kilo-opus",
        "kilo-sonnet",
        "deepseek-reasoner",
        "gemini-flash",
        "openrouter-fallback",
    )
    for key in seat_provider_keys:
        assert key in declared, f"{key} missing from programmatic limits"
        assert declared[key] is not None
        assert declared[key] > 0

    # Provenance, in the band that actually governs an advertisement. The old
    # uniform-band assertion ("262144 for every lane") became false once caps
    # were resolved per lane; the assertion that briefly replaced it
    # (``max_cap in declared.values()``) was vacuous, because ``max_cap`` is
    # itself ``max(declared.values())`` whenever no live backend is importable
    # — a set's maximum is trivially a member of the set. The real rule is the
    # one ``_resolve_advertised_input_limit`` enforces: an advertised token
    # number is a per-model fact carrying an evidence level, and is never
    # invented from the provider-wide placeholder band.
    from faigate.main import _resolve_advertised_input_limit
    from faigate.provider_catalog import get_model_input_cap_fact

    placeholder_band = {v for v in declared.values() if v is not None}
    for seat in bench.FIVE_SEATS:
        fact = get_model_input_cap_fact(seat)
        advertised, estimated = _resolve_advertised_input_limit(seat)
        if fact is None:
            # No evidence-tagged model fact: no token number may be advertised,
            # and the provider-wide placeholder must not leak in as one.
            assert advertised is None, (
                f"413 for {seat} advertises {advertised} with no evidence-tagged "
                f"model-cap fact; the provider placeholder band {sorted(placeholder_band)} "
                "must never be surfaced as a hard cap"
            )
            assert estimated is False
            continue
        level = str((fact.get("evidence") or {}).get("level") or "")
        cap = fact["max_input_tokens"]
        if level == "confirmed":
            assert advertised == cap and estimated is False, (
                f"413 for {seat} advertised {advertised} (estimated={estimated}); a "
                f"confirmed model cap {cap} must pass through unchanged"
            )
        elif level == "plausible":
            assert advertised == cap and estimated is True, (
                f"413 for {seat} advertised {advertised} (estimated={estimated}); a "
                f"plausible model cap {cap} must be shown as a best-effort estimate"
            )
        else:
            assert advertised is None, (
                f"413 for {seat} advertised {advertised} from an {level!r} fact; "
                "no hard cap may be invented"
            )


def test_recorded_five_seats_are_distinct():
    """AC-1 + AC-3: five distinct seats → five distinct answering models."""
    if not RESULT_PATH.exists():
        pytest.skip("no recorded result; run --mode live first")
    bench = _load_benchmark_module()
    result = bench.run_recorded(RESULT_PATH)

    models = [s["model"] for s in result["five_seats"] if s.get("model")]
    assert len(models) == 5
    assert len(set(models)) == 5
    # Every answerer is non-empty and reflects the true upstream, not the alias.
    assert all(m for m in models)
    # Envelope coherence for the four seats that self-report the answerer.
    for seat in result["five_seats"]:
        if seat["requested"] != "openrouter-fallback":
            assert seat.get("_faigate_model") == seat.get("model")


def test_substitution_premise_check():
    """AC-4: substitution-table premise is folded in and holds."""
    assert RESULT_PATH.exists()
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    assert result.get("premise_check") == "pass"
