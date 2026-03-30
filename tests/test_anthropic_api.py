"""Functional tests for the live Anthropic-compatible messages endpoint."""

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
from faigate.providers import ProviderError  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _CapturingProviderStub:
    def __init__(self, name: str = "cloud-default", *, transport: dict[str, object] | None = None):
        self.name = name
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {"chat": True, "local": False, "cloud": True, "network_zone": "public"}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000, "max_output_tokens": 4096}
        self.cache = {"mode": "none", "read_discount": False}
        self.image = {}
        self.transport = dict(transport or {})
        self.calls: list[dict[str, object]] = []
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

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return {
            "id": "chatcmpl-bridge",
            "object": "chat.completion",
            "model": "chat-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "anthropic ok"},
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            "_faigate": {"latency_ms": 12, "provider": self.name},
        }


class _MetricsStub:
    def log_request(self, **_kwargs):
        return None


class _FailingProviderStub(_CapturingProviderStub):
    def __init__(
        self,
        name: str = "cloud-default",
        *,
        status: int = 429,
        detail: str = "rate limited upstream",
        transport: dict[str, object] | None = None,
    ):
        super().__init__(name=name, transport=transport)
        self.status = status
        self.detail = detail

    def classify_runtime_issue(self, *, status: int, detail: str) -> str:
        lowered = detail.lower()
        if status == 429 and "quota" in lowered:
            return "quota-exhausted"
        if status == 429:
            return "rate-limited"
        if status in {401, 403}:
            return "auth-invalid"
        return "degraded"

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        raise ProviderError(self.name, self.status, self.detail)


@pytest.fixture
def anthropic_api_client(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
security:
  max_json_body_bytes: 4096
  max_upload_bytes: 8
  max_header_value_chars: 64
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
anthropic_bridge:
  enabled: true
  model_aliases:
    claude-code-premium: premium
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
        )
    )
    provider = _CapturingProviderStub()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {"cloud-default": provider}, raising=False)
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        yield client, provider


def test_anthropic_messages_returns_bridge_response(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "system": "Use markdown",
            "messages": [{"role": "user", "content": "Summarize this"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert body["content"][0]["type"] == "text"
    assert body["content"][0]["text"] == "anthropic ok"
    assert provider.calls[0]["extra_body"]["metadata"]["source"] == "claude-code"
    assert provider.calls[0]["messages"][0] == {"role": "system", "content": "Use markdown"}
    assert response.headers["x-faigate-bridge-surface"] == "anthropic-messages"
    assert response.headers["x-faigate-bridge-source"] == "claude-code"
    assert response.headers["x-faigate-bridge-model-requested"] == "claude-sonnet"


def test_anthropic_messages_applies_model_aliases(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-code-premium",
            "messages": [
                {
                    "role": "user",
                    "content": "Route this like a premium coding request",
                }
            ],
        },
    )

    assert response.status_code == 200
    metadata = provider.calls[0]["extra_body"]["metadata"]
    assert metadata["requested_model_original"] == "claude-code-premium"
    assert metadata["requested_model_resolved"] == "premium"
    assert response.headers["x-faigate-bridge-model-requested"] == "claude-code-premium"
    assert response.headers["x-faigate-bridge-model-resolved"] == "premium"


def test_anthropic_messages_preserve_version_headers(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        headers={
            "anthropic-client": "claude-desktop",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "tools-2024-04-04",
            "user-agent": "Claude-Code/1.0",
        },
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    bridge_headers = provider.calls[0]["extra_body"]["metadata"]["bridge_headers"]
    assert bridge_headers["anthropic-version"] == "2023-06-01"
    assert bridge_headers["anthropic-beta"] == "tools-2024-04-04"
    assert bridge_headers["user-agent"] == "Claude-Code/1.0"
    assert response.headers["x-faigate-bridge-source"] == "claude-desktop"
    assert response.headers["x-faigate-bridge-anthropic-version"] == "2023-06-01"
    assert response.headers["x-faigate-bridge-anthropic-beta"] == "tools-2024-04-04"


def test_anthropic_messages_forward_tool_use_and_tool_result_blocks(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "messages": [
                {"role": "user", "content": "Look up the design note"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_lookup",
                            "name": "lookup_doc",
                            "input": {"id": "design-note"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_lookup",
                            "content": "Design note loaded",
                        }
                    ],
                },
            ],
        },
    )

    assert response.status_code == 200
    forwarded_messages = provider.calls[0]["messages"]
    assert forwarded_messages[1]["role"] == "assistant"
    assert forwarded_messages[1]["tool_calls"][0]["function"]["name"] == "lookup_doc"
    assert forwarded_messages[2] == {
        "role": "tool",
        "content": "Design note loaded",
        "tool_call_id": "toolu_lookup",
    }


def test_anthropic_messages_rejects_non_text_blocks(anthropic_api_client):
    client, _provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image", "source": {"type": "base64"}}],
                }
            ],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
    assert "text and tool_result blocks" in body["error"]["message"]


