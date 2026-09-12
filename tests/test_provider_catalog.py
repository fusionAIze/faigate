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


def test_model_input_cap_is_none_without_catalog():
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


def test_provider_catalog_context_window_survives_external_merge(tmp_path, monkeypatch):
    """External catalog overlays must preserve the embedded context_window/limits.

    A nested dict field (limits) merged from an external overlay must not drop
    the embedded value, because _merge_catalog_entry recurses into dict values.
    """
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "providers").mkdir()
    external = metadata_dir / "providers" / "catalog.v1.json"
    external.write_text(
        '{"schema_version":"fusionaize-provider-catalog/v1.1",'
        '"providers":{"deepseek-chat":{"recommended_model":"deepseek/chat-overlay"}}}'
    )

    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_DIR", str(metadata_dir))
    monkeypatch.delenv("FAIGATE_PROVIDER_METADATA_FILE", raising=False)

    import faigate.provider_catalog as pc

    pc._EXTERNAL_CATALOG_CACHE = None
    pc._EXTERNAL_CATALOG_MTIME = 0.0

    entry = pc.get_provider_catalog_entry("deepseek-chat")

    # Overlay replaced the model but the embedded context window/limits remain.
    assert entry["recommended_model"] == "deepseek/chat-overlay"
    assert entry["context_window"] > 0
    assert 240000 < entry["limits"]["max_input_tokens"] <= 275000


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

    ``_CATALOG`` is a KNOWN, STILL-LIVE violation: 907 lines of embedded
    provider entries, seeded by ``_get_catalog_source`` and then overlaid by the
    resolved catalog. It is named here rather than asserted away. Deleting it
    is deferred: emptying it fails 19 further tests, because the snapshot does
    not yet carry every merged field the table contributes (notably a runtime
    ``recommended_model``). Until that migration lands, this guard's job is to
    keep the count at exactly one: a second embedded table is a regression, and
    so is any change to the legacy block, which lives here as a pinned
    allowance rather than as a silent pass.

    Honest scope. The guard walks the whole tree, so it sees a table assigned
    inside a function as well as at module level — the same reach as
    :func:`test_no_embedded_cap_table_in_provider_catalog`, and deliberately no
    weaker than it. It shares that guard's blind spot: a table that is assembled
    rather than written as an assignment literal (tuple of pairs, ``dict(...)``
    call, comprehension, nested one level deeper, or built by ``.update()``) is
    not seen. Those gaps are pinned by
    :func:`test_embedded_provider_table_guard_does_not_see_built_tables`.

    RED-PROOF 1: add a second table, e.g.
        _MY_PROVIDERS = {"acme": {"context_window": 128000, "aliases": ["acme"]}}
    anywhere in ``faigate/provider_catalog.py`` and this test fails naming it.
    RED-PROOF 2: rename ``_CATALOG`` and this test fails, because the known
    allowance no longer matches — forcing the allowance to be revisited rather
    than silently kept.
    """
    import inspect

    import faigate.provider_catalog as pc

    offending = set(_embedded_provider_table_literals(inspect.getsource(pc)))

    # The one table allowed to exist today, by name, on purpose.
    known = {"_CATALOG"}
    unexpected = offending - known

    assert not unexpected, (
        "provider_catalog.py declares a new embedded provider table: "
        f"{sorted(unexpected)}. Provider knowledge belongs in the catalog, "
        "not in code — see the bundled snapshot in assets/metadata/. "
        f"(The legacy table(s) {sorted(known)} are a pinned, tracked exception; "
        "see this test's docstring.)"
    )
    assert offending == known, (
        "the pinned embedded-table allowance no longer matches the module: "
        f"found {sorted(offending)}, allowance is {sorted(known)}. Update the "
        "allowance in this test and its docstring together — the guard and the "
        "known violation must not drift apart."
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
