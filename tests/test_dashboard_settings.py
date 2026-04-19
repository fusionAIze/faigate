"""Coverage for ``dashboard.quotas.default_view`` persistence and the
``/api/dashboard/settings`` + ``/dashboard/quotas`` redirect contract.

Pins (v2.3 Phase B.5):

1. ``dashboard_settings.get_settings()`` defaults to ``overview`` when the
   block is missing, and validates ``default_view`` on read (bad values
   degrade to ``overview`` instead of crashing the endpoint).

2. ``dashboard_settings.set_default_view()`` writes back to config.yaml
   through ruamel.yaml round-trip — **comments and neighbor keys
   survive**. This is the whole reason we took the ruamel.yaml
   dependency; a regression here silently destroys 200+ operator
   comments in the real config.

3. Bad ``default_view`` values (empty, uppercase garbage, unknown
   literal, bogus ``brand:`` suffix) raise ``ValueError`` and never
   touch the file.

4. ``POST /api/dashboard/settings`` surfaces validation errors as 400 and
   otherwise returns the canonical settings dict.

5. ``GET /dashboard/quotas`` redirects (302) for ``brand:<slug>`` and
   ``cockpit`` defaults, **except** when the caller passes
   ``?view=overview`` (the escape hatch a pinned-brand card uses to
   link back home).
"""

from __future__ import annotations

import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

sys.modules.pop("httpx", None)
import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sys.modules["httpx"] = httpx

sys.modules.pop("faigate.main", None)

import faigate.dashboard_settings as ds  # noqa: E402
import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


