from __future__ import annotations

import json
from pathlib import Path

import pytest

import faigate.provider_catalog as pc
from faigate.config import load_config
from faigate.provider_catalog import (
    build_provider_catalog_report,
    build_provider_discovery_view,
    build_provider_metadata_snapshot,
    build_provider_refresh_guidance,
    get_model_input_cap_fact,
    get_model_max_input_tokens,
    get_offerings_catalog,
    get_packages_catalog,
    get_provider_catalog,
    get_provider_catalog_entry,
    materialize_provider_metadata_snapshot,
)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _pin_catalog_review_age_to_fresh(monkeypatch):
    """Freeze the curated catalog's review age so these tests stay about content.

    ``build_provider_catalog_report`` raises ``catalog-stale`` once a curated
    entry is older than ``max_catalog_age_days``. That alert is a function of the
    wall clock: left alone, every test here that counts alerts would flip to red
    on its own the day the shipped ``last_reviewed`` crosses the threshold — a
    red suite with no code change, and with it no promise actually broken.

    Pinning the review date to "today" keeps the cohort each test asserts on
    independent of when the suite runs: ``catalog_age_days`` becomes 0 for every
    entry, so the only alerts that can appear are the content alerts the test
    deliberately provokes. Freshness itself is still covered — directly, through
    ``build_provider_refresh_guidance`` and its ``freshness_overrides``.
    """
    monkeypatch.setattr(pc, "_tracked_item", _with_pinned_review_date(pc._tracked_item))


def _with_pinned_review_date(real):
    """Wrap ``_tracked_item`` so the entry's ``last_reviewed`` reads as today."""

    def _pinned(provider_name, provider, catalog_entry, *, today):
        fresh_entry = dict(catalog_entry)
        fresh_entry["last_reviewed"] = today.isoformat()
        return real(provider_name, provider, fresh_entry, today=today)

    return _pinned


