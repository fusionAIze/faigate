"""Adapter interface for catalog sources.

Catalog sources feed model entries into the curated provider catalog. A
source is any place that knows about models, prices, context windows,
modalities, and capabilities: a provider's public docs, a pricing page, a
remote catalog JSON, or a bundled snapshot.

The :class:`SourceAdapter` protocol decouples *where data comes from* (the
``fetch`` step) from *what shape it lands in* (the ``normalize`` step), so
new sources can be added without touching downstream catalog consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: A modality is a coarse input/output content kind a model can handle.
#: Values are free strings (``text``, ``image``, ``audio``, ``video``) so
#: sources are not forced into a closed enumeration that lags reality.
Modality = str


@dataclass
class EntryPricing:
    """Per-token prices in USD per 1M tokens."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> EntryPricing:
        """Build pricing from a raw mapping, tolerating missing/foreign keys."""

        def _num(value: object) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            try:
                return float(str(value))
            except (TypeError, ValueError):
                return 0.0

        # Accept both the canonical field names and the legacy external
        # catalog names (input_cost_per_1m, output_cost_per_1m, ...).
        sources = {
            "input": raw.get("input", raw.get("input_cost_per_1m")),
            "output": raw.get("output", raw.get("output_cost_per_1m")),
            "cache_read": raw.get("cache_read", raw.get("cache_read_cost_per_1m")),
        }
        return cls(
            input=_num(sources["input"]),
            output=_num(sources["output"]),
            cache_read=_num(sources["cache_read"]),
        )


@dataclass
class FreeTier:
    """Free-tier and quota facts about one provider or model.

    Carries the upstream's documented recurring token budget and rate limits
    so a routing gateway can decide whether a candidate may be used without
    payment. Fields are optional: a source that only knows the monthly token
    budget contributes that one number without fabricating the rest.
    """

    tokens_per_day: int | None = None
    tokens_per_month: int | None = None
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    expires_at: str | None = None


@dataclass
class NormalizedEntry:
    """One normalized model entry produced by a source adapter.

    This is the interchange shape downstream catalog code consumes. It is
    deliberately minimal: identifiers, price, context window, modalities,
    and capabilities. Fields are optional so a partial source can still
    contribute what it knows without fabricating the rest.
    """

    provider_id: str
    model_id: str
    display_name: str | None = None
    context_window: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    pricing: EntryPricing = field(default_factory=EntryPricing)
    modalities: list[Modality] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    free_tier: FreeTier | None = None
    source_url: str | None = None


class SourceAdapter(Protocol):
    """Protocol every catalog source adapter must satisfy.

    ``fetch`` obtains raw data from the source. ``normalize`` turns that
    raw data into :class:`NormalizedEntry` objects. Keeping them separate
    lets callers cache the raw payload while still re-normalizing against
    newer schema expectations.
    """

    def fetch(self) -> object:
        """Return the raw data payload for this source."""
        ...

    def normalize(self, raw: object) -> list[NormalizedEntry]:
        """Convert a raw payload into normalized entries."""
        ...
