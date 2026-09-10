"""Tests for model identity resolution on the chat completion endpoint.

An unknown model id must be rejected with a ``model_not_found`` error instead
of being silently routed to the fallback chain. A configured provider id must
keep routing unchanged.
"""

from __future__ import annotations

import importlib
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

sys.modules.pop("httpx", None)
import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sys.modules["httpx"] = httpx

sys.modules.pop("faigate.providers", None)
sys.modules.pop("faigate.updates", None)
sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _ProviderStub:
    def __init__(self):
        self.name = "cloud-default"
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {"chat": True}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000}
        self.cache = {}
        self.image = {}
        self.health = types.SimpleNamespace(
            healthy=True,
            last_check=1.0,
            avg_latency_ms=12.0,
            last_error="",
            to_dict=lambda: {
                "name": "cloud-default",
                "healthy": True,
                "consecutive_failures": 0,
                "avg_latency_ms": 12.0,
                "last_error": "",
            },
        )

    async def close(self):
        return None

    async def complete(self, *_args, **_kwargs):
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_faigate": {"latency_ms": 12},
        }


class _MetricsStub:
    def log_request(self, **_kwargs):
        return None


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
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
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
        )
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": _ProviderStub()},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        yield client


def test_unknown_model_id_returns_not_found(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model-xyz",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "model_not_found"
    assert "nonexistent-model-xyz" in body["error"]


def test_configured_provider_routes_unchanged(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "cloud-default",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-faigate-provider"] == "cloud-default"


def test_auto_model_routes_unchanged(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200


def test_padded_model_id_normalizes_like_routing(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "  cloud-default  ",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-faigate-provider"] == "cloud-default"


def test_curated_catalog_entry_is_not_accepted(api_client):
    from faigate.provider_catalog import get_provider_catalog

    catalog = get_provider_catalog()
    curated_id = next(name for name in catalog if name != "cloud-default" and name not in main_module._providers)

    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": curated_id,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "model_not_found"

    assert main_module._is_known_model_identity(curated_id, main_module._config) is False


def test_broken_catalog_does_not_reject_valid_model(api_client, monkeypatch):
    import faigate.provider_catalog as provider_catalog

    def _broken_catalog(*_args, **_kwargs):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(provider_catalog, "get_provider_catalog", _broken_catalog)

    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "cloud-default",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert main_module._is_known_model_identity("cloud-default", main_module._config) is True


def test_identity_check_fails_open_on_internal_error(api_client, monkeypatch):
    def _broken_lookup(*_args, **_kwargs):
        raise RuntimeError("knowledge base unavailable")

    monkeypatch.setattr(main_module._router, "model_requested_is_accepted", _broken_lookup)

    assert main_module._is_known_model_identity("fabricated-id", main_module._config) is True


REAL_CONFIG_PATH = Path("/opt/homebrew/etc/faigate/config.yaml")


def _real_config_provider_names(cfg) -> list[str]:
    return sorted(cfg.providers.keys())


def _real_config_model_requested_triggers(cfg) -> list[str]:
    triggers: list[str] = []

    def _collect(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "model_requested":
                    patterns = value if isinstance(value, list) else [value]
                    triggers.extend(str(pattern) for pattern in patterns)
                else:
                    _collect(value)
        elif isinstance(node, list):
            for item in node:
                _collect(item)

    for rule in cfg.static_rules.get("rules", []):
        _collect(rule.get("match", {}))
    return triggers


@pytest.mark.skipif(not REAL_CONFIG_PATH.is_file(), reason="real faigate config not present")
def test_real_config_model_requested_and_providers_are_accepted(monkeypatch):
    """Every id the real config can route to must pass the identity gate.

    This runs against the real operator configuration, not a synthetic stub, so
    it catches the class of bug where the gate's own list drifts from what the
    routing layer actually resolves.
    """

    cfg = load_config(REAL_CONFIG_PATH)
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )

    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    for provider_name in _real_config_provider_names(cfg):
        assert main_module._is_known_model_identity(provider_name, cfg) is True, (
            f"configured provider '{provider_name}' was rejected"
        )

    for trigger in _real_config_model_requested_triggers(cfg):
        assert main_module._is_known_model_identity(trigger, cfg) is True, (
            f"model_requested trigger '{trigger}' was rejected"
        )

    assert main_module._is_known_model_identity("totally-invented-xyz", cfg) is False


@pytest.mark.skipif(not REAL_CONFIG_PATH.is_file(), reason="real faigate config not present")
def test_real_config_list_and_gate_agree(monkeypatch):
    """Against the real config, /v1/models and the gate accept the same ids.

    The list must not hide an id the gate accepts, and must not advertise one it
    rejects. Reading the candidate universe from the raw config shape keeps this
    check from trusting either side under test.
    """

    cfg = load_config(REAL_CONFIG_PATH)
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    listed = set(main_module._routable_model_entries().keys())

    candidates = set(cfg.providers)
    candidates |= set(cfg.routing_modes.get("modes", {}))
    candidates |= set(cfg.model_shortcuts.get("shortcuts", {}))
    candidates.add("auto")
    candidates.update(_real_config_model_requested_triggers(cfg))

    accepted = {candidate for candidate in candidates if main_module._is_known_model_identity(candidate, cfg)}

    accepted_not_listed = sorted(accepted - listed)
    listed_not_accepted = sorted(listed - accepted)

    assert accepted_not_listed == [], (
        f"the gate accepts these ids but /v1/models does not list them: {accepted_not_listed}"
    )
    assert listed_not_accepted == [], f"/v1/models lists these ids but the gate rejects them: {listed_not_accepted}"


def test_structural_config_model_requested_and_providers_are_accepted(tmp_path, monkeypatch):
    """A config fixture carrying the real structure must accept all its ids.

    Mirrors the real configuration shape: routing rules with ``model_requested``
    triggers plus several provider blocks. A stub provider cannot exercise this.
    """

    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-v4-pro:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "deepseek-v4-pro"
  deepseek-v4-flash:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "deepseek-v4-flash"
  gemini-flash-lite:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gemini-flash-lite"
fallback_chain:
  - deepseek-v4-flash
static_rules:
  enabled: true
  rules:
    - name: heartbeat
      route_to: gemini-flash-lite
      match:
        any:
          - model_requested:
              - heartbeat
              - cheap
              - flash-lite
    - name: explicit-reasoner
      route_to: deepseek-v4-pro
      match:
        model_requested:
          - reasoner
          - r1
          - think
          - deepseek-v4-pro
    - name: explicit-chat
      route_to: deepseek-v4-flash
      match:
        model_requested:
          - chat
          - ds
          - default
          - deepseek-v4-flash
metrics:
  enabled: false
""",
        )
    )
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {name: _ProviderStub() for name in cfg.providers},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)

    expected = [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "gemini-flash-lite",
        "heartbeat",
        "cheap",
        "flash-lite",
        "reasoner",
        "r1",
        "think",
        "chat",
        "ds",
        "default",
    ]
    for model_id in expected:
        assert main_module._is_known_model_identity(model_id, cfg) is True, f"routable id '{model_id}' was rejected"

    assert main_module._is_known_model_identity("totally-invented-xyz", cfg) is False


def test_static_model_requested_match_is_routable_by_name(tmp_path, monkeypatch):
    """A ``model_requested`` static rule proves the id is routable by name."""

    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  gemini-flash-lite:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gemini-flash-lite"
fallback_chain:
  - gemini-flash-lite
static_rules:
  enabled: true
  rules:
    - name: heartbeat
      route_to: gemini-flash-lite
      match:
        model_requested:
          - heartbeat
          - cheap
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    assert router.static_rule_matches_model_requested("heartbeat") is True
    assert router.static_rule_matches_model_requested("totally-invented-xyz") is False