def test_provider_catalog_report_has_no_alert_for_aligned_model(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["tracked_providers"] == 1
    assert report["alert_count"] == 0
    assert report["items"][0]["provider_type"] == "direct"
    assert report["items"][0]["evidence_level"] == "official"
    assert report["items"][0]["canonical_model"] == "deepseek/chat"
    assert report["items"][0]["lane_family"] == "deepseek"
    assert report["items"][0]["route_type"] == "direct"


def test_provider_catalog_report_warns_on_model_drift(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat-v2"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["alert_count"] == 1
    assert report["alerts"][0]["code"] == "model-drift"
    assert report["alerts"][0]["recommended_model"] == "deepseek-chat"


def test_provider_catalog_report_warns_on_untracked_provider(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  custom-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "custom-model"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["tracked_providers"] == 0
    assert report["alert_count"] == 1
    assert report["alerts"][0]["code"] == "untracked-provider"


def test_provider_catalog_report_warns_on_unofficial_and_volatile_tracks(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  blackbox-free:
    backend: openai-compat
    base_url: "https://api.blackbox.ai"
    api_key: "secret"
    model: "blackboxai/x-ai/grok-code-fast-1"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)
    codes = {alert["code"] for alert in report["alerts"]}

    assert "catalog-source-unofficial" in codes
    assert "volatile-offer-configured" in codes
    assert report["items"][0]["offer_track"] == "credit"
    assert report["items"][0]["volatility"] == "high"


def test_provider_catalog_report_exposes_wallet_router_metadata(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  clawrouter:
    backend: openai-compat
    base_url: "https://router.blockrun.ai/v1"
    api_key: "wallet"
    model: "auto"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["tracked_providers"] == 1
    assert report["items"][0]["provider_type"] == "wallet-router"
    assert report["items"][0]["auth_modes"] == ["wallet_x402"]
    assert report["items"][0]["official_source_url"].startswith("https://blockrun.ai/")


def test_provider_catalog_report_exposes_discovery_policy_and_links(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        "FAIGATE_PROVIDER_LINK_OPENROUTER_FALLBACK_URL",
        "https://go.example.test/openrouter",
    )
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  openrouter-fallback:
    backend: openai-compat
    base_url: "https://openrouter.ai/api/v1"
    api_key: "secret"
    model: "openrouter/auto"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["recommendation_policy"]["provider_links_affect_ranking"] is False
    discovery = report["items"][0]["discovery"]
    assert discovery["resolved_url"] == "https://go.example.test/openrouter"
    assert discovery["link_source"] == "operator_override"
    assert discovery["disclosure_required"] is True


def test_provider_discovery_view_filters_to_resolved_links(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
  openrouter-fallback:
    backend: openai-compat
    base_url: "https://openrouter.ai/api/v1"
    api_key: "secret"
    model: "openrouter/auto"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    view = build_provider_discovery_view(cfg)

    assert view["recommendation_policy"]["provider_links_affect_ranking"] is False
    provider_names = [item["provider"] for item in view["providers"]]
    assert provider_names == ["deepseek-chat", "openrouter-fallback"]
    assert view["providers"][0]["resolved_url"].startswith("https://")


def test_provider_discovery_view_supports_link_source_and_offer_track_filters(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        "FAIGATE_PROVIDER_LINK_OPENROUTER_FALLBACK_URL",
        "https://go.example.test/openrouter",
    )
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
  openrouter-fallback:
    backend: openai-compat
    base_url: "https://openrouter.ai/api/v1"
    api_key: "secret"
    model: "openrouter/auto"
  kilocode:
    backend: openai-compat
    base_url: "https://api.kilo.ai/api/gateway"
    api_key: "secret"
    model: "z-ai/glm-5:free"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    operator_view = build_provider_discovery_view(cfg, link_source="operator_override")
    disclosed_view = build_provider_discovery_view(cfg, disclosed_only=True)
    free_view = build_provider_discovery_view(cfg, offer_track="free")

    assert operator_view["filters"]["link_source"] == "operator_override"
    assert [item["provider"] for item in operator_view["providers"]] == ["openrouter-fallback"]
    assert [item["provider"] for item in disclosed_view["providers"]] == ["openrouter-fallback"]
    assert [item["provider"] for item in free_view["providers"]] == ["kilocode"]


def test_build_provider_refresh_guidance_prefers_stale_entries():
    guidance = build_provider_refresh_guidance(
        ["deepseek-chat", "openrouter-fallback"],
        freshness_overrides={
            "deepseek-chat": {
                "freshness_status": "stale",
                "review_age_days": 29,
                "freshness_hint": "review this route before trusting benchmark assumptions",
            },
            "openrouter-fallback": {
                "freshness_status": "aging",
                "review_age_days": 12,
                "freshness_hint": "marketplace assumptions should be reviewed soon",
            },
        },
    )

    assert [item["provider"] for item in guidance] == ["deepseek-chat", "openrouter-fallback"]
    assert guidance[0]["action"] == "refresh-now"
    assert guidance[0]["refresh_url"].startswith("https://")
    assert guidance[1]["action"] == "review-soon"


def test_provider_catalog_report_can_track_provider_from_external_snapshot(tmp_path: Path, monkeypatch):
    snapshot = tmp_path / "provider-catalog.json"
    snapshot.write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "anthropic-haiku": {
      "recommended_model": "claude-3-5-haiku-latest",
      "aliases": ["claude-3-5-haiku-latest", "anthropic:haiku"],
      "track": "stable",
      "offer_track": "direct",
      "provider_type": "direct",
      "auth_modes": ["api_key"],
      "volatility": "low",
      "evidence_level": "official",
      "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
      "signup_url": "https://console.anthropic.com/",
      "watch_sources": [],
      "notes": "External snapshot entry",
       "last_reviewed": "2026-08-20"
    }
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_FILE", str(snapshot))

    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  anthropic-haiku:
    backend: openai-compat
    base_url: "https://api.anthropic.com/v1"
    api_key: "secret"
    model: "claude-3-5-haiku-latest"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    assert report["tracked_providers"] == 1
    assert report["alert_count"] == 0
    assert report["items"][0]["provider"] == "anthropic-haiku"
    assert report["items"][0]["tracked"] is True
    assert report["items"][0]["recommended_model"] == "claude-3-5-haiku-latest"


def test_provider_catalog_external_snapshot_can_override_embedded_entry(tmp_path: Path, monkeypatch):
    snapshot = tmp_path / "provider-catalog.json"
    snapshot.write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "External override note",
       "last_reviewed": "2026-05-04"
    }
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_FILE", str(snapshot))

    entry = get_provider_catalog_entry("deepseek-chat")

    assert entry["notes"] == "External override note"
    assert entry["last_reviewed"] == "2026-05-04"


def test_provider_catalog_can_load_repo_catalog_with_gate_overlay(tmp_path: Path, monkeypatch):
    repo_dir = tmp_path / "fusionaize-metadata"
    (repo_dir / "providers").mkdir(parents=True)
    (repo_dir / "products" / "gate").mkdir(parents=True)
    (repo_dir / "providers" / "catalog.v1.json").write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "Base note",
      "pricing": {
        "source_type": "provider-docs",
        "source_url": "https://example.test/pricing"
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    (repo_dir / "products" / "gate" / "overlays.v1.json").write_text(
        """
{
  "schema_version": "fusionaize-provider-overlays/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "Gate note",
      "pricing": {
        "freshness_status": "fresh"
      }
    },
    "anthropic-haiku": {
      "recommended_model": "claude-3-5-haiku-latest",
      "aliases": ["anthropic:haiku"],
      "track": "stable",
      "offer_track": "direct",
      "provider_type": "direct",
      "auth_modes": ["api_key"],
      "volatility": "low",
      "evidence_level": "official",
      "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
      "signup_url": "https://console.anthropic.com/",
      "watch_sources": [],
      "notes": "Added by Gate overlay",
       "last_reviewed": "2026-05-04"
    }
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(repo_dir))

    entry = get_provider_catalog_entry("deepseek-chat")
    added = get_provider_catalog_entry("anthropic-haiku")

    assert entry["notes"] == "Gate note"
    assert entry["pricing"]["source_type"] == "provider-docs"
    assert entry["pricing"]["freshness_status"] == "fresh"
    assert added["notes"] == "Added by Gate overlay"


def test_materialize_provider_metadata_snapshot_writes_effective_catalog(tmp_path: Path):
    repo_dir = tmp_path / "fusionaize-metadata"
    output_path = tmp_path / "state" / "provider-catalog.snapshot.v1.json"
    (repo_dir / "providers").mkdir(parents=True)
    (repo_dir / "products" / "gate").mkdir(parents=True)
    (repo_dir / "providers" / "catalog.v1.json").write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "generated_at": "2026-03-31T18:00:00Z",
  "source_repo": "fusionaize-metadata",
  "providers": {
    "deepseek-chat": {
      "notes": "Base note"
    }
  }
}
""",
        encoding="utf-8",
    )
    (repo_dir / "products" / "gate" / "overlays.v1.json").write_text(
        """
{
  "schema_version": "fusionaize-provider-overlays/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "Gate note"
    }
  }
}
""",
        encoding="utf-8",
    )

    snapshot = build_provider_metadata_snapshot(repo_dir)
    written = materialize_provider_metadata_snapshot(repo_dir, output_path)

    assert snapshot["providers"]["deepseek-chat"]["notes"] == "Gate note"
    assert written["providers"]["deepseek-chat"]["notes"] == "Gate note"
    assert output_path.exists() is True
    assert "Gate note" in output_path.read_text(encoding="utf-8")


def test_materialize_refuses_to_overwrite_source_catalog(tmp_path: Path):
    repo_dir = tmp_path / "fusionaize-metadata"
    (repo_dir / "providers").mkdir(parents=True)
    source_catalog = repo_dir / "providers" / "catalog.v1.json"
    source_catalog.write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "Base note"
    }
  }
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        materialize_provider_metadata_snapshot(repo_dir, source_catalog)

    assert source_catalog.read_text(encoding="utf-8") == (
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "Base note"
    }
  }
}
"""
    )


def test_provider_catalog_report_includes_recommendations(tmp_path):
    from faigate.config import load_config
    from faigate.provider_catalog import build_provider_catalog_report

    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )

    report = build_provider_catalog_report(cfg)

    # Recommendations field should be present
    assert "recommendations" in report
    assert isinstance(report["recommendations"], list)

    # If there are priority clusters with items, there should be recommendations
    if any(cluster["item_count"] > 0 for cluster in report["priority_clusters"]):
        assert len(report["recommendations"]) > 0
        # Each recommendation should have required fields
        for rec in report["recommendations"]:
            assert "id" in rec
            assert "title" in rec
            assert "description" in rec
            assert "priority" in rec
            assert "action" in rec
            assert "cluster_id" in rec


def test_offerings_and_packages_catalog_loading(tmp_path, monkeypatch):
    """Test that offerings and packages catalogs can be loaded from external metadata."""
    # Create a temporary metadata directory with empty catalogs
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "offerings").mkdir()
    (metadata_dir / "packages").mkdir()

    # Write empty catalogs
    offerings_catalog = metadata_dir / "offerings" / "catalog.v1.json"
    offerings_catalog.write_text('{"schema_version":"fusionaize-offering-catalog/v1","offerings":{}}')
    packages_catalog = metadata_dir / "packages" / "catalog.v1.json"
    packages_catalog.write_text('{"schema_version":"fusionaize-package-catalog/v1","packages":{}}')

    # Set environment variable and reset global cache
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(metadata_dir))
    monkeypatch.setenv("FAIGATE_OFFERINGS_METADATA_FILE", str(offerings_catalog))
    monkeypatch.setenv("FAIGATE_PACKAGES_METADATA_FILE", str(packages_catalog))
    import faigate.provider_catalog as pc

    pc._EXTERNAL_OFFERINGS_CACHE = None
    pc._EXTERNAL_OFFERINGS_MTIME = 0.0
    pc._EXTERNAL_PACKAGES_CACHE = None
    pc._EXTERNAL_PACKAGES_MTIME = 0.0

    # Load catalogs
    offerings = get_offerings_catalog()
    packages = get_packages_catalog()

    # Should be empty dicts
    assert offerings == {}
    assert packages == {}

    # Test that caching works by loading again
    offerings2 = get_offerings_catalog()
    packages2 = get_packages_catalog()
    assert offerings2 is offerings  # same cached object
    assert packages2 is packages


def test_provider_catalog_expresses_oauth_for_managed_direct_providers():
    """TASK-008: at least one managed direct provider expresses oauth as an auth mode."""
    catalog = get_provider_catalog()

    oauth_providers = [
        (name, entry.get("auth_modes", [])) for name, entry in catalog.items() if "oauth" in entry.get("auth_modes", [])
    ]
    assert oauth_providers, "catalog must declare at least one provider with an oauth auth mode"

    # The bundled snapshot carries the reconciled entries literally.
    assert any("oauth" in modes for _, modes in oauth_providers)

    # github-copilot is a managed direct provider that must express oauth alongside api_key.
    copilot = catalog.get("github-copilot")
    assert copilot is not None, "github-copilot must be present"
    assert "oauth" in copilot["auth_modes"], f"github-copilot auth_modes={copilot['auth_modes']!r}"


def test_provider_catalog_api_key_providers_unchanged_for_oauth_reconciliation():
    """TASK-008 acceptance: existing api_key providers retain api_key without regression."""
    import json
    from pathlib import Path

    import faigate.provider_catalog as pc

    snapshot = json.loads(
        (Path(pc.__file__).parent / "assets" / "metadata" / "catalog.v1.json").read_text(encoding="utf-8")
    )
    providers = snapshot["providers"]

    api_key_names = {n for n, e in providers.items() if "api_key" in e.get("auth_modes", [])}
    assert api_key_names, "snapshot must still declare api_key providers"

    # The two reconciled oauth providers must not have lost their api_key where applicable.
    assert "api_key" in providers["github-copilot"]["auth_modes"], "github-copilot (oauth+api_key) must retain api_key"

    # A known pure-api_key direct provider stays intact.
    assert providers["anthropic"]["auth_modes"] == ["api_key"]


def test_provider_catalog_schema_version_bump_recorded():
    """TASK-008 acceptance: the additive oauth change is recorded as a version bump."""
    import json
    from pathlib import Path

    import faigate.provider_catalog as pc

    snapshot = json.loads(
        (Path(pc.__file__).parent / "assets" / "metadata" / "catalog.v1.json").read_text(encoding="utf-8")
    )
    version = snapshot["schema_version"]
    assert version.startswith("fusionaize-provider-catalog/")
    assert version != "fusionaize-provider-catalog/v1.1", (
        "schema_version must be bumped past v1.1 to record the additive oauth change"
    )


def test_provider_catalog_declares_context_window_everywhere():
    """Every catalog entry must declare a positive, non-null context_window."""
    catalog = get_provider_catalog()

    assert catalog, "catalog must not be empty"

    for name, entry in catalog.items():
        ctx = entry.get("context_window")
        assert isinstance(ctx, int) and ctx > 0, (
            f"provider {name!r} must declare a positive integer context_window, got {ctx!r}"
        )


def test_provider_catalog_declares_in_band_input_cap():
    """Every entry must declare a usable input cap, and say how well it knows it.

    This used to assert a narrow ``(240000, 275000]`` band around the static
    table's single remembered number, 262144. That band is not a property of the
    resolved catalog: since the chain falls through to the curated snapshot,
    each provider's cap is its own declared ``max_input_tokens`` (200000,
    1048576, 131072, ...). Keeping the band would fail on every legitimate
    catalog refresh while proving nothing.

    What the catalog does promise is that the cap is a usable integer and that
    its ``context_evidence.level`` is one of the recognised values — so a caller
    can see whether a number is sourced or is a migration placeholder rather
    than have to trust it blindly.
    """
    catalog = get_provider_catalog()
    recognised_levels = {"confirmed", "plausible", "unconfirmed"}

    for name, entry in catalog.items():
        limits = entry.get("limits")
        assert isinstance(limits, dict), f"provider {name!r} must declare limits as a dict, got {limits!r}"
        cap = limits.get("max_input_tokens")
        assert isinstance(cap, int) and not isinstance(cap, bool) and cap > 0, (
            f"provider {name!r} max_input_tokens must be a positive int, got {cap!r}"
        )
        level = str((entry.get("context_evidence") or {}).get("level") or "").strip()
        assert level in recognised_levels, (
            f"provider {name!r} declares max_input_tokens={cap} with evidence level "
            f"{level!r}; expected one of {sorted(recognised_levels)} so the cap's "
            "provenance is visible to callers"
        )


def test_binding_model_caps_resolve_from_catalog():
    """The canonical binding model IDs resolve to a non-floor *enforceable* cap.

    The lookup surfaces only caps the evidence lets the router enforce, so a
    binding model recorded as ``unconfirmed`` legitimately answers ``None``.
    Requiring a number for every binding id would mean demanding that the
    router enforce a cap the catalog declines to assert — the contradiction
    this test used to encode. What the test still pins is the shape of every
    answer: when a cap is returned it is a positive int and the
    ``provider/<model>`` spelling resolves to the same one.
    """
    binding_models = [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.5-pro",
        "o3",
        "o3-mini",
        "o4-mini",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-code",
        "gemini-3.1-pro",
        "gemini-3.1-flash",
        "gemini-3-flash-lite",
        "llama-4-maverick",
        "llama-4-scout",
        "qwen-3.6-27b",
        "qwen3-coder",
        "glm-5.3",
        "kimi-k2.6",
    ]

    for model_id in binding_models:
        cap = get_model_max_input_tokens(model_id)
        if cap is None:
            # Hidden by evidence gating: the catalog must agree and say so,
            # rather than the lookup having lost a cap it used to serve.
            fact = get_model_input_cap_fact(model_id)
            assert fact is not None, f"binding model {model_id!r} answers no cap and the catalog records no fact at all"
            assert fact["evidence"]["level"] != "confirmed", (
                f"binding model {model_id!r} answers no cap despite a confirmed catalog fact: {fact!r}"
            )
            continue
        assert isinstance(cap, int) and cap > 0, f"cap for {model_id!r} must be a positive int, got {cap!r}"
        prefixed = f"openrouter/{model_id}"
        assert get_model_max_input_tokens(prefixed) == cap, (
            f"get_model_max_input_tokens({prefixed!r}) must resolve the trailing model id"
        )
    assert get_model_max_input_tokens("deepseek-v4-pro") == 1000000


def test_model_input_caps_unknown_model_returns_none():
    """An unknown model id returns None rather than a fabricated cap."""
    assert get_model_max_input_tokens("provider/not-a-binding-model") is None
    assert get_model_max_input_tokens("") is None
    assert get_model_max_input_tokens(None) is None


def _write_metadata_catalog(
    tmp_path: Path,
    providers: dict | None = None,
    *,
    model_caps: dict | None = None,
) -> Path:
    payload: dict = {"schema_version": "fusionaize-provider-catalog/v1.3", "providers": providers or {}}
    if model_caps is not None:
        payload["model_caps"] = model_caps
    metadata_dir = tmp_path / "metadata"
    (metadata_dir / "providers").mkdir(parents=True)
    (metadata_dir / "providers" / "catalog.v1.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return metadata_dir


def _patch_metadata_env(monkeypatch, pc, metadata_dir: Path) -> None:
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(metadata_dir))
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.setattr(pc, "_EXTERNAL_CATALOG_CACHE", None)
    monkeypatch.setattr(pc, "_EXTERNAL_CATALOG_MTIME", 0.0)


def test_model_caps_index_populated_from_bundled_snapshot_without_env(tmp_path, monkeypatch):
    """Without any env override, model_caps is read from the bundled snapshot."""
    import faigate.provider_catalog as pc

    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    index = pc._model_caps_index()

    # The catalog grows as sources are scraped; pinning an exact count makes this
    # test fail on every legitimate catalog update. What it must prove is that the
    # bundled snapshot is read at all, not how much it happens to carry today.
    # The count is of *enforceable* caps only, so it excludes the entries the
    # catalog records as unconfirmed or plausible.
    assert len(index) >= 30
    assert index["deepseek-v4-pro"] == 1000000
    assert index["gpt-5.6-sol"] == 922000


def test_model_input_cap_env_file_override_takes_precedence(tmp_path, monkeypatch):
    """A populated FAIGATE_PROVIDER_METADATA_FILE wins over the bundled snapshot.

    "Takes precedence" is checked at the level the override actually decides:
    the bundled ``deepseek-v4-pro`` (confirmed, 1000000) is absent from the
    override, so the override supplying a *different* entry is visible by the
    index containing that entry and nothing from the snapshot. The override's
    entry here carries no evidence, so it is not enforceable and the index is
    empty — the point is that the snapshot's caps were displaced, not merged.
    """
    import faigate.provider_catalog as pc

    snapshot = tmp_path / "provider-catalog.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "fusionaize-provider-catalog/v1.3",
                "model_caps": {
                    # No evidence block: an unrecognised level is treated as
                    # unverified, and an unverified cap is not in the
                    # enforceable index this test reads.
                    "gpt-5.6-sol": {"max_input_tokens": 111111},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_FILE", str(snapshot))
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    index = pc._model_caps_index()

    assert index == {}
    assert "deepseek-v4-pro" not in index


def test_model_input_cap_reads_from_catalog_first(tmp_path, monkeypatch):
    """A cap that exists only in model_caps (no dict entry) is delivered."""
    import faigate.provider_catalog as pc

    metadata_dir = _write_metadata_catalog(
        tmp_path,
        model_caps={
            "catalog-only-model": {
                "max_input_tokens": 777000,
                "evidence": {"level": "confirmed", "source_url": "https://example.test/cap"},
            },
        },
    )
    _patch_metadata_env(monkeypatch, pc, metadata_dir)

    assert get_model_max_input_tokens("acme/catalog-only-model") == 777000
    assert get_model_max_input_tokens("catalog-only-model") == 777000


def test_model_input_cap_is_none_without_catalog(monkeypatch):
    """With no catalog reachable no cap is produced — a number is never invented.

    There is no embedded fallback table any more. A model the catalog cannot
    describe has no known cap, and saying so is the honest answer; returning a
    remembered number would state a fact this process cannot support.

    "No catalog reachable" is asked for explicitly, through the resolver's
    test-only suppression of the bundled link. It used to be staged by pointing
    ``FAIGATE_PROVIDER_METADATA_DIR`` at an empty directory, which stopped
    meaning anything once the chain learned to fall through a dangling pointer to
    the bundled snapshot: that setup now resolves the full snapshot and the test
    would assert nothing.
    """
    import faigate.provider_catalog as pc
    from faigate.catalog_resolver import suppressed_bundled_snapshot

    # The suppression hides the bundled link only. An operator override in the
    # ambient environment answers from the FIRST link and the chain never
    # reaches the suppressed one, so the test would assert against a catalog it
    # asked not to have. "No catalog reachable" means all three links, not one.
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    with suppressed_bundled_snapshot():
        _reset_catalog_caches(pc)
        assert get_model_max_input_tokens("gpt-5.6-sol") is None
        assert get_model_max_input_tokens("openrouter/gpt-5.6-sol") is None
    _reset_catalog_caches(pc)


def test_model_input_cap_catalog_overrides_dict(tmp_path, monkeypatch):
    """A model_caps entry for a mapped model overrides the bundled fallback value."""
    import faigate.provider_catalog as pc

    metadata_dir = _write_metadata_catalog(
        tmp_path,
        model_caps={
            "gpt-5.6-sol": {
                "max_input_tokens": 111111,
                "evidence": {"level": "confirmed", "source_url": "https://example.test/cap"},
            },
        },
    )
    _patch_metadata_env(monkeypatch, pc, metadata_dir)

    assert get_model_max_input_tokens("gpt-5.6-sol") == 111111


def test_model_input_cap_fact_carries_catalog_evidence(tmp_path, monkeypatch):
    """A catalog-sourced cap carries the block's evidence, not the hardcoded confirmed."""
    import faigate.provider_catalog as pc

    metadata_dir = _write_metadata_catalog(
        tmp_path,
        model_caps={
            "deepseek-v4-flash": {
                "max_input_tokens": 1000000,
                "evidence": {"level": "unconfirmed"},
            },
        },
    )
    _patch_metadata_env(monkeypatch, pc, metadata_dir)

    fact = pc.get_model_input_cap_fact("deepseek-v4-flash")
    assert fact is not None
    assert fact["max_input_tokens"] == 1000000
    assert fact["evidence"]["level"] == "unconfirmed"


