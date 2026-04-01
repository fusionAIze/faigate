from __future__ import annotations

from pathlib import Path

from faigate.config import load_config
from faigate.provider_catalog import (
    build_provider_catalog_report,
    build_provider_discovery_view,
    build_provider_metadata_snapshot,
    build_provider_refresh_guidance,
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


def test_provider_discovery_view_supports_link_source_and_offer_track_filters(
    tmp_path: Path, monkeypatch
):
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


def test_provider_catalog_report_can_track_provider_from_external_snapshot(
    tmp_path: Path, monkeypatch
):
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
      "last_reviewed": "2026-03-31"
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


def test_provider_catalog_external_snapshot_can_override_embedded_entry(
    tmp_path: Path, monkeypatch
):
    snapshot = tmp_path / "provider-catalog.json"
    snapshot.write_text(
        """
{
  "schema_version": "fusionaize-provider-catalog/v1",
  "providers": {
    "deepseek-chat": {
      "notes": "External override note",
      "last_reviewed": "2026-03-31"
    }
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("FAIGATE_PROVIDER_METADATA_FILE", str(snapshot))

    entry = get_provider_catalog_entry("deepseek-chat")

    assert entry["notes"] == "External override note"
    assert entry["last_reviewed"] == "2026-03-31"


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
      "last_reviewed": "2026-03-31"
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
