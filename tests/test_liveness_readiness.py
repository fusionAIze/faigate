"""Tests for liveness and readiness endpoint separation (F13-A).

Acceptance criteria:
1. Liveness (/livez) answers without external work and without provider probes.
2. Readiness (/readyz) returns 503 when a required provider is unreachable.
3. Which providers are required is config-driven, not hardcoded.
4. A test proves: optional provider down → readiness stays 200;
   required provider down → 503.
5. The detailed diagnosis stays on /health — /readyz is NOT the path
   a health check queries.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.modules.pop("faigate.providers", None)
sys.modules.pop("faigate.updates", None)
sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import Config, ConfigError  # noqa: E402

importlib.reload(main_module)


def _mock_config(required_providers: list[str] | None = None) -> Config:
    """Build a minimal Config with health.required_providers."""
    data: dict[str, Any] = {
        "server": {"host": "127.0.0.1", "port": 8090},
        "providers": {
            "required-ok": {"base_url": "http://localhost:8000", "model": "test"},
            "optional-ok": {"base_url": "http://localhost:8001", "model": "test"},
        },
        "health": {
            "required_providers": required_providers or [],
        },
    }
    return Config(data)


class _ProviderStub:
    """Minimal provider stub compatible with _provider_request_readiness."""

    def __init__(self, name: str, healthy: bool = True):
        self.name = name
        self.contract = "generic"
        self.backend_type = "openai-compat"
        self.tier = "default"
        self.capabilities = {"chat": True, "local": False, "cloud": True, "network_zone": "public"}
        self.context_window = 128000
        self.limits = {"max_input_tokens": 128000, "max_output_tokens": 4096}
        self.cache = {"mode": "none", "read_discount": False}
        self.image = {}
        self.lane = {}
        self.transport = {}
        self.health = types.SimpleNamespace(
            healthy=healthy,
            last_check=1.0,
            avg_latency_ms=12.0,
            last_error="",
            to_dict=lambda: {
                "name": name,
                "healthy": healthy,
                "consecutive_failures": 0,
                "avg_latency_ms": 12.0,
                "last_error": "",
            },
        )

    async def close(self):
        return None


# ── Criterion 1: /livez ─────────────────────────────────────────


class TestLiveness:
    """Criterion 1: /livez answers without external work."""

    def test_livez_returns_200(self) -> None:
        """/livez returns 200 OK with a simple status response."""
        main_module._config = _mock_config()
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            resp = client.get("/livez")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_livez_does_not_trigger_probes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """/livez never calls _refresh_local_worker_probes.

        The lifespan startup calls _refresh_local_worker_probes once with
        force=True.  The /livez endpoint handler must NOT call it again.
        We verify the count stayed at 1 (lifespan only).
        """
        probe_count = 0

        async def _fake_probes(*args: Any, **kwargs: Any) -> None:
            nonlocal probe_count
            probe_count += 1

        monkeypatch.setattr(main_module, "_refresh_local_worker_probes", _fake_probes)
        main_module._config = _mock_config()
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            probe_count = 0  # reset: lifespan has already run
            client.get("/livez")
        assert probe_count == 0, "/livez must not trigger provider probes"


# ── Criterion 2: /readyz ────────────────────────────────────────


class TestReadiness:
    """Criterion 2: /readyz checks required providers.

    These tests set ``_providers`` inside the TestClient context so the
    lifespan startup does not overwrite them with real backends.
    """

    def test_readyz_returns_200_when_no_required(self) -> None:
        """No required_providers configured -> trivially ready."""
        main_module._config = _mock_config(required_providers=[])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=[])  # lifespan overwrote it
            main_module._providers = {}  # reset after lifespan
            resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_readyz_returns_200_when_required_healthy(self) -> None:
        """All required providers healthy -> ready."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=True),
                "optional-ok": _ProviderStub("optional-ok", healthy=True),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_readyz_returns_503_when_required_unhealthy(self) -> None:
        """Required provider unhealthy -> 503."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=False),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["ready"] is False
        assert "required-ok" in body["unreachable_required"]

    def test_readyz_returns_200_when_optional_unhealthy(self) -> None:
        """Optional provider unhealthy -> still ready (200)."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=True),
                "optional-broken": _ProviderStub("optional-broken", healthy=False),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True


# ── Criterion 4: optional vs required isolation ─────────────────