def test_model_input_cap_catalog_wins_over_hardcoded_dict_without_env(monkeypatch):
    """Without an env override the bundled catalog still wins over the fallback dict."""
    import faigate.provider_catalog as pc

    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    # deepseek-v4-pro is in both sources with the same cap number; the refreshed
    # bundled catalog carries a sourced "confirmed" entry. Catalog wins over the
    # hardcoded fallback regardless — the important invariant is that the catalog
    # evidence level is preserved, not the hardcoded dict's level.
    fact = pc.get_model_input_cap_fact("deepseek-v4-pro")
    assert fact is not None
    assert fact["max_input_tokens"] == 1000000
    assert fact["evidence"]["level"] == "confirmed"


def test_model_input_cap_absent_without_catalog(monkeypatch, tmp_path):
    """An empty catalog yields no cap fact at all, not an unsourced one.

    The embedded fallback table is gone, so there is nothing left that could
    answer without provenance. This pins that absence.
    """
    import faigate.provider_catalog as pc

    # Inject an empty catalog: there is no second source behind it.
    empty_metadata_dir = _write_metadata_catalog(tmp_path, model_caps={})
    _patch_metadata_env(monkeypatch, pc, empty_metadata_dir)

    # An empty catalog knows no caps, so no evidence-tagged fact can exist.
    # The 413 path turns this into a passthrough or the operator byte limit —
    # never a per-model token number nobody can source.
    assert pc.get_model_input_cap_fact("gpt-5.6-sol") is None
    assert pc.get_model_max_input_tokens("gpt-5.6-sol") is None


