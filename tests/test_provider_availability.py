from __future__ import annotations

from pathlib import Path

from faigate.provider_availability import (
    build_provider_availability_overlay,
    record_availability_from_config,
    refresh_local_model_availability,
)
from faigate.provider_catalog_store import ProviderCatalogStore


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
                "https://api.blackbox.ai/v1/models": {
                    "data": [{"id": "x-ai/grok-code-fast-1"}]
                },
                "https://api.deepseek.com/v1/models": {
                    "data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]
                },
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
