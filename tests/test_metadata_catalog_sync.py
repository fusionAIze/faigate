"""Tests for MetadataCatalogSync, CatalogCache, and CatalogResolver."""

from __future__ import annotations

import importlib
import importlib.resources
import json
import logging
import math
from pathlib import Path
from typing import Any

import httpx
import pytest

from faigate import metadata_catalog_sync as _metadata_catalog_sync
from faigate.catalog_cache import CatalogCache
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.metadata_catalog_sync import (
    MetadataCatalogSync,
    SyncStatus,
)
from faigate.provider_catalog_refresh import build_catalog_alerts

# ── httpx isolation ───────────────────────────────────────────────────
#
# Several sibling test modules replace ``sys.modules["httpx"]`` with a
# stub at import time and never restore it. That stubbed module has no
# real ``HTTPError`` hierarchy, so once any of them has been collected
# this module would silently test against the wrong exception contract.
# ``tests/conftest.py`` restores the genuine package before collection, so
# the plain import above already yields the real hierarchy; it is pinned
# onto the module under test for every test here.


REAL_HTTPX = httpx


@pytest.fixture(autouse=True)
def _pin_real_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure MetadataCatalogSync sees the genuine httpx.HTTPError type."""
    monkeypatch.setattr(_metadata_catalog_sync, "httpx", REAL_HTTPX)


# ── fakes ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_shrink_baseline(monkeypatch: pytest.MonkeyPatch):
    """Neutralize the bundled shrink baseline for mechanic-focused tests.

    The integrity guard compares a synced catalog against the bundled
    snapshot. The small fixture catalogs used here would be rejected as
    "shrank too far"; tests that exercise that guard explicitly patch the
    baseline themselves.

    ``raising=False`` keeps the RED PROOF honest: against a baseline that
    lacks ``_load_bundled_baseline`` the patch is a no-op and the new tests
    fail with real assertion errors instead of setup errors.
    """
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: None, raising=False)


@pytest.fixture
def real_bundled_baseline(_no_shrink_baseline, monkeypatch: pytest.MonkeyPatch):
    """Undo the autouse neutralization so the real bundled loader runs."""
    monkeypatch.undo()


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
    return _catalog_payload(provider_count=10)


def _catalog_payload(provider_count: int) -> dict[str, Any]:
    providers = {f"provider-{i}": {"recommended_model": f"model-{i}"} for i in range(provider_count)}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
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
    assert result.payload["providers"]["provider-0"]["recommended_model"] == "model-0"


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
    sync = MetadataCatalogSync(fetcher=RaisingFetcher(REAL_HTTPX.ConnectError("dns failure")))
    result = sync.fetch("https://example/c.json")
    # A transport error is part of the HttpFetcher contract: the caller
    # gets an error status without an exception bubbling up.
    assert result.status == SyncStatus.ERROR
    assert "dns failure" in result.error


@pytest.mark.parametrize(
    "exc",
    [AttributeError("fetcher bug"), TypeError("fetcher bug")],
    ids=["attribute-error", "type-error"],
)
def test_fetch_programmer_error_propagates(exc: Exception):
    sync = MetadataCatalogSync(fetcher=RaisingFetcher(exc))
    with pytest.raises(type(exc)):
        sync.fetch("https://example/c.json")


def test_fetch_does_not_log_token_value(caplog: pytest.LogCaptureFixture):
    secret = "ghp_DO_NOT_LEAK_THIS_TOKEN_ABCDEF"
    fetcher = RaisingFetcher(REAL_HTTPX.ConnectError("dns"))
    sync = MetadataCatalogSync(fetcher=fetcher)

    with caplog.at_level(logging.DEBUG, logger="faigate.metadata_catalog_sync"):
        result = sync.fetch("https://example/c.json", token=secret)

    assert result.status == SyncStatus.ERROR
    full_log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret not in full_log, "secret token leaked into logs"


# ── Integrity guard ───────────────────────────────────────────────────


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_sync_rejects_catalog_below_minimum_entries():
    payload = _catalog_payload(provider_count=3)
    fetcher = FakeFetcher([(200, {}, _body(payload))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID
    assert result.payload is None
    assert "3" in result.error
    assert "10" in result.error


def test_sync_rejects_catalog_shrinking_too_far_from_baseline(monkeypatch: pytest.MonkeyPatch):
    baseline = _catalog_payload(provider_count=100)
    payload = _catalog_payload(provider_count=49)  # under 50% of baseline
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    fetcher = FakeFetcher([(200, {}, _body(payload))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID
    assert "49" in result.error
    assert "50" in result.error


def test_sync_accepts_catalog_within_shrink_threshold(monkeypatch: pytest.MonkeyPatch):
    baseline = _catalog_payload(provider_count=100)
    payload = _catalog_payload(provider_count=50)  # exactly 50% retained
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    fetcher = FakeFetcher([(200, {}, _body(payload))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.FRESH


def test_meta_keys_do_not_count_as_entries(monkeypatch: pytest.MonkeyPatch):
    baseline = {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "generated_at": "x",
        "source_repo": "y",
        "extra_meta": {"nested": True},
        "providers": {},
    }
    payload = _catalog_payload(provider_count=15)
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    fetcher = FakeFetcher([(200, {}, _body(payload))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json", min_entries=15)
    assert result.status == SyncStatus.FRESH


def test_min_entries_threshold_is_configurable(monkeypatch: pytest.MonkeyPatch):
    # A relaxed shrink ratio must not mask a min_entries violation.
    baseline = _catalog_payload(provider_count=100)
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    payload = _catalog_payload(provider_count=10)
    fetcher = FakeFetcher([(200, {}, _body(payload))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch(
        "https://example/c.json",
        min_entries=11,
        max_shrink_ratio=0.99,
    )
    assert result.status == SyncStatus.INVALID
    assert "below minimum 11" in result.error


def test_max_shrink_ratio_threshold_is_configurable(monkeypatch: pytest.MonkeyPatch):
    # A permissive min_entries must not mask a shrink violation, and widening
    # the ratio is the only thing that flips the verdict.
    baseline = _catalog_payload(provider_count=100)
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    payload = _catalog_payload(provider_count=45)

    rejected = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(payload))])).fetch(
        "https://example/c.json",
        min_entries=1,
        max_shrink_ratio=0.5,
    )
    assert rejected.status == SyncStatus.INVALID
    assert "below 50" in rejected.error

    accepted = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(payload))])).fetch(
        "https://example/c.json",
        min_entries=1,
        max_shrink_ratio=0.6,
    )
    assert accepted.status == SyncStatus.FRESH


def test_shrink_threshold_rounds_up_on_odd_baseline(monkeypatch: pytest.MonkeyPatch):
    # 47 * 0.5 = 23.5; ceil makes the floor 24 (~51%), not 23.
    baseline = _catalog_payload(provider_count=47)
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)

    at_floor = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(_catalog_payload(24)))])).fetch(
        "https://example/c.json"
    )
    assert at_floor.status == SyncStatus.FRESH

    below_floor = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(_catalog_payload(23)))])).fetch(
        "https://example/c.json"
    )
    assert below_floor.status == SyncStatus.INVALID
    assert "below 24" in below_floor.error


def test_accepted_small_sync_does_not_weaken_next_comparison(monkeypatch: pytest.MonkeyPatch):
    # The comparison baseline is the bundled snapshot, never the previously
    # fetched copy. A 60-entry catalog is accepted (>=50% of the 100-entry
    # bundle), but the following 35-entry sync must still be rejected against
    # the bundle -- not against the 60 that was just accepted.
    baseline = _catalog_payload(provider_count=100)
    monkeypatch.setattr(_metadata_catalog_sync, "_load_bundled_baseline", lambda: baseline)
    accepted_payload = _catalog_payload(provider_count=60)
    shrunk_payload = _catalog_payload(provider_count=35)
    fetcher = FakeFetcher(
        [
            (200, {}, _body(accepted_payload)),
            (200, {}, _body(shrunk_payload)),
        ]
    )
    sync = MetadataCatalogSync(fetcher=fetcher)
    first = sync.fetch("https://example/c.json")
    second = sync.fetch("https://example/c.json")
    assert first.status == SyncStatus.FRESH
    assert first.payload is not None
    assert second.status == SyncStatus.INVALID
    assert "35" in second.error
    assert "50" in second.error


# ── Bundled baseline loading (fails closed) ───────────────────────────


def test_sync_fails_closed_when_bundled_baseline_missing(real_bundled_baseline, monkeypatch: pytest.MonkeyPatch):
    def _missing(_package: str):
        raise FileNotFoundError("catalog.v1.json gone")

    monkeypatch.setattr(importlib.resources, "files", _missing)
    fetcher = FakeFetcher([(200, {}, _body(_valid_payload()))])
    result = MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")
    assert result.status == SyncStatus.INVALID
    assert result.payload is None
    assert "baseline" in result.error


def test_sync_propagates_unexpected_baseline_load_errors(real_bundled_baseline, monkeypatch: pytest.MonkeyPatch):
    def _boom(_package: str):
        raise RuntimeError("cannot read package resources")

    monkeypatch.setattr(importlib.resources, "files", _boom)
    fetcher = FakeFetcher([(200, {}, _body(_valid_payload()))])
    with pytest.raises(RuntimeError, match="cannot read package resources"):
        MetadataCatalogSync(fetcher=fetcher).fetch("https://example/c.json")


# ── Real bundled asset wiring ─────────────────────────────────────────


def test_integrity_guard_uses_real_bundled_asset(real_bundled_baseline):
    loader = getattr(_metadata_catalog_sync, "_load_bundled_baseline", None)
    assert loader is not None, "bundled baseline loader missing"
    baseline = loader()
    baseline_count = len(baseline["providers"])
    assert baseline_count > 1

    floor = math.ceil(baseline_count * 0.5)

    rejected = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(_catalog_payload(floor - 1)))])).fetch(
        "https://example/c.json"
    )
    assert rejected.status == SyncStatus.INVALID

    accepted = MetadataCatalogSync(fetcher=FakeFetcher([(200, {}, _body(_catalog_payload(floor)))])).fetch(
        "https://example/c.json"
    )
    assert accepted.status == SyncStatus.FRESH


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
    assert second.payload["providers"]["provider-0"]["recommended_model"] == "model-0"


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
    assert status["tiers"]["public"]["providers_count"] == 10
    assert status["tiers"]["private"]["present"] is False
    assert status["tiers"]["public"]["sync"]["last_status"] == "fresh"


def test_resolver_404_on_both_remotes_logs_one_warning_per_tier(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "faigate.catalog_resolver._load_bundled_snapshot",
        lambda: _valid_payload(),
    )
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[(404, {}, b""), (404, {}, b"")],
        token="ghp_test",
    )
    with caplog.at_level(logging.WARNING, logger="faigate.catalog_resolver"):
        resolved = resolver.resolve()

    assert resolved.source == "bundled"
    warnings = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "faigate.catalog_resolver" and rec.levelno >= logging.WARNING
    ]
    assert len(warnings) == 2
    by_tier: dict[str, str] = {}
    for msg in warnings:
        for tier in ("private", "public"):
            if tier in msg:
                by_tier[tier] = msg
    assert set(by_tier) == {"private", "public"}
    for msg in by_tier.values():
        assert "not_found" in msg
        assert "404" in msg


def test_resolver_status_reports_state_and_cause_per_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "faigate.catalog_resolver._load_bundled_snapshot",
        lambda: _valid_payload(),
    )
    resolver, _ = _make_resolver(
        tmp_path,
        plan=[(404, {}, b""), (404, {}, b"")],
        token="ghp_test",
    )
    resolved = resolver.resolve()
    assert resolved.source == "bundled"

    status = resolver.status()
    for tier in ("private", "public"):
        entry = status["tiers"][tier]
        assert entry["present"] is False
        assert entry["state"] == "unavailable"
        assert entry["cause"] == "http 404"


def test_update_check_nonzero_when_only_bundled_served(monkeypatch: pytest.MonkeyPatch):
    import argparse

    from faigate import models_cli

    class _FakeCache:
        def load(self, tier: str):  # noqa: ARG002
            return None

    class _FakeResolver:
        def __init__(self, *, config: Any = None) -> None:
            self._cache = _FakeCache()

        def status(self) -> dict[str, Any]:
            return {
                "tiers": {
                    "private": {"present": False, "state": "unavailable", "cause": ""},
                    "public": {"present": False, "state": "unavailable", "cause": ""},
                },
                "bundled_present": True,
                "bundled_providers_count": 1,
            }

    monkeypatch.setattr(models_cli, "CatalogResolver", _FakeResolver)
    rc = models_cli.cmd_update(argparse.Namespace(check=True, diff=False))
    assert rc != 0


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
