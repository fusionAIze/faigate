"""Tests for MetadataCatalogSync, CatalogCache, and CatalogResolver."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from faigate.catalog_cache import CatalogCache
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.metadata_catalog_sync import (
    MetadataCatalogSync,
    SyncStatus,
)
from faigate.provider_catalog_refresh import build_catalog_alerts

# ── fakes ─────────────────────────────────────────────────────────────


class FakeFetcher:
    """Programmable HTTP fetcher for tests."""

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


class RaisingFetcher:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def fetch(self, url: str, *, headers: dict[str, str], timeout_seconds: float):  # noqa: ARG002
        raise self.exc


def _valid_payload() -> dict[str, Any]:
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": {
            "anthropic": {"recommended_model": "claude-opus-4-7"},
        },
    }


def _valid_body() -> bytes:
    return json.dumps(_valid_payload()).encode("utf-8")


# ── MetadataCatalogSync ───────────────────────────────────────────────


def test_fetch_fresh_returns_payload_and_etag():
    fetcher = FakeFetcher([(200, {"etag": '"abc123"'}, _valid_body())])
    sync = MetadataCatalogSync(fetcher=fetcher)
    result = sync.fetch("https://example/catalog.json")
    assert result.status == SyncStatus.FRESH
    assert result.payload is not None
    assert result.etag == '"abc123"'
    assert result.payload["providers"]["anthropic"]["recommended_model"] == "claude-opus-4-7"


def test_fetch_passes_if_none_match_when_etag_provided():
    fetcher = FakeFetcher([(304, {}, b"")])
    sync = MetadataCatalogSync(fetcher=fetcher)
    result = sync.fetch("https://example/catalog.json", etag='"abc123"')
    assert result.status == SyncStatus.NOT_MODIFIED
    assert result.payload is None
    assert fetcher.calls[0][1]["If-None-Match"] == '"abc123"'


def test_fetch_attaches_bearer_token_when_provided():
    fetcher = FakeFetcher([(200, {}, _valid_body())])
    sync = MetadataCatalogSync(fetcher=fetcher)
    sync.fetch("https://example/catalog.json", token="ghp_secrettoken1234")
    headers = fetcher.calls[0][1]
    assert headers["Authorization"] == "Bearer ghp_secrettoken1234"


def test_fetch_401_returns_auth_failed_without_payload():
    fetcher = FakeFetcher([(401, {}, b"unauthorized")])
    sync = MetadataCatalogSync(fetcher=fetcher)
    result = sync.fetch("https://example/catalog.json", token="bad")
    assert result.status == SyncStatus.AUTH_FAILED
    assert result.payload is None


def test_fetch_404_returns_not_found():
    fetcher = FakeFetcher([(404, {}, b"")])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.NOT_FOUND


def test_fetch_500_returns_error():
    fetcher = FakeFetcher([(500, {}, b"oops")])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.ERROR


def test_fetch_invalid_json_returns_invalid():
    fetcher = FakeFetcher([(200, {}, b"not-json{{")])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID
    assert "json parse" in result.error


def test_fetch_wrong_schema_version_returns_invalid():
    payload = {"schema_version": "something-else/v9", "providers": {}}
    fetcher = FakeFetcher([(200, {}, json.dumps(payload).encode())])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID
    assert "schema_version" in result.error


def test_fetch_missing_providers_key_returns_invalid():
    payload = {"schema_version": "fusionaize-provider-catalog/v1.1"}
    fetcher = FakeFetcher([(200, {}, json.dumps(payload).encode())])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID


def test_fetch_network_error_returns_error_does_not_raise():
    import httpx

    sync = MetadataCatalogSync(fetcher=RaisingFetcher(httpx.ConnectError("dns failure")))
    result = sync.fetch("https://example/c.json")
    # Don't assert on prefix — httpx version drift means ConnectError may
    # land in either except branch. What matters: caller gets an error
    # status without an exception bubbling up.
    assert result.status == SyncStatus.ERROR
    assert "dns failure" in result.error


def test_fetch_does_not_log_token_value(caplog: pytest.LogCaptureFixture):
    secret = "ghp_DO_NOT_LEAK_THIS_TOKEN_ABCDEF"
    fetcher = RaisingFetcher(__import__("httpx").ConnectError("dns"))
    sync = MetadataCatalogSync(fetcher=fetcher)

    with caplog.at_level(logging.DEBUG, logger="faigate.metadata_catalog_sync"):
        result = sync.fetch("https://example/c.json", token=secret)

    assert result.status == SyncStatus.ERROR
    full_log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret not in full_log, "secret token leaked into logs"


# ── CatalogCache ──────────────────────────────────────────────────────


def test_cache_load_missing_returns_none(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    assert cache.load("public") is None


def test_cache_save_and_load_roundtrip(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    payload = _valid_payload()
    cache.save("public", payload, etag='"v1"')
    loaded = cache.load("public")
    assert loaded is not None
    assert loaded.payload == payload
    assert loaded.etag == '"v1"'
    assert loaded.tier == "public"


def test_cache_save_without_etag_clears_old_etag(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    cache.save("public", _valid_payload(), etag='"old"')
    cache.save("public", _valid_payload(), etag=None)
    loaded = cache.load("public")
    assert loaded is not None
    assert loaded.etag is None


def test_cache_clear_removes_files(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    cache.save("public", _valid_payload(), etag='"v1"')
    cache.clear("public")
    assert cache.load("public") is None


def test_cache_age_seconds(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    cache.save("public", _valid_payload(), etag=None)
    age = cache.age_seconds("public")
    assert age is not None and age >= 0


def test_cache_records_sync_state(tmp_path: Path):
    cache = CatalogCache(root=tmp_path)
    cache.save_state("public", status="invalid", success=False, error="schema mismatch", when=100.0)
    state = cache.load_state("public")
    assert state is not None
    assert state.last_status == "invalid"
    assert state.last_error == "schema mismatch"
    assert state.failure_count == 1

    cache.save_state("public", status="fresh", success=True, when=200.0)
    state = cache.load_state("public")
    assert state is not None
    assert state.last_success_at == 200.0
    assert state.success_count == 1
    assert state.failure_count == 1


# ── CatalogResolver chain ─────────────────────────────────────────────


def _make_resolver(
    tmp_path: Path,
    *,
    plan: list[tuple[int, dict[str, str], bytes]],
    token: str | None = None,
) -> tuple[CatalogResolver, FakeFetcher]:
    fetcher = FakeFetcher(plan)
    sync = MetadataCatalogSync(fetcher=fetcher)
    cache = CatalogCache(root=tmp_path)
    config = ResolverConfig(
        public_url="https://example/public.json",
        private_url="https://example/private.json",
        token=token,
        refresh_interval_seconds=10.0,
    )
    return CatalogResolver(config=config, cache=cache, sync=sync), fetcher


def test_resolver_uses_public_when_no_token(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[(200, {"etag": '"pub1"'}, _valid_body())],
        token=None,
    )
    resolved = resolver.resolve()
    assert resolved.source == "public"
    assert len(fetcher.calls) == 1
    assert "Authorization" not in fetcher.calls[0][1]


def test_resolver_prefers_private_when_token_present(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[(200, {"etag": '"priv1"'}, _valid_body())],
        token="ghp_test",
    )
    resolved = resolver.resolve()
    assert resolved.source == "private"
    # only one call — private succeeded so public never tried
    assert len(fetcher.calls) == 1


def test_resolver_falls_back_to_public_when_private_401(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[
            (401, {}, b""),  # private rejected
            (200, {"etag": '"pub1"'}, _valid_body()),
        ],
        token="ghp_bad",
    )
    resolved = resolver.resolve()
    assert resolved.source == "public"
    assert len(fetcher.calls) == 2


def test_resolver_uses_cache_when_within_ttl(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[(200, {"etag": '"v1"'}, _valid_body())],
    )
    # First call hits remote
    resolver.resolve()
    # Second call within TTL → no further fetch
    second = resolver.resolve()
    assert second.source == "public-cache"
    assert len(fetcher.calls) == 1


def test_resolver_force_refresh_skips_cache(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[
            (200, {"etag": '"v1"'}, _valid_body()),
            (200, {"etag": '"v2"'}, _valid_body()),
        ],
    )
    resolver.resolve()
    second = resolver.resolve(force_refresh=True)
    assert second.source == "public"
    assert len(fetcher.calls) == 2


def test_resolver_304_uses_cache(tmp_path: Path):
    resolver, fetcher = _make_resolver(
        tmp_path,
        plan=[
            (200, {"etag": '"v1"'}, _valid_body()),
            (304, {}, b""),
        ],
    )
    resolver.resolve()
    # Force refresh past TTL — but server returns 304
    second = resolver.resolve(force_refresh=True)
    assert second.source == "public-cache"
    assert second.payload["providers"]["anthropic"]["recommended_model"] == "claude-opus-4-7"


def test_resolver_falls_back_to_bundled_when_all_remotes_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_bundled = {
        "schema_version": "fusionaize-provider-catalog/v1",
        "providers": {"bundled": {"recommended_model": "demo"}},
    }
    monkeypatch.setattr(
        "faigate.catalog_resolver._load_bundled_snapshot",
        lambda: fake_bundled,
    )
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[
            (500, {}, b""),  # private fails (no token, so this isn't called actually)
            (500, {}, b""),  # public fails
        ],
    )
    resolved = resolver.resolve()
    assert resolved.source == "bundled"
    assert "bundled" in resolved.payload["providers"]


def test_resolver_returns_empty_when_nothing_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "faigate.catalog_resolver._load_bundled_snapshot",
        lambda: None,
    )
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[(500, {}, b"")],
    )
    resolved = resolver.resolve()
    assert resolved.source == "empty"
    assert resolved.payload["providers"] == {}


def test_resolver_status_reports_cache_state(tmp_path: Path):
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[(200, {"etag": '"v1"'}, _valid_body())],
    )
    resolver.resolve()
    status = resolver.status()
    assert status["tiers"]["public"]["present"] is True
    assert status["tiers"]["public"]["providers_count"] == 1
    assert status["tiers"]["private"]["present"] is False
    assert status["tiers"]["public"]["sync"]["last_status"] == "fresh"


def test_build_catalog_alerts_includes_metadata_sync_invalid():
    alerts = build_catalog_alerts(
        {
            "metadata_sync": {
                "public": {
                    "sync": {
                        "last_status": "invalid",
                        "last_error": "schema mismatch",
                        "last_success_at": None,
                        "seconds_since_success": None,
                    }
                }
            }
        }
    )
    assert alerts[0]["kind"] == "sync-invalid"
    assert alerts[0]["severity"] == "critical"


def test_build_catalog_alerts_includes_metadata_sync_auth():
    alerts = build_catalog_alerts(
        {
            "metadata_sync": {
                "private": {
                    "sync": {
                        "last_status": "auth_failed",
                        "last_error": "http 403",
                        "last_success_at": None,
                        "seconds_since_success": None,
                    }
                }
            }
        }
    )
    assert alerts[0]["kind"] == "sync-auth"


def test_build_catalog_alerts_includes_metadata_sync_stale():
    alerts = build_catalog_alerts(
        {
            "metadata_sync": {
                "public": {
                    "sync": {
                        "last_status": "fresh",
                        "last_error": "",
                        "last_success_at": 1.0,
                        "seconds_since_success": 8 * 86400,
                    }
                }
            }
        }
    )
    assert alerts[0]["kind"] == "sync-stale"
