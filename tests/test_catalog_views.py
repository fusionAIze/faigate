"""Acceptance tests for the enforceable/advisory evidence-view split.

The catalog carries facts tagged with ``evidence.level`` on the three-step
scale ``unbestaetigt < plausibel < belegt``. ``faigate.catalog_views`` splits
those facts into two views at load time:

* ``enforceable`` — only ``belegt`` facts (hard decisions).
* ``advisory`` — ``belegt`` + ``plausibel`` facts (best-effort, flagged as an
  estimate when surfaced to a client).

``unbestaetigt`` facts land in neither view. These tests pin the three TASK-B1
criteria and the default-unverified behaviour for missing or unknown levels.
"""

from __future__ import annotations

from typing import Any

from faigate.catalog_views import (
    LEVEL_BELEGT,
    LEVEL_PLAUSIBEL,
    LEVEL_UNBESTAETIGT,
    CatalogViews,
    evidence_level,
    split_catalog_facts,
)


def _fact(level: str | None, *, include_block: bool = True) -> dict[str, Any]:
    """Build one fact entry with an ``evidence`` block carrying ``level``."""
    fact: dict[str, Any] = {"vendor": "deepseek", "model": "deepseek-v4-flash"}
    if include_block:
        evidence: dict[str, Any] = {}
        if level is not None:
            evidence["level"] = level
        fact["evidence"] = evidence
    return fact


def _belegt() -> dict[str, Any]:
    return _fact(LEVEL_BELEGT)


def _plausibel() -> dict[str, Any]:
    return _fact(LEVEL_PLAUSIBEL)


def _unbestaetigt() -> dict[str, Any]:
    return _fact(LEVEL_UNBESTAETIGT)


# --------------------------------------------------------------------------- #
# Criterion 1 — unbestaetigt is invisible to the enforceable view
# --------------------------------------------------------------------------- #


def test_unbestaetigt_is_absent_from_enforceable_view() -> None:
    views = split_catalog_facts({"a": _unbestaetigt()})

    assert "a" not in views.enforceable


# --------------------------------------------------------------------------- #
# Criterion 2 — belegt lands in both views
# --------------------------------------------------------------------------- #


def test_belegt_lands_in_both_views() -> None:
    views = split_catalog_facts({"a": _belegt()})

    assert "a" in views.enforceable
    assert "a" in views.advisory
    assert views.enforceable["a"] is views.advisory["a"]


def test_plausibel_lands_in_advisory_but_not_enforceable() -> None:
    views = split_catalog_facts({"p": _plausibel()})

    assert "p" not in views.enforceable
    assert "p" in views.advisory


def test_mixed_catalog_splits_into_the_expected_buckets() -> None:
    facts = {
        "hard": _belegt(),
        "soft": _plausibel(),
        "rumour": _unbestaetigt(),
    }
    views = split_catalog_facts(facts)

    assert set(views.enforceable) == {"hard"}
    assert set(views.advisory) == {"hard", "soft"}


# --------------------------------------------------------------------------- #
# Criterion 3 — a change to evidence.level moves the fact, no further step
# --------------------------------------------------------------------------- #


def test_promoting_level_moves_fact_without_reordering() -> None:
    fact = _unbestaetigt()

    first = split_catalog_facts({"a": fact})
    assert "a" not in first.enforceable
    assert "a" not in first.advisory

    fact["evidence"]["level"] = LEVEL_BELEGT
    second = split_catalog_facts({"a": fact})

    assert "a" in second.enforceable
    assert "a" in second.advisory


def test_demoting_level_removes_fact_without_reordering() -> None:
    fact = _belegt()

    before = split_catalog_facts({"a": fact})
    assert "a" in before.enforceable

    fact["evidence"]["level"] = LEVEL_UNBESTAETIGT
    after = split_catalog_facts({"a": fact})

    assert "a" not in after.enforceable
    assert "a" not in after.advisory


def test_views_are_recomputed_on_every_call() -> None:
    fact = _plausibel()
    views_once = split_catalog_facts({"p": fact})
    views_twice = split_catalog_facts({"p": fact})

    assert views_once == views_twice
    # Distinct objects: no shared mutable cache between derivations.
    assert views_once.enforceable is not views_twice.enforceable
    assert views_once.advisory is not views_twice.advisory


# --------------------------------------------------------------------------- #
# Default-unverified: missing or unknown evidence must never surface as belegt
# --------------------------------------------------------------------------- #


def test_missing_evidence_block_is_treated_as_unverified() -> None:
    views = split_catalog_facts({"a": _fact(None, include_block=False)})

    assert "a" not in views.enforceable
    assert "a" not in views.advisory


def test_missing_level_is_treated_as_unverified() -> None:
    views = split_catalog_facts({"a": _fact(None)})

    assert "a" not in views.enforceable
    assert "a" not in views.advisory


def test_unknown_level_is_treated_as_unverified() -> None:
    fact = _fact(LEVEL_BELEGT)
    fact["evidence"]["level"] = "official"

    views = split_catalog_facts({"a": fact})

    assert "a" not in views.enforceable
    assert "a" not in views.advisory


# --------------------------------------------------------------------------- #
# evidence_level helper
# --------------------------------------------------------------------------- #


def test_evidence_level_reads_recognised_levels() -> None:
    assert evidence_level(_belegt()) == LEVEL_BELEGT
    assert evidence_level(_plausibel()) == LEVEL_PLAUSIBEL
    assert evidence_level(_unbestaetigt()) == LEVEL_UNBESTAETIGT


def test_evidence_level_returns_none_when_absent_or_unrecognised() -> None:
    assert evidence_level(_fact(None, include_block=False)) is None
    assert evidence_level(_fact(None)) is None
    assert evidence_level({"evidence": {"level": "official"}}) is None


def test_split_catalog_facts_returns_catalog_views() -> None:
    assert isinstance(split_catalog_facts({}), CatalogViews)
