"""Tests backing the conformance matrix (docs/CONFORMANCE-MATRIX.md).

Every row in the matrix cites a test name. ``test_matrix_citations_resolve``
fails if any cited name does not resolve to a real test function in ``tests/``,
so a matrix claim cannot outlive the test that backs it. Rows without a backing
test are marked ``untested`` in the matrix and are never reported as supported.

Evidence kinds follow the catalog convention:
    derivable, not_applicable, runtime_dependent, unlisted

Measurement basis: fusionAIze Gate v2.9.3 (2026-09-24), hermetic pytest.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
import types
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


SHIPPED_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"
MATRIX_PATH = Path(__file__).resolve().parent.parent / "docs" / "CONFORMANCE-MATRIX.md"
TESTS_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _ProviderStub:
    def __init__(self):
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
        self.calls = []
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


class _StreamingProviderStub(_ProviderStub):
    """Yield OpenAI SSE byte chunks when ``stream=True`` is requested."""

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if not kwargs.get("stream"):
            return await super().complete(messages, **kwargs)

        async def _gen():
            first = {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}],
            }
            last = {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(first)}\n".encode()
            yield b"\n"
            yield f"data: {json.dumps(last)}\n".encode()
            yield b"\n"
            yield b"data: [DONE]\n"
            yield b"\n"

        return _gen()


class _FailingProviderStub(_ProviderStub):
    async def complete(self, *_args, **_kwargs):
        raise main_module.ProviderError("cloud-default", 502, "upstream error")


class _ImageProviderStub(_ProviderStub):
    def __init__(self):
        super().__init__()
        self.name = "image-provider"
        self.capabilities = {
            **self.capabilities,
            "image_generation": True,
            "image_editing": True,
        }
        self.image = {"max_outputs": 4, "max_side_px": 2048, "supported_sizes": ["1024x1024"]}

    async def generate_image(self, *_args, **_kwargs):
        return {
            "id": "img-123",
            "object": "image",
            "data": [{"url": "https://example.com/img.png"}],
        }

    async def edit_image(self, *_args, **_kwargs):
        return {
            "id": "img-456",
            "object": "image",
            "data": [{"url": "https://example.com/edited.png"}],
        }


class _MetricsStub:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


@pytest.fixture
def minimal_config(tmp_path):
    """Return a config path with one cloud-default provider."""
    return _write_config(
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


@pytest.fixture
def bridge_config(tmp_path):
    """Config with anthropic_bridge.enabled: true (surface follows by default)."""
    return _write_config(
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


@pytest.fixture
def image_config(tmp_path):
    """Config with an image-capable provider."""
    return _write_config(
        tmp_path,
        """
server:
  host: "127.0.0.1"
  port: 8090
security:
  max_upload_bytes: 20971520
providers:
  image-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gpt-image-1"
    capabilities:
      image_generation: true
      image_editing: true
fallback_chain:
  - image-provider
metrics:
  enabled: false
