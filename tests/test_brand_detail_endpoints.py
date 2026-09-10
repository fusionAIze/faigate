"""Coverage for the v2.3 per-brand detail view endpoints.

Pins the contract the ``/dashboard/quotas/<slug>`` widget reads from:

1. ``_brand_context(slug)`` resolves a brand_slug → active providers, or
   returns ``None`` for unknown/no-active-packages brands (so the HTTP
   handlers 404 rather than returning empty JSON).
2. ``/api/quotas/<slug>/{clients,routes,analytics}`` all 404 on unknown
   brands and echo back ``brand`` / ``brand_slug`` / ``providers`` on
   success so the widget can render a header without a second round trip.
3. The multi-provider ``providers=[...]`` filter reaches the metrics
   layer (``_build_where_clause`` turns it into ``provider IN (...)``).
4. ``/dashboard/quotas/<slug>`` serves the detail-view shell with the
   brand slug and cockpit URL substituted at render time.

See ``docs/GATE-BAR-DESIGN.md`` §3.4 for the Design-Thinking rationale
("quick view most-relevant subset of the Operator Cockpit").
"""

from __future__ import annotations

import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx  # noqa: F401,E402
import pytest
from fastapi.testclient import TestClient  # noqa: E402

sys.modules.pop("faigate.providers", None)
sys.modules.pop("faigate.updates", None)
sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


# ── Canned catalog ────────────────────────────────────────────────────────────
# Two active brands (Claude + DeepSeek), one unreachable brand (Qwen — the
# credential is "missing" in the stub). This mirrors the real fusionAIze
# catalog shape after the v1.3 brand pivot.

