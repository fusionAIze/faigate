"""Provider source registry for model catalogs, pricing, and billing metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "anthropic": {
        "provider_id": "anthropic",
        "display_name": "Anthropic",
        "refresh_interval_seconds": 43_200,
        "billing_notes": (
            "Anthropic usage can combine direct API billing with operator-side "
            "subscription or quota windows. Local route availability should be tracked "
            "separately from the public model docs."
        ),
        "route_prefixes": ["anthropic", "claude"],
        "provider_names": ["anthropic-claude", "anthropic-sonnet"],
        "endpoints": [
            {
                "kind": "models",
                "url": "https://docs.anthropic.com/en/docs/about-claude/models",
                "parser_type": "regex-model-refs",
                "model_patterns": [
                    r"\bclaude-[a-z0-9.\-]+",
                ],
            }
        ],
        "availability": {
            "supports_models_endpoint": False,
            "models_paths": [],
            "transport": "anthropic",
        },
    },
    "blackbox": {
        "provider_id": "blackbox",
        "display_name": "BLACKBOX",
        "refresh_interval_seconds": 21_600,
        "billing_notes": (
            "BLACKBOX can expose both free and paid model variants. Local key availability "
            "must be checked separately from the global pricing catalog."
        ),
        "route_prefixes": ["blackbox"],
        "provider_names": ["blackbox-free"],
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
            "models_paths": ["/v1/models", "/models"],
            "transport": "openai-compat",
        },
    },
    "deepseek": {
        "provider_id": "deepseek",
        "display_name": "DeepSeek",
        "refresh_interval_seconds": 43_200,
        "billing_notes": (
            "DeepSeek route cost and quota behavior can differ between direct API billing "
            "and operator-specific subscription or account limits."
        ),
        "route_prefixes": ["deepseek"],
        "provider_names": ["deepseek-chat", "deepseek-reasoner"],
        "endpoints": [
            {
                "kind": "models",
                "url": "https://api-docs.deepseek.com/",
                "parser_type": "regex-model-refs",
                "model_patterns": [
                    r"\bdeepseek-[a-z0-9.\-]+",
                ],
            }
        ],
        "availability": {
            "supports_models_endpoint": True,
            "models_paths": ["/v1/models", "/models"],
            "transport": "openai-compat",
        },
    },
    "google": {
        "provider_id": "google",
        "display_name": "Google",
        "refresh_interval_seconds": 43_200,
        "billing_notes": (
            "Google model access can sit behind AI Studio or platform-specific quotas. "
            "Local availability and operator limits should be overlaid separately."
        ),
        "route_prefixes": ["google", "gemini"],
        "provider_names": ["gemini-flash", "gemini-flash-lite"],
        "endpoints": [
            {
                "kind": "models",
                "url": "https://ai.google.dev/gemini-api/docs/models",
                "parser_type": "regex-model-refs",
                "model_patterns": [
                    r"\bgemini-[a-z0-9.\-:]+",
                    r"\bgemma-[a-z0-9.\-:]+",
                ],
            }
        ],
        "availability": {
            "supports_models_endpoint": False,
            "models_paths": [],
            "transport": "google",
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
        "route_prefixes": ["kilo"],
        "provider_names": ["kilocode", "kilo-sonnet", "kilo-opus"],
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
            "models_paths": [],
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
        "route_prefixes": ["openai", "gpt", "o1", "o3", "o4"],
        "provider_names": ["openai-gpt4o", "openai-images"],
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
            "models_paths": ["/models", "/v1/models"],
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


def resolve_provider_source_id(
    provider_name: str,
    provider: dict[str, Any] | None = None,
) -> str:
    """Map one configured route to a provider source family."""
    normalized_name = str(provider_name or "").strip().lower()
    lane = dict((provider or {}).get("lane") or {})
    family = str(lane.get("family") or "").strip().lower()

    for provider_id, source in _SOURCE_REGISTRY.items():
        if family and family == provider_id:
            return provider_id
        for explicit_name in list(source.get("provider_names") or []):
            if normalized_name == str(explicit_name or "").strip().lower():
                return provider_id
        for prefix in list(source.get("route_prefixes") or []):
            token = str(prefix or "").strip().lower()
            if token and (
                normalized_name == token
                or normalized_name.startswith(f"{token}-")
                or normalized_name.startswith(f"{token}_")
            ):
                return provider_id
    return family or normalized_name.split("-", 1)[0] or normalized_name
