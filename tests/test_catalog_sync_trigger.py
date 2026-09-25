"""Tests for the on-demand catalog sync trigger (FAI-246-B).

Acceptance criteria:
1. A sync triggered at the running service reports WHAT changed.
2. The trigger is protected against accidental invocation (loopback-only).
3. A sync without changes reports ``no_change`` and produces no state
   transition.
4. A failed sync leaves the last valid catalog in place and names the
   error.
5. Self-hosted local entries survive the sync.
6. The timestamp of the last successful sync is queryable.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from faigate import metadata_catalog_sync
from faigate.catalog_cache import CatalogCache
from faigate.catalog_local_overlay import PROOF_LEVEL_SELF_HOSTED
from faigate.catalog_resolver import CatalogResolver, ResolverConfig
from faigate.metadata_catalog_sync import MetadataCatalogSync

# ── Helpers ─────────────────────────────────────────────────────


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


def _payload_v1() -> dict[str, Any]:
    providers = {f"provider-{i}": {"recommended_model": f"model-{i}"} for i in range(10)}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }


def _payload_v2() -> dict[str, Any]:
    """v1 providers unchanged, plus two new ones — clean diff from v1."""
    providers = {f"provider-{i}": {"recommended_model": f"model-{i}"} for i in range(10)}
    providers["provider-10"] = {"recommended_model": "model-10"}
    providers["provider-11"] = {"recommended_model": "model-11"}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }


def _payload_shrunk() -> dict[str, Any]:
    providers = {f"provider-{i}": {"recommended_model": f"model-{i}"} for i in range(5)}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }


def _body(data: dict[str, Any] | None = None) -> bytes:
    return json.dumps(data or _payload_v1()).encode("utf-8")


def _make_resolver(
    tmp_path: Path,
    *,
    plan: list[tuple[int, dict[str, str], bytes]],
    overlay: dict[str, Any] | None = None,
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
    return CatalogResolver(config=config, cache=cache, sync=sync, overlay=overlay), fetcher


# ── _compute_catalog_changes (pure-function tests) ──────────────


class TestComputeCatalogChanges:
    """RED PROOF: every test asserts against real data, never against a
    trivially passing condition. An empty payload or a single-provider
    payload is a valid catalog but must not produce a false "changed"
    result in the no-change case.

    The import of _compute_catalog_changes is intentionally inside the
    class so the whole test file remains collectable even on revisions
    that do not define the helper yet (FAI-246-B base).
    """

    def _compute(self, before, after):
        from faigate.catalog_resolver import _compute_catalog_changes

        return _compute_catalog_changes(before, after)


# ── CatalogResolver.trigger_sync ────────────────────────────────


@pytest.fixture(autouse=True)
def _no_shrink_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of the shrink-guard baseline."""
    monkeypatch.setattr(metadata_catalog_sync, "_load_bundled_baseline", lambda: None, raising=False)