# Heavily-commented fragment modeled after the real ``config.yaml`` so the
# round-trip test can verify every kind of comment survives: section
# banners, inline end-of-line notes, and blank-line separators.
_COMMENTED_CONFIG = """\
# ── Server section ────────────────────────────────────────────────────
server:
  host: "127.0.0.1"
  port: 8090  # dev default

# providers left intentionally empty for this test
providers: {}

fallback_chain: []

# ── Metrics ───────────────────────────────────────────────────────────
metrics:
  enabled: false

# End-of-file trailing comment — should also survive.
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(_COMMENTED_CONFIG, encoding="utf-8")
    return path


# ── Unit tests: dashboard_settings module ────────────────────────────────────


class TestGetSettings:
    def test_missing_block_returns_overview_defaults(self, config_path: Path):
        got = ds.get_settings(config_path)
        assert got == {"default_view": "overview", "pinned_brand_slug": ""}

    def test_reads_brand_view_after_write(self, config_path: Path):
        ds.set_default_view("brand:claude", path=config_path)
        got = ds.get_settings(config_path)
        assert got == {"default_view": "brand:claude", "pinned_brand_slug": "claude"}

    def test_cockpit_view_has_no_pinned_slug(self, config_path: Path):
        ds.set_default_view("cockpit", path=config_path)
        got = ds.get_settings(config_path)
        assert got == {"default_view": "cockpit", "pinned_brand_slug": ""}

    def test_bad_stored_value_degrades_to_overview(self, config_path: Path):
        # Simulate a hand-edited config with a garbage value — the reader
        # must not 500; it degrades to overview so the dashboard loads.
        config_path.write_text(
            _COMMENTED_CONFIG + "\ndashboard:\n  quotas:\n    default_view: lolwut\n",
            encoding="utf-8",
        )
        got = ds.get_settings(config_path)
        assert got["default_view"] == "overview"

    def test_nonexistent_file_returns_defaults(self, tmp_path: Path):
        got = ds.get_settings(tmp_path / "does-not-exist.yaml")
        assert got == {"default_view": "overview", "pinned_brand_slug": ""}


class TestValidateDefaultView:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("overview", "overview"),
            ("  OVERVIEW  ", "overview"),  # trimmed + lowered
            ("cockpit", "cockpit"),
            ("brand:claude", "brand:claude"),
            ("brand:deepseek-chat", "brand:deepseek-chat"),
            ("BRAND:CLAUDE", "brand:claude"),
        ],
    )
    def test_accepts_canonical_values(self, value: str, expected: str):
        assert ds.validate_default_view(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["", "home", "brand:", "brand:Has Spaces", "brand:", "random", "cockpit:claude", "brand:under_score"],
    )
    def test_rejects_bad_values(self, value: str):
        with pytest.raises(ValueError):
            ds.validate_default_view(value)


class TestSetDefaultViewRoundTrip:
    def test_preserves_comments_and_blank_lines(self, config_path: Path):
        before = config_path.read_text(encoding="utf-8")
        before_comment_count = before.count("#")
        assert before_comment_count >= 4  # sanity: the fixture has 4+ comment lines

        ds.set_default_view("brand:claude", path=config_path)
        after = config_path.read_text(encoding="utf-8")

        # Every comment survives the round-trip.
        assert after.count("#") == before_comment_count
        for sentinel in (
            "# ── Server section",
            "port: 8090  # dev default",
            "# providers left intentionally empty for this test",
            "# ── Metrics",
            "# End-of-file trailing comment — should also survive.",
        ):
            assert sentinel in after, f"Lost comment: {sentinel!r}"

        # The new block was appended, other keys stayed intact.
        assert "dashboard:" in after
        assert "default_view: brand:claude" in after
        assert "pinned_brand_slug: claude" in after
        assert "providers: {}" in after
        assert "fallback_chain: []" in after

    def test_pinning_a_different_brand_updates_both_keys(self, config_path: Path):
        ds.set_default_view("brand:claude", path=config_path)
        ds.set_default_view("brand:deepseek", path=config_path)
        got = ds.get_settings(config_path)
        assert got == {"default_view": "brand:deepseek", "pinned_brand_slug": "deepseek"}

    def test_switching_away_from_brand_drops_pinned_slug_key(self, config_path: Path):
        ds.set_default_view("brand:claude", path=config_path)
        assert "pinned_brand_slug: claude" in config_path.read_text(encoding="utf-8")

        ds.set_default_view("overview", path=config_path)
        text = config_path.read_text(encoding="utf-8")
        assert "pinned_brand_slug" not in text
        assert "default_view: overview" in text

    def test_rejects_bad_values_without_touching_file(self, config_path: Path):
        before = config_path.read_text(encoding="utf-8")
        with pytest.raises(ValueError):
            ds.set_default_view("not-a-real-view", path=config_path)
        assert config_path.read_text(encoding="utf-8") == before

    def test_atomic_rename_leaves_no_tmp_files(self, config_path: Path):
        ds.set_default_view("brand:claude", path=config_path)
        siblings = list(config_path.parent.iterdir())
        leftover = [s for s in siblings if s.name.startswith(".dashboard_settings.")]
        assert leftover == [], f"leftover tmp files: {leftover}"


# ── HTTP-level tests: endpoints + redirect ──────────────────────────────────


def _write_minimal_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """\
server:
  host: "127.0.0.1"
  port: 8090
providers: {}
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    cfg_path = _write_minimal_config(tmp_path)
    cfg = load_config(cfg_path)

    # dashboard_settings always reads FAIGATE_CONFIG_FILE (same env var as
    # the rest of faigate) — point it at our scratch file.
    monkeypatch.setenv("FAIGATE_CONFIG_FILE", str(cfg_path))
    monkeypatch.setenv("FAIGATE_COCKPIT_URL", "https://cockpit.example")

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {}, raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app, follow_redirects=False) as client:
        client.config_path = cfg_path  # type: ignore[attr-defined]
        yield client


