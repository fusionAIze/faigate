"""Tests for the catalog source adapter interface."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

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


# --- OmniRoute adapter --------------------------------------------------------


def _omniroute_model(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "model-a",
        "name": "Model A",
        "toolCalling": True,
        "supportsReasoning": True,
        "supportsVision": False,
        "supportsAudio": False,
        "supportsVideo": False,
        "supportsXHighEffort": None,
        "supportedThinkingEfforts": None,
        "maxOutputTokens": 4096,
        "contextLength": 131072,
        "maxInputTokens": None,
    }
    record.update(overrides)
    return record


def _omniroute_provider(models: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": "deepseek", "alias": "ds", "models": models}


def _omniroute_payload(
    providers: dict[str, Any] | None = None,
    free_model_budgets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "providers": providers or {"deepseek": _omniroute_provider([_omniroute_model()])},
        "free_model_budgets": free_model_budgets if free_model_budgets is not None else [],
    }


def _big_omniroute_payload(count: int = 120) -> dict[str, Any]:
    """Synthesize a provider catalog with ``count`` providers and one model each."""
    providers: dict[str, Any] = {}
    for i in range(count):
        provider_id = f"provider-{i}"
        providers[provider_id] = _omniroute_provider([_omniroute_model(id=f"model-{i}", name=f"Model {i}")])
    return _omniroute_payload(providers=providers)


def test_omniroute_repo_url_is_hardwired() -> None:
    from faigate.catalog_sources.omniroute import OMNIROUTE_REPO_URL

    assert OMNIROUTE_REPO_URL == "https://github.com/diegosouzapw/OmniRoute.git"


def test_omniroute_repo_url_rejects_fork() -> None:
    from faigate.catalog_sources.omniroute import OMNIROUTE_REPO_URL

    # A fork (or lookalike) must not silently become the source. Any string
    # that is not the canonical diegosouzapw URL is a fork mix-up.
    assert OMNIROUTE_REPO_URL != "https://github.com/someone-else/OmniRoute.git"
    assert OMNIROUTE_REPO_URL != "https://github.com/diegosouzapw/omni-Route.git"
    assert "diegosouzapw/OmniRoute" in OMNIROUTE_REPO_URL


def test_omniroute_normalizes_at_least_100_providers() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    entries = OmniRouteAdapter().normalize(_big_omniroute_payload(count=120))
    provider_ids = {e.provider_id for e in entries}
    assert len(provider_ids) >= 100
    assert len(provider_ids) == 120


def test_omniroute_maps_registry_flags_to_modalities_and_capabilities() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    payload = _omniroute_payload(
        providers={
            "deepseek": _omniroute_provider(
                [
                    _omniroute_model(
                        id="deepseek-v4-pro",
                        name="DeepSeek V4 Pro",
                        supportsVision=True,
                        supportsAudio=True,
                        supportsReasoning=True,
                        toolCalling=True,
                        supportedThinkingEfforts=["none", "low", "high", "max"],
                        contextLength=1_000_000,
                        maxOutputTokens=384_000,
                    )
                ]
            )
        }
    )
    entry = OmniRouteAdapter().normalize(payload)[0]

    assert entry.provider_id == "deepseek"
    assert entry.model_id == "deepseek-v4-pro"
    assert entry.display_name == "DeepSeek V4 Pro"
    assert entry.context_window == 1_000_000
    assert entry.max_output_tokens == 384_000
    assert "image" in entry.modalities
    assert "audio" in entry.modalities
    assert "toolCalling" in entry.capabilities
    assert "supportsReasoning" in entry.capabilities
    assert "thinking_efforts" in entry.capabilities


def test_omniroute_free_tier_lands_in_free_tier_field() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    payload = _omniroute_payload(
        providers={"cerebras": _omniroute_provider([_omniroute_model(id="zai-glm-4.7", name="GLM 4.7")])},
        free_model_budgets=[
            {
                "provider": "cerebras",
                "modelId": "zai-glm-4.7",
                "monthlyTokens": 30_000_000,
                "creditTokens": 0,
                "freeType": "recurring-daily",
            }
        ],
    )
    entry = OmniRouteAdapter().normalize(payload)[0]

    assert entry.free_tier is not None
    assert entry.free_tier.tokens_per_month == 30_000_000


def test_omniroute_uncapped_free_tier_has_no_cap() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    payload = _omniroute_payload(
        providers={"blackbox": _omniroute_provider([_omniroute_model(id="gpt-4o")])},
        free_model_budgets=[
            {
                "provider": "blackbox",
                "modelId": "gpt-4o",
                "monthlyTokens": 0,
                "creditTokens": 0,
                "freeType": "keyless",
            }
        ],
    )
    entry = OmniRouteAdapter().normalize(payload)[0]

    assert entry.free_tier is not None
    assert entry.free_tier.tokens_per_month is None


def test_omniroute_free_tier_is_model_scoped_not_provider_scoped() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    # A provider-level budget must not leak onto unrelated models of the same
    # provider. Only models with their own (provider, modelId) budget are free.
    payload = _omniroute_payload(
        providers={
            "demo": _omniroute_provider(
                [
                    _omniroute_model(id="free-model"),
                    _omniroute_model(id="paid-model"),
                ]
            )
        },
        free_model_budgets=[
            {
                "provider": "demo",
                "modelId": "free-model",
                "monthlyTokens": 30_000_000,
                "creditTokens": 0,
                "freeType": "recurring-daily",
            }
        ],
    )
    entries = OmniRouteAdapter().normalize(payload)
    by_id = {e.model_id: e for e in entries}

    assert by_id["free-model"].free_tier is not None
    assert by_id["free-model"].free_tier.tokens_per_month == 30_000_000
    assert by_id["paid-model"].free_tier is None


def test_omniroute_free_tier_ignores_budget_without_model_id() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    # A budget lacking a modelId is dropped, not attributed to every model.
    payload = _omniroute_payload(
        providers={"demo": _omniroute_provider([_omniroute_model(id="some-model")])},
        free_model_budgets=[
            {
                "provider": "demo",
                "modelId": None,
                "monthlyTokens": 10_000_000,
                "creditTokens": 0,
                "freeType": "recurring-daily",
            }
        ],
    )
    entry = OmniRouteAdapter().normalize(payload)[0]

    assert entry.free_tier is None


def test_omniroute_ollama_cloud_pins_8_free_4_not() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    # Real upstream case: ollama-cloud carries 12 models but only 8 have a
    # free-model budget. The other 4 must not be marked free by provider fallback.
    model_ids = [
        "glm-5.2",
        "gpt-oss:120b",
        "gpt-oss:20b",
        "minimax-m3",
        "qwen3-coder:30b",
        "deepseek-r1:7b",
        "llama3.3:70b",
        "hermes3:405b",
        "paid-model-1",
        "paid-model-2",
        "paid-model-3",
        "paid-model-4",
    ]
    free_ids = set(model_ids[:8])
    budgets = [
        {
            "provider": "ollama-cloud",
            "modelId": mid,
            "monthlyTokens": 20_000_000 if mid != "gpt-oss:120b" else 0,
            "creditTokens": 0,
            "freeType": "recurring-daily",
        }
        for mid in free_ids
    ]
    payload = _omniroute_payload(
        providers={"ollama-cloud": _omniroute_provider([_omniroute_model(id=mid) for mid in model_ids])},
        free_model_budgets=budgets,
    )
    entries = OmniRouteAdapter().normalize(payload)

    free_tiered = {e.model_id for e in entries if e.free_tier is not None}
    assert free_tiered == free_ids
    assert len(free_tiered) == 8
    assert len(entries) - len(free_tiered) == 4


def test_omniroute_resolve_node_major_reads_pin_files() -> None:
    from faigate.catalog_sources.omniroute import _resolve_node_major

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert _resolve_node_major(root) == "24"

        (root / ".nvmrc").write_text("24\n", encoding="utf-8")
        assert _resolve_node_major(root) == "24"

        (root / ".node-version").write_text("22.22.2\n", encoding="utf-8")
        assert _resolve_node_major(root) == "22"


def test_omniroute_check_node_major_fails_loudly_on_mismatch() -> None:
    from faigate.catalog_sources.omniroute import _check_node_major

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".node-version").write_text("24\n", encoding="utf-8")

        with mock.patch(
            "faigate.catalog_sources.omniroute.subprocess.run",
            return_value=mock.Mock(stdout="v26.8.1\n", stderr="", returncode=0),
        ):
            with pytest.raises(RuntimeError, match="pins Node major 24"):
                _check_node_major(root)


def test_omniroute_check_node_major_accepts_matching_runtime() -> None:
    from faigate.catalog_sources.omniroute import _check_node_major

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".node-version").write_text("24\n", encoding="utf-8")

        with mock.patch(
            "faigate.catalog_sources.omniroute.subprocess.run",
            return_value=mock.Mock(stdout="v24.9.0\n", stderr="", returncode=0),
        ):
            _check_node_major(root)


def test_omniroute_tsx_command_pins_version_and_ignore_scripts() -> None:
    from faigate.catalog_sources.omniroute import _install_tsx, _tsx_binary_dir

    with TemporaryDirectory() as tmp:
        root = Path(tmp)

        def _fake_install(argv, **kwargs):
            assert argv[0] == "npm"
            assert argv[1] == "install"
            assert "--ignore-scripts" in argv
            assert "--no-audit" in argv
            assert "--no-fund" in argv
            assert any(arg.startswith("tsx@") for arg in argv)
            assert "tsx@4.23.13" in argv
            bin_dir = root / ".faigate-tsx-runtime" / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            (bin_dir / "tsx").write_text("#!/bin/sh\n", encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch(
            "faigate.catalog_sources.omniroute.subprocess.run",
            side_effect=_fake_install,
        ):
            tsx_bin = _install_tsx(root)

        assert tsx_bin.is_file()
        assert tsx_bin == _tsx_binary_dir(root) / "node_modules" / ".bin" / "tsx"


def test_omniroute_normalize_returns_empty_for_non_dict() -> None:
    from faigate.catalog_sources.omniroute import OmniRouteAdapter

    assert OmniRouteAdapter().normalize("not a dict") == []
    assert OmniRouteAdapter().normalize(None) == []
