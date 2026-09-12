"""Split catalog facts into enforceable and advisory views by evidence level.

The provider catalog carries facts — model-level physical truths — each tagged
with an ``evidence`` block::

    {
        "evidence": {
            "level": "confirmed",
            "source_url": "https://api-docs.deepseek.com/",
            "as_of": "2026-09-10",
        }
    }

``evidence.level`` follows the three-step scale fixed by the catalog schema:

    unconfirmed < plausible < confirmed

Two views are derived at load time so the runtime only ever receives the facts
it is allowed to act on:

* **enforceable** — hard decisions. Only ``confirmed`` facts. The router and the
  capacity calculator may rely on these unconditionally.
* **advisory** — best-effort. ``confirmed`` + ``plausible`` facts. A consumer
  presenting this view to a client must flag the ``plausible`` subset as an
  estimate rather than a guarantee.

``unconfirmed`` facts appear in *neither* view: they are invisible to the
router, the capacity calculator, and error output. A fact whose ``evidence``
block is missing, or whose level is not one of the three recognised values, is
treated as unverified and excluded from both views for the same reason.

The split is recomputed from the current level on every call and is never
cached. Changing ``evidence.level`` therefore moves a fact between views on the
next derivation with no separate "move" step and no further intervention.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Evidence level names fixed by the provider-catalog schema. Order is
# meaningful: a higher rank is a stronger claim about the fact's verification.
LEVEL_CONFIRMED = "confirmed"
LEVEL_PLAUSIBLE = "plausible"
LEVEL_UNCONFIRMED = "unconfirmed"

_LEVELS = (LEVEL_UNCONFIRMED, LEVEL_PLAUSIBLE, LEVEL_CONFIRMED)

# Which views each level feeds, keyed by level.
#   confirmed    -> enforceable + advisory (hard decisions also surface as advice)
#   plausible    -> advisory only (best-effort, flagged as estimate)
#   unconfirmed  -> neither (invisible to router, capacity, and error output)
_VIEW_MEMBERSHIP: dict[str, tuple[bool, bool]] = {
    LEVEL_CONFIRMED: (True, True),
    LEVEL_PLAUSIBLE: (False, True),
    LEVEL_UNCONFIRMED: (False, False),
}


@dataclass(frozen=True)
class CatalogViews:
    """The two facts views: one the runtime may enforce, one it may advise on."""

    enforceable: dict[str, Any]
    advisory: dict[str, Any]


def evidence_level(fact: Mapping[str, Any]) -> str | None:
    """Return the ``evidence.level`` of a fact, or ``None`` when absent/unrecognised.

    A missing ``evidence`` block or a level outside the three recognised values
    signals an unverified fact. Returning ``None`` lets the splitter treat it
    like ``LEVEL_UNCONFIRMED`` without ever inventing a level.
    """
    evidence = fact.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    level = evidence.get("level")
    if level in _LEVELS:
        return level
    return None


def split_catalog_facts(facts: Mapping[str, Any]) -> CatalogViews:
    """Split ``facts`` into the enforceable and advisory views by evidence level.

    ``facts`` maps a fact identifier to a fact entry. Each entry's
    ``evidence.level`` decides which views it feeds; entries without a recognised
    level are dropped from both.
    """
    enforceable: dict[str, Any] = {}
    advisory: dict[str, Any] = {}

    for fact_id, fact in facts.items():
        level = evidence_level(fact)
        membership = _VIEW_MEMBERSHIP.get(level, (False, False))
        if membership[0]:
            enforceable[fact_id] = fact
        if membership[1]:
            advisory[fact_id] = fact

    return CatalogViews(enforceable=enforceable, advisory=advisory)