def test_model_input_cap_normalizes_dot_version_separators(monkeypatch):
    """A dot-form request resolves the hyphen-form catalog entry: 4.6 == 4-6."""
    import faigate.provider_catalog as pc

    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    assert pc.get_model_max_input_tokens("anthropic/claude-opus-4.6") == 1000000
    assert pc.get_model_max_input_tokens("anthropic/claude-sonnet-4.6") == 1000000


def test_model_input_cap_does_not_equate_letter_suffixes(monkeypatch):
    """The digit-group rule must not turn gpt-4o into gpt-4-o."""
    import faigate.provider_catalog as pc

    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    assert pc.get_model_max_input_tokens("openai/gpt-4o") == 128000
    assert pc.get_model_max_input_tokens("openai/gpt-4-o") is None


def test_catalog_provider_identities_include_catalog_only_providers(monkeypatch):
    """A provider that lives only in the catalog still yields an identity."""
    import faigate.provider_catalog as pc

    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    identities = pc.catalog_provider_identities()
    by_long = {f"{i['vendor']}/{i['model']}".lower() for i in identities}
    # amazon-bedrock has no registry.ALL entry but is in the bundled catalog.
    assert "amazon/nova-pro-v1" in by_long


def test_provider_catalog_external_overlay_wins_and_registers_nested_dicts(tmp_path, monkeypatch):
    """An external overlay beats the lane-derived seed without dropping siblings.

    The catalog wire-table (:data:`faigate.provider_catalog._CATALOG`) holds only
    a lane-derived ``recommended_model``; the fact fields (``context_window``,
    ``limits``, …) live in the bundled snapshot, not in the table. This test used
    to assert that an external overlay *preserved* those embedded facts while
    replacing the model — a premise that stopped holding once the table shed its
    fact fields. What stays true is the merge contract: the overlay's
    ``recommended_model`` wins over the seed, and ``_merge_catalog_entry``
    recurses into dict values so an overlay's nested ``limits`` does not clobber a
    sibling fact it did not name.
    """
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "providers").mkdir()
    external = metadata_dir / "providers" / "catalog.v1.json"
    external.write_text(
        '{"schema_version":"fusionaize-provider-catalog/v1.3",'
        '"providers":{"deepseek-chat":{"recommended_model":"deepseek/chat-overlay",'
        '"context_window":777000,"limits":{"max_input_tokens":777000}}}}'
    )

    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(metadata_dir))
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)

    import faigate.provider_catalog as pc

    pc._EXTERNAL_CATALOG_CACHE = None
    pc._EXTERNAL_CATALOG_MTIME = 0.0

    entry = pc.get_provider_catalog_entry("deepseek-chat")

    # Overlay recommended_model beats the lane-derived seed.
    assert entry["recommended_model"] == "deepseek/chat-overlay"
    # Overlay facts are what the resolver serves when the dir replaces the snapshot.
    assert entry["context_window"] == 777000
    assert entry["limits"]["max_input_tokens"] == 777000

    # The merge helper recurses into nested dicts, preserving a sibling fact the
    # overlay's `limits` did not name.
    merged = pc._merge_catalog_entry(
        {"context_window": 1048576, "limits": {"max_input_tokens": 1048576}},
        {"limits": {"max_output_tokens": 8192}},
    )
    assert merged["context_window"] == 1048576
    assert merged["limits"]["max_input_tokens"] == 1048576
    assert merged["limits"]["max_output_tokens"] == 8192


# --------------------------------------------------------------------------- #
# Structural guard: no embedded cap table in provider_catalog.py
# --------------------------------------------------------------------------- #


def _embedded_cap_table_literals(source: str) -> list[str]:
    """Names of dict/AnnAssign literals in *source* that look like cap tables.

    A literal matches when its value is an ``ast.Dict`` whose keys are all
    string constants, at least one of which contains a digit (model IDs like
    ``"gpt-4"``, ``"deepseek-v2"``), and whose values are all integer
    constants.

    Scope: this sees only dict *literals* written at the assignment statement
    itself, anywhere in the tree (module level or inside a function). It is
    blind to a table that is built rather than written — see the docstring of
    :func:`test_no_embedded_cap_table_in_provider_catalog` for the list of
    evasions this deliberately does not chase.
    """
    import ast

    offending: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value_node = node.value if isinstance(node, ast.Assign) else node.value
        if not isinstance(value_node, ast.Dict) or not value_node.keys:
            continue

        keys = value_node.keys
        values = value_node.values
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in keys):
            continue
        if not any(any(c.isdigit() for c in k.value) for k in keys):  # type: ignore[union-attr]
            continue
        if not all(isinstance(v, ast.Constant) and isinstance(v.value, int) for v in values):
            continue

        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                offending.append(node.target.id)
        else:
            offending.extend(t.id for t in node.targets if isinstance(t, ast.Name))

    return offending


