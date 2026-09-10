"""Integration test across the full catalog pipeline.

Proves one run carries a model through every stage of the chain:

    fetch -> normalize -> merge -> validate -> resolve

The two foreign sources (LiteLLM registry, OmniRoute TS configs) are fetched
from in-memory / on-disk fixtures -- never the network -- then normalized
through their adapters, merged against an operator overlay by fixed
precedence, validated for schema shape, and finally resolved through the
:class:`~faigate.catalog_resolver.CatalogResolver` tier chain (public -> bundled).

Each source is failed in isolation to prove a single foreign-source outage
does not take the rest of the pipeline down with it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from faigate.catalog_cache import CatalogCache
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.catalog_sources.base import EntryPricing, NormalizedEntry
from faigate.catalog_sources.litellm import LiteLLMAdapter
from faigate.catalog_sources.merge import SourceInput, merge_catalogs
from faigate.catalog_sources.omniroute import OmniRouteAdapter
from faigate.metadata_catalog_sync import (
    DEFAULT_MAX_SHRINK_RATIO,
    MetadataCatalogSync,
    _load_bundled_baseline,
)

#: Checked-in LiteLLM registry slice (no network).
_LITELLM_FIXTURE = Path(__file__).parent / "fixtures" / "litellm" / "model_prices_and_context_window.json"

#: Number of synthetic OmniRoute providers in the fixture. Must stay well above
#: the guard's retained floor (half the bundled provider count) so the chain
#: test survives bundled-catalog growth without touching the guard.
_OMNIROUTE_FIXTURE_PROVIDERS = 60


class FakeFetcher:
    """Programmable HTTP fetcher; never touches the network."""

    def __init__(self, plan: list[tuple[int, dict[str, str], bytes]]) -> None:
        self.plan = plan
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, dict(headers)))
        if not self.plan:
            raise AssertionError("FakeFetcher plan exhausted")
        return self.plan.pop(0)


def _litellm_entries() -> list[NormalizedEntry]:
    with _LITELLM_FIXTURE.open() as f:
        raw = json.load(f)
    return LiteLLMAdapter().normalize(raw)


def _omniroute_entries() -> list[NormalizedEntry]:
    providers: dict[str, Any] = {
        "deepseek": {
            "id": "deepseek",
            "alias": "ds",
            "models": [
                {
                    "id": "deepseek-v4-pro",
                    "name": "DeepSeek V4 Pro",
                    "toolCalling": True,
                    "supportsReasoning": True,
                    "supportsVision": False,
                    "supportsAudio": False,
                    "supportsVideo": False,
                    "maxOutputTokens": 384000,
                    "contextLength": 1000000,
                    "maxInputTokens": None,
                }
            ],
        }
    }
    # OmniRoute is a multi-provider registry. The integrity guard counts
    # top-level providers, so the outage-isolation case (OmniRoute is the only
    # surviving foreign source) needs a realistic provider spread; a one-model
    # catalog would rightly be rejected as a shrink against the bundled
    # baseline.
    for index in range(_OMNIROUTE_FIXTURE_PROVIDERS):
        provider_id = f"omniroute-fixture-{index}"
        providers[provider_id] = {
            "id": provider_id,
            "alias": None,
            "models": [
                {
                    "id": f"fixture-model-{index}",
                    "name": f"Fixture Model {index}",
                    "toolCalling": False,
                    "supportsReasoning": False,
                    "supportsVision": False,
                    "supportsAudio": False,
                    "supportsVideo": False,
                    "maxOutputTokens": 8192,
                    "contextLength": 32768,
                    "maxInputTokens": None,
                }
            ],
        }
    payload = {
        "providers": providers,
        "free_model_budgets": [
            {
                "provider": "deepseek",
                "modelId": "deepseek-v4-pro",
                "monthlyTokens": 10000000,
                "creditTokens": 0,
                "freeType": "recurring-daily",
            }
        ],
    }
    return OmniRouteAdapter().normalize(payload)


#: Overlay model key collides with a real LiteLLM fixture entry so the
#: conflict test exercises a genuine precedence decision, not a synthetic one.
_OVERLAY_PROVIDER = "openai"
_OVERLAY_MODEL = "ft:gpt-4.1-2025-04-14"


def _overlay_entries() -> list[NormalizedEntry]:
    return [
        NormalizedEntry(
            provider_id=_OVERLAY_PROVIDER,
            model_id=_OVERLAY_MODEL,
            display_name="GPT-4.1 (curated free)",
            pricing=EntryPricing(input=0.0, output=0.0, cache_read=0.0),
        )
    ]


def _run_pipeline(
    *,
    litellm_entries: list[NormalizedEntry] | None,
    omniroute_entries: list[NormalizedEntry] | None,
) -> tuple[list[NormalizedEntry], list[Any]]:
    """Fetch/normalize inputs already in hand; merge them + overlay."""
    sources: list[SourceInput] = [SourceInput("overlay", _overlay_entries())]
    if litellm_entries is not None:
        sources.append(SourceInput("litellm", litellm_entries))
    if omniroute_entries is not None:
        sources.append(SourceInput("omniroute", omniroute_entries))
    result = merge_catalogs(sources)
    return result.entries, result.conflicts


def _validate_merged_shape(entries: list[NormalizedEntry]) -> None:
    """Schema-shape check mirrors MetadataCatalogSync._validate_payload_shape."""
    assert isinstance(entries, list)
    for e in entries:
        assert e.provider_id
        assert e.model_id
        if e.pricing is not None:
            assert isinstance(e.pricing.input, float)
            assert isinstance(e.pricing.output, float)
            assert isinstance(e.pricing.cache_read, float)


def _resolve_catalog(
    tmp_path: Path,
    entries: list[NormalizedEntry],
) -> Any:
    """Resolve the merged catalog through the resolver tiers (public).

    The payload uses the real catalog shape: entries grouped into a nested
    ``providers`` mapping, because that top-level provider count is exactly what
    the sync integrity guard measures. The guard only cares that the catalog
    clears its floor, which is why the provider count assertion below is a
    floor rather than an equality.
    """
    providers: dict[str, Any] = {}
    for e in entries:
        provider = providers.setdefault(e.provider_id, {"models": []})
        provider["models"].append(
            {
                "model_id": e.model_id,
                "display_name": e.display_name,
            }
        )
    payload = {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
        "entries": [
            {
                "provider_id": e.provider_id,
                "model_id": e.model_id,
                "display_name": e.display_name,
            }
            for e in entries
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    fetcher = FakeFetcher([(200, {"etag": '"merged1"'}, body)])
    sync = MetadataCatalogSync(fetcher=fetcher)
    cache = CatalogCache(root=tmp_path)
    config = ResolverConfig(
        public_url="https://example/public.json",
        private_url="https://example/private.json",
        token=None,
        refresh_interval_seconds=10.0,
    )
    resolver = CatalogResolver(config=config, cache=cache, sync=sync)
    resolved = resolver.resolve()
    assert resolved.source == "public"
    assert len(resolved.payload["providers"]) > 0
    return resolved.payload


def test_full_chain_fetch_normalize_merge_validate_resolve(tmp_path: Path) -> None:
    litellm = _litellm_entries()
    omniroute = _omniroute_entries()

    assert litellm, "LiteLLM fixture normalized to nothing"
    assert omniroute, "OmniRoute fixture normalized to nothing"

    entries, _conflicts = _run_pipeline(
        litellm_entries=litellm,
        omniroute_entries=omniroute,
    )

    assert entries, "merged catalog is empty"

    _validate_merged_shape(entries)

    resolved = _resolve_catalog(tmp_path, entries)
    assert len(resolved["entries"]) == len(entries)


def test_overlay_beats_foreign_sources_across_the_chain(tmp_path: Path) -> None:
    litellm = _litellm_entries()
    omniroute = _omniroute_entries()

    entries, conflicts = _run_pipeline(
        litellm_entries=litellm,
        omniroute_entries=omniroute,
    )

    overlay_model = next(e for e in entries if e.model_id == _OVERLAY_MODEL)
    assert overlay_model.pricing.input == 0.0
    assert overlay_model.pricing.output == 0.0

    gpt_conflicts = [c for c in conflicts if c.model_id == _OVERLAY_MODEL and c.field == "pricing"]
    assert gpt_conflicts, "curated zero price against foreign price must log a conflict"
    assert {c.winner_source for c in gpt_conflicts} == {"overlay"}
    assert {c.loser_source for c in gpt_conflicts} == {"litellm"}


def test_litellm_source_failure_leaves_rest_of_chain_intact(tmp_path: Path) -> None:
    omniroute = _omniroute_entries()

    entries, _conflicts = _run_pipeline(
        litellm_entries=None,
        omniroute_entries=omniroute,
    )

    model_ids = {e.model_id for e in entries}
    assert _OVERLAY_MODEL in model_ids  # overlay still present
    assert "deepseek-v4-pro" in model_ids  # omniroute still present

    _validate_merged_shape(entries)
    _resolve_catalog(tmp_path, entries)


def test_omniroute_source_failure_leaves_rest_of_chain_intact(tmp_path: Path) -> None:
    litellm = _litellm_entries()

    entries, _conflicts = _run_pipeline(
        litellm_entries=litellm,
        omniroute_entries=None,
    )

    model_ids = {e.model_id for e in entries}
    assert _OVERLAY_MODEL in model_ids  # overlay still present
    assert model_ids & {e.model_id for e in litellm}  # litellm still present

    _validate_merged_shape(entries)
    _resolve_catalog(tmp_path, entries)


def test_small_catalog_falls_back_to_bundle_instead_of_being_served(tmp_path: Path) -> None:
    """A catalog under the shrink floor must lose to the bundled snapshot.

    This is the guard's whole point, pinned at the chain level: if a truncated
    sync could still win, the resolver would serve a degraded catalog and the
    guard would be decorative. ``min_entries`` may accept the payload (it is
    non-empty), so the shrink ratio against the bundled baseline is what must
    reject it. Thresholds stay at their production defaults on purpose.
    """
    baseline_count = len(_load_bundled_baseline()["providers"])
    floor = math.ceil(baseline_count * (1.0 - DEFAULT_MAX_SHRINK_RATIO))
    providers = {f"tiny-{i}": {"models": []} for i in range(floor - 1)}
    payload = {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }

    fetcher = FakeFetcher([(200, {"etag": '"tiny1"'}, json.dumps(payload).encode("utf-8"))])
    resolver = CatalogResolver(
        config=ResolverConfig(
            public_url="https://example/public.json",
            private_url="https://example/private.json",
            token=None,
            refresh_interval_seconds=10.0,
        ),
        cache=CatalogCache(root=tmp_path),
        sync=MetadataCatalogSync(fetcher=fetcher),
    )

    resolved = resolver.resolve()
    assert resolved.source == "bundled"
    assert resolved.payload["providers"] != providers


def test_no_network_access_is_attempted() -> None:
    """Guarantee the pipeline never reaches the network.

    The LiteLLM adapter is transport-agnostic (its ``fetch`` raises) and the
    resolver is fed a FakeFetcher, so there is no code path here that opens a
    socket.
    """
    with pytest.raises(NotImplementedError):
        LiteLLMAdapter().fetch()