class TestRequiredVsOptionalIsolation:
    """Criterion 4: optional provider down != 503; required provider down == 503."""

    def test_optional_provider_down_readiness_stays_200(self) -> None:
        """Only optional providers unhealthy -> /readyz returns 200."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=True),
                "optional-broken": _ProviderStub("optional-broken", healthy=False),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_required_provider_down_readiness_returns_503(self) -> None:
        """Required provider unhealthy -> /readyz returns 503."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=False),
                "optional-ok": _ProviderStub("optional-ok", healthy=True),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["ready"] is False
        assert "required-ok" in body["unreachable_required"]

    def test_multiple_required_one_down_returns_503(self) -> None:
        """Multiple required providers, one down -> 503."""
        main_module._config = _mock_config(required_providers=["r1", "r2"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["r1", "r2"])  # lifespan overwrote it
            main_module._providers = {
                "r1": _ProviderStub("r1", healthy=True),
                "r2": _ProviderStub("r2", healthy=False),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 503
        assert "r2" in resp.json()["unreachable_required"]


# ── Criterion 5: /health carries full diagnosis ─────────────────


class TestHealthCarriesFullDiagnosis:
    """Criterion 5: /health carries full provider-level diagnosis.

    The detailed readiness view (providers, request_readiness per
    provider) stays on /health.  /readyz is a simple binary check
    that does NOT include per-provider detail.
    """

    def test_health_includes_provider_details(self) -> None:
        """/health returns per-provider diagnosis including request_readiness."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=True),
            }
            resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "providers" in body, "/health must carry per-provider diagnosis"
        assert "request_readiness" in body, "/health must carry request_readiness summary"
        assert "summary" in body, "/health must carry summary block"
        assert "version" in body, "/health must carry version"
        # /health includes per-provider details
        assert "required-ok" in body["providers"], "/health must list each provider"
        provider_block = body["providers"]["required-ok"]
        assert "request_readiness" in provider_block, "/health must include per-provider request_readiness"

    def test_readyz_lacks_provider_details(self) -> None:
        """/readyz does NOT include per-provider details (binary check only)."""
        main_module._config = _mock_config(required_providers=["required-ok"])
        main_module._providers = {}
        with TestClient(main_module.app) as client:
            main_module._config = _mock_config(required_providers=["required-ok"])  # lifespan overwrote it
            main_module._providers = {
                "required-ok": _ProviderStub("required-ok", healthy=True),
                "optional-ok": _ProviderStub("optional-ok", healthy=True),
            }
            resp = client.get("/readyz")
        assert resp.status_code == 200
        body = resp.json()
        # /readyz returns only {status, ready} — no provider details
        assert set(body.keys()) == {"status", "ready"}, (
            f"/readyz must be a simple binary check, got keys: {list(body.keys())}"
        )

    def test_health_and_readyz_are_different_endpoints(self) -> None:
        """/health and /readyz are registered as separate routes."""
        paths = [r.path for r in main_module.app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/readyz" in paths
        assert "/health" != "/readyz"


# ── Criterion 3: Config validation ──────────────────────────────


class TestRequiredProvidersConfig:
    """Criterion 3: required_providers lives in config, not code."""

    def test_required_providers_validates_against_known_providers(self) -> None:
        """Unknown provider in required_providers raises ConfigError."""
        from faigate.config import _normalize_health

        data: dict[str, Any] = {
            "providers": {"p1": {"base_url": "http://localhost:8000", "model": "m1"}},
            "health": {"required_providers": ["unknown-provider"]},
        }
        with pytest.raises(ConfigError, match="unknown-provider"):
            _normalize_health(data)

    def test_required_providers_empty_is_valid(self) -> None:
        """Empty required_providers is valid and normalizes cleanly."""
        from faigate.config import _normalize_health

        data: dict[str, Any] = {
            "providers": {},
            "health": {"required_providers": []},
        }
        result = _normalize_health(data)
        assert result["health"]["required_providers"] == []

    def test_required_providers_accepts_valid_names(self) -> None:
        """Known provider names pass validation."""
        from faigate.config import _normalize_health

        data: dict[str, Any] = {
            "providers": {
                "p1": {"base_url": "http://localhost:8000", "model": "m1"},
                "p2": {"base_url": "http://localhost:8001", "model": "m2"},
            },
            "health": {"required_providers": ["p1", "p2"]},
        }
        result = _normalize_health(data)
        assert result["health"]["required_providers"] == ["p1", "p2"]

    def test_required_providers_not_a_list_raises(self) -> None:
        """required_providers that is not a list raises ConfigError."""
        from faigate.config import _normalize_health

        data: dict[str, Any] = {
            "providers": {},
            "health": {"required_providers": "not-a-list"},
        }
        with pytest.raises(ConfigError):
            _normalize_health(data)


# ── RED PROOF ────────────────────────────────────────────────────


class TestRouteAbsenceRedProof:
    """RED PROOF: /livez and /readyz are absent on the base revision.

    Against 5f9376e (the F13-A base) these routes do not exist.
    These tests assert their presence and must FAIL on the base.
    """

    def test_livez_route_is_registered(self) -> None:
        """On the feature branch /livez must be registered."""
        paths = [r.path for r in main_module.app.routes if hasattr(r, "path")]
        assert "/livez" in paths, (
            "RED PROOF: /livez route not found in app.routes -- this assertion must FAIL against base 5f9376e"
        )

    def test_readyz_route_is_registered(self) -> None:
        """On the feature branch /readyz must be registered."""
        paths = [r.path for r in main_module.app.routes if hasattr(r, "path")]
        assert "/readyz" in paths, (
            "RED PROOF: /readyz route not found in app.routes -- this assertion must FAIL against base 5f9376e"
        )
