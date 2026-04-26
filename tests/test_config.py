"""Tests for config safe DB path resolution and env expansion."""

from pathlib import Path

import pytest
import yaml

from faigate.config import ConfigError, _safe_db_path, load_config

ROOT = Path(__file__).parent.parent
SHIPPED_CONFIG = ROOT / "config.yaml"


def _load_shipped_config_raw() -> dict:
    with SHIPPED_CONFIG.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _unknown_provider_refs(select: dict, providers: set[str]) -> set[str]:
    unknown = set()
    for field_name in ("allow_providers", "deny_providers", "prefer_providers"):
        for value in select.get(field_name, []) or []:
            if value not in providers:
                unknown.add(value)
    return unknown


# ── _safe_db_path unit tests ──────────────────────────────────────────────────


def test_safe_db_path_env_var_wins(monkeypatch):
    """FAIGATE_DB_PATH env var always takes priority."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/custom/path/faigate.db")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert _safe_db_path() == "/custom/path/faigate.db"


def test_safe_db_path_env_var_over_configured(monkeypatch):
    """Env var wins even when a configured path is provided."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/env/faigate.db")
    assert _safe_db_path("/configured/faigate.db") == "/env/faigate.db"


def test_safe_db_path_rejects_dot_slash(monkeypatch):
    """./faigate.db must never be returned — it would pollute the repo."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("./faigate.db")
    assert not result.startswith("./"), f"unsafe path returned: {result}"
    assert "faigate.db" in result


def test_safe_db_path_rejects_bare_name(monkeypatch):
    """Bare 'faigate.db' (relative) must also be rejected."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path("faigate.db")
    assert result != "faigate.db"
    assert result.startswith("/")


def test_safe_db_path_accepts_absolute_configured(monkeypatch):
    """An absolute path in config.yaml is used as-is."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    expected = "/var/lib/faigate/faigate.db"
    assert _safe_db_path(expected) == expected


def test_safe_db_path_xdg(monkeypatch):
    """XDG_DATA_HOME is used when no env/configured path is set."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
    result = _safe_db_path()
    assert result == "/xdg/data/faigate/faigate.db"