class TestSettingsApi:
    def test_get_defaults_when_unset(self, api_client):
        r = api_client.get("/api/dashboard/settings")
        assert r.status_code == 200
        assert r.json() == {"default_view": "overview", "pinned_brand_slug": ""}

    def test_post_brand_persists_and_echoes(self, api_client):
        r = api_client.post("/api/dashboard/settings", json={"default_view": "brand:claude"})
        assert r.status_code == 200
        assert r.json() == {"default_view": "brand:claude", "pinned_brand_slug": "claude"}

        # Value is visible on the next GET (persisted through config.yaml).
        r = api_client.get("/api/dashboard/settings")
        assert r.json()["default_view"] == "brand:claude"

    def test_post_cockpit(self, api_client):
        r = api_client.post("/api/dashboard/settings", json={"default_view": "cockpit"})
        assert r.status_code == 200
        assert r.json() == {"default_view": "cockpit", "pinned_brand_slug": ""}

    def test_post_overview(self, api_client):
        api_client.post("/api/dashboard/settings", json={"default_view": "brand:claude"})
        r = api_client.post("/api/dashboard/settings", json={"default_view": "overview"})
        assert r.status_code == 200
        assert r.json() == {"default_view": "overview", "pinned_brand_slug": ""}

    def test_post_bad_value_400s(self, api_client):
        r = api_client.post("/api/dashboard/settings", json={"default_view": "bogus"})
        assert r.status_code == 400
        assert "default_view" in r.json()["error"]

    def test_post_missing_key_400s(self, api_client):
        r = api_client.post("/api/dashboard/settings", json={})
        assert r.status_code == 400

    def test_post_non_object_400s(self, api_client):
        r = api_client.post("/api/dashboard/settings", json=["overview"])
        assert r.status_code == 400

    def test_post_invalid_json_400s(self, api_client):
        r = api_client.post(
            "/api/dashboard/settings",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400


class TestDashboardRedirect:
    def test_overview_default_renders_html(self, api_client):
        r = api_client.get("/dashboard/quotas")
        assert r.status_code == 200
        assert "<html" in r.text.lower()

    def test_brand_default_redirects(self, api_client):
        api_client.post("/api/dashboard/settings", json={"default_view": "brand:claude"})
        r = api_client.get("/dashboard/quotas")
        assert r.status_code == 302
        assert r.headers["location"] == "/dashboard/quotas/claude"

    def test_cockpit_default_redirects_offsite(self, api_client):
        api_client.post("/api/dashboard/settings", json={"default_view": "cockpit"})
        r = api_client.get("/dashboard/quotas")
        assert r.status_code == 302
        assert r.headers["location"] == "https://cockpit.example"

    def test_view_overview_query_overrides_redirect(self, api_client):
        api_client.post("/api/dashboard/settings", json={"default_view": "brand:claude"})
        r = api_client.get("/dashboard/quotas?view=overview")
        assert r.status_code == 200  # NOT redirected
        # Detail page has "Back to overview" — overview page doesn't.
        assert "Back to overview" not in r.text

    def test_bad_settings_file_falls_back_to_overview(self, api_client, tmp_path, monkeypatch):
        # Point FAIGATE_CONFIG_FILE at a deliberately-broken YAML so the
        # settings read raises. The handler must degrade to the overview
        # HTML, not 500.
        broken = tmp_path / "broken.yaml"
        broken.write_text(": : : not valid\nyaml:", encoding="utf-8")
        monkeypatch.setenv("FAIGATE_CONFIG_FILE", str(broken))
        r = api_client.get("/dashboard/quotas")
        assert r.status_code == 200
        assert "<html" in r.text.lower()


class TestDashboardHtmlHasPinUi:
    """Pin UI lives in the inlined HTML — smoke-check the sentinels so a
    template regression (e.g. stripped JS handler) is loud rather than
    silent."""

    def test_overview_html_has_pin_controls(self, api_client):
        r = api_client.get("/dashboard/quotas?view=overview")
        for needle in ("pin-status", "toggleBrandPin", "setHomeView", "loadSettings"):
            assert needle in r.text, f"missing sentinel: {needle}"

    def test_detail_html_has_pin_button(self, api_client):
        # Any slug works — the HTML is the same template with substitution.
        r = api_client.get("/dashboard/quotas/claude")
        assert r.status_code == 200
        for needle in ("pinBtn", "togglePin", "loadPinSettings", "PIN_SETTINGS"):
            assert needle in r.text, f"missing sentinel: {needle}"
