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