""",
    )


@pytest.fixture
def api_client(minimal_config, monkeypatch):
    """TestClient with one stub provider and no bridge."""
    cfg = load_config(minimal_config)
    return _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)


@pytest.fixture
def streaming_api_client(minimal_config, monkeypatch):
    """TestClient with a provider that can emit streaming chunks."""
    cfg = load_config(minimal_config)
    return _build_client(cfg, {"cloud-default": _StreamingProviderStub()}, monkeypatch)


@pytest.fixture
def bridge_api_client(bridge_config, monkeypatch):
    """TestClient with anthropic bridge enabled."""
    cfg = load_config(bridge_config)
    return _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)


@pytest.fixture
def streaming_bridge_api_client(bridge_config, monkeypatch):
    """Anthropic bridge client whose provider emits streaming chunks."""
    cfg = load_config(bridge_config)
    return _build_client(cfg, {"cloud-default": _StreamingProviderStub()}, monkeypatch)


@pytest.fixture
def image_api_client(image_config, monkeypatch):
    """TestClient with an image-capable provider."""
    cfg = load_config(image_config)
    return _build_client(cfg, {"image-provider": _ImageProviderStub()}, monkeypatch)


def _build_client(cfg, providers, monkeypatch):
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", providers, raising=False)
    monkeypatch.setattr(main_module, "_metrics", _MetricsStub(), raising=False)
    monkeypatch.setattr(main_module.app.router, "lifespan_context", _noop_lifespan, raising=False)

    return TestClient(main_module.app)


# ===================================================================
# Kriterium 4: the matrix is mechanically bound to its backing tests
# ===================================================================


def test_matrix_exists():
    """The conformance matrix must exist.

    RED PROOF: fails on the base branch, where the file does not exist.
    """
    assert MATRIX_PATH.exists(), "docs/CONFORMANCE-MATRIX.md is required"


def test_matrix_citations_resolve():
    """Every test name cited in the matrix resolves to a real test function.

    A matrix that cites tests which do not exist reports something other than
    the fact. This is the mechanical guard for criterion 4.

    Guardrail against itself: an empty set of citations fails, so deleting the
    citations cannot make this check pass vacuously.
    """
    assert MATRIX_PATH.exists(), "docs/CONFORMANCE-MATRIX.md is required"
    cited = set(re.findall(r"`(test_[a-z0-9_]+)`", MATRIX_PATH.read_text("utf-8")))
    assert cited, "matrix cites no tests at all; criterion 4 not met"

    defined: set[str] = set()
    for source in sorted(TESTS_DIR.glob("test_*.py")):
        defined.update(re.findall(r"^def (test_[a-z0-9_]+)", source.read_text("utf-8"), re.MULTILINE))

    missing = sorted(cited - defined)
    assert not missing, f"matrix cites tests that do not exist: {missing}"


def test_matrix_names_error_envelopes():
    """Criterion 2: deviating top-level error schemas are named."""
    text = MATRIX_PATH.read_text("utf-8")
    assert "error format" in text.lower()
    # The OpenAI envelope and the Anthropic envelope must both be spelled out.
    assert '"error":{"message"' in text.replace(" ", "")
    assert '"type":"error"' in text.replace(" ", "")


def test_matrix_states_tested_client_versions():
    """Criterion 1: the tested client version is present."""
    text = MATRIX_PATH.read_text("utf-8")
    assert "openai-python" in text
    assert "anthropic" in text.lower()
    assert re.search(r"openai-python\s*[0-9]", text) or re.search(r">=\s*[0-9]", text)


# ===================================================================
# Kriterium 3: dual-switch semantics, measured
# ===================================================================


def test_bridge_and_surface_both_required(tmp_path, monkeypatch):
    """The runtime gate requires BOTH switches; neither alone exposes the surface."""
    for bridge, surface in ((True, False), (False, True), (False, False)):
        cfg = load_config(
            _write_config(
                tmp_path,
                f"""
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
  anthropic_messages: {str(surface).lower()}
anthropic_bridge:
  enabled: {str(bridge).lower()}
fallback_chain:
  - cloud-default
metrics:
  enabled: false
