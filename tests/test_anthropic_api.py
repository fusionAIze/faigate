"""Functional tests for the live Anthropic-compatible messages endpoint."""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import AsyncIterator
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
from faigate.bridges.anthropic import openai_sse_to_anthropic  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.providers import ProviderError  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


class _CapturingProviderStub:
    def __init__(
        self,
        name: str = "cloud-default",
        *,
        transport: dict[str, object] | None = None,
    ):
        self.name = name
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {
            "chat": True,
            "local": False,
            "cloud": True,
            "network_zone": "public",
        }
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


class _StreamingProviderStub(_CapturingProviderStub):
    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})

        async def _iter() -> AsyncIterator[bytes]:
            yield (
                b'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk",'
                b'"model":"chat-model","choices":[{"index":0,"delta":{"role":"assistant",'
                b'"content":"Hello"},"finish_reason":null}]}\n'
            )
            yield b"\n"
            yield (
                b'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk",'
                b'"model":"chat-model","choices":[{"index":0,"delta":{"content":" world"},'
                b'"finish_reason":"stop"}],"usage":{"prompt_tokens":11,'
                b'"completion_tokens":2,"total_tokens":13}}\n'
            )
            yield b"\n"
            yield b"data: [DONE]\n"
            yield b"\n"

        return _iter()


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
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": provider},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(
        main_module.app.router,
        "lifespan_context",
        _noop_lifespan,
        raising=False,
    )

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
    assert provider.calls[0]["messages"][0] == {
        "role": "system",
        "content": "Use markdown",
    }
    assert response.headers["x-faigate-bridge-surface"] == "anthropic-messages"
    assert response.headers["x-faigate-bridge-source"] == "claude-code"
    assert response.headers["x-faigate-bridge-model-requested"] == "claude-sonnet"


def test_anthropic_messages_accept_system_text_blocks(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "system": [
                {"type": "text", "text": "Use markdown"},
                {"type": "text", "text": "Prefer concise patches"},
            ],
            "messages": [{"role": "user", "content": "Summarize this"}],
        },
    )

    assert response.status_code == 200
    assert provider.calls[0]["messages"][0] == {
        "role": "system",
        "content": "Use markdown",
    }
    assert provider.calls[0]["messages"][1] == {
        "role": "system",
        "content": "Prefer concise patches",
    }


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


def test_anthropic_messages_applies_builtin_claude_code_model_aliases(
    anthropic_api_client,
):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6[1m]",
            "messages": [
                {
                    "role": "user",
                    "content": "Use the Claude Code model name directly",
                }
            ],
        },
    )

    assert response.status_code == 200
    metadata = provider.calls[0]["extra_body"]["metadata"]
    assert metadata["requested_model_original"] == "claude-sonnet-4-6[1m]"
    assert metadata["requested_model_resolved"] == "auto"
    assert response.headers["x-faigate-bridge-model-requested"] == "claude-sonnet-4-6-1m"
    assert response.headers["x-faigate-bridge-model-resolved"] == "auto"


def test_anthropic_messages_can_redirect_claude_code_model_ids_to_gateway_routes(
    anthropic_api_client,
):
    client, provider = anthropic_api_client
    main_module._config.anthropic_bridge["model_aliases"]["claude-sonnet-4-6[1m]"] = "kilo-sonnet"

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6[1m]",
            "messages": [
                {
                    "role": "user",
                    "content": "Prefer the gateway-managed sonnet lane",
                }
            ],
        },
    )

    assert response.status_code == 200
    metadata = provider.calls[0]["extra_body"]["metadata"]
    assert metadata["requested_model_original"] == "claude-sonnet-4-6[1m]"
    assert metadata["requested_model_resolved"] == "kilo-sonnet"
    assert response.headers["x-faigate-bridge-model-resolved"] == "kilo-sonnet"


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


def test_anthropic_messages_forward_tool_use_and_tool_result_blocks(
    anthropic_api_client,
):
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


def test_anthropic_messages_tolerate_tool_result_without_id(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "content": "Detached tool result text",
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    forwarded_messages = provider.calls[0]["messages"]
    assert forwarded_messages == [
        {
            "role": "user",
            "content": "Detached tool result text",
        }
    ]


def test_anthropic_messages_keep_tool_result_adjacent_before_user_text(anthropic_api_client):
    client, provider = anthropic_api_client

    response = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "messages": [
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
                        {"type": "text", "text": "Use the most relevant snippet"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_lookup",
                            "content": "Design note loaded",
                        },
                    ],
                },
            ],
        },
    )

    assert response.status_code == 200
    forwarded_messages = provider.calls[0]["messages"]
    assert forwarded_messages == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "toolu_lookup",
                    "type": "function",
                    "function": {
                        "name": "lookup_doc",
                        "arguments": '{"id":"design-note"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "Design note loaded",
            "tool_call_id": "toolu_lookup",
        },
        {
            "role": "user",
            "content": "Use the most relevant snippet",
        },
    ]


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


