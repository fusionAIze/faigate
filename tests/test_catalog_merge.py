"""Tests for precedence-aware catalog merge and its conflict log."""

from __future__ import annotations

from faigate.catalog_sources.base import EntryPricing, NormalizedEntry
from faigate.catalog_sources.merge import (
    PRECEDENCE,
    SourceInput,
    merge_catalogs,
)


def _entry(
    provider_id: str = "openai",
    model_id: str = "gpt-4o",
    *,
    pricing: EntryPricing | None = None,
    context_window: int | None = None,
    modalities: list[str] | None = None,
    **kwargs: object,
) -> NormalizedEntry:
    return NormalizedEntry(
        provider_id=provider_id,
        model_id=model_id,
        pricing=pricing,
        context_window=context_window,
        modalities=modalities or [],
        **kwargs,
    )


def test_precedence_order_is_overlay_then_litellm_then_omniroute() -> None:
    assert PRECEDENCE == ("overlay", "litellm", "omniroute")
    assert PRECEDENCE.index("overlay") < PRECEDENCE.index("litellm") < PRECEDENCE.index("omniroute")


def test_overlay_beats_newer_foreign_price() -> None:
    overlay = _entry(pricing=EntryPricing(input=3.0, output=8.0))
    litellm = _entry(pricing=EntryPricing(input=5.0, output=25.0))
    omniroute = _entry(pricing=EntryPricing(input=7.0, output=30.0))

    result = merge_catalogs(
        [
            SourceInput("overlay", [overlay]),
            SourceInput("litellm", [litellm]),
            SourceInput("omniroute", [omniroute]),
        ]
    )

    merged = result.entries[0]
    assert merged.pricing.input == 3.0
    assert merged.pricing.output == 8.0


def test_litellm_beats_omniroute_without_overlay() -> None:
    litellm = _entry(pricing=EntryPricing(input=5.0))
    omniroute = _entry(pricing=EntryPricing(input=7.0))

    result = merge_catalogs([SourceInput("litellm", [litellm]), SourceInput("omniroute", [omniroute])])

    assert result.entries[0].pricing.input == 5.0


def test_constructed_price_conflict_appears_fully_in_log() -> None:
    overlay = _entry(pricing=EntryPricing(input=3.0, output=8.0))
    litellm = _entry(pricing=EntryPricing(input=5.0, output=25.0))
    omniroute = _entry(pricing=EntryPricing(input=5.0, output=25.0))

    result = merge_catalogs(
        [
            SourceInput("overlay", [overlay]),
            SourceInput("litellm", [litellm]),
            SourceInput("omniroute", [omniroute]),
        ]
    )

    pricing_conflicts = [c for c in result.conflicts if c.field == "pricing"]
    assert pricing_conflicts

    conflict = pricing_conflicts[0]
    assert conflict.provider_id == "openai"
    assert conflict.model_id == "gpt-4o"
    assert conflict.field == "pricing"
    assert conflict.winner_source == "overlay"
    assert conflict.loser_source == "litellm"
    assert conflict.winner_value == EntryPricing(input=3.0, output=8.0)
    assert conflict.loser_value == EntryPricing(input=5.0, output=25.0)


def test_conflict_logs_each_disagreeing_source() -> None:
    overlay = _entry(pricing=EntryPricing(input=3.0))
    litellm = _entry(pricing=EntryPricing(input=5.0))
    omniroute = _entry(pricing=EntryPricing(input=7.0))

    result = merge_catalogs(
        [
            SourceInput("overlay", [overlay]),
            SourceInput("litellm", [litellm]),
            SourceInput("omniroute", [omniroute]),
        ]
    )

    # overlay wins against litellm AND against omniroute, both recorded.
    pricing_conflicts = [c for c in result.conflicts if c.field == "pricing"]
    winners = {c.winner_source for c in pricing_conflicts}
    losers = {c.loser_source for c in pricing_conflicts}
    assert winners == {"overlay"}
    assert losers == {"litellm", "omniroute"}


def test_non_conflicting_fields_are_filled_from_lower_precedence() -> None:
    # Overlay supplies only a price; LiteLLM fills the context window; both
    # survive because they target different fields.
    overlay = _entry(pricing=EntryPricing(input=3.0), context_window=None)
    litellm = _entry(pricing=None, context_window=128000)

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    merged = result.entries[0]
    assert merged.pricing.input == 3.0
    assert merged.context_window == 128000


