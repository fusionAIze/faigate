"""LiteLLM catalog source adapter.

LiteLLM publishes a single JSON registry, ``model_prices_and_context_window.json``,
that already normalizes prices and context windows across hundreds of providers
and thousands of models. This adapter turns that registry into
:class:`~faigate.catalog_sources.base.NormalizedEntry` objects.

The LiteLLM names are what the adapter understands:

* ``input_cost_per_token`` / ``output_cost_per_token`` /
  ``cache_read_input_token_cost`` — per-token prices, converted here to the
  USD-per-1M-token convention used by
  :class:`~faigate.catalog_sources.base.EntryPricing`.
* ``max_input_tokens`` / ``max_output_tokens`` / ``max_tokens`` — context window
  and token limits.
* ``supports_vision`` / ``supports_image_input`` / ``supports_audio_input`` /
  ``supports_video_input`` / ``supported_modalities`` — mapped onto ``modalities``.
* ``deprecation_date`` — carried onto ``tier_status``: a past date flags
  ``deprecated`` and a future date flags ``retiring``, so a scheduled
  retirement is told apart from one that has already happened.
* ``supports_reasoning`` / ``supports_function_calling`` — mapped onto
  ``capabilities``.
* ``litellm_provider`` — the model's provider id.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from faigate.catalog_sources.base import EntryPricing, NormalizedEntry

logger = logging.getLogger(__name__)

#: LiteLLM stores per-token prices; the interchange shape is USD per 1M tokens.
_TOKENS_PER_MILLION = 1_000_000

#: LiteLLM ``mode`` values that model a text conversation (the kinds of models
#: a routing gateway prices and routes as chat completions). Non-chat modes
#: (embedding, image_generation, audio_*, moderation, ...) are skipped because
#: they do not carry a meaningful chat context window.
_CHAT_MODES = {"chat", "completion", "responses", "realtime"}

#: ``tier_status`` values used by the downstream catalog.
_STATUS_ACTIVE = "active"
_STATUS_DEPRECATED = "deprecated"
_STATUS_RETIRING = "retiring"


def _as_float(value: object, *, field: str, model_id: str) -> float:
    """Parse a numeric field, logging loudly when it cannot be coerced.

    LiteLLM prices are normally plain numbers. A non-numeric or absent price --
    most notably a ``tiered_pricing`` entry whose ``*_cost_per_token`` is
    ``None`` -- would otherwise collapse to ``0.0`` and silently report a free
    model. Returning ``0.0`` preserves today's downstream behaviour but the
    warn makes the coerce visible instead of hidden.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, bool):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        logger.warning("litellm: non-numeric %r for %r on %r; coerce to 0.0", field, value, model_id)
        return 0.0


def _to_price_per_1m(value: object, *, field: str, model_id: str) -> float:
    """Convert a LiteLLM per-token price to USD per 1M tokens."""
    return _as_float(value, field=field, model_id=model_id) * _TOKENS_PER_MILLION


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        logger.warning("litellm: non-numeric token limit %r; coerce to None", value)
        return None


def _derive_modalities(raw: dict[str, Any]) -> list[str]:
    """Map LiteLLM capability flags onto ``modalities``.

    ``supported_modalities`` is the authoritative list when present and emits
    the same tokens the interchange shape documents (``text``, ``image``,
    ``audio``, ``video``). When it is absent, the boolean flags
    ``supports_vision`` / ``supports_image_input`` / ``supports_audio_input`` /
    ``supports_video_input`` are used so that ``supports_vision`` ends up as an
    ``image`` modality.
    """
    declared = raw.get("supported_modalities")
    if isinstance(declared, list) and declared:
        return sorted({str(m).lower() for m in declared if str(m).lower() != "code"})

    modalities: set[str] = set()
    if raw.get("supports_vision") or raw.get("supports_image_input") or raw.get("supports_pdf_input"):
        modalities.add("image")
    if raw.get("supports_audio_input"):
        modalities.add("audio")
    if raw.get("supports_video_input"):
        modalities.add("video")

    return sorted(modalities)


def _derive_capabilities(raw: dict[str, Any]) -> list[str]:
    capabilities: list[str] = []
    if raw.get("supports_reasoning"):
        capabilities.append("reasoning")
    if raw.get("supports_function_calling"):
        capabilities.append("function_calling")
    return capabilities