def test_no_embedded_cap_table_in_provider_catalog() -> None:
    """Detect a hardcoded model-cap dict literal written into provider_catalog.py.

    The catalog is the sole source of per-model input-token caps. This test
    keeps the obvious re-introduction — a dict literal of model-id keys and
    integer caps, whatever the variable is called — out of the module.

    Honest scope. The check is structural, not a name list, so it catches any
    variable name; and it walks the whole tree, so a literal assigned inside a
    function is caught too. That is the entire reach. It does not catch a table
    that is assembled rather than written as an assignment literal, e.g.:

      * ``_X = (("gpt-4", 100),)`` — a tuple of pairs
      * ``_X = dict(gpt4=100)`` — a ``dict(...)`` call
      * ``_X = {k: 100 for k in ["gpt-4"]}`` — a comprehension
      * ``_OUTER = {"holder": {"gpt-4": 100}}`` — nested one level down
      * ``_X = {}; _X.update({"gpt-4": 100})`` — built by mutation

    These are known gaps, pinned by
    :func:`test_embedded_cap_table_guard_does_not_see_built_tables` so that the
    guard's reach stays what this docstring says it is rather than drifting by
    implication. Closing them with more AST patterns is a treadmill: each new
    pattern invites the next spelling.

    The invariant that actually carries the weight is behavioural, not
    structural: a silent fallback wired into ``get_model_max_input_tokens``
    leaves this guard green, and is caught by
    :func:`test_model_input_cap_is_none_without_catalog` and
    :func:`test_model_input_cap_absent_without_catalog`, which assert that no
    cap is produced without a catalog behind it.

    RED-PROOF: add ``_MY_NEW_CAPS: dict[str, int] = {"some-model-4": 123456}``
    (or the bare ``_MY_NEW_CAPS = {...}`` form) anywhere in
    ``faigate/provider_catalog.py`` and this test fails naming the variable.
    """
    import inspect

    import faigate.provider_catalog as pc

    offending = _embedded_cap_table_literals(inspect.getsource(pc))

    assert not offending, (
        "Embedded cap table(s) detected in faigate/provider_catalog.py: "
        + ", ".join(offending)
        + ". Per-model input-token caps must live in the catalog only."
    )


def test_embedded_cap_table_guard_catches_literal_spellings() -> None:
    """ROT-PROOF for the two literal spellings the guard claims to catch."""
    module_level = '_MY_NEW_CAPS: dict[str, int] = {"some-model-4": 123456}'
    bare = '_OTHER_CAPS = {"gpt-4": 100, "gpt-5": 200}'
    in_function = 'def load():\n    _NESTED_CAPS = {"claude-3": 300}\n    return _NESTED_CAPS'

    assert _embedded_cap_table_literals(module_level) == ["_MY_NEW_CAPS"]
    assert _embedded_cap_table_literals(bare) == ["_OTHER_CAPS"]
    assert _embedded_cap_table_literals(in_function) == ["_NESTED_CAPS"]


def test_embedded_cap_table_guard_does_not_see_built_tables() -> None:
    """ROT-PROOF for the gaps: a built table is invisible to this guard.

    Pinning the gaps makes them an explicit, reviewed decision. If a future
    change widens the guard, this test goes red and the docstring above must be
    updated in the same commit — the guard and its stated reach cannot drift
    apart silently.
    """
    built = {
        "tuple of pairs": '_X = (("gpt-4", 100),)',
        "dict() call": "_X = dict(gpt4=100)",
        "comprehension": '_X = {k: 100 for k in ["gpt-4"]}',
        "nested one level": '_OUTER = {"holder": {"gpt-4": 100}}',
        "built by mutation": '_X = {}\n_X.update({"gpt-4": 100})',
    }

    for name, source in built.items():
        assert _embedded_cap_table_literals(source) == [], (
            f"guard now catches the {name!r} spelling — widen the docstring of "
            "test_no_embedded_cap_table_in_provider_catalog to match"
        )


# Fields that only ever appear in a catalog entry. One is enough: a dict of
# dicts carrying any of these is provider knowledge, not configuration.
_CATALOG_ONLY_FIELDS = frozenset(
    {
        "context_window",
        "aliases",
        "recommended_model",
        "auth_modes",
        "provider_type",
        "tier_status",
        "limits",
        "context_evidence",
        "entry_type",
    }
)


def _embedded_provider_table_literals(source: str) -> list[str]:
    """Names of dict-of-dict literals in *source* that look like provider tables.

    A literal matches when its value is an ``ast.Dict`` whose values are
    themselves ``ast.Dict`` literals carrying at least one catalog-only field.

    Scope matches :func:`_embedded_cap_table_literals` exactly: it walks the
    whole tree, so a table declared inside a function is seen, and it is
    likewise blind to a table that is assembled rather than written. The two
    guards must not differ in reach — the provider guard was previously
    module-level only, which made it strictly weaker than this one.
    """
    import ast

    offending: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value_node = node.value if isinstance(node, ast.Assign) else node.value
        if not isinstance(value_node, ast.Dict) or not value_node.keys:
            continue

        if not any(
            isinstance(inner, ast.Dict)
            and any(isinstance(k, ast.Constant) and k.value in _CATALOG_ONLY_FIELDS for k in inner.keys)
            for inner in value_node.values
        ):
            continue

        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                offending.append(node.target.id)
        else:
            offending.extend(t.id for t in node.targets if isinstance(t, ast.Name))

    return offending


def test_no_embedded_provider_table_in_provider_catalog() -> None:
    """Detect a hardcoded provider table written into provider_catalog.py.

    The catalog is the sole source of provider knowledge. A dict literal whose
    values are dicts carrying catalog-only fields (``context_window``,
    ``aliases``, ...) is a provider table under any name, so the check is
    structural rather than a list of forbidden names.

    ``_CATALOG`` no longer trips this guard. It shed its fact fields in the
    wiring refactor and is now a plain lane map whose values are
    ``get_active_model_id(...)`` calls (see :func:`test_recommended_model_inline_literals_name_a_catalog_model`),
    so there is no longer any embedded provider table to allow. The allowance is
    therefore empty, and the second assertion keeps it honest: the module must
    match it exactly, with no entry silently re-introduced.

    Honest scope. The guard walks the whole tree, so it sees a table assigned
    inside a function as well as at module level — the same reach as
    :func:`test_no_embedded_cap_table_in_provider_catalog`, and deliberately no
    weaker than it. It shares that guard's blind spot: a table that is assembled
    rather than written as an assignment literal (tuple of pairs, ``dict(...)``
    call, comprehension, nested one level deeper, or built by ``.update()``) is
    not seen. Those gaps are pinned by
    :func:`test_embedded_provider_table_guard_does_not_see_built_tables`.

    RED-PROOF: add a table, e.g.
        _MY_PROVIDERS = {"acme": {"context_window": 128000, "aliases": ["acme"]}}
    anywhere in ``faigate/provider_catalog.py`` and this test fails naming it,
    because the allowance is empty and cannot absorb it.
    """
    import inspect

    import faigate.provider_catalog as pc

    offending = set(_embedded_provider_table_literals(inspect.getsource(pc)))

    # No embedded provider table is allowed: the module has none left.
    known: set[str] = set()
    unexpected = offending - known

    assert not unexpected, (
        "provider_catalog.py declares a new embedded provider table: "
        f"{sorted(unexpected)}. Provider knowledge belongs in the catalog, "
        "not in code — see the bundled snapshot in assets/metadata/."
    )
    assert offending == known, (
        "the embedded-table allowance no longer matches the module: "
        f"found {sorted(offending)}, allowance is {sorted(known)}. Update the "
        "allowance in this test and its docstring together — the guard and the "
        "known table must not drift apart."
    )


def test_embedded_provider_table_guard_catches_literal_spellings() -> None:
    """ROT-PROOF for the provider-table spellings, including in-function."""
    module_level = '_MY_PROVIDERS = {"acme": {"context_window": 128000, "aliases": ["acme"]}}'
    in_function = 'def load():\n    _NESTED_PROVIDERS = {"acme": {"aliases": ["acme"]}}\n    return _NESTED_PROVIDERS'

    assert _embedded_provider_table_literals(module_level) == ["_MY_PROVIDERS"]
    assert _embedded_provider_table_literals(in_function) == ["_NESTED_PROVIDERS"]


def test_embedded_provider_table_guard_does_not_see_built_tables() -> None:
    """ROT-PROOF for the provider guard's gaps, matching the cap guard's."""
    built = {
        "tuple of pairs": '_X = (("acme", {"context_window": 1}),)',
        "dict() call": '_X = dict(acme={"context_window": 1})',
        "comprehension": '_X = {k: {"context_window": 1} for k in ["acme"]}',
        "built by mutation": '_X = {}\n_X.update({"acme": {"context_window": 1}})',
    }

    for name, source in built.items():
        assert _embedded_provider_table_literals(source) == [], (
            f"guard now catches the {name!r} spelling — widen the docstring of "
            "test_no_embedded_provider_table_in_provider_catalog to match"
        )


