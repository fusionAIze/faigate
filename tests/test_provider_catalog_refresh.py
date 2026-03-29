from __future__ import annotations

from faigate.provider_catalog_refresh import (
    ProviderCatalogRefresher,
    build_catalog_summary,
    due_provider_ids,
    parse_markdown_pricing_table,
    parse_regex_model_refs,
)
from faigate.provider_catalog_store import ProviderCatalogStore


class FakeFetcher:
    def __init__(self, payloads):
        self._payloads = payloads

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str:
        return self._payloads[url]


def test_parse_markdown_pricing_table_handles_free_and_paid_rows():
    text = """
| Model Name | Model ID | Input Cost | Output Cost | Context Length |
| ---------- | -------- | ---------- | ----------- | -------------- |
| xAI: Grok Code Fast 1 | x-ai/grok-code-fast-1:free | Free | Free | 256000 |
| Anthropic: Claude Sonnet 4.6 | anthropic/claude-sonnet-4.6 | $3.00 | $15.00 | 1000000 |
"""
    rows = parse_markdown_pricing_table(text)
    assert rows[0]["is_free"] is True
    assert rows[0]["input_cost"] == 0.0
    assert rows[1]["model_id"] == "anthropic/claude-sonnet-4.6"
    assert rows[1]["output_cost"] == 15.0


def test_parse_regex_model_refs_extracts_provider_specific_models():
    text = """
Use anthropic/claude-opus-4.6 or anthropic/claude-sonnet-4.6.
Kilo auto routes include kilo-auto/frontier and z-ai/glm-5:free.
"""
    rows = parse_regex_model_refs(
        text,
        model_prefixes=["anthropic/", "kilo-auto/", "z-ai/"],
    )
    ids = {row["model_id"] for row in rows}
    assert "anthropic/claude-opus-4.6" in ids
    assert "kilo-auto/frontier" in ids
    assert "z-ai/glm-5:free" in ids


def test_provider_catalog_refresher_records_change_events(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    payloads = {
        "https://docs.blackbox.ai/llms.txt": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
        "https://docs.blackbox.ai/api-reference/models/chat-pricing": """
| Model Name | Model ID | Input Cost | Output Cost | Context Length |
| ---------- | -------- | ---------- | ----------- | -------------- |
| xAI: Grok Code Fast 1 | x-ai/grok-code-fast-1:free | Free | Free | 256000 |
""",
    }
    refresher = ProviderCatalogRefresher(store, fetcher=FakeFetcher(payloads))
    first = refresher.refresh(provider_ids=["blackbox"])
    assert all(item.ok for item in first)

    payloads["https://docs.blackbox.ai/api-reference/models/chat-pricing"] = """
| Model Name | Model ID | Input Cost | Output Cost | Context Length |
| ---------- | -------- | ---------- | ----------- | -------------- |
| xAI: Grok Code Fast 1 | x-ai/grok-code-fast-1 | $0.20 | $0.50 | 256000 |
"""
    second = refresher.refresh(provider_ids=["blackbox"])
    assert all(item.ok for item in second)
    events = store.get_recent_change_events(provider_id="blackbox")
    change_types = {item["change_type"] for item in events}
    assert "model-added" in change_types or "field-changed" in change_types


def test_catalog_summary_marks_due_and_error_sources(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()
    refresher = ProviderCatalogRefresher(
        store,
        fetcher=FakeFetcher(
            {
                "https://docs.blackbox.ai/llms.txt": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
                "https://docs.blackbox.ai/api-reference/models/chat-pricing": """
| Model Name | Model ID | Input Cost | Output Cost | Context Length |
| ---------- | -------- | ---------- | ----------- | -------------- |
| xAI: Grok Code Fast 1 | x-ai/grok-code-fast-1:free | Free | Free | 256000 |
""",
            }
        ),
    )
    refresher.refresh(provider_ids=["blackbox"])
    store.mark_source_check("blackbox", success=True)
    store.upsert_source(
        {
            "provider_id": "kilo",
            "display_name": "Kilo",
            "refresh_interval_seconds": 21600,
            "billing_notes": "",
            "endpoints": [],
            "availability": {},
        }
    )
    store.mark_source_check("kilo", success=False, error="dns lookup failed")

    summary = build_catalog_summary(store)

    assert summary["tracked_sources"] >= 1
    assert summary["error_sources"] >= 1
    assert summary["priority_next"]["path"] == "Provider Catalog Refresh"


def test_due_provider_ids_returns_sources_without_recent_success(tmp_path):
    db_path = tmp_path / "faigate.db"
    store = ProviderCatalogStore(str(db_path))
    store.init()

    due = due_provider_ids(store, provider_ids=["blackbox", "kilo"])

    assert "blackbox" in due
    assert "kilo" in due