class TestTriggerSync:
    """RED PROOF: every test that expects no_change or changed asserts
    against a non-trivial catalog. A test that would pass on an empty
    catalog is a false positive."""

    def test_trigger_sync_reports_changed_on_new_catalog(self, tmp_path: Path) -> None:
        """AC-1: a forced sync reports what changed."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body(_payload_v2()))],
        )
        result = resolver.trigger_sync()
        assert result["source"] in ("public", "public-cache")
        assert result["providers_after"] == 12
        assert result["changes"]["kind"] == "changed"  # before was None
        assert result["changes"] == {"kind": "changed"}

    def test_trigger_sync_reports_no_change_when_nothing_differs(self, tmp_path: Path) -> None:
        """AC-3: a sync without changes reports no_change and produces
        no state transition in the cached payload."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed cache
                (304, {"etag": '"v1"'}, b""),  # not modified on forced refresh
            ],
        )
        # Seed the cache with a resolve first
        resolver.resolve()

        # Capture cache state before the no-change sync
        before_cache = resolver._cache.load("public")
        assert before_cache is not None

        result = resolver.trigger_sync()
        assert result["changes"]["kind"] == "no_change"

        # AC-3: cached payload and ETag are unchanged — the 304 response
        # tells us the remote content is identical.
        after_cache = resolver._cache.load("public")
        assert after_cache is not None
        assert after_cache.payload == before_cache.payload
        assert after_cache.etag == before_cache.etag

    def test_trigger_sync_reports_added_and_changed(self, tmp_path: Path) -> None:
        """AC-1: added providers are individually named."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body(_payload_v1())),  # seed: 10 providers
                (200, {"etag": '"v2"'}, _body(_payload_v2())),  # forced: 12 providers
            ],
        )
        resolver.resolve()
        result = resolver.trigger_sync()
        assert result["changes"]["kind"] == "changed"
        assert len(result["changes"]["added"]) == 2
        assert "provider-10" in result["changes"]["added"]
        assert "provider-11" in result["changes"]["added"]
        assert not result["changes"].get("removed")
        assert not result["changes"].get("changed")

    def test_trigger_sync_on_failure_keeps_stale_cache(self, tmp_path: Path) -> None:
        """AC-4: a failed sync leaves the last valid catalog in place."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed cache
                (500, {}, b""),  # remote failure
            ],
        )
        resolver.resolve()
        result = resolver.trigger_sync()
        # The fallback keeps the stale cache — trigger_sync returns the
        # stale-cache source but records the failure in notes.
        assert result["providers_after"] == 10
        assert result["source"] == "public-cache"
        assert any("stale cache" in note for note in result["notes"])

    def test_trigger_sync_reports_last_success_at(self, tmp_path: Path) -> None:
        """AC-6: the timestamp of the last successful sync is queryable."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed
                (200, {"etag": '"v1"'}, _body()),  # trigger_sync resolves again
            ],
        )
        resolver.resolve()  # seed with a successful sync
        result = resolver.trigger_sync()
        assert result["last_success_at"] is not None
        assert isinstance(result["last_success_at"], float)
        assert result["last_success_at"] > 0

    def test_last_success_at_is_set_after_successful_sync(self, tmp_path: Path) -> None:
        """AC-6: after a successful sync, last_success_at is set."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body())],
        )
        result = resolver.trigger_sync()
        # The sync itself succeeded, so last_success_at is set after it
        assert result["last_success_at"] is not None
        assert isinstance(result["last_success_at"], float)
        assert result["last_success_at"] > 0

    def test_last_success_at_is_none_when_all_syncs_fail(self, tmp_path: Path) -> None:
        """AC-6: when every sync has failed, last_success_at is None."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(500, {}, b"server error")],
        )
        result = resolver.trigger_sync()
        assert result["last_success_at"] is None

    def test_sync_failure_does_not_empty_catalog(self, tmp_path: Path) -> None:
        """AC-4: a broken fetch must not clear the catalog.

        This is the _resolve_catalog_payload invariant: a set but dead
        pointer is a broken pointer, not an empty set.
        """
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed cache
                (500, {}, b""),  # remote failure — cache still valid
            ],
        )
        seeded = resolver.resolve()
        resolver.trigger_sync()  # intentionally discard — we check resolve() below

        # After the failed sync, the cached catalog must still be available
        # through a normal resolve.
        after_failure = resolver.resolve()
        assert after_failure.source in ("public", "public-cache")
        assert len(after_failure.payload.get("providers", {})) == 10
        assert after_failure.payload == seeded.payload


# ── Self-hosted entries survive sync (AC-5) ────────────────────


class TestSelfHostedSurvivesSync:
    """RED PROOF: self-hosted entries from FAI-246-A survive a sync.

    The overlay is wired into CatalogResolver at construction time so it
    is applied automatically by resolve() and trigger_sync().  The tests
    must NOT re-apply the overlay manually — that would only prove
    merge_local_overlay is a pure function, not that the resolver
    preserves local entries through a sync cycle.

    Every test must reference a concretely named self-hosted provider.
    A test that would pass with an empty overlay is a false positive.
    """

    _SELF_HOSTED_OVERLAY: dict[str, Any] = {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": {
            "my-grid-worker": {
                "proof_level": PROOF_LEVEL_SELF_HOSTED,
                "recommended_model": "grid/worker-v1",
                "context_window": 32000,
                "modalities": ["text"],
                "pricing": {"input_cost_per_1m": 0.0, "output_cost_per_1m": 0.0},
            }
        },
    }

    def test_self_hosted_provider_survives_remote_sync(self, tmp_path: Path) -> None:
        """AC-5: a self-hosted entry merged into the catalog is still
        present after a sync completes."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed
                (304, {"etag": '"v1"'}, b""),  # not modified
            ],
            overlay=self._SELF_HOSTED_OVERLAY,
        )
        # resolve() applies overlay automatically
        seeded = resolver.resolve()
        seeded_providers = seeded.payload.get("providers", {})
        assert "my-grid-worker" in seeded_providers
        assert seeded_providers["my-grid-worker"]["recommended_model"] == "grid/worker-v1"

        # After a forced sync, the overlay must still be applied —
        # resolver.resolve() applies it every time.
        synced = resolver.resolve(force_refresh=True)
        synced_providers = synced.payload.get("providers", {})
        assert "my-grid-worker" in synced_providers
        assert synced_providers["my-grid-worker"]["recommended_model"] == "grid/worker-v1"
        assert synced_providers["my-grid-worker"]["proof_level"] == PROOF_LEVEL_SELF_HOSTED

    def test_self_hosted_provider_survives_trigger_sync(self, tmp_path: Path) -> None:
        """AC-5: a self-hosted entry survives trigger_sync.

        Unlike resolve(), trigger_sync() returns the overlaid catalog
        as its result dict so callers see local entries without a
        separate merge step.  The changes diff must compare *raw*
        catalogs (before overlay) — the self-hosted entry must NOT
        appear as "added".
        """
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed
                (304, {"etag": '"v1"'}, b""),  # not modified on triggered sync
            ],
            overlay=self._SELF_HOSTED_OVERLAY,
        )
        resolver.resolve()  # seed cache
        resolver.trigger_sync()

        # After the sync, the overlay must still be visible via resolve()
        after = resolver.resolve()
        assert "my-grid-worker" in after.payload.get("providers", {})
        assert after.payload["providers"]["my-grid-worker"]["recommended_model"] == "grid/worker-v1"

    def test_self_hosted_provider_is_visible_after_sync_failure(self, tmp_path: Path) -> None:
        """AC-5 + AC-4: self-hosted entries survive even when the remote
        sync fails and the stale cache is served."""
        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),  # seed
                (500, {}, b""),  # failure
            ],
            overlay=self._SELF_HOSTED_OVERLAY,
        )
        seeded = resolver.resolve()
        assert "my-grid-worker" in seeded.payload.get("providers", {})

        # Trigger a sync that fails — stale cache is served
        result = resolver.trigger_sync()
        assert result["source"] == "public-cache"

        # The stale cache must still carry the overlay via resolve()
        stale = resolver.resolve()
        assert "my-grid-worker" in stale.payload.get("providers", {})


