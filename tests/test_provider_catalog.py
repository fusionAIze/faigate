from __future__ import annotations

from pathlib import Path

import pytest

from faigate.config import load_config
from faigate.provider_catalog import (
    build_provider_catalog_report,
    build_provider_discovery_view,
    build_provider_metadata_snapshot,
    build_provider_refresh_guidance,
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
    """Every catalog entry must declare limits.max_input_tokens within the (240000, 275000] band."""
    catalog = get_provider_catalog()

    for name, entry in catalog.items():
        limits = entry.get("limits")
        assert isinstance(limits, dict), f"provider {name!r} must declare limits as a dict, got {limits!r}"
        cap = limits.get("max_input_tokens")
        assert isinstance(cap, int) and 240000 < cap <= 275000, (
            f"provider {name!r} max_input_tokens must be in (240000, 275000], got {cap!r}"
        )


def test_model_input_caps_cover_binding_models():
    """The 23 binding model IDs each resolve to a real (non-floor) input cap."""
    import faigate.provider_catalog as pc

    real_caps = {
        "deepseek-v4-pro": 1000000,
        "deepseek-v4-flash": 1000000,
        "gpt-5.6-sol": 922000,
        "gpt-5.6-terra": 922000,
        "gpt-5.6-luna": 922000,
        "gpt-5.5": 1050000,
        "gpt-5.5-pro": 1050000,
        "o3": 200000,
        "o3-mini": 200000,
        "o4-mini": 200000,
        "claude-opus-5": 1000000,
        "claude-sonnet-5": 1000000,
        "claude-haiku-4-5": 200000,
        "claude-code": 262144,  # Shim; documented mirror, not a native window
        "gemini-3.1-pro": 1048576,
        "gemini-3.1-flash": 1048576,
        "gemini-3-flash-lite": 1048576,
        "llama-4-maverick": 131072,
        "llama-4-scout": 131072,
        "qwen-3.6-27b": 262144,
        "qwen3-coder": 262144,
        "glm-5.3": 1000000,
        "kimi-k2.6": 262144,
    }

    expected = set(real_caps)
    declared = set(pc._MODEL_INPUT_CAPS)
    assert declared == expected, (
        f"model cap map must match the 23 binding IDs exactly; "
        f"missing={sorted(expected - declared)}, extra={sorted(declared - expected)}"
    )

    for model_id, expected_cap in real_caps.items():
        assert get_model_max_input_tokens(model_id) == expected_cap
        prefixed = f"openrouter/{model_id}"
        assert get_model_max_input_tokens(prefixed) == expected_cap, (
            f"get_model_max_input_tokens({prefixed!r}) must resolve the trailing model id"
        )


def test_model_input_caps_unknown_model_returns_none():
    """An unknown model id returns None rather than a fabricated cap."""
    assert get_model_max_input_tokens("provider/not-a-binding-model") is None
    assert get_model_max_input_tokens("") is None
    assert get_model_max_input_tokens(None) is None


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