""",
            )
        )
        client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
        response = client.post(
            "/v1/messages",
            json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 404, (bridge, surface)
        assert response.json()["error"]["type"] == "not_found_error"


def test_bridge_enabled_alone_still_needs_surface(tmp_path, monkeypatch):
    """anthropic_bridge.enabled: true with the surface explicitly false -> 404.

    Measured 2026-09-24: the surface does not answer when only the bridge is on.
    """
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
    client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
    response = client.post(
        "/v1/messages",
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 404


def test_surface_defaults_to_bridge_enabled(tmp_path, monkeypatch):
    """When api_surfaces.anthropic_messages is absent it follows anthropic_bridge.enabled.

    bridge=true, surface absent -> surface resolves true -> 200.
    """
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
    assert cfg.api_surfaces.get("anthropic_messages") is True
    client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
    response = client.post(
        "/v1/messages",
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 200


def test_anthropic_messages_disabled_response(minimal_config, monkeypatch):
    """The disabled surface answers 404 with the Anthropic error envelope."""
    cfg = load_config(minimal_config)
    client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
    response = client.post(
        "/v1/messages",
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "not_found_error"
    assert body["error"]["message"] == "Anthropic bridge is disabled"


# ===================================================================
# 1. OpenAI-Compatible Surface — POST /v1/chat/completions
# ===================================================================


def test_openai_chat_text(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "say hi"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "ok"


def test_openai_chat_streaming(streaming_api_client):
    """Streaming emits SSE chunks (not merely a matching content-type)."""
    with streaming_api_client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "auto", "stream": True, "messages": [{"role": "user", "content": "say hi"}]},
    ) as response:
        body = b"".join(response.iter_bytes()).decode("utf-8")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"content":"ok"' in body.replace(" ", "")
    assert "data: [DONE]" in body


def test_openai_chat_usage(api_client):
    body = api_client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "say hi"}]},
    ).json()
    assert body["usage"]["prompt_tokens"] == 10
    assert body["usage"]["completion_tokens"] == 5


def test_openai_chat_model_routing(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={"model": "cloud-default", "messages": [{"role": "user", "content": "say hi"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "ok"


def test_openai_chat_system_message(api_client):
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "say hi"},
            ],
        },
    )
    assert response.status_code == 200


def test_openai_chat_tools_forwarded(minimal_config, monkeypatch):
    """Tool definitions are forwarded to the provider."""
    cfg = load_config(minimal_config)
    provider = _ProviderStub()
    client = _build_client(cfg, {"cloud-default": provider}, monkeypatch)
    tools = [{"type": "function", "function": {"name": "f", "parameters": {}}}]
    response = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}], "tools": tools},
    )
    assert response.status_code == 200
    assert provider.calls[-1]["tools"] == tools


def test_openai_chat_sampling_forwarded(minimal_config, monkeypatch):
    """temperature / max_tokens / stop / response_format reach the provider."""
    cfg = load_config(minimal_config)
    provider = _ProviderStub()
    client = _build_client(cfg, {"cloud-default": provider}, monkeypatch)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "temperature": 0.2,
            "stop": ["END"],
            "response_format": {"type": "json_object"},
        },
    )
    assert response.status_code == 200
    call = provider.calls[-1]
    assert call["max_tokens"] == 5
    assert call["temperature"] == 0.2
    assert call["extra_body"]["stop"] == ["END"]
    assert call["extra_body"]["response_format"] == {"type": "json_object"}


def test_openai_chat_multimodal_accepted(api_client):
    """Image content blocks are accepted and passed through."""
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/i.png"}},
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200


def test_openai_chat_error_format(api_client, monkeypatch):
    """Provider failure uses the OpenAI envelope: {"error": {"message", "type"}}."""
    monkeypatch.setattr(main_module, "_providers", {"cloud-default": _FailingProviderStub()}, raising=False)
    response = api_client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "say hi"}]},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["message"] == "All providers failed"
    # Measured: the top-level type reflects the upstream status class, and the
    # per-attempt detail carries the provider error type.
    assert body["error"]["type"] == "upstream_server_error"
    assert body["error"]["attempts"][0]["category"] == "upstream_server_error"


# ===================================================================
# 1b. OpenAI-Compatible Surface — GET /v1/models
# ===================================================================


def test_openai_models_list(api_client):
    body = api_client.get("/v1/models").json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1


def test_openai_models_includes_gate_models(api_client):
    body = api_client.get("/v1/models").json()
    assert "auto" in [m["id"] for m in body["data"]]


# ===================================================================
# 1c. OpenAI-Compatible Surface — images
# ===================================================================


def test_openai_image_generation(image_api_client):
    response = image_api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "a test image", "n": 1, "size": "1024x1024"},
    )
    assert response.status_code == 200
    assert "data" in response.json()


def test_openai_image_generation_validation(image_api_client):
    """Invalid size is rejected before the provider call."""
    response = image_api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "test", "n": 1, "size": "invalid"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "invalid_request_error"
    # Distinct shape: error is a string, not an object, on the image endpoints.
    assert isinstance(body["error"], str)


def test_openai_image_generation_without_capability(api_client):
    """A provider without image_generation is refused with the image error shape."""
    response = api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "cat", "n": 1, "size": "1024x1024"},
    )
    assert response.status_code == 400
    body = response.json()
    assert isinstance(body["error"], str)
    assert body["type"] == "invalid_request_error"


def test_openai_image_edits(image_api_client):
    response = image_api_client.post(
        "/v1/images/edits",
        data={"model": "auto", "prompt": "remove background"},
        files={"image": ("input.png", b"png data here", "image/png")},
    )
    assert response.status_code == 200
    assert "data" in response.json()


def test_openai_image_edits_upload_limit(tmp_path, monkeypatch):
    """Uploads above security.max_upload_bytes are refused with 413."""
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
security:
  max_upload_bytes: 32
providers:
  image-provider:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "gpt-image-1"
    capabilities:
      image_generation: true
      image_editing: true
fallback_chain:
  - image-provider
metrics:
  enabled: false
""",
        )
    )
    client = _build_client(cfg, {"image-provider": _ImageProviderStub()}, monkeypatch)
    response = client.post(
        "/v1/images/edits",
        data={"model": "auto", "prompt": "x"},
        files={"image": ("a.png", b"Z" * 100, "image/png")},
    )
    assert response.status_code == 413
    body = response.json()
    assert isinstance(body["error"], str)
    assert body["type"] == "payload_too_large"