def test_conflicts_never_resolved_silently() -> None:
    overlay = _entry(context_window=100_000)
    litellm = _entry(context_window=128_000)

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    assert result.entries[0].context_window == 100_000
    context_conflicts = [c for c in result.conflicts if c.field == "context_window"]
    assert len(context_conflicts) == 1
    assert context_conflicts[0].winner_source == "overlay"
    assert context_conflicts[0].loser_source == "litellm"


def test_unknown_source_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown source"):
        SourceInput("nonsense", [])


def test_merge_keys_on_provider_and_model_id() -> None:
    a = _entry(provider_id="openai", model_id="gpt-4o", pricing=EntryPricing(input=1.0))
    b = _entry(provider_id="openai", model_id="gpt-3.5", pricing=EntryPricing(input=2.0))

    result = merge_catalogs([SourceInput("overlay", [a, b])])

    assert len(result.entries) == 2
    by_id = {e.model_id: e for e in result.entries}
    assert by_id["gpt-4o"].pricing.input == 1.0
    assert by_id["gpt-3.5"].pricing.input == 2.0


def test_entry_only_in_lower_precedence_is_preserved() -> None:
    omniroute_line = _entry(
        provider_id="deepseek",
        model_id="deepseek-v4-pro",
        pricing=EntryPricing(input=0.1),
        context_window=1_000_000,
    )

    result = merge_catalogs([SourceInput("overlay", []), SourceInput("omniroute", [omniroute_line])])

    assert len(result.entries) == 1
    assert result.entries[0].model_id == "deepseek-v4-pro"


def test_curated_free_price_of_zero_beats_foreign_price() -> None:
    # A curated free model at 0/0/0 is a *value*, not "no price". It must win
    # over LiteLLM's real price, and the disagreement must be logged naming
    # both values -- never read as "overlay had nothing".
    overlay = _entry(pricing=EntryPricing(input=0.0, output=0.0, cache_read=0.0))
    litellm = _entry(pricing=EntryPricing(input=5.0, output=25.0))

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    merged = result.entries[0]
    assert merged.pricing is not None
    assert merged.pricing.input == 0.0
    assert merged.pricing.output == 0.0

    pricing_conflicts = [c for c in result.conflicts if c.field == "pricing"]
    assert pricing_conflicts, "a curated zero against a real price must log a conflict"
    conflict = pricing_conflicts[0]
    assert conflict.winner_source == "overlay"
    assert conflict.loser_source == "litellm"
    assert conflict.winner_value == EntryPricing(input=0.0, output=0.0, cache_read=0.0)
    assert conflict.loser_value == EntryPricing(input=5.0, output=25.0)


def test_unordered_lists_do_not_log_phantom_conflict() -> None:
    overlay = _entry(modalities=["text", "image"])
    litellm = _entry(modalities=["image", "text"])

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    modality_conflicts = [c for c in result.conflicts if c.field == "modalities"]
    assert modality_conflicts == []
    assert set(result.entries[0].modalities) == {"text", "image"}


def test_source_url_disagreement_is_logged_not_resolved_silently() -> None:
    overlay = _entry(source_url="https://docs.acme.com/models/gpt-4o")
    litellm = _entry(source_url="https://litellm.ai/models/gpt-4o")

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    assert result.entries[0].source_url == "https://docs.acme.com/models/gpt-4o"
    source_url_conflicts = [c for c in result.conflicts if c.field == "source_url"]
    assert len(source_url_conflicts) == 1
    assert source_url_conflicts[0].winner_source == "overlay"
    assert source_url_conflicts[0].loser_source == "litellm"


def test_absent_pricing_allows_lower_source_to_fill() -> None:
    # ``None`` (absent) pricing must fall through to the lower source; only a
    # *present* (including zero) price should own the field.
    overlay = _entry(pricing=None)
    litellm = _entry(pricing=EntryPricing(input=5.0))

    result = merge_catalogs([SourceInput("overlay", [overlay]), SourceInput("litellm", [litellm])])

    assert result.entries[0].pricing == EntryPricing(input=5.0)
    assert [c for c in result.conflicts if c.field == "pricing"] == []


def test_all_none_free_tier_does_not_suppress_populated_tier() -> None:
    from faigate.catalog_sources.base import FreeTier

    empty_overlay = _entry(free_tier=FreeTier())
    real_litellm = _entry(free_tier=FreeTier(tokens_per_month=10_000_000))

    result = merge_catalogs([SourceInput("overlay", [empty_overlay]), SourceInput("litellm", [real_litellm])])

    merged = result.entries[0]
    assert merged.free_tier is not None
    assert merged.free_tier.tokens_per_month == 10_000_000
    assert [c for c in result.conflicts if c.field == "free_tier"] == []