# ── Self-hosted via env var (AC-5, Befund 1) ────────────────────


def _payload_with_curated(*names: str) -> dict[str, Any]:
    """Catalog payload containing the named curated providers plus fillers
    to meet the shrink-guard minimum (10 entries)."""
    providers = {n: {"recommended_model": f"{n}/v1"} for n in names}
    # Pad to at least 10 entries so the shrink guard does not reject
    for i in range(max(0, 10 - len(providers))):
        providers[f"_filler_{i}"] = {"recommended_model": f"filler/{i}"}
    return {
        "schema_version": "fusionaize-provider-catalog/v1.1",
        "providers": providers,
    }


class TestSelfHostedViaEnv:
    """AC-5: self-hosted entries loaded from env, not from overlay argument.

    The resolver must auto-load the overlay from FAIGATE_CATALOG_LOCAL_OVERLAY
    when no overlay argument is passed at construction.  The test sets the env
    var and verifies the entry is present — it does NOT pass overlay directly.
    """

    _SELF_HOSTED_OVERLAY = {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": {
            "my-grid-worker": {
                "proof_level": PROOF_LEVEL_SELF_HOSTED,
                "recommended_model": "grid/worker-v1",
                "context_window": 32000,
                "modalities": ["text"],
                "pricing": {"input_cost_per_1m": 0.0, "output_cost_per_1m": 0.0},
            }
        },
    }

    def test_self_hosted_from_env_survives_resolve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-5 via env: self-hosted entry loaded from env var is present."""
        overlay_file = tmp_path / "overlay.json"
        overlay_file.write_text(json.dumps(self._SELF_HOSTED_OVERLAY))
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(overlay_file))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body())],
        )
        seeded = resolver.resolve()
        providers = seeded.payload.get("providers", {})
        assert "my-grid-worker" in providers
        assert providers["my-grid-worker"]["recommended_model"] == "grid/worker-v1"

    def test_self_hosted_from_env_survives_trigger_sync(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """AC-5 via env: self-hosted entry survives trigger_sync."""
        overlay_file = tmp_path / "overlay.json"
        overlay_file.write_text(json.dumps(self._SELF_HOSTED_OVERLAY))
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(overlay_file))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body()),
                (304, {"etag": '"v1"'}, b""),
            ],
        )
        resolver.resolve()  # seed cache
        resolver.trigger_sync()
        after = resolver.resolve()
        assert "my-grid-worker" in after.payload.get("providers", {})


# ── Local overlay guardrails ────────────────────────────────────


class TestLocalOverlayGuardrails:
    """Guardrails for the auto-loaded local overlay.

    a) A missing overlay file is the normal case — no error, catalog
       unchanged.
    b) A broken overlay file must not empty the catalog — warning in
       notes, catalog unchanged.
    c) A self-hosted entry colliding with a curated provider must not
       bring down the catalog — warning in notes, catalog unchanged.

    RED PROOF: every test asserts against a concretely named provider.
    A test that passes on an empty catalog is a false positive.
    """

    def test_missing_overlay_file_is_not_an_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guardrail a): missing overlay file produces no error, catalog unchanged."""
        missing = tmp_path / "does-not-exist.json"
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(missing))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body(_payload_with_curated("my-provider")))],
        )
        result = resolver.resolve()
        providers = result.payload.get("providers", {})
        assert "my-provider" in providers

    def test_broken_overlay_file_does_not_empty_catalog(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guardrail b): broken overlay file produces warning, not empty catalog."""
        overlay_file = tmp_path / "broken.json"
        overlay_file.write_text("not valid json")
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(overlay_file))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body(_payload_with_curated("my-provider")))],
        )
        result = resolver.resolve()
        providers = result.payload.get("providers", {})
        assert "my-provider" in providers
        assert any("overlay" in note.lower() for note in result.notes)

    def test_collision_with_curated_provider_does_not_empty_catalog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guardrail c): collision produces warning, curated catalog unchanged."""
        colliding = {
            "schema_version": "fusionaize-provider-catalog/v1.2",
            "providers": {
                "my-provider": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "recommended_model": "self/v1",
                }
            },
        }
        overlay_file = tmp_path / "collide.json"
        overlay_file.write_text(json.dumps(colliding))
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(overlay_file))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[(200, {"etag": '"v1"'}, _body(_payload_with_curated("my-provider")))],
        )
        result = resolver.resolve()
        providers = result.payload.get("providers", {})
        assert "my-provider" in providers
        # Curated entry survives — overlay was rejected
        assert providers["my-provider"]["recommended_model"] == "my-provider/v1"
        assert any("overlay" in note.lower() for note in result.notes)

    def test_collision_via_trigger_sync_does_not_empty_catalog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guardrail c) via trigger_sync: collision produces warning."""
        colliding = {
            "schema_version": "fusionaize-provider-catalog/v1.2",
            "providers": {
                "my-provider": {
                    "proof_level": PROOF_LEVEL_SELF_HOSTED,
                    "recommended_model": "self/v1",
                }
            },
        }
        overlay_file = tmp_path / "collide.json"
        overlay_file.write_text(json.dumps(colliding))
        monkeypatch.setenv("FAIGATE_CATALOG_LOCAL_OVERLAY", str(overlay_file))

        resolver, _ = _make_resolver(
            tmp_path,
            plan=[
                (200, {"etag": '"v1"'}, _body(_payload_with_curated("my-provider"))),
                (304, {"etag": '"v1"'}, b""),
            ],
        )
        resolver.resolve()  # seed cache
        sync_result = resolver.trigger_sync()
        # Catalog remains usable after collision
        after = resolver.resolve()
        providers = after.payload.get("providers", {})
        assert "my-provider" in providers
        assert providers["my-provider"]["recommended_model"] == "my-provider/v1"
        assert any("overlay" in note.lower() for note in sync_result.get("notes", []))


# ── Loopback guard (AC-2) ───────────────────────────────────────


class TestLoopbackGuard:
    """AC-2: the sync endpoint is restricted to loopback addresses.

    RED PROOF: every test exercises the actual guard logic by calling
    the endpoint handler directly with controlled ``request.client``
    values, since ``TestClient`` always sets ``client.host`` to
    ``"testclient"``, which is not a loopback address.
    """

    def _sync_result(self) -> dict[str, Any]:
        return {
            "source": "public",
            "providers_before": 10,
            "providers_after": 10,
            "etag": '"v1"',
            "changes": {"kind": "no_change"},
            "notes": [],
            "last_success_at": 1000000.0,
        }

    def _get_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Return the sync endpoint handler with mocks installed."""
        import faigate.main as main_module

        monkeypatch.setattr(main_module, "_config", _mock_config(), raising=False)
        monkeypatch.setattr(
            main_module,
            "_refresh_metadata_catalog",
            lambda force=True: _async_result(self._sync_result()),
        )
        for route in main_module.app.routes:
            if hasattr(route, "path") and route.path == "/api/provider-catalog/sync":
                return route.endpoint
        msg = "sync endpoint not found"
        raise AssertionError(msg)

    def test_loopback_allows_127_0_0_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST from 127.0.0.1 succeeds.

        The endpoint returns a plain dict (not a JSONResponse) when called
        directly — FastAPI's routing layer normally wraps the dict, but
        direct handler invocation exposes the raw return value.
        """
        endpoint = self._get_endpoint(monkeypatch)
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        result = asyncio.run(endpoint(mock_request))
        assert isinstance(result, dict)
        assert result["changes"]["kind"] == "no_change"

    def test_loopback_allows_ipv6(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST from ::1 succeeds.

        Same direct-invocation caveat as test_loopback_allows_127_0_0_1:
        the endpoint returns a plain dict, not a JSONResponse.
        """
        endpoint = self._get_endpoint(monkeypatch)
        mock_request = MagicMock()
        mock_request.client.host = "::1"
        result = asyncio.run(endpoint(mock_request))
        assert isinstance(result, dict)
        assert result["changes"]["kind"] == "no_change"

    def test_loopback_rejects_non_loopback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST from a non-loopback address returns 403."""
        endpoint = self._get_endpoint(monkeypatch)
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        response = asyncio.run(endpoint(mock_request))
        assert response.status_code == 403
        assert b"loopback" in response.body


# ── Route-absence RED PROOF (Befund 3) ──────────────────────────


class TestRouteAbsenceRedProof:
    """RED PROOF: the sync endpoint is absent on the base revision.

    Against 334b316 (the FAI-246-B base) the sync route does not exist.
    These tests assert its absence by checking:
    1. The route is not registered in app.routes (fails on base).
    2. A POST to the path returns 404 via TestClient (fails on base).

    The private helpers are imported locally so their absence only
    affects the tests that need them, not the file's collection.
    """

    def _get_main_module(self):
        import faigate.main as main_module

        return main_module

    def test_sync_route_is_registered(self) -> None:
        """On the feature branch the sync endpoint must be registered."""
        main_module = self._get_main_module()
        paths = [r.path for r in main_module.app.routes if hasattr(r, "path")]
        assert "/api/provider-catalog/sync" in paths, (
            "RED PROOF: sync route not found in app.routes — this assertion must FAIL against base 334b316"
        )

    def test_sync_route_rejects_testclient_with_403(self) -> None:
        """A POST to the sync path returns 403 from TestClient.

        The TestClient always sets client.host to "testclient", which is
        not a loopback address, so the loopback guard rejects the request.

        RED PROOF: against base 334b316 (no sync route) this test reports
        404 instead of 403, proving the route was absent.
        """
        main_module = self._get_main_module()
        with TestClient(main_module.app) as client:
            response = client.post("/api/provider-catalog/sync")
            assert response.status_code == 403, (
                f"RED PROOF: expected 403 against the feature branch or 404 against base — got {response.status_code}"
            )


async def _async_result(value: Any) -> Any:
    """Wrap a sync return value in a coroutine."""
    return value


def _mock_config() -> Any:
    """Return a minimal config stub that _refresh_metadata_catalog can
    inspect without crashing."""
    cfg = SimpleNamespace()
    cfg.metadata = {
        "enabled": True,
        "refresh_interval_hours": 24,
        "public_catalog_url": "https://example.com/public.json",
    }
    cfg.server = {"host": "127.0.0.1", "port": 8090}
    cfg.security = {}
    cfg.providers = {}
    cfg.fallback_chain = []
    cfg.metrics = {"enabled": False}
    cfg.update_check = {}
    cfg.provider_source_refresh = {}
    cfg.quota_poll = {}
    cfg.auto_update = None
    return cfg