def test_anthropic_messages_support_streaming(tmp_path, monkeypatch):
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

    provider = _StreamingProviderStub()
    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": provider},
        raising=False,
    )
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(
        main_module.app.router,
        "lifespan_context",
        _noop_lifespan,
        raising=False,
    )

    with TestClient(main_module.app) as client:
        with client.stream(
            "POST",
            "/v1/messages",
            json={
                "model": "claude-sonnet",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        ) as response:
            body = b"".join(response.iter_bytes()).decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-faigate-bridge-surface"] == "anthropic-messages"
    assert "event: message_start" in body
    assert "event: content_block_start" in body
    assert '"type":"text_delta","text":"Hello"' in body
    assert '"type":"text_delta","text":" world"' in body
    assert '"stop_reason":"end_turn"' in body
    assert "event: message_stop" in body
    assert provider.calls[0]["stream"] is True


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
                    "input_schema": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
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
    monkeypatch.setattr(
        main_module.app.router,
        "lifespan_context",
        _noop_lifespan,
        raising=False,
    )

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


def test_anthropic_messages_skip_shared_quota_group_after_quota_failure(
    tmp_path,
    monkeypatch,
):
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
    mirror = _CapturingProviderStub(
        "kilo-mirror",
        transport={"quota_group": "anthropic-main"},
    )
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
    monkeypatch.setattr(
        main_module.app.router,
        "lifespan_context",
        _noop_lifespan,
        raising=False,
    )

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


@pytest.mark.asyncio
async def test_openai_sse_to_anthropic_maps_tool_call_deltas():
    async def _iter() -> AsyncIterator[bytes]:
        yield (
            b'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk",'
            b'"model":"chat-model","choices":[{"index":0,"delta":{"tool_calls":[{'
            b'"index":0,"id":"call_1","type":"function","function":{"name":"lookup_doc",'
            b'"arguments":"{\\"id\\":"}}]},"finish_reason":null}]}\n'
        )
        yield b"\n"
        yield (
            b'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk",'
            b'"model":"chat-model","choices":[{"index":0,"delta":{"tool_calls":[{'
            b'"index":0,"function":{"arguments":"\\"design-note\\"}"}}]},'
            b'"finish_reason":"tool_calls"}]}\n'
        )
        yield b"\n"
        yield b"data: [DONE]\n"
        yield b"\n"

    chunks: list[str] = []
    async for chunk in openai_sse_to_anthropic(
        _iter(),
        requested_model="claude-code",
        resolved_model="premium",
    ):
        chunks.append(chunk.decode("utf-8"))

    body = "".join(chunks)
    assert "event: content_block_start" in body
    assert '"type":"tool_use","id":"call_1","name":"lookup_doc","input":{}' in body
    assert '"type":"input_json_delta","partial_json":"{\\"id\\":' in body
    assert '"type":"input_json_delta","partial_json":"\\"design-note\\"}"' in body
    assert '"stop_reason":"tool_use"' in body


@pytest.mark.asyncio
async def test_openai_sse_to_anthropic_closes_open_text_block_before_error():
    async def _iter() -> AsyncIterator[bytes]:
        yield (
            b'data: {"id":"chatcmpl-stream","object":"chat.completion.chunk",'
            b'"model":"chat-model","choices":[{"index":0,"delta":{"role":"assistant",'
            b'"content":"Hello"},"finish_reason":null}]}\n'
        )
        yield b"\n"
        yield (
            b'data: {"error":{"type":"api_error","message":"upstream broke"}}\n'
        )
        yield b"\n"

    chunks: list[str] = []
    async for chunk in openai_sse_to_anthropic(
        _iter(),
        requested_model="claude-code",
        resolved_model="premium",
    ):
        chunks.append(chunk.decode("utf-8"))

    body = "".join(chunks)
    assert "event: content_block_start" in body
    assert '"type":"text_delta","text":"Hello"' in body
    assert 'event: content_block_stop' in body
    assert 'event: error' in body
    assert body.index('event: content_block_stop') < body.index('event: error')
    assert '"message":"upstream broke"' in body


@pytest.mark.asyncio
async def test_safe_openai_sse_stream_emits_error_frame_and_done():
    async def _iter() -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        raise ProviderError("kilo-sonnet", 429, "rate limited mid-stream")

    chunks: list[bytes] = []
    async for chunk in main_module._safe_openai_sse_stream(
        _iter(),
        provider_name="kilo-sonnet",
        trace_id="trace-stream-1",
    ):
        chunks.append(chunk)

    body = b"".join(chunks).decode("utf-8")
    assert 'data: {"choices":[{"delta":{"content":"Hello"}}]}' in body
    assert '"message":"rate limited mid-stream"' in body
    assert '"type":"rate-limited"' in body
    assert '"provider":"kilo-sonnet"' in body
    assert '"trace_id":"trace-stream-1"' in body
    assert body.rstrip().endswith("data: [DONE]")
