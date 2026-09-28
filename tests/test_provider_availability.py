from __future__ import annotations

from pathlib import Path

import faigate.main as faigate_main
from faigate.provider_availability import (
    build_provider_availability_overlay,
    record_availability_from_config,
    refresh_local_model_availability,
)
from faigate.provider_catalog_store import ProviderCatalogStore
from faigate.providers import ProviderBackend


class FakeJsonFetcher:
    def __init__(self, payloads: dict[str, dict]):
        self._payloads = payloads

    def fetch_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict:
        return dict(self._payloads[url])


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  blackbox-free:
    backend: openai-compat
    base_url: "https://api.blackbox.ai"
    api_key: "secret"
    model: "x-ai/grok-code-fast-1:free"
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "secret"
    model: "deepseek-chat"
fallback_chain: []
metrics:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def test_local_models_endpoint_overlay_detects_key_specific_mismatch(tmp_path: Path):
    config_path = _write_config(tmp_path)
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.replace_model_snapshot(
        "blackbox",
        "pricing",
        [
            {
                "model_id": "x-ai/grok-code-fast-1:free",
                "model_name": "Grok Code Fast 1 Free",
                "input_cost": 0.0,
                "output_cost": 0.0,
                "context_length": 256000,
                "is_free": True,
                "raw_source_hash": "hash-blackbox",
            }
        ],
    )
    store.replace_model_snapshot(
        "deepseek",
        "models",
        [
            {
                "model_id": "deepseek-chat",
                "model_name": "DeepSeek Chat",
                "input_cost": None,
                "output_cost": None,
                "context_length": None,
                "is_free": False,
                "raw_source_hash": "hash-deepseek",
            }
        ],
    )

    record_availability_from_config(
        store,
        config_path=str(config_path),
        health_payload={
            "providers": {
                "blackbox-free": {
                    "request_readiness": {
                        "ready": False,
                        "status": "degraded",
                        "reason": "last request failed",
                    }
                },
                "deepseek-chat": {
                    "request_readiness": {
                        "ready": True,
                        "status": "ready",
                        "reason": "healthy",
                    }
                },
            }
        },
    )
    refresh_local_model_availability(
        store,
        config_path=str(config_path),
        fetcher=FakeJsonFetcher(
            {
                "https://api.blackbox.ai/v1/models": {"data": [{"id": "x-ai/grok-code-fast-1"}]},
                "https://api.deepseek.com/v1/models": {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]},
            }
        ),
    )

    blackbox_overlay = build_provider_availability_overlay(
        store,
        provider_id="blackbox",
        global_model_ids={"x-ai/grok-code-fast-1:free"},
        global_free_model_ids={"x-ai/grok-code-fast-1:free"},
    )
    deepseek_overlay = build_provider_availability_overlay(
        store,
        provider_id="deepseek",
        global_model_ids={"deepseek-chat", "deepseek-reasoner"},
        global_free_model_ids=set(),
    )

    assert blackbox_overlay["status"] == "intervention-needed"
    assert blackbox_overlay["key_model_mismatches"][0]["route_name"] == "blackbox-free"
    assert blackbox_overlay["local_only_models"] == ["x-ai/grok-code-fast-1"]
    assert blackbox_overlay["free_models_missing_locally"] == ["x-ai/grok-code-fast-1:free"]
    assert deepseek_overlay["status"] == "clear"
    assert deepseek_overlay["visible_models"] == ["deepseek-chat", "deepseek-reasoner"]


# ── Request-readiness names its own states (FAI-237-B) ───────────────────────
#
# ``ready`` currently means "the key resolved and the endpoint answered". The
# field reads as "this route accepts requests". As long as addressability is
# not carried alongside, the field does not mean what it says and an operator
# has no signal for the failure FAI-237-A fixed: a provider no routing rule
# targets is unreachable by its own name.
#
# The acceptance criteria below pin four things:
#   1. a provider no rule addresses reports not-ready and names the reason,
#   2. the reason separates 'no key', 'endpoint did not answer' and
#      'not addressable' as their own states,
#   3. the /health roll-up sums the states against the individual providers,
#   4. providers that were ready before stay ready (no readiness regression).


def _make_backend(
    name: str,
    *,
    api_key: str = "secret",
    last_error: str = "",
    healthy: bool = True,
    addressable: bool = True,
) -> ProviderBackend:
    """Build a minimal OpenAI-compatible backend with an explicit ready state.

    The readiness ladder in ``request_readiness`` consults four things in
    order: the key, ``health.last_error``, addressability and the probe
    history. This helper drives each independently so a test can pin exactly
    one state without a network client or a probe.
    """
    backend = ProviderBackend(
        name,
        {
            "backend": "openai-compat",
            "base_url": "https://api.example.com/v1",
            "api_key": api_key,
            "model": "test-model",
        },
    )
    backend._addressable = addressable
    backend.health.healthy = healthy
    if last_error:
        backend.health.last_error = last_error
    return backend


