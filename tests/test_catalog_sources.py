"""Tests for the catalog source adapter interface."""

from __future__ import annotations

from typing import Any

import pytest

from faigate.catalog_sources.base import (
    EntryPricing,
    NormalizedEntry,
    SourceAdapter,
)


class FakeAdapter:
    """A source adapter backed by an in-memory payload.

    Exercises the :class:`SourceAdapter` protocol without network access,
    proving the interface is satisfiable by concrete adapters.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.fetch_calls = 0

    def fetch(self) -> object:
        self.fetch_calls += 1
        return self._payload

    def normalize(self, raw: object) -> list[NormalizedEntry]:
        data = raw if isinstance(raw, dict) else {}
        models = data.get("models", [])
        entries: list[NormalizedEntry] = []
        for m in models:
            entries.append(
                NormalizedEntry(
                    provider_id=m["provider_id"],
                    model_id=m["model_id"],
                    display_name=m.get("display_name"),
                    context_window=m.get("context_window"),
                    max_input_tokens=(m.get("limits") or {}).get("max_input_tokens"),
                    max_output_tokens=(m.get("limits") or {}).get("max_output_tokens"),
                    pricing=EntryPricing.from_mapping(m.get("pricing") or {}),
                    modalities=list(m.get("modalities") or []),
                    capabilities=list(m.get("capabilities") or []),
                    source_url=m.get("source_url"),
                )
            )
        return entries


_SAMPLE_PAYLOAD = {
    "models": [
        {
            "provider_id": "anthropic",
            "model_id": "claude-opus-4-6",
            "display_name": "Claude Opus 4.6",
            "context_window": 200000,
            "limits": {"max_input_tokens": 262144, "max_output_tokens": 32768},
            "pricing": {
                "input_cost_per_1m": 5.0,
                "output_cost_per_1m": 25.0,
                "cache_read_cost_per_1m": 0.5,
            },
            "modalities": ["text", "image"],
            "capabilities": ["tools", "vision", "long_context"],
            "source_url": "https://www.anthropic.com/claude/opus",
        },
        {
            "provider_id": "openai",
            "model_id": "gpt-4o",
            "context_window": 128000,
            "pricing": {"input": 2.5, "output": 10.0},
            "modalities": ["text", "image", "audio"],
            "capabilities": ["tools"],
        },
    ]
}


def test_fake_adapter_satisfies_protocol() -> None:
    adapter: SourceAdapter = FakeAdapter(_SAMPLE_PAYLOAD)
    raw = adapter.fetch()
    entries = adapter.normalize(raw)

    assert isinstance(entries, list)
    assert len(entries) == 2


def test_normalized_entry_covers_prices_context_modalities_capabilities() -> None:
    adapter = FakeAdapter(_SAMPLE_PAYLOAD)
    first = adapter.normalize(adapter.fetch())[0]

    assert first.provider_id == "anthropic"
    assert first.model_id == "claude-opus-4-6"
    assert first.context_window == 200000
    assert first.max_input_tokens == 262144
    assert first.max_output_tokens == 32768
    assert first.pricing.input == 5.0
    assert first.pricing.output == 25.0
    assert first.pricing.cache_read == 0.5
    assert first.modalities == ["text", "image"]
    assert first.capabilities == ["tools", "vision", "long_context"]


def test_pricing_from_mapping_accepts_canonical_field_names() -> None:
    pricing = EntryPricing.from_mapping({"input": 1.5, "output": 8.0, "cache_read": 0.25})
    assert pricing.input == 1.5
    assert pricing.output == 8.0
    assert pricing.cache_read == 0.25


def test_pricing_from_mapping_tolerates_missing_and_non_numeric() -> None:
    pricing = EntryPricing.from_mapping({"input": None, "output": "12.5", "nope": 1})
    assert pricing.input == 0.0
    assert pricing.output == 12.5
    assert pricing.cache_read == 0.0


def test_fetch_and_normalize_are_independent_steps() -> None:
    adapter = FakeAdapter(_SAMPLE_PAYLOAD)
    raw = adapter.fetch()
    assert adapter.fetch_calls == 1

    assert raw is not None
    assert adapter.normalize(raw) == adapter.normalize(raw)


# --- LiteLLM adapter ----------------------------------------------------------


def _litellm_model(**overrides: Any) -> dict[str, Any]:
    """Build a LiteLLM-shaped model record with sensible chat defaults."""
    record: dict[str, Any] = {
        "litellm_provider": "openai",
        "mode": "chat",
        "max_input_tokens": 128000,
        "max_output_tokens": 16384,
        "input_cost_per_token": 2.5e-06,
        "output_cost_per_token": 1.0e-05,
        "cache_read_input_token_cost": 1.25e-06,
        "supports_vision": False,
        "supports_image_input": False,
        "supports_pdf_input": False,
        "supports_audio_input": False,
        "supports_video_input": False,
        "supports_reasoning": False,
        "supports_function_calling": True,
    }
    record.update(overrides)
    return record


_LITELLM_PAYLOAD = {
    "gpt-4o": _litellm_model(
        supports_vision=True,
        supports_image_input=True,
        supports_function_calling=True,
    ),
    "gpt-3.5-turbo": _litellm_model(
        input_cost_per_token=5.0e-07,
        output_cost_per_token=1.5e-06,
        deprecation_date="2026-10-23",
    ),
    "text-embedding-3-small": _litellm_model(mode="embedding"),
}


def test_litellm_norm_skips_non_chat_modes() -> None:
    from faigate.catalog_sources.litellm import LiteLLMAdapter

    entries = LiteLLMAdapter().normalize(_LITELLM_PAYLOAD)
    model_ids = {e.model_id for e in entries}
    assert model_ids == {"gpt-4o", "gpt-3.5-turbo"}
    assert "text-embedding-3-small" not in model_ids


def test_litellm_norm_converts_per_token_price_to_per_1m() -> None:
    from faigate.catalog_sources.litellm import LiteLLMAdapter

    entry = LiteLLMAdapter().normalize({"gpt-4o": _litellm_model()})[0]
    assert entry.pricing.input == pytest.approx(2.5)
    assert entry.pricing.output == pytest.approx(10.0)
    assert entry.pricing.cache_read == pytest.approx(1.25)
    assert entry.context_window == 128000
    assert entry.max_output_tokens == 16384


def test_litellm_norm_maps_supports_vision_to_image_modality() -> None:
    from faigate.catalog_sources.litellm import LiteLLMAdapter

    entry = LiteLLMAdapter().normalize({"gpt-4o": _litellm_model(supports_vision=True)})[0]
    assert "image" in entry.modalities

    plain = LiteLLMAdapter().normalize({"gpt-3.5-turbo": _litellm_model()})[0]
    assert "image" not in plain.modalities


def test_litellm_norm_carries_deprecation_date_onto_tier_status() -> None:
    from faigate.catalog_sources.litellm import LiteLLMAdapter

    entries = LiteLLMAdapter().normalize(_LITELLM_PAYLOAD)
    by_id = {e.model_id: e for e in entries}

    deprecated = by_id["gpt-3.5-turbo"]
    assert deprecated.tier_status == "deprecated"
    assert deprecated.deprecation_date == "2026-10-23"

    active = by_id["gpt-4o"]
    assert active.tier_status == "active"
    assert active.deprecation_date is None


def test_litellm_norm_produces_at_least_250_priced_context_entries() -> None:
    from faigate.catalog_sources.litellm import LiteLLMAdapter

    payload = {
        f"model-{i}": _litellm_model(
            max_input_tokens=64000 + i,
            input_cost_per_token=(1.0 + i) * 1.0e-06,
            output_cost_per_token=(2.0 + i) * 1.0e-06,
        )
        for i in range(251)
    }
    entries = LiteLLMAdapter().normalize(payload)

    assert len(entries) == 251
    priced_with_context = [e for e in entries if (e.pricing.input > 0 or e.pricing.output > 0) and e.context_window]
    assert len(priced_with_context) >= 250
