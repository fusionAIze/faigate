"""Provider source registry for model catalogs, pricing, and billing metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "blackbox": {
        "provider_id": "blackbox",
        "display_name": "BLACKBOX",
        "refresh_interval_seconds": 21_600,
        "billing_notes": (
            "BLACKBOX can expose both free and paid model variants. Local key availability "
            "must be checked separately from the global pricing catalog."
        ),
        "endpoints": [
            {
                "kind": "docs-index",
                "url": "https://docs.blackbox.ai/llms.txt",
                "parser_type": "llms-index",
            },
            {
                "kind": "pricing",
                "url": "https://docs.blackbox.ai/api-reference/models/chat-pricing",
                "parser_type": "markdown-pricing-table",
            },
        ],
        "availability": {
            "supports_models_endpoint": True,
            "models_path": "/v1/models",
            "transport": "openai-compat",
        },
    },
    "kilo": {
        "provider_id": "kilo",
        "display_name": "Kilo",
        "refresh_interval_seconds": 21_600,
        "billing_notes": (
            "Kilo mixes gateway wallet, free models, and BYOK-style execution paths. "
            "Local billing interpretation should be overlaid from account usage and route probes."
        ),
        "endpoints": [
            {
                "kind": "models",
                "url": "https://kilo.ai/docs/gateway/models-and-providers",
                "parser_type": "regex-model-refs",
                "model_prefixes": [
                    "anthropic/",
                    "google/",
                    "openai/",
                    "z-ai/",
                    "kilo-auto/",
                ],
            },
            {
                "kind": "billing",
                "url": "https://kilo.ai/docs/gateway/usage-and-billing",
                "parser_type": "billing-keywords",
            },
        ],
        "availability": {
            "supports_models_endpoint": False,
            "models_path": "",
            "transport": "openai-compat",
        },
    },
    "openai": {
        "provider_id": "openai",
        "display_name": "OpenAI",
        "refresh_interval_seconds": 43_200,
        "billing_notes": (
            "OpenAI may involve token billing, prepaid credits, or operator-specific subscription "
            "limits outside the raw API pricing table. Local account state should be "
            "tracked separately."
        ),
        "endpoints": [
            {
                "kind": "models",
                "url": "https://platform.openai.com/docs/models",
                "parser_type": "regex-model-refs",
                "model_patterns": [
                    r"\bgpt-[a-z0-9.\-:]+",
                    r"\bo[134]-[a-z0-9.\-:]+",
                    r"\bo1(?:-[a-z0-9.\-:]+)?",
                    r"\bo3(?:-[a-z0-9.\-:]+)?",
                    r"\bo4(?:-[a-z0-9.\-:]+)?",
                    r"\bcodex-[a-z0-9.\-:]+",
                ],
            }
        ],
        "availability": {
            "supports_models_endpoint": True,
            "models_path": "/v1/models",
            "transport": "openai-compat",
        },
    },
}


def get_provider_source_registry() -> dict[str, dict[str, Any]]:
    """Return the full provider source registry."""
    return deepcopy(_SOURCE_REGISTRY)


def get_provider_source(provider_id: str) -> dict[str, Any]:
    """Return one provider source definition."""
    return deepcopy(_SOURCE_REGISTRY.get(provider_id, {}))


def list_provider_sources(provider_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Return provider source definitions in a stable order."""
    names = provider_ids or sorted(_SOURCE_REGISTRY)
    items: list[dict[str, Any]] = []
    for name in names:
        item = get_provider_source(name)
        if item:
            items.append(item)
    return items
