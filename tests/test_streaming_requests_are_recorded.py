"""A streaming request must leave the same trace in the metrics as a plain one.

Measured on 2026-09-24 against the running 2.9.2: the same endpoint, the same
model and the same client, differing only in the ``stream`` flag, produced one
metrics row for ``stream: false`` and none for ``stream: true``.

``main._execute_chat`` guards the whole metrics block with
``isinstance(result, dict)``. A streaming completion returns an async iterator,
so the block never runs.

Agentic clients stream almost always, which makes non-streaming requests the
exception. The metric therefore misses exactly the load that matters and keeps
the load that does not: three dispatched lanes with 199 model calls between
them left zero rows, while the provider's own console showed 63.82 percent of
the five-hour quota consumed.

That is a gap with a sign, not with noise. Every provider comparison and every
cost statement built on these rows is a selection that does not announce itself
as one.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.modules.pop("faigate.providers", None)
sys.modules.pop("faigate.updates", None)
sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)

CONFIG = """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
providers:
  cloud-default:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "chat-model"
    pricing:
      input: 1.0
      output: 2.0
fallback_chain:
  - cloud-default
metrics:
  enabled: true
  log_requests: true
"""


class _RecordingMetrics:
    """Collects the rows the gateway would have written."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def log_request(self, **kwargs):
        self.rows.append(kwargs)
        return len(self.rows)

    def log_operator_event(self, **_kwargs):
        return None


class _ProviderStub:
    def __init__(self) -> None:
        self.name = "cloud-default"
        self.model = "chat-model"
        self.backend_type = "openai-compat"
        self.contract = "generic"
        self.tier = "default"
        self.capabilities = {"chat": True, "local": False, "cloud": True, "network_zone": "public"}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000, "max_output_tokens": 4096}
        self.cache = {"mode": "none", "read_discount": False}
        self.image = {}
        self.transport = {}
        self.health = types.SimpleNamespace(
            healthy=True,
            last_check=1.0,
            avg_latency_ms=12.0,
            last_error="",
            to_dict=lambda: {"name": "cloud-default", "healthy": True},
        )

    async def close(self):
        return None

    async def complete(self, messages, **kwargs):
        if kwargs.get("stream"):

            async def _iter() -> AsyncIterator[bytes]:
                yield (
                    b'data: {"id":"s","object":"chat.completion.chunk","model":"chat-model",'
                    b'"choices":[{"index":0,"delta":{"role":"assistant","content":"hi"},'
                    b'"finish_reason":null}]}\n\n'
                )
                yield (
                    b'data: {"id":"s","object":"chat.completion.chunk","model":"chat-model",'
                    b'"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
                    b'"usage":{"prompt_tokens":11,"completion_tokens":2,"total_tokens":13}}\n\n'
                )
                yield b"data: [DONE]\n\n"

            return _iter()
        return {
            "id": "chatcmpl-plain",
            "object": "chat.completion",
            "model": "chat-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13},
            "_faigate": {"latency_ms": 12, "provider": self.name},
        }


@pytest.fixture
def client_and_metrics(tmp_path: Path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    cfg = load_config(str(path))
    metrics = _RecordingMetrics()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {"cloud-default": _ProviderStub()}, raising=False)
    monkeypatch.setattr(main_module, "_metrics", metrics, raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    with TestClient(main_module.app) as client:
        yield client, metrics


def _post(client, *, stream: bool):
    body = {"model": "cloud-default", "messages": [{"role": "user", "content": "hi"}], "stream": stream}
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == 200, response.text
    if stream:
        # Drain the body; a stream is only finished once the client has read it.
        assert b"[DONE]" in response.content
    return response


def test_the_plain_path_records_a_row(client_and_metrics):
    """Guard for this module: without it every assertion below could pass empty."""
    client, metrics = client_and_metrics
    _post(client, stream=False)
    assert len(metrics.rows) == 1, "the non-streaming path records nothing — this test cannot measure anything"


def test_a_streaming_request_records_exactly_one_row(client_and_metrics):
    client, metrics = client_and_metrics
    _post(client, stream=True)
    assert len(metrics.rows) == 1, (
        "a streaming request left no metrics row; agentic clients stream almost "
        "always, so this is the load the metric misses"
    )


def test_both_paths_record_the_same_fields(client_and_metrics):
    client, metrics = client_and_metrics
    _post(client, stream=False)
    _post(client, stream=True)
    assert len(metrics.rows) == 2, f"expected one row per request, got {len(metrics.rows)}"

    plain, streamed = metrics.rows
    for field in ("provider", "model", "requested_model", "modality", "layer", "rule_name"):
        assert streamed.get(field) == plain.get(field), (
            f"{field}: streaming row says {streamed.get(field)!r}, plain row says {plain.get(field)!r}"
        )
    assert streamed.get("prompt_tokens") == 11
    assert streamed.get("completion_tokens") == 2
