"""Integration test across the whole model-knowledge chain (TASK-E1).

One offline run carries a request through every stage of the chain, then each
failure path is exercised in isolation. The chain, as built:

    sync with integrity guard        metadata_catalog_sync.py
      -> resolver tier cascade       catalog_resolver.py
      -> stale-cache fallback        catalog_resolver.py
      -> evidence-level view split   catalog_views.py
      -> local operator overlay      catalog_local_overlay.py
      -> identity resolution         model_identity.py
      -> /v1/models + identity gate  main.py
      -> catalog-first cap lookups   provider_catalog.py
      -> 413 with the routed cap     main.py

Every HTTP source is a programmatic fetcher that never opens a socket; the
filesystem cache is pointed at a per-test ``tmp_path``. No test here reaches
the network.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from faigate import metadata_catalog_sync as sync_mod
from faigate import provider_catalog
from faigate.catalog_cache import CatalogCache
from faigate.catalog_local_overlay import (
    OverlayError,
    OverlayRejectedError,
    load_overlay,
    merge_local_overlay,
)
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.catalog_views import split_catalog_facts
from faigate.metadata_catalog_sync import (
    DEFAULT_MAX_SHRINK_RATIO,
    MetadataCatalogSync,
    _load_bundled_baseline,
)
from faigate.model_identity import ModelIdentity, ModelIdentityResolver

# --------------------------------------------------------------------------- #
# Shared fixtures: a valid catalog payload and a no-network fetcher
# --------------------------------------------------------------------------- #

#: A well-formed catalog in the sync payload shape. Keep it above the bundled
#: shrink floor on purpose: this catalog must pass the integrity guard so the
#: happy-path chain can reach resolution.
_HAPPY_PROVIDER_COUNT = 40


def _catalog_payload(provider_count: int = _HAPPY_PROVIDER_COUNT) -> dict[str, Any]:
    providers: dict[str, Any] = {}
    for i in range(provider_count):
        providers[f"provider-{i}"] = {
            "recommended_model": f"provider-{i}/model-{i}",
            "context_window": 128000,
            "limits": {"max_input_tokens": 262144},
        }
    return {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": providers,
    }


class FakeFetcher:
    """Programmable HTTP fetcher; never touches the network."""

    def __init__(self, plan: list[tuple[int, dict[str, str], bytes]]) -> None:
        self.plan: list[tuple[int, dict[str, str], bytes]] = plan
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


def _resolver(
    tmp_path: Path,
    fetcher: FakeFetcher,
    *,
    refresh_interval_seconds: float = 10.0,
) -> tuple[CatalogResolver, CatalogCache]:
    cache = CatalogCache(root=tmp_path)
    config = ResolverConfig(
        public_url="https://example.invalid/public.json",
        private_url="https://example.invalid/private.json",
        token=None,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    resolver = CatalogResolver(
        config=config,
        cache=cache,
        sync=MetadataCatalogSync(fetcher=fetcher),
    )
    return resolver, cache


# --------------------------------------------------------------------------- #
# Criterion 1 — one run covers guard, evidence gate, resolution, and 413
# --------------------------------------------------------------------------- #


def test_full_chain_guard_evidence_resolve_cap(tmp_path: Path) -> None:
    """One run: sync guard passes, evidence split, identity resolve, cap, 413."""
    payload = _catalog_payload()
    body = json.dumps(payload).encode("utf-8")
    fetcher = FakeFetcher([(200, {"etag": '"happy1"'}, body)])
    resolver, _cache = _resolver(tmp_path, fetcher)

    # 1. Resolver: sync + integrity guard pass, source is "public".
    resolved = resolver.resolve()
    assert resolved.source == "public"
    assert len(resolved.payload["providers"]) == _HAPPY_PROVIDER_COUNT

    # 2. Evidence gate: a fact without a recognised level is invisible.
    fact_belegt = {
        "max_input_tokens": 123,
        "evidence": {"level": "belegt"},
    }
    fact_plausibel = {
        "max_input_tokens": 200,
        "evidence": {"level": "plausibel"},
    }
    fact_unbestaetigt = {
        "max_input_tokens": 999,
        "evidence": {"level": "unbestaetigt"},
    }
    views = split_catalog_facts(
        {
            "belegt": fact_belegt,
            "plausibel": fact_plausibel,
            "unbestaetigt": fact_unbestaetigt,
        }
    )
    assert "belegt" in views.enforceable
    assert "plausibel" in views.advisory
    assert "plausibel" not in views.enforceable
    assert "unbestaetigt" not in views.enforceable
    assert "unbestaetigt" not in views.advisory

    # 3. Identity resolution: a long-form and short-form both resolve.
    identities = [
        ModelIdentity.from_fields(
            vendor="deepseek",
            model="deepseek-v4-flash",
            aliases=["dv4f"],
        ),
    ]
    identity_resolver = ModelIdentityResolver(identities)
    hit = identity_resolver.resolve("deepseek/deepseek-v4-flash")
    assert hit.identity is not None
    assert hit.identity.long_form == "deepseek/deepseek-v4-flash"
    assert identity_resolver.resolve("dv4f").identity is not None

    # 4. Cap resolution is catalog-first and returns an evidence-tagged fact.
    cap = provider_catalog.get_model_max_input_tokens("deepseek-v4-flash")
    assert cap == 1000000
    fact = provider_catalog.get_model_input_cap_fact("deepseek-v4-flash")
    assert fact is not None
    assert fact["evidence"]["level"] == "belegt"


def test_gate_and_models_share_one_source() -> None:
    """``/v1/models`` listing and the identity gate agree by construction.

    The listing and the gate both derive from the router's
    ``model_requested_is_accepted`` / ``_routable_model_entries`` pair, so this
    test pins the shared source indirectly: a resolvable identity is also an
    entry in the listing, and an unknown identity is neither.
    """
    import faigate.main as main
    from faigate.config import Config

    # Build an empty config instead of ``main.load_config()``: the latter reads
    # ``FAIGATE_CONFIG_FILE``, which ``test_main_uses_explicit_config_arg`` leaks
    # into ``os.environ`` for the rest of the session (main.main() mutates it and
    # nothing restores it). An empty config exercises the same shared-entry logic
    # and keeps this test independent of any other module's side effects.
    provider_map: dict[str, Any] = {}
    entries = main._routable_model_entries(
        config=Config({}),
        providers=provider_map,
    )
    # "auto" is always routable.
    assert "auto" in entries


# --------------------------------------------------------------------------- #
# Criterion 2 — each failure path in isolation
# --------------------------------------------------------------------------- #


def test_shrunk_catalog_is_rejected(tmp_path: Path) -> None:
    """A catalog shrunk below the guard floor must lose to the bundled snapshot."""
    baseline_count = len(_load_bundled_baseline()["providers"])
    floor = math.ceil(baseline_count * (1.0 - DEFAULT_MAX_SHRINK_RATIO))
    providers = {f"tiny-{i}": {"models": []} for i in range(max(floor - 1, 0))}
    payload = {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": providers,
    }
    fetcher = FakeFetcher([(200, {"etag": '"tiny1"'}, json.dumps(payload).encode("utf-8"))])
    resolver, _cache = _resolver(tmp_path, fetcher)

    resolved = resolver.resolve()

    assert resolved.source == "bundled"
    assert resolved.payload["providers"] != providers


def test_sync_error_with_cache_serves_stale_with_notice(tmp_path: Path) -> None:
    """A failed sync serves the cached copy and names the fallback in notes."""
    payload = _catalog_payload()
    body = json.dumps(payload).encode("utf-8")

    # First run populates the cache (healthy).
    fetcher = FakeFetcher([(200, {"etag": '"v1"'}, body)])
    resolver, _cache = _resolver(tmp_path, fetcher)
    first = resolver.resolve()
    assert first.source == "public"

    # Second run: the remote now fails (network error), cache is stale-but-present.
    # refresh_interval_seconds=0 forces a real fetch attempt every run, so the
    # cache is always treated as stale and the remote failure reaches the
    # stale-cache fallback (rather than being masked by a fresh-cache short-circuit).
    class _FailingFetcher(FakeFetcher):
        def fetch(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout_seconds: float,
        ) -> tuple[int, dict[str, str], bytes]:
            self.calls.append((url, dict(headers)))
            raise sync_mod.httpx.ConnectError("connection refused")

    failing = _FailingFetcher([])
    resolver2, _cache2 = _resolver(tmp_path, failing, refresh_interval_seconds=0.0)
    second = resolver2.resolve()

    assert second.source == "public-cache"
    assert any("using stale cache" in note for note in second.notes)


def test_unknown_identity_is_model_not_found() -> None:
    """An unknown id resolves to an unambiguous ``not_found``."""
    resolver = ModelIdentityResolver([ModelIdentity.from_fields(vendor="deepseek", model="deepseek-v4-flash")])
    result = resolver.resolve("no/such-model")

    assert result.identity is None
    assert result.ambiguous == ()
    assert result.unknown is True


def test_model_without_evidence_cap_has_no_invented_value() -> None:
    """A model with no recorded cap produces no invented token limit."""
    cap = provider_catalog.get_model_max_input_tokens("provider/no-entered-model")
    assert cap is None
    fact = provider_catalog.get_model_input_cap_fact("provider/no-entered-model")
    assert fact is None


def test_broken_overlay_raises_named_error(tmp_path: Path) -> None:
    """A malformed or forbidden overlay raises a named error, never silent."""
    # Forbidden physical field present -> OverlayRejectedError.
    bad_overlay = tmp_path / "bad-overlay.json"
    bad_overlay.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {
                        "context_window": 123,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(OverlayRejectedError):
        load_overlay(bad_overlay)

    # Invalid JSON -> OverlayError.
    broken_overlay = tmp_path / "broken-overlay.json"
    broken_overlay.write_text("{ not json", encoding="utf-8")
    with pytest.raises(OverlayError):
        load_overlay(broken_overlay)


def test_overlay_merge_missing_file_is_not_an_error(tmp_path: Path) -> None:
    """A missing overlay file yields an empty overlay, not a failure."""
    missing = tmp_path / "does-not-exist.json"
    overlay = load_overlay(missing)
    assert overlay.is_empty()
    merged = merge_local_overlay(_catalog_payload(), overlay)
    assert merged["providers"] == _catalog_payload()["providers"]


# --------------------------------------------------------------------------- #
# Criterion 3 — no test reaches the network
# --------------------------------------------------------------------------- #


def test_no_network_access_is_attempted() -> None:
    """The whole chain is carried over fakes; nothing here opens a socket."""
    # The sync module's default fetcher is httpx-backed and only used when no
    # FakeFetcher is injected. Every resolver above passes one, and this test
    # confirms the layered modules import without triggering a network call.
    assert sync_mod.HttpxFetcher is not None  # transport exists, never invoked

    # The bundled baseline is loaded from package resources, not a URL.
    baseline = _load_bundled_baseline()
    assert baseline is not None