def test_safe_db_path_home_fallback(monkeypatch):
    """Falls back to ~/.local/share/faigate/faigate.db when nothing else is set."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    result = _safe_db_path()
    assert result.endswith("/.local/share/faigate/faigate.db")
    assert result.startswith("/")


# ── Config.metrics integration ────────────────────────────────────────────────


def test_metrics_db_path_uses_env_override(monkeypatch):
    """FAIGATE_DB_PATH env var is reflected in cfg.metrics['db_path']."""
    monkeypatch.setenv("FAIGATE_DB_PATH", "/var/lib/faigate/test.db")
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.metrics["db_path"] == "/var/lib/faigate/test.db"


def test_load_config_uses_explicit_config_env_file(tmp_path, monkeypatch):
    path = tmp_path / "custom-config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 9001
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    monkeypatch.setenv("FAIGATE_CONFIG_FILE", str(path))
    cfg = load_config()
    assert cfg.server["port"] == 9001


def test_metrics_db_path_never_dot_slash(monkeypatch):
    """cfg.metrics['db_path'] must never start with './' regardless of config.yaml content."""
    monkeypatch.delenv("FAIGATE_DB_PATH", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    cfg = load_config(SHIPPED_CONFIG)
    db_path = cfg.metrics["db_path"]
    assert not db_path.startswith("./"), f"unsafe db_path in metrics: {db_path}"
    assert db_path.startswith("/"), f"expected absolute path, got: {db_path}"


def test_auto_update_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.auto_update["enabled"] is False
    assert cfg.auto_update["allow_major"] is False
    assert cfg.auto_update["rollout_ring"] == "early"
    assert cfg.auto_update["require_healthy_providers"] is True
    assert cfg.auto_update["max_unhealthy_providers"] == 0
    assert cfg.auto_update["min_release_age_hours"] == 0
    assert cfg.auto_update["provider_scope"] == {
        "allow_providers": [],
        "deny_providers": ["openrouter-fallback"],
    }
    assert cfg.auto_update["verification"] == {
        "enabled": False,
        "command": "faigate-health",
        "timeout_seconds": 30,
        "rollback_command": "",
    }
    assert cfg.auto_update["maintenance_window"]["enabled"] is False
    assert cfg.auto_update["maintenance_window"]["timezone"] == "UTC"
    assert cfg.auto_update["maintenance_window"]["days"] == ["sat", "sun"]
    assert cfg.auto_update["maintenance_window"]["start_hour"] == 2
    assert cfg.auto_update["maintenance_window"]["end_hour"] == 5
    assert cfg.auto_update["apply_command"] == "faigate-update"


def test_update_check_defaults_include_stable_release_channel():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.update_check["release_channel"] == "stable"


def test_routing_modes_and_model_shortcuts_are_exposed(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_modes:
  enabled: true
  default: premium
  modes:
    premium:
      aliases: ["quality"]
      description: "Best quality"
      select:
        prefer_providers: ["cloud-default"]
model_shortcuts:
  enabled: true
  shortcuts:
    fast:
      target: cloud-default
      aliases: ["chat"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    app:
      routing_mode: premium
  rules: []
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.routing_modes["enabled"] is True
    assert cfg.routing_modes["default"] == "premium"
    assert cfg.routing_modes["modes"]["premium"]["aliases"] == ["quality"]
    assert cfg.model_shortcuts["shortcuts"]["fast"]["target"] == "cloud-default"
    assert cfg.client_profiles["profiles"]["app"]["routing_mode"] == "premium"


def test_provider_lane_metadata_is_normalized(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
    lane:
      family: custom
      name: workhorse
      canonical_model: custom/chat-model
      route_type: direct
      cluster: balanced-workhorse
      benchmark_cluster: internal-eval
      quality_tier: mid
      reasoning_strength: mid
      context_strength: mid
      tool_strength: low
      same_model_group: custom/chat-model
      degrade_to: [custom/backup-model]
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.providers["cloud-default"]["lane"]["canonical_model"] == "custom/chat-model"
    assert cfg.providers["cloud-default"]["lane"]["route_type"] == "direct"
    assert cfg.providers["cloud-default"]["lane"]["degrade_to"] == ["custom/backup-model"]


def test_provider_transport_metadata_is_normalized(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
    transport:
      chat_path: /responses/chat
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.providers["cloud-default"]["transport"]["auth_mode"] == "bearer"
    assert cfg.providers["cloud-default"]["transport"]["profile"] == "openai-compatible"
    assert cfg.providers["cloud-default"]["transport"]["compatibility"] == "native"
    assert cfg.providers["cloud-default"]["transport"]["probe_payload_kind"] == "openai-chat-minimal"
    assert cfg.providers["cloud-default"]["transport"]["probe_payload_text"] == "ping"
    assert cfg.providers["cloud-default"]["transport"]["probe_payload_max_tokens"] == 1
    assert cfg.providers["cloud-default"]["transport"]["billing_mode"] == ""
    assert cfg.providers["cloud-default"]["transport"]["models_path"] == "/models"
    assert cfg.providers["cloud-default"]["transport"]["chat_path"] == "/responses/chat"
    assert cfg.providers["cloud-default"]["transport"]["quota_group"] == ""
    assert cfg.providers["cloud-default"]["transport"]["quota_isolated"] is False


def test_provider_transport_quota_metadata_is_normalized(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
    transport:
      billing_mode: byok
      quota_group: anthropic-main
      quota_isolated: true
fallback_chain: []
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.providers["cloud-default"]["transport"]["billing_mode"] == "byok"
    assert cfg.providers["cloud-default"]["transport"]["quota_group"] == "anthropic-main"
    assert cfg.providers["cloud-default"]["transport"]["quota_isolated"] is True


def test_client_profile_rejects_unknown_routing_mode(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
routing_modes:
  enabled: true
  default: auto
  modes:
    premium:
      select:
        prefer_providers: ["cloud-default"]
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    app:
      routing_mode: missing
  rules: []
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="unknown routing_mode 'missing'"):
        load_config(path)


def test_security_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.security == {
        "response_headers": True,
        "cache_control": "no-store",
        "max_json_body_bytes": 1048576,
        "max_upload_bytes": 10485760,
        "max_header_value_chars": 160,
    }


def test_provider_catalog_check_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.provider_catalog_check == {
        "enabled": True,
        "warn_on_untracked": True,
        "warn_on_model_drift": True,
        "warn_on_unofficial_sources": True,
        "warn_on_volatile_offers": True,
        "max_catalog_age_days": 30,
    }


def test_provider_source_refresh_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.provider_source_refresh == {
        "enabled": True,
        "on_startup": True,
        "timeout_seconds": 10.0,
        "interval_seconds": 21600,
        "providers": ["blackbox", "kilo", "openai"],
    }


def test_metadata_sync_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.metadata == {
        "enabled": True,
        "public_catalog_url": "",
        "private_catalog_url": "",
        "refresh_interval_hours": 24.0,
        "timeout_seconds": 10.0,
        "on_startup": False,
    }


def test_metadata_sync_can_be_disabled_with_zero_interval(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
metadata:
  refresh_interval_hours: 0
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.metadata["refresh_interval_hours"] == 0.0


def test_provider_source_refresh_rejects_invalid_interval(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
provider_source_refresh:
  interval_seconds: 0
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="provider_source_refresh.interval_seconds"):
        load_config(path)


def test_anthropic_bridge_defaults_are_exposed():
    cfg = load_config(SHIPPED_CONFIG)
    assert cfg.api_surfaces == {
        "openai_compatible": True,
        "anthropic_messages": True,
    }
    assert cfg.anthropic_bridge == {
        "enabled": True,
        "route_prefix": "/v1",
        "allow_claude_code_hints": True,
        "model_aliases": {
            "claude-code": "auto",
            "claude-code-fast": "eco",
            "claude-code-premium": "premium",
            "claude-sonnet-4-6": "auto",
            "claude-sonnet-4-6-20251001": "auto",
            "claude-sonnet-4-6[1m]": "auto",
            "claude-opus-4-6": "premium",
            "claude-opus-4-6-20251001": "premium",
            "claude-opus-4-6[1m]": "premium",
            "claude-haiku-4-5": "eco",
            "claude-haiku-4-5-20251001": "eco",
            # Claude Desktop model aliases
            "claude-3-5-sonnet-20241022": "auto",
            "claude-3-5-sonnet": "auto",
            "claude-3-opus-20240229": "premium",
            "claude-3-opus": "premium",
            "claude-3-haiku-20240307": "eco",
            "claude-3-haiku": "eco",
        },
    }


def test_anthropic_bridge_rejects_invalid_route_prefix(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
anthropic_bridge:
  enabled: true
  route_prefix: v1
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="anthropic_bridge.route_prefix"):
        load_config(path)


def test_api_surfaces_follow_bridge_enablement_when_not_set_explicitly(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
anthropic_bridge:
  enabled: true
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.api_surfaces == {
        "openai_compatible": True,
        "anthropic_messages": True,
    }


def test_api_surfaces_rejects_invalid_anthropic_messages_value(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
api_surfaces:
  anthropic_messages: "yes"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="api_surfaces.anthropic_messages"):
        load_config(path)


def test_security_rejects_invalid_limit_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
security:
  max_json_body_bytes: 0
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="security.max_json_body_bytes"):
        load_config(path)


def test_provider_rejects_public_http_base_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cloud-default:
    backend: openai-compat
    base_url: "http://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    with pytest.raises(ConfigError, match="must use https"):
        load_config(path)


def test_provider_allows_local_http_base_url(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  local-worker:
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
fallback_chain: []
metrics:
  enabled: false
"""
    )

    cfg = load_config(path)
    assert cfg.providers["local-worker"]["base_url"] == "http://127.0.0.1:11434/v1"


