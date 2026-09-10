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

from faigate.catalog_cache import CatalogCache
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.metadata_catalog_sync import MetadataCatalogSync


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
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": {"anthropic": {"recommended_model": "claude-opus-4-7"}},
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