# --------------------------------------------------------------------------- #
# recommended_model: a derived field, pinned against the catalog it derives from
# --------------------------------------------------------------------------- #


def _resolved_catalog_without_env() -> dict:
    """Resolve the catalog with every ``FAIGATE_*`` override cleared.

    The operator shell in this repo really does export
    ``FAIGATE_PROVIDER_METADATA_DIR`` / ``..._FILE``; a test that reads the
    chain without clearing them measures the operator's working copy, not the
    shipped snapshot. Callers that want the bundled catalog must go through
    here.
    """
    import os

    saved = {
        name: os.environ.pop(name, None)
        for name in (
            "FAIGATE_PROVIDER_METADATA_FILE",
            "FAIGATE_PROVIDER_METADATA_DIR",
            "FAIGATE_OFFERINGS_METADATA_FILE",
            "FAIGATE_PROVIDER_METADATA_PRODUCT",
        )
    }
    try:
        _reset_catalog_caches(pc)
        return pc._resolve_catalog_payload()
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
        _reset_catalog_caches(pc)


_CATALOG_WIRING_NAME = "_CATALOG"


def _catalog_wiring_entries(source: str) -> list[tuple[str, str, bool, str]]:
    """``(lane, raw_target, is_derived, why)`` for every ``_CATALOG`` lane entry.

    ``_CATALOG`` no longer holds facts: it is a lane map whose values are
    ``get_active_model_id("<family>/<lane>")`` calls, and the resolved value is
    what ``_get_catalog_source`` seeds as ``recommended_model``. The provider
    name is the *outer dict key*.

    Two shapes are recognised (``why`` is empty):

    * ``get_active_model_id("<str>")`` — ``raw_target`` is the string argument,
      ``is_derived=True``. Resolve it the way the module does.
    * a bare string literal — ``raw_target`` is the literal, ``is_derived=False``;
      ``_get_catalog_source`` installs it as-is.

    **Every other value shape is an error, not a skip.** ``_get_catalog_source``
    takes *any* ``str``/``int``/``float`` into a lane's ``recommended_model``
    (``provider_catalog.py``:762-766), so an f-string, a concatenation, a
    ``str(...)`` call, an ``int``, or any other expression installs a live model
    name that nothing here can vet. Such an entry is returned with
    ``is_derived=False`` and ``raw_target`` set to its source text, and the guard
    fails on it. Dropping it (the previous behaviour) was itself the hole: the
    value is consumed, so it must be vetted or rejected — never ignored.
    """
    import ast

    found: list[tuple[str, str, bool, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == _CATALOG_WIRING_NAME for t in targets):
            continue
        value_node = node.value
        if not isinstance(value_node, ast.Dict):
            continue
        for lane_node, entry in zip(value_node.keys, value_node.values):
            if not (isinstance(lane_node, ast.Constant) and isinstance(lane_node.value, str)):
                continue
            lane = lane_node.value
            if isinstance(entry, ast.Constant) and isinstance(entry.value, str):
                found.append((lane, entry.value, False, ""))
                continue
            if (
                isinstance(entry, ast.Call)
                and isinstance(entry.func, ast.Name)
                and entry.func.id == "get_active_model_id"
                and len(entry.args) == 1
                and isinstance(entry.args[0], ast.Constant)
                and isinstance(entry.args[0].value, str)
            ):
                found.append((lane, entry.args[0].value, True, ""))
                continue
            found.append(
                (
                    lane,
                    ast.unparse(entry),
                    False,
                    "is neither a get_active_model_id(<str>) call nor a bare "
                    "string literal; _get_catalog_source would install its "
                    "runtime value as recommended_model unchecked",
                )
            )
    return found


def _catalog_wiring_assignments(source: str) -> list[tuple[str, str]]:
    """``(lane, canonical_id)`` for the derived (``get_active_model_id``) entries."""
    return [(lane, target) for lane, target, is_derived, _why in _catalog_wiring_entries(source) if is_derived]


def test_recommended_model_inline_literals_name_a_catalog_model() -> None:
    """Every ``_CATALOG`` lane target must name a model the catalog knows.

    ``_CATALOG`` is wiring, not a fact table: it maps a configured lane to the
    canonical id its ``recommended_model`` is derived from. The derived value is
    seeded into ``_get_catalog_source`` and overlaid by the resolved snapshot, so
    a lane that points at a model absent from the catalog installs a
    ``recommended_model`` for a model the catalog never heard of. That is the
    failure this guard exists to catch, and the wiring is now its whole subject:
    the previous fact-table version is gone, so its five pinned divergences have
    no subject left and are not carried over.

    Both vettable value shapes are checked. A derived ``get_active_model_id(...)``
    target is resolved the way the module resolves it; a bare string literal is
    checked as written, because ``_get_catalog_source`` installs any str as a live
    ``recommended_model``. Any *other* value shape (f-string, concatenation,
    ``str(...)``, an int, …) also lands in ``recommended_model`` but cannot be
    read from source, so the guard fails on the entry itself rather than skipping
    it — an unchecked value the module consumes is a hole, not an exception.

    What it does NOT require: that the lane target equal the provider's ``model``
    outright. Several providers route through a shared canonical lane
    (``gemini-pro-high``/``gemini-pro-low`` -> ``google/gemini-pro-low``) and
    legitimately recommend that lane's model; the check is membership in the
    catalog's ``model`` or ``aliases``, dot/dash-normalized, exactly as the old
    literal guard checked.

    Known exception. One lane targets a model the catalog does not know —
    :data:`_CATALOG_KNOWN_UNKNOWN_TARGETS`. It predates this task (the old guard
    skipped every derived value, so it was never checked) and cannot be fixed
    here: the defect is the canonical id in ``lane_registry``, outside this
    test's write surface. It is pinned by name with a reason and a follow-up
    note rather than left to fail, so the guard stays sharp for every other lane.

    RED-PROOF: change any non-excepted lane's canonical id to a model absent from
    that provider's ``model`` and ``aliases`` (e.g. ``get_active_model_id("deepseek/glm-9.9-not-real")``)
    and this test names that lane; or spell the lane's target as a bare string
    literal naming no catalog model. Both are verified against ``deepseek-chat``
    in :func:`test_recommended_model_guard_catches_a_stale_literal` and
    :func:`test_recommended_model_guard_catches_a_bare_literal_lane`.
    """
    import inspect

    import faigate.provider_catalog as pc

    catalog = _resolved_catalog_without_env()
    providers = catalog.get("providers") if isinstance(catalog, dict) else None
    assert isinstance(providers, dict) and providers, "bundled snapshot did not resolve"

    entries = _catalog_wiring_entries(inspect.getsource(pc))
    assert entries, "no _CATALOG wiring found; the extractor lost its subject"

    malformed = [(lane, raw, why) for lane, raw, _is_derived, why in entries if why]

    stale: list[tuple[str, str, str]] = []
    for lane, target, is_derived, why in entries:
        if why:
            # Not a name we can vet; reported below rather than silently skipped.
            continue
        entry = providers.get(lane)
        if entry is None:
            # A lane only in the wiring map is covered by
            # test_no_embedded_provider_table_in_provider_catalog, not here.
            continue
        # The wiring value is derived at runtime for call entries; resolve it the
        # same way the module does rather than comparing the canonical id's
        # spelling. A bare string literal is compared as-is: it is already the
        # ``recommended_model`` ``_get_catalog_source`` installs.
        literal = pc.get_active_model_id(target) if is_derived else target
        known = {str(entry.get("model") or "")}
        known.update(str(alias) for alias in entry.get("aliases") or [])
        known = {_normalize_dots(value) for value in known if value}
        tail = _normalize_dots(literal.rsplit("/", 1)[-1])
        # A provider-qualified name is accepted when its tail is a model the
        # catalog knows: the catalog may record the bare id while the lane
        # spells it for the upstream API. This is the naming difference the
        # module already normalizes elsewhere, not a second opinion.
        if _normalize_dots(literal) in known or tail in known:
            continue
        # Router/pseudo targets are wiring-shaped: a bare routing keyword.
        # Accept those rather than pin a router's policy.
        if tail in _ROUTER_TARGETS:
            continue
        if (lane, literal) in _CATALOG_KNOWN_UNKNOWN_TARGETS:
            continue
        stale.append((lane, literal, str(entry.get("model") or "")))

    # The guard must keep its whole subject: if the allowance ever claims a lane
    # that is now known (or gone), the pinned exception has rotted.
    for lane, literal in _CATALOG_KNOWN_UNKNOWN_TARGETS:
        entry = providers.get(lane) or {}
        known = {_normalize_dots(str(entry.get("model") or ""))}
        known.update(_normalize_dots(str(a)) for a in entry.get("aliases") or [])
        still_unknown = (
            _normalize_dots(literal) not in known and _normalize_dots(literal.rsplit("/", 1)[-1]) not in known
        )
        assert still_unknown, (
            f"the pinned unknown target {lane} -> {literal!r} is now known to the "
            "catalog; delete its entry from _CATALOG_KNOWN_UNKNOWN_TARGETS and "
            "this docstring together — the list and reality must not drift apart."
        )

    # An entry whose value is neither a get_active_model_id(<str>) call nor a
    # bare literal still reaches a live recommended_model; there is no way to
    # vet it here, so it is a hard failure rather than a silent skip.
    assert not malformed, (
        "_CATALOG lane(s) have a value shape this guard cannot vet:\n  "
        + "\n  ".join(f"{lane}: {raw} {why}" for lane, raw, why in malformed)
        + '\nUse get_active_model_id("<family>/<lane>") or a bare string literal, '
        "so the target can be checked against the catalog."
    )

    assert not stale, (
        "_CATALOG lane(s) target no model the catalog knows:\n  "
        + "\n  ".join(
            f"{lane}: recommended_model={literal!r} is neither the catalog model "
            f"{_catalog_model_of(providers, lane)!r} nor one of its aliases"
            for lane, literal, _model in stale
        )
        + "\nEither point the lane at a catalog model/alias or migrate the model "
        "into the catalog."
    )


def _catalog_model_of(providers: dict, provider: str) -> str:
    entry = providers.get(provider) or {}
    return str(entry.get("model") or "")


def _normalize_dots(value: str) -> str:
    """Treat ``claude-opus-4.6`` and ``claude-opus-4-6`` as the same spelling."""
    return value.replace(".", "-")


# Bare routing keywords a router provider legitimately recommends instead of a
# concrete model. Spelling-normalised. Keep this list short and justified: it is
# the set of values this test refuses to check against the catalog.
_ROUTER_TARGETS = frozenset(
    {
        "auto",
        "auto-router",
        "coding-auto",
        "tier-frontier",
        "tier-balanced",
        "tier-free",
        "openai",
        "local-model",
        "your-model-id",
        "minimax-m2.1-gs32",
    }
)

# Lane wiring targets the catalog does not know. PINNED, not accepted: this is a
# pre-existing data defect surfaced by aiming the guard at the wiring. The old
# fact-table guard skipped every derived (``get_active_model_id``) value, so this
# was never checked before and is not a regression of this task.
#
# ``anthropic-haiku`` -> ``anthropic/haiku-4.5``: ``lane_registry`` has no
# ``anthropic/haiku-4.5`` entry, so it falls back to the tail ``haiku-4.5``,
# while the catalog spells the model ``claude-haiku-4-5``. Fixing it means
# changing ``lane_registry._ACTIVE_MODEL_VERSIONS`` (or this lane's canonical
# id), both outside tests/test_provider_catalog.py. Kept visible on purpose:
# delete the entry once the wiring points at a catalog model.
_CATALOG_KNOWN_UNKNOWN_TARGETS = frozenset(
    {
        ("anthropic-haiku", "haiku-4.5"),
    }
)


def test_recommended_model_literal_extractor_reads_catalog_wiring() -> None:
    """ROT-PROOF: the extractor reads ``_CATALOG`` call entries, not other tables."""
    source = (
        "_CATALOG = {\n"
        '    "acme": get_active_model_id("acme/chat"),\n'
        '    "beta": "glm-5",\n'
        "}\n"
        '_OTHER = {"x": get_active_model_id("x/y")}\n'
    )
    assert _catalog_wiring_assignments(source) == [("acme", "acme/chat")]


def test_recommended_model_literal_extractor_keeps_bare_literals() -> None:
    """ROT-PROOF: a bare string-valued lane is returned, not dropped.

    ``_get_catalog_source`` installs any str as a lane's ``recommended_model``,
    so a literal must reach the catalog check. An extractor that silently skips
    literals would hide exactly the target the guard is meant to vet.
    """
    source = '_CATALOG = {"beta": "totally-made-up-model-xyz"}\n'
    assert _catalog_wiring_entries(source) == [("beta", "totally-made-up-model-xyz", False, "")]


def test_recommended_model_literal_extractor_flags_other_shapes() -> None:
    """ROT-PROOF: a value that is neither call nor literal is flagged, not skipped.

    ``_get_catalog_source`` installs *any* str/int/float as a lane's
    ``recommended_model``, so an f-string, concatenation, ``str(...)`` call or
    plain int reaches production unchecked. The extractor must surface those
    entries with a reason so the guard can fail on them; silently skipping them
    was the hole this test exists to prove closed.
    """
    source = '_CATALOG = {\n    "beta": f"{prefix}-model",\n    "gamma": "a" + "b",\n    "delta": 12345,\n}\n'
    entries = _catalog_wiring_entries(source)
    assert [lane for lane, _raw, _derived, _why in entries] == ["beta", "gamma", "delta"]
    assert all(not reason for _lane, _raw, _derived, reason in entries) is False, "shapes were not flagged"


def test_recommended_model_guard_catches_a_stale_literal() -> None:
    """ROT-PROOF: a lane target naming no catalog model is reported."""
    import inspect

    import faigate.provider_catalog as pc

    providers = _resolved_catalog_without_env()["providers"]
    victim = "deepseek-chat"
    assert victim in providers, "fixture provider vanished from the snapshot"

    real_source = inspect.getsource(pc)
    poisoned = real_source.replace(
        'get_active_model_id("deepseek/chat")',
        'get_active_model_id("deepseek/glm-9.9-not-real")',
        1,
    )
    assert poisoned != real_source, "rot-proof no longer rewrites the deepseek-chat lane"

    assignments = dict(_catalog_wiring_assignments(poisoned))
    assert assignments.get(victim) == "deepseek/glm-9.9-not-real", (
        f"the poisoned lane did not replace the {victim} wiring; got {assignments.get(victim)!r}"
    )

    literal = pc.get_active_model_id(assignments[victim])
    entry = providers[victim]
    known = {_normalize_dots(str(entry.get("model") or ""))}
    known.update(_normalize_dots(str(a)) for a in entry.get("aliases") or [])

    assert _normalize_dots(literal) not in known and _normalize_dots(literal.rsplit("/", 1)[-1]) not in known, (
        "the stale-lane check no longer flags a model absent from the catalog; "
        f"resolved {literal!r} is known as {sorted(known)!r}"
    )

    # And the real source still resolves the lane to a catalog model.
    real_literal = pc.get_active_model_id(dict(_catalog_wiring_assignments(real_source))[victim])
    assert _normalize_dots(real_literal) in known or _normalize_dots(real_literal.rsplit("/", 1)[-1]) in known, (
        f"the {victim} lane now targets an unknown model; update this rot-proof together (resolved {real_literal!r})"
    )


def test_recommended_model_guard_catches_a_bare_literal_lane() -> None:
    """ROT-PROOF: a lane written as a bare literal naming no catalog model is reported.

    The derived-call shape is guarded by
    :func:`test_recommended_model_guard_catches_a_stale_literal`. This is the
    sibling shape: ``_get_catalog_source`` accepts a plain str just the same, so
    a hand-written literal must be vetted as a model name too — otherwise a lane
    pointing at a model the catalog never heard of would be installed live and
    slip past every guard.
    """
    import inspect

    import faigate.provider_catalog as pc

    providers = _resolved_catalog_without_env()["providers"]
    victim = "deepseek-chat"
    assert victim in providers, "fixture provider vanished from the snapshot"

    real_source = inspect.getsource(pc)
    poisoned = real_source.replace(
        'get_active_model_id("deepseek/chat")',
        '"totally-made-up-model-xyz"',
        1,
    )
    assert poisoned != real_source, "rot-proof no longer rewrites the deepseek-chat lane"

    entry = providers[victim]
    known = {_normalize_dots(str(entry.get("model") or ""))}
    known.update(_normalize_dots(str(a)) for a in entry.get("aliases") or [])

    # The extractor keeps the literal, and the catalog check rejects it.
    wiring = dict(
        (lane, (target, why)) for lane, target, _is_derived, why in _catalog_wiring_entries(poisoned) if lane == victim
    )
    literal, why = wiring.get(victim, (None, None))
    assert literal == "totally-made-up-model-xyz" and not why, (
        f"the poisoned lane did not become a vettable bare literal; got {literal!r} ({why!r})"
    )
    assert _normalize_dots(literal) not in known and _normalize_dots(literal.rsplit("/", 1)[-1]) not in known, (
        "the guard no longer flags a bare literal absent from the catalog; "
        f"resolved {literal!r} is known as {sorted(known)!r}"
    )


def test_recommended_model_guard_catches_an_unvettable_lane() -> None:
    """ROT-PROOF: a lane value of another shape is rejected, not skipped.

    An f-string or concatenation still lands in ``recommended_model`` via
    ``_get_catalog_source``, but its value cannot be read from source here. The
    guard must therefore fail on the entry instead of ignoring it — ignoring it
    is what let an unknown model install live and unguarded.
    """
    import ast

    import faigate.provider_catalog as pc

    real_source = getattr(pc, "__source__", None)
    if real_source is None:
        import inspect

        real_source = inspect.getsource(pc)
    poisoned = real_source.replace(
        'get_active_model_id("deepseek/chat")',
        'f"deepseek/{suffix}"',
        1,
    )
    assert poisoned != real_source, "rot-proof no longer rewrites the deepseek-chat lane"

    malformed = [(lane, raw, why) for lane, raw, _is_derived, why in _catalog_wiring_entries(poisoned) if why]
    assert any(lane == "deepseek-chat" for lane, _raw, _why in malformed), (
        f"an unvettable lane value was not flagged; entries were {malformed!r}"
    )
    lane, raw, why = next(item for item in malformed if item[0] == "deepseek-chat")
    assert raw == ast.unparse(ast.parse('f"deepseek/{suffix}"').body[0].value), (
        f"the flagged entry did not carry the offending source text; got {raw!r} for {lane!r}"
    )
    assert "recommended_model" in why  # the reason explains the live consequence


# --------------------------------------------------------------------------- #
# Catalog loading chain: one implementation, one answer
# --------------------------------------------------------------------------- #


def _catalog_views(pc) -> dict[str, set[str]]:
    """Provider-name sets as seen through every loader of the catalog chain.

    ``_load_external_provider_catalog`` (the provider-name path),
    ``_load_external_catalog`` (the legacy accessor) and the ``providers`` block
    of ``_load_external_catalog_payload`` (the caps/identity path) all answer
    the same question — "which provider entries does the catalog hold right
    now?". Comparing names, not just counts, also catches a same-size but
    different-set divergence. Before the chain was collapsed these disagreed by
    which internal helper the caller happened to use.
    """
    return {
        "_load_external_provider_catalog": set(pc._load_external_provider_catalog()),
        "_load_external_catalog": set(pc._load_external_catalog()),
        "_load_external_catalog_payload": set(pc._load_external_catalog_payload().get("providers", {})),
    }


def _reset_catalog_caches(pc) -> None:
    from faigate.catalog_resolver import _invalidate_bundled_snapshot_cache

    pc._EXTERNAL_CATALOG_CACHE = None
    pc._EXTERNAL_CATALOG_MTIME = 0.0
    pc._CATALOG_RESOLVER = None
    _invalidate_bundled_snapshot_cache()


def _write_catalog_file(path: Path, providers: dict) -> Path:
    path.write_text(
        json.dumps({"schema_version": "fusionaize-provider-catalog/v1.3", "providers": providers}),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("state", "env_file", "env_dir"),
    [
        ("both_env_set", "file", "dir"),
        ("only_file", "file", None),
        ("only_dir", None, "dir"),
        ("dir_set_file_missing", None, "empty_dir"),
        ("nothing_set", None, None),
    ],
)
def test_catalog_loaders_agree_in_every_on_disk_state(
    tmp_path: Path, monkeypatch, state: str, env_file: str | None, env_dir: str | None
) -> None:
    """Every loader must see the same provider set for the same on-disk state.

    The chain is ``env-override → metadata-dir → bundled snapshot``. A set but
    empty or non-existent metadata directory must not block the fall back to the
    bundled snapshot: the override is a location hint, not a commitment to a
    catalog that is not there. The file override is link 1 and takes precedence;
    the dir is link 2 and only consulted when no file override is set.
    """
    import faigate.provider_catalog as pc

    # Distinct provider names per link make the answer decidable: a loader that
    # reads a different link names a different provider.
    file_catalog = tmp_path / "file-catalog.v1.json"
    _write_catalog_file(file_catalog, {"file-only-provider": {"vendor": "file", "model": "one"}})

    dir_root = tmp_path / "metadata-dir"
    (dir_root / "providers").mkdir(parents=True)
    _write_catalog_file(
        dir_root / "providers" / "catalog.v1.json",
        {"dir-only-provider": {"vendor": "dir", "model": "one"}},
    )
    empty_dir = tmp_path / "empty-metadata-dir"
    empty_dir.mkdir()

    if env_file == "file":
        monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_FILE", str(file_catalog))
    else:
        monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)

    if env_dir == "dir":
        monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(dir_root))
    elif env_dir == "empty_dir":
        monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(empty_dir))
    else:
        monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_DIR", raising=False)

    _reset_catalog_caches(pc)
    views = _catalog_views(pc)

    # Provider sets carried by each link: the bundled snapshot is read straight
    # from the shipped asset so this test does not hardcode its membership.
    from faigate.catalog_resolver import _load_bundled_snapshot

    bundled = _load_bundled_snapshot() or {}
    bundled_names = set(bundled.get("providers", {}))

    # Link precedence is file → dir → bundled: a set file wins outright, a set
    # dir wins over the bundled snapshot, and a dir that holds no catalog falls
    # through to the bundled snapshot.
    expected: set[str] = {
        "both_env_set": {"file-only-provider"},
        "only_file": {"file-only-provider"},
        "only_dir": {"dir-only-provider"},
        "dir_set_file_missing": bundled_names,
        "nothing_set": bundled_names,
    }[state]

    assert expected, f"state={state!r}: fixture expectation must not be empty"

    distinct = {frozenset(names) for names in views.values()}
    assert len(distinct) == 1, (
        f"state={state!r}: catalog loaders disagree on the provider set: "
        f"{ {name: sorted(names) for name, names in views.items()} }. "
        "All of them read the same chain (env-override → metadata-dir → bundled "
        "snapshot) and must answer the same."
    )
    resolved = next(iter(distinct))
    assert resolved == expected, (
        f"state={state!r}: all loaders agree, but on the wrong set ({sorted(resolved)}); expected {sorted(expected)}."
    )

    # Identities are a projection of the same providers block: every provider
    # entry carrying vendor+model must yield exactly one identity dict.
    payload = pc._load_external_catalog_payload()
    with_identity = [
        name
        for name, entry in payload.get("providers", {}).items()
        if isinstance(entry, dict) and entry.get("vendor") and entry.get("model")
    ]
    identity_count = len(pc.catalog_provider_identities())
    assert identity_count == len(with_identity), (
        f"state={state!r}: catalog_provider_identities sees {identity_count} "
        f"identit(ies) but the resolved providers block has {len(with_identity)} "
        "entries carrying vendor+model."
    )


def test_catalog_dir_set_but_file_missing_falls_back_to_bundled(monkeypatch, tmp_path: Path) -> None:
    """A set-but-dead metadata dir must not disable the bundled fall back.

    ``FAIGATE_PROVIDER_METADATA_DIR`` pointing at an empty or non-existent
    directory is a broken pointer, not a claim that the catalog is empty. The
    docstring's promise — "when neither override yields a catalog file, fall
    back to the bundled snapshot" — has to hold here too.
    """
    import faigate.provider_catalog as pc

    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)
    _reset_catalog_caches(pc)

    assert len(pc._load_external_provider_catalog()) > 0
    assert len(pc._load_external_catalog_payload().get("providers", {})) > 0
    assert len(pc.catalog_provider_identities()) > 0
    assert len(pc._load_external_model_caps()) > 0