def test_anthropic_count_tokens_returns_estimate_with_headers(anthropic_api_client):
    client, _provider = anthropic_api_client

    response = client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "claude-sonnet",
            "system": "Be concise",
            "messages": [{"role": "user", "content": "Count these tokens please"}],
            "tools": [
                {
                    "name": "lookup_doc",
                    "description": "Load one doc",
                    "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["input_tokens"], int)
    assert body["input_tokens"] > 0
    assert response.headers["x-faigate-token-count-exact"] == "false"
    assert response.headers["x-faigate-token-count-method"] == "estimated-char-v1"
    assert response.headers["x-faigate-bridge-surface"] == "anthropic-messages"
    assert response.headers["x-faigate-bridge-model-requested"] == "claude-sonnet"


def test_anthropic_count_tokens_preserve_version_headers(anthropic_api_client):
    client, _provider = anthropic_api_client

    response = client.post(
        "/v1/messages/count_tokens",
        headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "tools-2024-04-04",
        },
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "Count these tokens please"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-faigate-bridge-anthropic-version"] == "2023-06-01"
    assert response.headers["x-faigate-bridge-anthropic-beta"] == "tools-2024-04-04"


def test_anthropic_count_tokens_rejects_invalid_payload(anthropic_api_client):
    client, _provider = anthropic_api_client

    response = client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "claude-sonnet",
            "messages": "not-a-list",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
    assert "messages" in body["error"]["message"]


def test_anthropic_messages_can_be_disabled_by_surface_toggle(tmp_path, monkeypatch):
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
api_surfaces:
  anthropic_messages: false
anthropic_bridge:
  enabled: true
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
        {"cloud-default": _CapturingProviderStub()},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "not_found_error"


def test_anthropic_messages_maps_rate_limit_provider_errors(tmp_path, monkeypatch):
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
anthropic_bridge:
  enabled: true
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
        {"cloud-default": _FailingProviderStub()},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 429
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "rate_limit_error"


def test_anthropic_messages_skip_shared_quota_group_after_quota_failure(tmp_path, monkeypatch):
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
    transport:
      quota_group: anthropic-main
  kilo-mirror:
    backend: openai-compat
    base_url: "https://api.kilo.example/v1"
    api_key: "secret"
    model: "claude-sonnet"
    transport:
      quota_group: anthropic-main
  local-worker:
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
fallback_chain:
  - kilo-mirror
  - local-worker
anthropic_bridge:
  enabled: true
  model_aliases:
    claude-sonnet: cloud-default
metrics:
  enabled: false
""",
        )
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    primary = _FailingProviderStub(
        "cloud-default",
        detail="insufficient_quota on upstream account",
        transport={"quota_group": "anthropic-main"},
    )
    mirror = _CapturingProviderStub("kilo-mirror", transport={"quota_group": "anthropic-main"})
    local = _CapturingProviderStub("local-worker")

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {
            "cloud-default": primary,
            "kilo-mirror": mirror,
            "local-worker": local,
        },
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 200
    assert len(primary.calls) == 1
    assert mirror.calls == []
    assert len(local.calls) == 1
    assert response.headers["x-faigate-provider"] == "local-worker"
