"""Precedence-aware merge of catalog source entries.

Multiple sources feed model entries into the curated catalog. When they
disagree about one model, that disagreement must never be resolved silently:
the winning value is chosen by a fixed precedence order and every conflict is
recorded -- with the field, both values, and the source that won -- so the
choice is auditable after the fact.

Precedence (highest first):

1. **overlays** -- operator-curated corrections that always beat foreign data,
   no matter how fresh the foreign data is.
2. **litellm** -- the LiteLLM registry.
3. **omniroute** -- OmniRoute's TypeScript configs.

The merge keys entries by ``(provider_id, model_id)``. Within one key, each
field is settled field-by-field from highest to lowest precedence; the first
source that supplies a *present* value for a field owns it, and any later
source with a *different* present value produces a conflict record that names
the winner. Present is not the same as non-zero: a curated free model whose
price is ``0.0`` is a value, and must not be read as "no data".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faigate.catalog_sources.base import FreeTier, NormalizedEntry

#: Fixed source precedence, highest first. Lower index wins.
#: Overlays are curated corrections and must beat any foreign source; LiteLLM
#: is preferred over OmniRoute as the primary foreign registry.
PRECEDENCE = ("overlay", "litellm", "omniroute")


@dataclass
class Conflict:
    """One recorded disagreement between sources about a single field.

    ``field`` names the normalized-entry field that disagreed (e.g. ``pricing``,
    ``context_window``). ``winner_source`` is who supplied the value that made
    it into the merged entry, ``loser_source`` who supplied the losing value,
    and ``winner_value`` / ``loser_value`` are the two values verbatim.
    """

    provider_id: str
    model_id: str
    field: str
    winner_source: str
    loser_source: str
    winner_value: object
    loser_value: object


@dataclass
class MergeResult:
    """The outcome of a precedence merge.

    ``entries`` is the merged catalog (one entry per model). ``conflicts``
    lists every disagreement, in the order they were encountered, so a caller
    can surface a full conflict log alongside the merged data.
    """

    entries: list[NormalizedEntry] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


@dataclass
class SourceInput:
    """One source's normalized entries plus its precedence rank.

    ``name`` must be one of :data:`PRECEDENCE`; anything else raises so an
    unknown source cannot accidentally take part in the merge with an
    unforeseen rank.
    """

    name: str
    entries: list[NormalizedEntry]

    def __post_init__(self) -> None:
        if self.name not in PRECEDENCE:
            known = ", ".join(PRECEDENCE)
            raise ValueError(f"unknown source {self.name!r}; expected one of {known}")


#: Non-scalar ``NormalizedEntry`` fields are compared as multisets: the order a
#: source lists ``["text", "image"]`` versus ``["image", "text"]`` is not a
#: disagreement. ``source_url`` is a scalar provenance field like any other, so
#: it participates in conflict detection rather than being resolved silently.
_UNORDERED_FIELDS = ("modalities", "capabilities")

#: Fields treated as a single mergeable atom. Each is compared as a whole so a
#: pricing disagreement is one conflict naming the whole ``pricing`` object,
#: not three conflicts over its sub-fields.
_MERGE_FIELDS = (
    "display_name",
    "context_window",
    "max_input_tokens",
    "max_output_tokens",
    "pricing",
    "modalities",
    "capabilities",
    "tier_status",
    "deprecation_date",
    "free_tier",
    "source_url",
)

#: Scalar fields whose absence is ``None`` plus the two unordered list fields
#: whose absence is ``[]``. ``pricing`` and ``free_tier`` are handled by
#: :func:`_is_meaningful` with their own presence rules.
_EMPTY_LIST_FIELDS = ("modalities", "capabilities")

#: Fields on :class:`~faigate.catalog_sources.base.FreeTier` that carry real
#: data. An all-``None`` ``FreeTier`` is an empty struct, not "free with no
#: numbers", and must not suppress a populated tier from a lower source.
_FREE_TIER_FIELDS = (
    "tokens_per_day",
    "tokens_per_month",
    "requests_per_minute",
    "requests_per_day",
    "expires_at",
)


def _empty(field: str) -> Any:
    """The sentinel 'empty' value a field carries when a source has nothing."""
    if field in _EMPTY_LIST_FIELDS:
        return []
    return None


def _free_tier_has_data(value: FreeTier) -> bool:
    """Whether a ``FreeTier`` carries at least one real fact."""
    return any(getattr(value, name) is not None for name in _FREE_TIER_FIELDS)


def _is_meaningful(field: str, value: Any) -> bool:
    """Whether a value is *present*, i.e. not the empty sentinel.

    Presence is not the same as non-zero. A curated free price of
    ``EntryPricing(0.0, 0.0, 0.0)`` is present and must win over a lower
    source's real (non-zero) price, logging a conflict that names both. By
    contrast, an all-``None`` :class:`FreeTier` carries no fact and counts as
    absent.
    """
    if field == "free_tier":
        return isinstance(value, FreeTier) and _free_tier_has_data(value)
    return value != _empty(field)


def _values_equal(field: str, left: Any, right: Any) -> bool:
    """Compare two present values for equality, order-insensitively where the
    field is unordered (``modalities``, ``capabilities``)."""
    if field in _UNORDERED_FIELDS:
        return set(left) == set(right)
    return left == right


def _value(field: str, entry: NormalizedEntry) -> Any:
    return getattr(entry, field)


def _merge_field(
    result: MergeResult,
    key: tuple[str, str],
    field: str,
    sources: list[tuple[str, NormalizedEntry]],
) -> Any:
    """Settle one field by precedence, recording any conflict.

    Walks sources from highest to lowest precedence. The first meaningful
    value wins; every later *different* meaningful value is logged as a
    conflict and discarded. Returns the winning value (or the empty sentinel
    when no source supplied one).
    """
    provider_id, model_id = key
    winner_source: str | None = None
    winner_value: Any = _empty(field)

    for source_name, entry in sources:
        value = _value(field, entry)
        if not _is_meaningful(field, value):
            continue
        if winner_source is None:
            winner_source = source_name
            winner_value = value
            continue
        if not _values_equal(field, value, winner_value):
            result.conflicts.append(
                Conflict(
                    provider_id=provider_id,
                    model_id=model_id,
                    field=field,
                    winner_source=winner_source,
                    loser_source=source_name,
                    winner_value=winner_value,
                    loser_value=value,
                )
            )

    return winner_value


def _build_entry(key: tuple[str, str], resolved: dict[str, Any]) -> NormalizedEntry:
    """Assemble a merged :class:`NormalizedEntry` from per-field winners."""
    provider_id, model_id = key
    pricing = resolved["pricing"]
    return NormalizedEntry(
        provider_id=provider_id,
        model_id=model_id,
        display_name=resolved["display_name"],
        context_window=resolved["context_window"],
        max_input_tokens=resolved["max_input_tokens"],
        max_output_tokens=resolved["max_output_tokens"],
        pricing=pricing,
        modalities=resolved["modalities"],
        capabilities=resolved["capabilities"],
        tier_status=resolved["tier_status"],
        deprecation_date=resolved["deprecation_date"],
        free_tier=resolved["free_tier"],
        # Provenance is a merge field like the rest: the highest-precedence
        # source that named a URL wins, and a later different URL is logged as
        # a conflict, never resolved silently.
        source_url=resolved["source_url"],
    )


def merge_catalogs(sources: list[SourceInput]) -> MergeResult:
    """Merge normalized entries from multiple sources by precedence.

    ``sources`` may be given in any order; they are re-ranked by the fixed
    :data:`PRECEDENCE` order internally. Entries from a higher-precedence
    source always beat lower-precedence entries on a per-field basis, and
    every disagreement is recorded in the returned :class:`MergeResult`.
    """
    ranked = sorted(sources, key=lambda s: PRECEDENCE.index(s.name))

    # Collect, per (provider_id, model_id), the ordered list of
    # (source_name, entry) pairs. Duplicate keys within one source: first wins.
    grouped: dict[tuple[str, str], list[tuple[str, NormalizedEntry]]] = {}
    for source in ranked:
        for entry in source.entries:
            key = (entry.provider_id, entry.model_id)
            existing = grouped.setdefault(key, [])
            if not any(name == source.name for name, _ in existing):
                existing.append((source.name, entry))

    result = MergeResult()
    for key, entries in grouped.items():
        resolved: dict[str, Any] = {}
        for field_name in _MERGE_FIELDS:
            resolved[field_name] = _merge_field(result, key, field_name, entries)

        result.entries.append(_build_entry(key, resolved))

    return result
