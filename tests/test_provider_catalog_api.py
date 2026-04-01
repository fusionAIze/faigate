from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

sys.modules.pop("faigate.main", None)

import faigate.main as main_module  # noqa: E402
from faigate.config import load_config  # noqa: E402
from faigate.provider_catalog_store import ProviderCatalogStore  # noqa: E402
from faigate.router import Router  # noqa: E402

importlib.reload(main_module)


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def provider_catalog_api_state(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "faigate.db"
    cfg = load_config(
        _write_config(
            tmp_path,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  blackbox-free:
    backend: openai-compat
    base_url: "https://api.blackbox.ai"
    api_key: "secret"
    model: "blackboxai/x-ai/grok-code-fast-1"
fallback_chain:
  - blackbox-free
metrics:
  enabled: false
  db_path: "{db_path}"
provider_source_refresh:
  enabled: true
  on_startup: false
  providers:
    - blackbox
""",
        )
    )

    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.upsert_source(
        {
            "provider_id": "blackbox",
            "display_name": "BLACKBOX",
            "refresh_interval_seconds": 21600,
            "billing_notes": "free and paid tracks can drift by key",
            "endpoints": [
                {
                    "kind": "pricing",
                    "url": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
                    "parser_type": "markdown-pricing-table",
                }
            ],
            "availability": {},
        }
    )
    store.mark_source_check("blackbox", success=False, error="404 from pricing source")
    store.record_change_events(
        [
            {
                "provider_id": "blackbox",
                "detected_at": 1.0,
                "source_kind": "pricing",
                "change_type": "model-removed",
                "severity": "warning",
                "model_id": "x-ai/grok-code-fast-1:free",
                "field_name": "model_id",
                "old_value": "x-ai/grok-code-fast-1:free",
                "new_value": "",
                "message": ("blackbox: model 'x-ai/grok-code-fast-1:free' disappeared from pricing."),
            }
        ]
    )

    monkeypatch.setattr(main_module, "_config", cfg, raising=False)
    monkeypatch.setattr(main_module, "_router", Router(cfg), raising=False)
    monkeypatch.setattr(main_module, "_providers", {}, raising=False)
    monkeypatch.setattr(main_module, "_provider_catalog_store", store, raising=False)
    yield
    store.close()


def test_provider_catalog_endpoint_includes_source_alerts(provider_catalog_api_state):
    body = asyncio.run(main_module.provider_catalog())

    assert body["source_catalog"]["tracked_sources"] == 1
    assert body["source_catalog"]["error_sources"] == 1
    assert body["source_alert_summary"]["status"] == "intervention-needed"
    assert body["source_alert_summary"]["fix_now"] == 2
    assert body["source_catalog"]["alerts"][0]["kind"] == "source-refresh-error"
    assert any(alert["kind"] == "catalog-change" for alert in body["source_alerts"])
    assert any(
        "verify the source URL, parser, or auth assumptions" in alert["suggestion"] for alert in body["source_alerts"]
    )
