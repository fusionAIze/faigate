"""Observability contract for the CatalogResolver stale-cache fallback.

When a remote tier fails but a previously cached catalog is still on disk,
the resolver keeps serving that stale copy. That fallback is intentional —
these tests pin three properties around it:

1. On ``SyncStatus.ERROR`` with a cache present the stale copy is served
   *and* the fallback is reported: a warning naming the reason and the age
   of the copy.
2. On a normal ``FRESH`` sync no stale-cache warning is emitted, so the
   signal stays meaningful instead of becoming background noise.
3. The fallback behaviour itself is unchanged: a stale copy is returned,
   never an error and never an empty catalog.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from faigate import metadata_catalog_sync
from faigate.catalog_cache import CatalogCache
from faigate.catalog_resolver import (
    CatalogResolver,
    ResolverConfig,
    _invalidate_bundled_snapshot_cache,
    _load_bundled_snapshot,
)
from faigate.metadata_catalog_sync import MetadataCatalogSync


@pytest.fixture(autouse=True)
def _no_shrink_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the resolver-fallback contract independent of the shrink guard."""
    monkeypatch.setattr(metadata_catalog_sync, "_load_bundled_baseline", lambda: None, raising=False)


class FakeFetcher:
    """HTTP fetcher that replays a fixed plan of (status, headers, body)."""

    def __init__(self, plan: list[tuple[int, dict[str, str], bytes]]) -> None:
        self.plan = plan
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fetch(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,  # noqa: ARG002
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, dict(headers)))
        if not self.plan:
            raise AssertionError("FakeFetcher plan exhausted")
        return self.plan.pop(0)


def _payload() -> dict[str, Any]:
    providers = {f"provider-{i}": {"recommended_model": f"model-{i}"} for i in range(10)}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }


def _body() -> bytes:
    return json.dumps(_payload()).encode("utf-8")


def _make_resolver(
    tmp_path: Path,
    *,
    plan: list[tuple[int, dict[str, str], bytes]],
) -> tuple[CatalogResolver, FakeFetcher]:
    fetcher = FakeFetcher(plan)
    sync = MetadataCatalogSync(fetcher=fetcher)
    cache = CatalogCache(root=tmp_path)
    config = ResolverConfig(
        public_url="https://example/public.json",
        private_url="https://example/private.json",
        token=None,
        refresh_interval_seconds=10.0,
    )
    return CatalogResolver(config=config, cache=cache, sync=sync), fetcher


def _resolver_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "faigate.catalog_resolver" and rec.levelno >= logging.WARNING
    ]


def test_error_with_cache_warns_with_reason_and_age(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[
            (200, {"etag": '"v1"'}, _body()),  # seed the cache
            (500, {}, b""),  # remote now unhealthy → SyncStatus.ERROR
        ],
    )
    resolver.resolve()

    with caplog.at_level(logging.WARNING, logger="faigate.catalog_resolver"):
        stale = resolver.resolve(force_refresh=True)

    assert stale.source == "public-cache"
    assert any("using stale cache" in note for note in stale.notes)

    warnings = _resolver_warnings(caplog)
    assert warnings, "stale-cache fallback produced no warning"
    assert any(
        "using stale cache" in msg and "http 500" in msg and "age=" in msg and "reason=http 500" in msg
        for msg in warnings
    ), f"warning missing reason/age detail: {warnings}"


def test_fresh_sync_does_not_emit_stale_cache_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[(200, {"etag": '"v1"'}, _body())],
    )

    with caplog.at_level(logging.WARNING, logger="faigate.catalog_resolver"):
        resolved = resolver.resolve()

    assert resolved.source == "public"
    assert not any("stale cache" in msg for msg in _resolver_warnings(caplog))


def test_error_with_cache_serves_stale_copy_instead_of_failing(tmp_path: Path) -> None:
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[
            (200, {"etag": '"v1"'}, _body()),
            (500, {}, b""),
        ],
    )
    seeded = resolver.resolve()
    stale = resolver.resolve(force_refresh=True)

    assert stale.source == "public-cache"
    assert stale.payload == seeded.payload
    assert stale.etag == '"v1"'


def test_bundled_snapshot_is_memoised_and_invalidatable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bundled snapshot parse happens once, not per call, and is resettable.

    ``_load_bundled_snapshot`` sits on the request path (the resolution chain and
    ``/v1/models`` both feed from it) and parses a ~59 KB JSON asset. It must be
    memoised so the parse cost is paid once. ``_invalidate_bundled_snapshot_cache``
    is the named invalidation hook: it makes the next call re-read.
    """
    # Count real parses by patching json.load, which the loader calls exactly
    # once per uncached read.
    import faigate.catalog_resolver as cr

    real_json_load = json.load
    parse_count = {"n": 0}

    def _counting_load(*args, **kwargs):
        parse_count["n"] += 1
        return real_json_load(*args, **kwargs)

    _invalidate_bundled_snapshot_cache()
    monkeypatch.setattr(cr.json, "load", _counting_load)

    first = _load_bundled_snapshot()
    second = _load_bundled_snapshot()
    assert parse_count["n"] == 1  # parsed once across two calls
    assert first is second  # same cached object

    _invalidate_bundled_snapshot_cache()
    _load_bundled_snapshot()
    assert parse_count["n"] == 2  # named invalidation forced a re-parse
