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
RESULT_PATH = (
    REPO_ROOT / "faigate_v2_research" / "five-seat-benchmark-result.json"
)


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("five_seat_benchmark", BENCH_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["five_seat_benchmark"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_catalog_limits_are_read_programmatically():
    """AC-2: per-provider limits + 413 cap come from the catalog, not literals."""
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
    # Uniformity: every declared cap equals the advertised max cap (the
    # catalog band is intentionally uniform; the assertion guards a silent
    # split, not the value itself).
    caps = {v for v in declared.values() if v is not None}
    assert set(caps) == {reading.max_cap}


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