class TestAddressabilityReadiness:
    """Criterion 1 & 2: not-addressable is a named, distinct readiness state."""

    def test_unaddressed_provider_is_not_ready_and_names_the_reason(self):
        """A provider no rule addresses must not report ready, and must say why.

        Existing ready providers change nothing here: this provider is only
        ready because a rule addresses it. Remove the rule (addressable=False)
        and readiness must drop, with the reason naming both the provider and
        the missing routing target.
        """
        backend = _make_backend("orphan-provider", addressable=False)

        readiness = backend.request_readiness()

        assert readiness["ready"] is False
        assert readiness["status"] == "not-addressable"
        assert "orphan-provider" in readiness["reason"]
        assert "no routing rule" in readiness["reason"]
        assert readiness["operator_hint"] == (
            "no routing rule targets this provider; add a static rule or route its name explicitly"
        )

    def test_addressable_provider_with_key_is_ready(self):
        """The control case: same backend, addressability restored, is ready.

        Without this the previous test would pass even if ``request_readiness``
        returned not-ready for every provider.
        """
        backend = _make_backend("addressed-provider", addressable=True)

        readiness = backend.request_readiness()

        assert readiness["ready"] is True
        assert readiness["status"] == "ready"

    def test_key_endpoint_and_addressability_are_distinct_states(self):
        """The three failure modes must be their own status, not one bucket.

        'no key', 'the endpoint did not answer' and 'not addressable' are
        different operator problems with different fixes. Collapsing them into
        one status would make the readiness field name a cause it cannot
        distinguish.
        """
        missing_key = _make_backend("no-key-provider", api_key="")
        endpoint_down = _make_backend(
            "down-provider",
            last_error="Probe connection error: [Errno 61] Connection refused",
            healthy=False,
        )
        not_addressable = _make_backend("unaddressed-provider", addressable=False)

        states = {model.request_readiness()["status"] for model in (missing_key, endpoint_down, not_addressable)}

        # A signal must be present for every input, otherwise the guard below
        # would pass on an empty set.
        assert len(states) == 3, f"expected three distinct states, got {states}"
        assert "missing-key" in states
        assert "not-addressable" in states
        assert "connection_error" in states or "transport-error" in states


class TestReadinessSummaryRollup:
    """Criterion 3: /health sums the states against the individual providers.

    ``_request_readiness_summary`` is what ``/health`` and ``/api/providers``
    publish under ``request_readiness``. A roll-up that does not match the
    per-provider states is a lying dashboard: the operator sees a total that
    cannot be reconstructed from the detail.
    """

    def test_summary_counts_each_provider_state_exactly_once(self, monkeypatch):
        providers = {
            "ready-a": _make_backend("ready-a"),
            "ready-b": _make_backend("ready-b"),
            "no-key": _make_backend("no-key", api_key=""),
            "unaddressed": _make_backend("unaddressed", addressable=False),
            "down": _make_backend(
                "down",
                last_error="Probe connection error: refused",
                healthy=False,
            ),
        }
        monkeypatch.setattr(faigate_main, "_providers", providers, raising=False)

        summary = faigate_main._request_readiness_summary()

        # The states counted in the roll-up must be exactly the states the
        # individual providers report — no invented states, none dropped.
        expected_statuses = {p.request_readiness()["status"] for p in providers.values()}
        assert set(summary["statuses"]) == expected_statuses
        assert sum(summary["statuses"].values()) == len(providers)

        assert summary["providers_total"] == len(providers)
        assert summary["providers_ready"] == 2
        assert summary["providers_not_ready"] == len(providers) - 2
        assert summary["statuses"]["not-addressable"] == 1
        assert summary["statuses"]["missing-key"] == 1

    def test_summary_does_not_invent_states_for_an_unknown_provider(self, monkeypatch):
        """A provider whose readiness carries no status lands under 'unknown'.

        The roll-up must never silently drop a provider: total, ready and
        not-ready have to stay consistent even for a status-less provider.
        """

        class _Statusless:
            name = "statusless"

            def request_readiness(self):
                return {"ready": False}

        monkeypatch.setattr(faigate_main, "_providers", {"statusless": _Statusless()}, raising=False)

        summary = faigate_main._request_readiness_summary()

        assert summary["providers_total"] == 1
        assert summary["providers_not_ready"] == 1
        assert summary["statuses"] == {"unknown": 1}
        assert sum(summary["statuses"].values()) == summary["providers_total"]