def _derive_tier_status(raw: dict[str, Any], *, model_id: str) -> str | None:
    """Carry LiteLLM ``deprecation_date`` onto ``tier_status``.

    A deprecation date that has already passed (compared to the day the
    registry is normalized) flags ``deprecated``. A date still in the future
    flags ``retiring`` -- the model is scheduled for retirement but not yet
    retired. The downstream catalog treats both as non-``active``, so routing
    already excludes them; the split keeps the states honest for operators
    instead of reporting a months-away retirement as already done.
    """
    raw_date = raw.get("deprecation_date")
    if not raw_date:
        return _STATUS_ACTIVE

    text = str(raw_date).strip()
    try:
        when = datetime.date.fromisoformat(text)
    except ValueError:
        # Unparseable date: treat conservatively as already deprecated.
        logger.warning("litellm: unparseable deprecation_date %r on %r", text, model_id)
        return _STATUS_DEPRECATED

    if when <= datetime.date.today():
        return _STATUS_DEPRECATED
    return _STATUS_RETIRING


def _build_entry(model_id: str, raw: dict[str, Any]) -> NormalizedEntry:
    max_input: int | None = _as_int(raw.get("max_input_tokens"))
    max_output: int | None = _as_int(raw.get("max_output_tokens"))
    max_tokens: int | None = _as_int(raw.get("max_tokens"))
    if max_output is None:
        max_output = max_tokens

    context_window: int | None = max_input if max_input is not None else max_tokens
    if context_window is None:
        context_window = max_output

    if raw.get("tiered_pricing") and raw.get("input_cost_per_token") is None:
        # A tiered model carries no flat price; the per-token fields collapse
        # to 0.0. Surface that so a free-looking model is never silent.
        logger.warning(
            "litellm: %r has tiered_pricing but no flat input_cost_per_token; prices will be 0.0",
            model_id,
        )

    pricing = EntryPricing(
        input=_to_price_per_1m(raw.get("input_cost_per_token"), field="input_cost_per_token", model_id=model_id),
        output=_to_price_per_1m(raw.get("output_cost_per_token"), field="output_cost_per_token", model_id=model_id),
        cache_read=_to_price_per_1m(
            raw.get("cache_read_input_token_cost"), field="cache_read_input_token_cost", model_id=model_id
        ),
    )

    deprecation_date = str(raw["deprecation_date"]) if raw.get("deprecation_date") else None

    return NormalizedEntry(
        provider_id=str(raw.get("litellm_provider") or "unknown"),
        model_id=model_id,
        display_name=model_id,
        context_window=context_window,
        max_input_tokens=max_input if max_input is not None else max_tokens,
        max_output_tokens=max_output,
        pricing=pricing,
        modalities=_derive_modalities(raw),
        capabilities=_derive_capabilities(raw),
        tier_status=_derive_tier_status(raw, model_id=model_id),
        deprecation_date=deprecation_date,
    )


class LiteLLMAdapter:
    """Source adapter for LiteLLM's ``model_prices_and_context_window.json``.

    Satisfies :class:`SourceAdapter`. ``fetch`` returns the raw registry (a
    ``{model_id: {fields...}}`` map) and ``normalize`` turns it into a flat
    list of :class:`NormalizedEntry` objects, skipping non-chat modes.
    """

    def fetch(self) -> object:
        """Return the raw LiteLLM registry.

        The registry is normally loaded from a bundled or remotely fetched JSON
        file; the adapter itself is transport-agnostic and only requires the
        parsed payload on ``normalize``.
        """
        raise NotImplementedError(
            "LiteLLMAdapter.fetch is transport-agnostic; call normalize(raw) "
            "with the parsed registry, or subclass to wire up a source."
        )

    def normalize(self, raw: object) -> list[NormalizedEntry]:
        if not isinstance(raw, dict):
            return []

        entries: list[NormalizedEntry] = []
        for model_id, fields in raw.items():
            if not isinstance(fields, dict):
                continue
            if fields.get("mode") not in _CHAT_MODES:
                continue
            entries.append(_build_entry(model_id, fields))
        return entries
