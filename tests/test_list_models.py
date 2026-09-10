"""Tests for GET /v1/models: it lists every routable model id, and only those."""

from pathlib import Path

import pytest

import faigate.main as main_module
from faigate.config import load_config
from faigate.main import list_models

_CONFIG = """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-v4-flash:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
    tier: default
  deepseek-v4-pro:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "deepseek-reasoner"
    tier: reasoning
  gemini-flash:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gemini-flash"
    tier: default
routing_modes:
  enabled: true
  default: auto
  modes:
    auto:
      description: "Balanced (default)"
      select:
        prefer_tiers: ["default", "reasoning"]
    eco:
      aliases: ["cheap-mode"]
      description: "Cheapest possible"
      select:
        prefer_providers: ["gemini-flash"]
        prefer_tiers: ["default"]
model_shortcuts:
  enabled: __SHORTCUTS_ENABLED__
  shortcuts:
    sonnet:
      target: deepseek-v4-pro
      aliases: ["claude-sonnet"]
    haiku:
      target: deepseek-v4-flash
      aliases: ["claude-haiku"]
static_rules:
  enabled: true
  rules:
    - name: heartbeat
      route_to: gemini-flash
      match:
        any:
          - model_requested: ["heartbeat", "flash-lite"]
    - name: explicit-reasoner
      route_to: deepseek-v4-pro
      match:
        model_requested: ["reasoner", "r1", "think"]
    - name: explicit-chat
      route_to: deepseek-v4-flash
      match:
        model_requested: ["chat", "ds", "default"]
"""

_TRIGGERS = {
    "heartbeat",
    "flash-lite",
    "reasoner",
    "r1",
    "think",
    "chat",
    "ds",
    "default",
}


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _ProviderStub:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        backend_type: str = "openai-compat",
        contract: str = "generic",
        tier: str = "default",
        capabilities: dict | None = None,
    ):
        self.name = name
        self.model = model
        self.backend_type = backend_type
        self.contract = contract
        self.tier = tier
        self.capabilities = capabilities or {}
        self.context_window = 0
        self.limits = {}
        self.cache = {"mode": "none", "read_discount": False}


def _install_config(monkeypatch, tmp_path: Path, *, shortcuts_enabled: bool = False):
    body = _CONFIG.replace("__SHORTCUTS_ENABLED__", "true" if shortcuts_enabled else "false")
    cfg = load_config(_write_config(tmp_path, body))
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            name: _ProviderStub(
                name=name,
                model=str(spec.get("model", name)),
                tier=str(spec.get("tier", "default")),
            )
            for name, spec in cfg.providers.items()
        },
        raising=False,
    )
    return cfg


@pytest.fixture
def models_config(tmp_path, monkeypatch):
    return _install_config(monkeypatch, tmp_path, shortcuts_enabled=False)


@pytest.fixture
def models_config_with_shortcuts(tmp_path, monkeypatch):
    return _install_config(monkeypatch, tmp_path, shortcuts_enabled=True)


async def _model_ids() -> list[str]:
    payload = await list_models()
    return [row["id"] for row in payload["data"]]


@pytest.mark.asyncio
async def test_model_ids_are_unique(models_config):
    """A model id is claimed by exactly one source; the list has no duplicates."""
    ids = await _model_ids()
    duplicates = sorted({model_id for model_id in ids if ids.count(model_id) > 1})

    assert duplicates == [], f"/v1/models listed duplicate ids: {duplicates}"
    assert ids.count("auto") == 1


@pytest.mark.asyncio
async def test_model_requested_triggers_are_listed(models_config):
    """Every enabled static-rule model_requested trigger is routable and listed."""
    ids = set(await _model_ids())
    missing = sorted(_TRIGGERS - ids)

    assert missing == [], f"static-rule model_requested triggers missing from /v1/models: {missing}"


@pytest.mark.asyncio
async def test_provider_ids_colliding_with_triggers_appear_once(models_config):
    """A trigger that names a provider is satisfied by the provider entry."""
    ids = await _model_ids()

    assert ids.count("deepseek-v4-flash") == 1
    assert ids.count("deepseek-v4-pro") == 1


@pytest.mark.asyncio
async def test_disabled_shortcuts_are_not_listed(models_config):
    """Regression guard: a disabled shortcut is not routable and must stay out.

    This test already passes on the base commit; it guards the line rather than
    proving the fix.
    """
    ids = set(await _model_ids())

    assert "sonnet" not in ids
    assert "haiku" not in ids
    assert "claude-sonnet" not in ids


@pytest.mark.asyncio
async def test_enabled_shortcuts_are_listed(models_config_with_shortcuts):
    """The existing enabled branch keeps working: enabled shortcuts are listed."""
    ids = set(await _model_ids())

    assert {"sonnet", "haiku"} <= ids


@pytest.mark.asyncio
async def test_list_models_uses_the_shared_routable_registry(models_config):
    """The endpoint serializes the same registry that identity checks query."""
    registry = getattr(main_module, "_routable_model_entries", None)

    assert registry is not None, "list_models must build on the shared routable-model registry"
    payload = await list_models()
    assert payload["data"] == list(registry().values())


@pytest.mark.asyncio
async def test_routable_ids_resolve_mode_and_shortcut_aliases(models_config_with_shortcuts):
    """Aliases are routable identifiers even though they are not separate entries."""
    routable = main_module._routable_model_ids()

    assert "cheap-mode" in routable
    assert "claude-sonnet" in routable