# ===================================================================
# 2. Anthropic-Compatible Bridge
# ===================================================================


def test_anthropic_messages_text(bridge_api_client):
    response = bridge_api_client.post(
        "/v1/messages",
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert len(body["content"]) >= 1


def test_anthropic_messages_streaming(streaming_bridge_api_client):
    """Streaming is supported: the bridge emits Anthropic SSE events."""
    with streaming_bridge_api_client.stream(
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
    assert "event: message_start" in body
    assert "event: message_stop" in body


def test_anthropic_messages_system_string(bridge_api_client):
    response = bridge_api_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200


def test_anthropic_messages_system_text_block(bridge_api_client):
    response = bridge_api_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "system": [{"type": "text", "text": "You are helpful."}],
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200


def test_anthropic_messages_error_format(bridge_api_client):
    """Anthropic envelope: {"type": "error", "error": {"type", "message"}}."""
    response = bridge_api_client.post("/v1/messages", json={"model": "", "messages": []})
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
    assert body["error"]["message"]


def test_anthropic_count_tokens_estimated(bridge_api_client):
    response = bridge_api_client.post(
        "/v1/messages/count_tokens",
        json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "count these"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["input_tokens"] > 0
    assert response.headers["x-faigate-token-count-exact"] == "false"


def test_anthropic_count_tokens_error_format(bridge_api_client):
    response = bridge_api_client.post("/v1/messages/count_tokens", json={"model": "", "messages": []})
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"


# ===================================================================
# 3. Health / Operator Endpoints
# ===================================================================


def test_health_endpoint(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "providers" in body


def test_livez_endpoint(api_client):
    response = api_client.get("/livez")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_endpoint(api_client):
    response = api_client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_required_providers_config(tmp_path, monkeypatch):
    cfg = load_config(
        _write_config(
            tmp_path,
            """
server:
  host: "127.0.0.1"
  port: 8090
health:
  required_providers:
    - cloud-default
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
    client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
    assert client.get("/readyz").status_code == 200


def test_api_providers(api_client):
    response = api_client.get("/api/providers")
    assert response.status_code == 200
    assert "providers" in response.json()


def test_api_route_dryrun(api_client):
    response = api_client.post(
        "/api/route",
        json={"model": "auto", "messages": [{"role": "user", "content": "route this"}]},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/api/stats", "/api/recent", "/api/traces", "/api/quotas", "/api/provider-catalog"],
)
def test_operator_endpoints_respond(api_client, path):
    """Operator introspection surfaces answer (measured 200)."""
    assert api_client.get(path).status_code == 200
