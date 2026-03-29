from __future__ import annotations

from faigate.provider_catalog_store import ProviderCatalogStore


def test_provider_catalog_store_round_trips_sources_and_account_profiles(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.upsert_source(
        {
            "provider_id": "blackbox",
            "display_name": "BLACKBOX",
            "refresh_interval_seconds": 21600,
            "billing_notes": "notes",
            "endpoints": [
                {
                    "kind": "pricing",
                    "url": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
                }
            ],
            "availability": {"supports_models_endpoint": True},
        }
    )
    store.upsert_account_profile(
        "openai",
        billing_mode="subscription",
        subscription_name="Plus",
        quota_window="monthly",
        quota_remaining=42,
        notes="local operator profile",
    )

    sources = store.list_sources()
    assert sources[0]["provider_id"] == "blackbox"
    assert sources[0]["pricing_url"].endswith("/chat-pricing")

    profile = store.get_account_profile("openai")
    assert profile["billing_mode"] == "subscription"
    assert profile["subscription_name"] == "Plus"
    assert profile["quota_remaining"] == 42


def test_provider_catalog_store_persists_snapshots_and_events(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    store.replace_model_snapshot(
        "blackbox",
        "pricing",
        [
            {
                "model_id": "x-ai/grok-code-fast-1:free",
                "model_name": "Grok Code Fast",
                "input_cost": 0.0,
                "output_cost": 0.0,
                "context_length": 256000,
                "is_free": True,
                "raw_source_hash": "abc",
            }
        ],
        snapshot_at=1.0,
    )
    store.record_change_events(
        [
            {
                "provider_id": "blackbox",
                "detected_at": 2.0,
                "source_kind": "pricing",
                "change_type": "model-added",
                "message": "added",
            }
        ]
    )

    latest = store.get_latest_models("blackbox", "pricing")
    assert latest[0]["model_id"] == "x-ai/grok-code-fast-1:free"

    events = store.get_recent_change_events(provider_id="blackbox")
    assert events[0]["change_type"] == "model-added"
