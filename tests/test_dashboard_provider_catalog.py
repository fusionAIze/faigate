from __future__ import annotations

from faigate.dashboard import build_dashboard_report, render_dashboard_text
from faigate.provider_catalog_store import ProviderCatalogStore


def test_dashboard_surfaces_provider_catalog_alerts(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.upsert_source(
        {
            "provider_id": "kilo",
            "display_name": "Kilo",
            "refresh_interval_seconds": 21600,
            "billing_notes": "wallet, byok, and free tracks vary by account",
            "endpoints": [
                {
                    "kind": "models",
                    "url": "https://kilo.ai/docs/gateway/models-and-providers",
                    "parser_type": "regex-model-refs",
                }
            ],
            "availability": {},
        }
    )
    store.mark_source_check("kilo", success=False, error="timeout from models source")
    store.record_change_events(
        [
            {
                "provider_id": "kilo",
                "detected_at": 1.0,
                "source_kind": "models",
                "change_type": "field-changed",
                "severity": "notice",
                "model_id": "anthropic/claude-opus-4.6",
                "field_name": "input_cost",
                "old_value": "5.0",
                "new_value": "6.0",
                "message": (
                    "kilo: input_cost for 'anthropic/claude-opus-4.6' changed from 5.0 to 6.0."
                ),
            }
        ]
    )
    store.close()

    report = build_dashboard_report(db_path=str(db_path))

    assert report["provider_catalog_alerts"][0]["kind"] == "source-refresh-error"
    assert report["cards"]["provider_catalog"]["alerts"] >= 1

    text = render_dashboard_text(report, view="alerts")
    assert "Provider source refresh failing for kilo" in text
    assert "Catalog change detected for kilo" in text