def test_shipped_config_loads_as_release_candidate():
    cfg = load_config(SHIPPED_CONFIG)
    assert "premium" in cfg.routing_modes["modes"]
    assert "coding-auto" in cfg.routing_modes["modes"]
    assert "claude-code" in cfg.anthropic_bridge["model_aliases"]


def test_shipped_config_mapping_references_are_consistent():
    raw = _load_shipped_config_raw()
    providers = set((raw.get("providers") or {}).keys())
    routing_modes = raw.get("routing_modes") or {}
    mode_names = set((routing_modes.get("modes") or {}).keys())
    shortcuts = (raw.get("model_shortcuts") or {}).get("shortcuts") or {}
    shortcut_names = set(shortcuts.keys())

    assert not set(raw.get("fallback_chain") or []) - providers

    for name, mode in (routing_modes.get("modes") or {}).items():
        assert not _unknown_provider_refs((mode or {}).get("select") or {}, providers), name

    client_profiles = raw.get("client_profiles") or {}
    profiles = client_profiles.get("profiles") or {}
    for name, profile in profiles.items():
        assert not _unknown_provider_refs(profile or {}, providers), name
        routing_mode = str((profile or {}).get("routing_mode", "") or "").strip()
        assert not routing_mode or routing_mode in mode_names, name

    rules = client_profiles.get("rules") or []
    profile_names = set(profiles.keys()) | {str(client_profiles.get("default") or "").strip()}
    for idx, rule in enumerate(rules, start=1):
        assert str((rule or {}).get("profile", "") or "").strip() in profile_names, idx

    for idx, rule in enumerate(((raw.get("routing_policies") or {}).get("rules") or []), start=1):
        assert not _unknown_provider_refs((rule or {}).get("select") or {}, providers), idx

    provider_scope = (raw.get("auto_update") or {}).get("provider_scope") or {}
    assert not _unknown_provider_refs(provider_scope, providers)

    for name, shortcut in shortcuts.items():
        assert str((shortcut or {}).get("target", "") or "").strip() in providers, name

    valid_alias_targets = providers | mode_names | shortcut_names
    for alias, target in ((raw.get("anthropic_bridge") or {}).get("model_aliases") or {}).items():
        assert str(target or "").strip() in valid_alias_targets, alias


def test_legacy_provider_reference_aliases_load_for_upgrade_configs(tmp_path):
    path = tmp_path / "legacy-upgrade.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  gemini-pro-high:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
fallback_chain:
  - gemini-pro
routing_modes:
  enabled: true
  default: premium
  modes:
    premium:
      select:
        prefer_providers: ["gemini-pro"]
model_shortcuts:
  enabled: true
  shortcuts:
    default-pro:
      target: gemini-pro
anthropic_bridge:
  enabled: true
  model_aliases:
    claude-opus-4-6: gemini-pro
auto_update:
  provider_scope:
    allow_providers: ["gemini-pro"]
metrics:
  enabled: false
""",
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.fallback_chain == ["gemini-pro-high"]
    assert cfg.routing_modes["modes"]["premium"]["select"]["prefer_providers"] == ["gemini-pro-high"]
    assert cfg.model_shortcuts["shortcuts"]["default-pro"]["target"] == "gemini-pro-high"
    assert cfg.anthropic_bridge["model_aliases"]["claude-opus-4-6"] == "gemini-pro-high"
    assert cfg.auto_update["provider_scope"]["allow_providers"] == ["gemini-pro-high"]
