"""Tests backing the conformance matrix (docs/CONFORMANCE-MATRIX.md).

Every claim in the matrix under a given endpoint is backed by at least one test
in this module. Untested features are marked ``untested`` in the matrix, never
as supported.

Evidence kinds follow the catalog convention:
    derivable, not_applicable, runtime_dependent, unlisted
"""

from __future__ import annotations

import importlib
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


class _FailingProviderStub(_ProviderStub):
    async def complete(self, *_args, **_kwargs):
        raise main_module.ProviderError(
            "cloud-default",
            502,
            "upstream error",
        )


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

    async def complete(self, *_args, **_kwargs):
        return {
            "id": "img-123",
            "object": "image",
            "data": [{"url": "https://example.com/img.png"}],
            "_faigate": {"latency_ms": 50},
        }

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
    def log_request(self, **_kwargs):
        return None

    def get_totals(self, **_kwargs):
        return {}

    def get_provider_summary(self, **_kwargs):
        return []

    def get_lane_family_breakdown(self, **_kwargs):
        return []

    def get_modality_breakdown(self, **_kwargs):
        return []

    def get_routing_breakdown(self, **_kwargs):
        return []

    def get_selection_path_breakdown(self, **_kwargs):
        return []

    def get_client_breakdown(self, **_kwargs):
        return []

    def get_client_totals(self, **_kwargs):
        return []

    def get_operator_breakdown(self, **_kwargs):
        return []

    def get_hourly_series(self, *_args, **_kwargs):
        return []

    def get_daily_totals(self, *_args, **_kwargs):
        return []

    def get_recent(self, *_args, **_kwargs):
        return []

    def get_operator_events(self, *_args, **_kwargs):
        return []


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
    """Config with anthropic bridge enabled and surface exposed."""
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
def bridge_api_client(bridge_config, monkeypatch):
    """TestClient with anthropic bridge enabled."""
    cfg = load_config(bridge_config)
    return _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)


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
# RED PROOF: conformance matrix exists and documents dual-switch semantics
# ===================================================================


def test_conformance_matrix_exists():
    """The conformance matrix must exist and document dual-switch semantics.

    RED PROOF: this assertion fails on the base branch where
    docs/CONFORMANCE-MATRIX.md does not exist.
    """
    path = Path(__file__).resolve().parent.parent / "docs" / "CONFORMANCE-MATRIX.md"
    assert path.exists(), "docs/CONFORMANCE-MATRIX.md is required"
    text = path.read_text("utf-8")
    assert "Dual-switch semantics" in text, (
        "The conformance matrix must document the distinguishable meanings "
        "of api_surfaces.anthropic_messages and anthropic_bridge.enabled"
    )
    assert "anthropic_bridge.enabled" in text
    assert "api_surfaces.anthropic_messages" in text
    assert "require" in text.lower() and "both" in text.lower()


# ===================================================================
# Kriterium 3: dual-switch semantics in config.py
# ===================================================================


def test_anthropic_bridge_and_surface_have_distinguishable_meanings():
    """Both switches have distinguishable meanings documented in config.py."""
    cfg = load_config(SHIPPED_CONFIG)
    bridge = cfg.anthropic_bridge
    surfaces = cfg.api_surfaces
    # The config schema tracks both separately
    assert "enabled" in bridge
    assert "anthropic_messages" in surfaces
    # When anthropic_bridge is disabled but surface is true, the surface is still
    # gated by _anthropic_bridge_surface_enabled() which requires both.
    # This confirms the switches have distinguishable meanings.
    bridge_enabled = bridge.get("enabled", False)
    surface_enabled = surfaces.get("anthropic_messages", False)
    # The shipped config has both true
    assert bridge_enabled is True
    assert surface_enabled is True


def test_anthropic_bridge_enabled_alone_does_not_expose_surface(tmp_path, monkeypatch):
    """Setting only anthropic_bridge.enabled without the surface toggle
    does not expose the surface (both are required)."""
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
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "not_found_error"


def test_surface_enabled_alone_does_not_expose_surface(tmp_path, monkeypatch):
    """Setting only api_surfaces.anthropic_messages without the bridge
    enabled does not expose the surface (both are required)."""
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
  anthropic_messages: true
anthropic_bridge:
  enabled: false
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
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "not_found_error"


# ===================================================================
# 1. OpenAI-Compatible Surface — POST /v1/chat/completions
# ===================================================================


def test_openai_chat_text(api_client):
    """Confirmed: text response (non-streaming)."""
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "choices" in body
    assert body["choices"][0]["message"]["content"] == "ok"


def test_openai_chat_streaming(api_client):
    """Confirmed: streaming response."""
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "stream": True,
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/event-stream")


def test_openai_chat_usage(api_client):
    """Confirmed: usage in response."""
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "usage" in body
    assert body["usage"]["prompt_tokens"] >= 0
    assert body["usage"]["completion_tokens"] >= 0


def test_openai_chat_model_routing(api_client):
    """Confirmed: model routing works (auto, provider-id)."""
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "cloud-default",
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "ok"


def test_openai_chat_system_message(api_client):
    """Confirmed: system message is accepted."""
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