_CATALOG: dict[str, dict[str, Any]] = {
    "anthropic-pro-5h-session": {
        "package_id": "anthropic-pro-5h-session",
        "provider_id": "anthropic-claude",
        "provider_group": "anthropic",
        "brand": "Claude",
        "brand_slug": "claude",
        "package_type": "rolling_window",
        "window_hours": 5,
        "limit_per_window": 100,
        "_requires_credential": "claude-code",
    },
    "anthropic-pro-weekly": {
        "package_id": "anthropic-pro-weekly",
        "provider_id": "anthropic-claude-weekly",
        "provider_group": "anthropic",
        "brand": "Claude",
        "brand_slug": "claude",
        "package_type": "rolling_window",
        "window_hours": 168,
        "limit_per_window": 500,
        "_requires_credential": "claude-code",
    },
    "deepseek-pay-as-you-go": {
        "package_id": "deepseek-pay-as-you-go",
        "provider_id": "deepseek-chat",
        "provider_group": "deepseek",
        "brand": "DeepSeek",
        "brand_slug": "deepseek",
        "package_type": "credits",
        "total_credits": 28.42,
        "used_credits": 0.0,
        "_requires_credential": "DEEPSEEK_API_KEY",
    },
    "qwen-free-daily": {
        "package_id": "qwen-free-daily",
        "provider_id": "qwen-portal",
        "provider_group": "qwen",
        "brand": "Qwen",
        "brand_slug": "qwen",
        "package_type": "daily",
        "limit_per_day": 2000,
        "_requires_credential": "qwen-portal-missing",
    },
}


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _MetricsRecorder:
    """Metrics double that records the filters passed to each method.

    The endpoints' *only* job on top of the metrics layer is to inject
    ``providers=[...]`` — so we check the recorded call shape rather than
    the (boring) fake data coming back.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    # Quota endpoints use these four:
    def get_client_breakdown(self, **kw):
        self._record("get_client_breakdown", **kw)
        return [{"client_profile": "openclaw", "client_tag": "agent", "requests": 3}]

    def get_client_totals(self, **kw):
        self._record("get_client_totals", **kw)
        return [{"client_profile": "openclaw", "client_tag": "agent", "requests": 3}]

    def get_lane_family_breakdown(self, **kw):
        self._record("get_lane_family_breakdown", **kw)
        return [{"lane_family": "claude-coding", "requests": 3, "providers": 1, "cost_usd": 0.0}]

    def get_routing_breakdown(self, **kw):
        self._record("get_routing_breakdown", **kw)
        return []

    def get_selection_path_breakdown(self, **kw):
        self._record("get_selection_path_breakdown", **kw)
        return []

    def get_totals(self, **kw):
        self._record("get_totals", **kw)
        return {"total_requests": 3, "total_failures": 0, "total_cost_usd": 0.0}

    def get_provider_summary(self, **kw):
        self._record("get_provider_summary", **kw)
        return []

    def get_hourly_series(self, *args, **kw):
        self._record("get_hourly_series", hours=args[0] if args else None, **kw)
        return [{"hour_offset": 0, "requests": 1, "cost_usd": 0.0, "tokens": 10}]

    def get_daily_totals(self, *args, **kw):
        self._record("get_daily_totals", days=args[0] if args else None, **kw)
        return []

    # Unused by the brand endpoints but the quotas handler needs them:
    def log_request(self, **_kw):
        pass


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers: {}
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    recorder = _MetricsRecorder()
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {}, raising=False)
    monkeypatch.setattr(main_module, "_metrics", recorder, raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    # Catalog shim: both the detail endpoints and /api/quotas reach into
    # ``provider_catalog.get_packages_catalog``. Patch the canonical module.
    from faigate import provider_catalog

    monkeypatch.setattr(provider_catalog, "get_packages_catalog", lambda: _CATALOG, raising=False)

    # Credential gate: treat "claude-code" + "DEEPSEEK_API_KEY" as present,
    # but reject the Qwen one so it appears in skipped/inactive.
    def _cred_available(hint):
        return bool(hint) and hint != "qwen-portal-missing"

    monkeypatch.setattr(main_module, "_credential_available", _cred_available, raising=False)

    with TestClient(main_module.app) as client:
        client.metrics_recorder = recorder  # type: ignore[attr-defined]
        yield client


# ── _brand_context unit tests ────────────────────────────────────────────────


class TestBrandContext:
    def test_known_brand_returns_providers(self, api_client):
        ctx = main_module._brand_context("claude")
        assert ctx is not None
        assert ctx["brand"] == "Claude"
        assert ctx["brand_slug"] == "claude"
        # Two packages under the same brand contribute two provider IDs.
        assert ctx["providers"] == ["anthropic-claude", "anthropic-claude-weekly"]
        assert len(ctx["packages"]) == 2

    def test_unknown_brand_returns_none(self, api_client):
        assert main_module._brand_context("nope") is None
        assert main_module._brand_context("") is None

    def test_inactive_brand_returns_none(self, api_client):
        # Qwen is in the catalog but credential missing → filtered out →
        # _brand_context sees no packages → None (so the endpoint 404s
        # instead of silently returning empty data for "active" Qwen).
        assert main_module._brand_context("qwen") is None

    def test_slug_is_case_insensitive(self, api_client):
        ctx = main_module._brand_context("ClAuDe")
        assert ctx is not None
        assert ctx["brand_slug"] == "claude"


# ── HTTP-level tests ──────────────────────────────────────────────────────────


class TestClientsEndpoint:
    def test_returns_404_for_unknown_brand(self, api_client):
        r = api_client.get("/api/quotas/nope/clients")
        assert r.status_code == 404

    def test_returns_clients_scoped_to_brand_providers(self, api_client):
        r = api_client.get("/api/quotas/claude/clients")
        assert r.status_code == 200
        body = r.json()
        assert body["brand"] == "Claude"
        assert body["brand_slug"] == "claude"
        assert body["providers"] == ["anthropic-claude", "anthropic-claude-weekly"]
        assert body["clients"] and body["clients"][0]["client_profile"] == "openclaw"

        # Most important: the providers list reached the metrics layer.
        recorder: _MetricsRecorder = api_client.metrics_recorder  # type: ignore[attr-defined]
        breakdown_calls = [c for c in recorder.calls if c[0] == "get_client_breakdown"]
        assert breakdown_calls
        assert breakdown_calls[-1][1]["providers"] == [
            "anthropic-claude",
            "anthropic-claude-weekly",
        ]


class TestRoutesEndpoint:
    def test_returns_404_for_unknown_brand(self, api_client):
        r = api_client.get("/api/quotas/nope/routes")
        assert r.status_code == 404

    def test_lane_families_filter_passes_through(self, api_client):
        r = api_client.get("/api/quotas/deepseek/routes")
        assert r.status_code == 200
        body = r.json()
        assert body["brand"] == "DeepSeek"
        assert body["providers"] == ["deepseek-chat"]
        assert body["lane_families"][0]["lane_family"] == "claude-coding"

        recorder: _MetricsRecorder = api_client.metrics_recorder  # type: ignore[attr-defined]
        lane_calls = [c for c in recorder.calls if c[0] == "get_lane_family_breakdown"]
        assert lane_calls
        assert lane_calls[-1][1]["providers"] == ["deepseek-chat"]


class TestAnalyticsEndpoint:
    def test_returns_404_for_unknown_brand(self, api_client):
        r = api_client.get("/api/quotas/nope/analytics")
        assert r.status_code == 404

    def test_defaults_and_clamping(self, api_client):
        # 99999-hour window should be clamped to the max (24 * 7 = 168h).
        r = api_client.get("/api/quotas/claude/analytics?hours=99999&days=9999")
        assert r.status_code == 200
        recorder: _MetricsRecorder = api_client.metrics_recorder  # type: ignore[attr-defined]
        hourly_calls = [c for c in recorder.calls if c[0] == "get_hourly_series"]
        daily_calls = [c for c in recorder.calls if c[0] == "get_daily_totals"]
        assert hourly_calls and hourly_calls[-1][1]["hours"] == 24 * 7
        assert daily_calls and daily_calls[-1][1]["days"] == 90

    def test_totals_and_series_piped_through(self, api_client):
        r = api_client.get("/api/quotas/claude/analytics")
        body = r.json()
        assert body["brand"] == "Claude"
        assert body["totals"]["total_requests"] == 3
        assert body["hourly"][0]["requests"] == 1
        # Providers filter is propagated to every metrics call the endpoint
        # makes — this is the core invariant the detail view relies on.
        recorder: _MetricsRecorder = api_client.metrics_recorder  # type: ignore[attr-defined]
        for name in (
            "get_totals",
            "get_provider_summary",
            "get_hourly_series",
            "get_daily_totals",
        ):
            matching = [c for c in recorder.calls if c[0] == name]
            assert matching, f"{name} was not called"
            assert matching[-1][1]["providers"] == [
                "anthropic-claude",
                "anthropic-claude-weekly",
            ], f"{name} missing providers filter"


class TestDetailHTML:
    def test_brand_slug_is_substituted(self, api_client):
        r = api_client.get("/dashboard/quotas/claude")
        assert r.status_code == 200
        text = r.text
        assert 'const BRAND_SLUG = "claude"' in text
        # No stray placeholders should leak into the response.
        assert "__BRAND_SLUG__" not in text
        assert "__COCKPIT_URL__" not in text
        # The overview page's "back" breadcrumb is wired up.
        assert "/dashboard/quotas" in text

    def test_cockpit_url_respects_env(self, api_client, monkeypatch):
        monkeypatch.setenv("FAIGATE_COCKPIT_URL", "https://cockpit.example.test/")
        r = api_client.get("/dashboard/quotas/deepseek")
        assert r.status_code == 200
        # Trailing slash stripped by _cockpit_base_url; the JS string is
        # baked in at render time.
        assert 'COCKPIT_URL = "https://cockpit.example.test"' in r.text

    def test_unknown_brand_slug_still_serves_shell(self, api_client):
        # The HTML is intentionally brand-agnostic — it probes the API on
        # load and shows "Brand not found" client-side when the API 404s.
        # Serving a 404 for the page itself would break shareable links.
        r = api_client.get("/dashboard/quotas/made-up-brand")
        assert r.status_code == 200
        assert 'const BRAND_SLUG = "made-up-brand"' in r.text