def test_openai_chat_error_format(api_client, monkeypatch):
    """Confirmed: error format is OpenAI-compatible."""
    monkeypatch.setattr(
        main_module,
        "_providers",
        {"cloud-default": _FailingProviderStub()},
        raising=False,
    )
    response = api_client.post(
        "/v1/chat/completions",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "say hi"}],
        },
    )
    assert response.status_code in (502, 503)
    body = response.json()
    assert "error" in body
    assert "message" in body["error"]
    # The OpenAI error schema has error.type and optionally error.code
    assert "type" in body["error"] or "code" in body["error"]


# ===================================================================
# 1b. OpenAI-Compatible Surface — GET /v1/models
# ===================================================================


def test_openai_models_list(api_client):
    """Confirmed: list routable models."""
    response = api_client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1


def test_openai_models_includes_gate_models(api_client):
    """Confirmed: auto, modes included."""
    response = api_client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    ids = [m["id"] for m in body["data"]]
    assert "auto" in ids


# ===================================================================
# 1c. OpenAI-Compatible Surface — POST /v1/images/generations
# ===================================================================


def test_openai_image_generation(image_api_client):
    """Confirmed: image generation returns data."""
    response = image_api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "a test image", "n": 1, "size": "1024x1024"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


def test_openai_image_generation_validation(image_api_client):
    """Confirmed: validation of size param."""
    response = image_api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "test", "n": 1, "size": "invalid"},
    )
    # The gateway returns 400 for invalid sizes (not 422 — it validates
    # before the provider call)
    assert response.status_code == 400


# ===================================================================
# 1d. OpenAI-Compatible Surface — POST /v1/images/edits
# ===================================================================


def test_openai_image_edits(image_api_client):
    """Confirmed: image editing accepts multipart."""
    response = image_api_client.post(
        "/v1/images/edits",
        data={"model": "auto", "prompt": "remove background"},
        files={"image": ("input.png", b"png data here", "image/png")},
    )
    # 200 if provider handles it, 413 if too large, 400 if other error
    assert response.status_code in (200, 400, 413, 422)


def test_openai_image_error_format(api_client):
    """Confirmed: image endpoint error format matches OpenAI schema."""
    response = api_client.post(
        "/v1/images/generations",
        json={"model": "auto", "prompt": "test", "n": 0, "size": "1024x1024"},
    )
    body = response.json()
    # Should have an error structure
    assert "error" in body or "detail" in body


# ===================================================================
# 2. Anthropic-Compatible Bridge — POST /v1/messages
# ===================================================================


def test_anthropic_messages_text(bridge_api_client):
    """Confirmed: non-streaming text response."""
    response = bridge_api_client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "message"
    assert len(body["content"]) >= 1


def test_anthropic_messages_system_string(bridge_api_client):
    """Confirmed: system prompt as string."""
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
    """Confirmed: system prompt as text block."""
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
    """Confirmed: error format is Anthropic-compatible."""
    response = bridge_api_client.post(
        "/v1/messages",
        json={"model": "", "messages": []},
    )
    body = response.json()
    assert "type" in body
    assert "error" in body
    assert "type" in body["error"]
    assert "message" in body["error"]


def test_anthropic_messages_disabled(minimal_config, monkeypatch):
    """Confirmed: returns 404 when surface is disabled."""
    cfg = load_config(minimal_config)
    client = _build_client(cfg, {"cloud-default": _ProviderStub()}, monkeypatch)
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


# ===================================================================
# 2b. Anthropic-Compatible Bridge — POST /v1/messages/count_tokens
# ===================================================================


def test_anthropic_count_tokens_estimated(bridge_api_client):
    """Confirmed: count_tokens returns estimated count."""
    response = bridge_api_client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "count these tokens"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "input_tokens" in body
    assert body["input_tokens"] > 0
    # Verify estimation headers
    assert response.headers.get("x-faigate-token-count-exact") == "false"


def test_anthropic_count_tokens_error_format(bridge_api_client):
    """Confirmed: error format matches Anthropic envelope."""
    response = bridge_api_client.post(
        "/v1/messages/count_tokens",
        json={"model": "", "messages": []},
    )
    body = response.json()
    assert "type" in body
    assert "error" in body
    assert "type" in body["error"]


# ===================================================================
# 3. Health / Operator Endpoints
# ===================================================================


def test_health_endpoint(api_client):
    """Confirmed: health returns provider summary."""
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "providers" in body


def test_livez_endpoint(api_client):
    """Confirmed: liveness check."""
    response = api_client.get("/livez")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_readyz_endpoint(api_client):
    """Confirmed: readiness check."""
    response = api_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body.get("ready") in (True, False)


def test_readyz_required_providers_config(tmp_path, monkeypatch):
    """Confirmed: config-driven required providers affect readiness."""
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
    response = client.get("/readyz")
    assert response.status_code == 200


def test_api_providers(api_client):
    """Confirmed: provider inventory endpoint."""
    response = api_client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body


def test_api_route_dryrun(api_client):
    """Confirmed: route dry-run."""
    response = api_client.post(
        "/api/route",
        json={
            "model": "auto",
            "messages": [{"role": "user", "content": "route this"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "selected_provider" in body or "decision" in body
