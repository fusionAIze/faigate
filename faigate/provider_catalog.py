"""Curated provider catalog and drift/freshness reporting.

This module manages external metadata catalogs for providers, offerings, and packages.
Catalogs are loaded from the external fusionaize-metadata repository (or local overrides)
and cached for performance.

Environment variables:
- FAIGATE_PROVIDER_METADATA_FILE: override path to provider catalog JSON
- FAIGATE_PROVIDER_METADATA_DIR: root directory of metadata repository
- FAIGATE_PROVIDER_METADATA_PRODUCT: product name for overlays (default "gate")
- FAIGATE_OFFERINGS_METADATA_FILE: override path to offerings catalog JSON
- FAIGATE_PACKAGES_METADATA_FILE: override path to packages catalog JSON
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import registry
from .config import Config
from .lane_registry import (
    get_active_model_id,
    get_active_model_label,
    get_canonical_model_catalog,
    get_provider_lane_binding,
)

logger = logging.getLogger("faigate.provider_catalog")

# Path to external fusionaize-metadata repository (set via FAIGATE_PROVIDER_METADATA_DIR)
_EXTERNAL_METADATA_ROOT = Path("/nonexistent/faigate-metadata-fallback")

_COMMUNITY_WATCHLIST = {
    "label": "free-llm-api-resources",
    "url": "https://github.com/cheahjs/free-llm-api-resources",
}

_DISCOVERY_DISCLOSURE = (
    "Provider recommendations stay performance-led. "
    "Shown signup or discovery links are informational only "
    "and do not affect ranking."
)

_EXTERNAL_CATALOG_ENV = "FAIGATE_PROVIDER_METADATA_FILE"
_EXTERNAL_CATALOG_DIR_ENV = "FAIGATE_PROVIDER_METADATA_DIR"
_EXTERNAL_CATALOG_PRODUCT_ENV = "FAIGATE_PROVIDER_METADATA_PRODUCT"
_OFFERINGS_CATALOG_ENV = "FAIGATE_OFFERINGS_METADATA_FILE"
_PACKAGES_CATALOG_ENV = "FAIGATE_PACKAGES_METADATA_FILE"
_DEFAULT_METADATA_PRODUCT = "gate"
_METADATA_CATALOG_RELATIVE_PATH = Path("providers") / "catalog.v1.json"
_OFFERINGS_CATALOG_RELATIVE_PATH = Path("offerings") / "catalog.v1.json"
_PACKAGES_CATALOG_RELATIVE_PATH = Path("packages") / "catalog.v1.json"

# Hardcoded fallback path for external metadata repository (legacy - non-existent by default)
# Override with FAIGATE_PROVIDER_METADATA_DIR environment variable

# Cache for external metadata
_EXTERNAL_CATALOG_CACHE: dict[str, Any] | None = None
_EXTERNAL_CATALOG_MTIME: float = 0.0
_EXTERNAL_OVERLAY_CACHE: dict[str, Any] | None = None
_EXTERNAL_OVERLAY_MTIME: float = 0.0
_EXTERNAL_OFFERINGS_CACHE: dict[str, Any] | None = None
_EXTERNAL_OFFERINGS_MTIME: float = 0.0
_EXTERNAL_PACKAGES_CACHE: dict[str, Any] | None = None
_EXTERNAL_PACKAGES_MTIME: float = 0.0


def _get_external_metadata_root() -> Path:
    """Determine the external metadata root directory from environment variables."""
    metadata_dir = os.environ.get(_EXTERNAL_CATALOG_DIR_ENV, "").strip()
    if metadata_dir:
        return Path(metadata_dir).expanduser()
    # Fallback to hardcoded path
    return _EXTERNAL_METADATA_ROOT


def _get_external_catalog_path() -> Path:
    """Get path to external catalog.v1.json."""
    metadata_file = os.environ.get(_EXTERNAL_CATALOG_ENV, "").strip()
    if metadata_file:
        return Path(metadata_file).expanduser()
    # Fallback to default location relative to metadata root
    root = _get_external_metadata_root()
    return root / "providers" / "catalog.v1.json"


def _get_external_overlay_path() -> Path:
    """Get path to external overlays.v1.json for the current product."""
    product = os.environ.get(_EXTERNAL_CATALOG_PRODUCT_ENV, _DEFAULT_METADATA_PRODUCT).strip()  # noqa: E501
    if not product:
        product = _DEFAULT_METADATA_PRODUCT
    root = _get_external_metadata_root()
    return root / "products" / product / "overlays.v1.json"


def _get_external_offerings_path() -> Path:
    """Get path to external offerings catalog.v1.json."""
    metadata_file = os.environ.get(_OFFERINGS_CATALOG_ENV, "").strip()
    if metadata_file:
        return Path(metadata_file).expanduser()
    root = _get_external_metadata_root()
    return root / "offerings" / "catalog.v1.json"


def _get_external_packages_path() -> Path:
    """Get path to external packages catalog.v1.json."""
    metadata_file = os.environ.get(_PACKAGES_CATALOG_ENV, "").strip()
    if metadata_file:
        return Path(metadata_file).expanduser()
    root = _get_external_metadata_root()
    return root / "packages" / "catalog.v1.json"


def _load_external_catalog() -> dict[str, Any]:
    """Load external catalog.v1.json if available."""
    global _EXTERNAL_CATALOG_CACHE, _EXTERNAL_CATALOG_MTIME

    catalog_path = _get_external_catalog_path()

    # Check if cache is still valid
    if _EXTERNAL_CATALOG_CACHE is not None and catalog_path.exists():
        current_mtime = catalog_path.stat().st_mtime
        if current_mtime <= _EXTERNAL_CATALOG_MTIME:
            return _EXTERNAL_CATALOG_CACHE
        # File has changed, invalidate cache
        _EXTERNAL_CATALOG_CACHE = None

    if not catalog_path.exists():
        _EXTERNAL_CATALOG_CACHE = {}
        _EXTERNAL_CATALOG_MTIME = 0.0
        return {}

    try:
        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)
        _EXTERNAL_CATALOG_CACHE = data.get("providers", {})
        _EXTERNAL_CATALOG_MTIME = catalog_path.stat().st_mtime
    except Exception:
        _EXTERNAL_CATALOG_CACHE = {}
        _EXTERNAL_CATALOG_MTIME = 0.0

    return _EXTERNAL_CATALOG_CACHE


def _load_external_overlay() -> dict[str, Any]:
    """Load external overlays.v1.json if available."""
    global _EXTERNAL_OVERLAY_CACHE, _EXTERNAL_OVERLAY_MTIME

    overlay_path = _get_external_overlay_path()

    # Check if cache is still valid
    if _EXTERNAL_OVERLAY_CACHE is not None and overlay_path.exists():
        current_mtime = overlay_path.stat().st_mtime
        if current_mtime <= _EXTERNAL_OVERLAY_MTIME:
            return _EXTERNAL_OVERLAY_CACHE
        # File has changed, invalidate cache
        _EXTERNAL_OVERLAY_CACHE = None

    if not overlay_path.exists():
        _EXTERNAL_OVERLAY_CACHE = {}
        _EXTERNAL_OVERLAY_MTIME = 0.0
        return {}

    try:
        with open(overlay_path, encoding="utf-8") as f:
            data = json.load(f)
        _EXTERNAL_OVERLAY_CACHE = data.get("providers", {})
        _EXTERNAL_OVERLAY_MTIME = overlay_path.stat().st_mtime
    except Exception:
        _EXTERNAL_OVERLAY_CACHE = {}
        _EXTERNAL_OVERLAY_MTIME = 0.0

    return _EXTERNAL_OVERLAY_CACHE


def _load_external_offerings() -> dict[str, Any]:
    """Load external offerings catalog.v1.json if available."""
    global _EXTERNAL_OFFERINGS_CACHE, _EXTERNAL_OFFERINGS_MTIME

    offerings_path = _get_external_offerings_path()

    # Check if cache is still valid
    if _EXTERNAL_OFFERINGS_CACHE is not None and offerings_path.exists():
        current_mtime = offerings_path.stat().st_mtime
        if current_mtime <= _EXTERNAL_OFFERINGS_MTIME:
            logger.debug("Offerings catalog cache hit for %s", offerings_path)
            return _EXTERNAL_OFFERINGS_CACHE
        # File has changed, invalidate cache
        _EXTERNAL_OFFERINGS_CACHE = None

    if not offerings_path.exists():
        logger.debug("Offerings catalog file not found: %s", offerings_path)
        _EXTERNAL_OFFERINGS_CACHE = {}
        _EXTERNAL_OFFERINGS_MTIME = 0.0
        return {}

    try:
        with open(offerings_path, encoding="utf-8") as f:
            data = json.load(f)
        _EXTERNAL_OFFERINGS_CACHE = data.get("offerings", {})
        _EXTERNAL_OFFERINGS_MTIME = offerings_path.stat().st_mtime
        logger.debug("Loaded offerings catalog from %s (%d entries)", offerings_path, len(_EXTERNAL_OFFERINGS_CACHE))
    except Exception as e:
        logger.warning("Failed to load offerings catalog from %s: %s", offerings_path, e)
        _EXTERNAL_OFFERINGS_CACHE = {}
        _EXTERNAL_OFFERINGS_MTIME = 0.0

    return _EXTERNAL_OFFERINGS_CACHE


def _load_external_packages() -> dict[str, Any]:
    """Load external packages catalog.v1.json if available."""
    global _EXTERNAL_PACKAGES_CACHE, _EXTERNAL_PACKAGES_MTIME

    packages_path = _get_external_packages_path()

    # Check if cache is still valid
    if _EXTERNAL_PACKAGES_CACHE is not None and packages_path.exists():
        current_mtime = packages_path.stat().st_mtime
        if current_mtime <= _EXTERNAL_PACKAGES_MTIME:
            logger.debug("Packages catalog cache hit for %s", packages_path)
            return _EXTERNAL_PACKAGES_CACHE
        # File has changed, invalidate cache
        _EXTERNAL_PACKAGES_CACHE = None

    if not packages_path.exists():
        logger.debug("Packages catalog file not found: %s", packages_path)
        _EXTERNAL_PACKAGES_CACHE = {}
        _EXTERNAL_PACKAGES_MTIME = 0.0
        return {}

    try:
        with open(packages_path, encoding="utf-8") as f:
            data = json.load(f)
        _EXTERNAL_PACKAGES_CACHE = data.get("packages", {})
        _EXTERNAL_PACKAGES_MTIME = packages_path.stat().st_mtime
        logger.debug("Loaded packages catalog from %s (%d entries)", packages_path, len(_EXTERNAL_PACKAGES_CACHE))
    except Exception as e:
        logger.warning("Failed to load packages catalog from %s: %s", packages_path, e)
        _EXTERNAL_PACKAGES_CACHE = {}
        _EXTERNAL_PACKAGES_MTIME = 0.0

    return _EXTERNAL_PACKAGES_CACHE


def _get_provider_pricing(provider_name: str) -> dict[str, Any]:
    """Get pricing metadata for a provider from multiple sources."""
    pricing = {}

    # 1. Check external overlay (product-specific)
    overlay = _load_external_overlay()
    if provider_name in overlay:
        provider_data = overlay[provider_name]
        if "pricing" in provider_data:
            pricing.update(provider_data["pricing"])

    # 2. Check external base catalog
    catalog = _load_external_catalog()
    if provider_name in catalog:
        provider_data = catalog[provider_name]
        if "pricing" in provider_data:
            # Overlay may have overridden some fields, merge
            for key, value in provider_data["pricing"].items():
                if key not in pricing:
                    pricing[key] = value

    # Normalize pricing field names from external catalog
    # Map input_cost_per_1m -> input, output_cost_per_1m -> output,
    # cache_read_cost_per_1m -> cache_read
    field_mapping = {
        "input_cost_per_1m": "input",
        "output_cost_per_1m": "output",
        "cache_read_cost_per_1m": "cache_read",
    }
    for src, dst in field_mapping.items():
        if src in pricing and dst not in pricing:
            pricing[dst] = pricing[src]

    # 3. Check built-in registry for numeric rates
    # Map provider_name to registry key (simplistic: try exact match, then partial)
    registry_key = None
    if provider_name in registry.BUILTIN:
        registry_key = provider_name
    else:
        # Special case mappings
        special_mappings = {
            "anthropic-haiku": "anthropic",
            "anthropic-sonnet": "anthropic",
            "anthropic-claude": "anthropic",
            "gemini-flash": "google",
            "gemini-flash-lite": "google",
            "gemini-pro-high": "google",
            "gemini-pro-low": "google",
            "openai-gpt4o": "openai",
            "openai-images": "openai",
            "openai-codex": "openai",
            "openrouter-fallback": "openrouter",
        }
        if provider_name in special_mappings:
            registry_key = special_mappings[provider_name]
        else:
            # Try prefix matching (e.g., "mistral-large" -> "mistral")
            for key in registry.BUILTIN:
                if provider_name.startswith(key) or key.startswith(provider_name):
                    registry_key = key
                    break
            # If still not found, try partial match in key
            if registry_key is None:
                for key in registry.BUILTIN:
                    if provider_name in key or key in provider_name:
                        registry_key = key
                        break

    if registry_key and "pricing" in registry.BUILTIN[registry_key]:
        registry_pricing = registry.BUILTIN[registry_key]["pricing"]
        # Merge numeric rates, but don't overwrite metadata fields
        numeric_fields = {"input", "output", "cache_read"}
        for field in numeric_fields:
            if field in registry_pricing and registry_pricing[field]:
                # Convert to float if not already
                value = registry_pricing[field]
                if isinstance(value, (int, float)) and value > 0 and field not in pricing:  # noqa: E501
                    pricing[field] = float(value)

    return pricing


_CATALOG: dict[str, dict[str, Any]] = {
    "deepseek-chat": {
        "recommended_model": get_active_model_id("deepseek/chat"),
        "aliases": ["deepseek-chat", "ds-v3"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://api-docs.deepseek.com/",
        "signup_url": "https://platform.deepseek.com/",
        "watch_sources": [],
        "notes": get_active_model_label("deepseek/chat"),
        "last_reviewed": "2026-03-29",
    },
    "deepseek-reasoner": {
        "recommended_model": get_active_model_id("deepseek/reasoner"),
        "aliases": ["deepseek-reasoner", "r1"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://api-docs.deepseek.com/",
        "signup_url": "https://platform.deepseek.com/",
        "watch_sources": [],
        "notes": get_active_model_label("deepseek/reasoner"),
        "last_reviewed": "2026-03-29",
    },
    "gemini-flash-lite": {
        "recommended_model": get_active_model_id("google/gemini-flash-lite"),
        "aliases": ["gemini-2.5-flash-lite", "gemini-3-flash-lite"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": get_active_model_label("google/gemini-flash-lite"),
        "last_reviewed": "2026-03-29",
    },
    "gemini-flash": {
        "recommended_model": get_active_model_id("google/gemini-flash"),
        "aliases": ["gemini-2.5-flash", "gemini-3-flash"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": get_active_model_label("google/gemini-flash"),
        "last_reviewed": "2026-03-29",
    },
    "openrouter-fallback": {
        "recommended_model": "openrouter/auto",
        "aliases": ["openrouter/auto"],
        "track": "stable",
        "offer_track": "byok",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://openrouter.ai/docs/features/provider-routing",
        "signup_url": "https://openrouter.ai/",
        "watch_sources": [],
        "notes": "Marketplace fallback path with official provider routing and BYOK support",  # noqa: E501
        "last_reviewed": "2026-03-19",
    },
    "kilocode": {
        "recommended_model": "z-ai/glm-5:free",
        "aliases": ["z-ai/glm-5:free"],
        "track": "free",
        "offer_track": "free",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "high",
        "evidence_level": "official",
        "official_source_url": "https://kilo.ai/docs/gateway/models-and-providers",
        "signup_url": "https://kilo.ai/",
        "watch_sources": [_COMMUNITY_WATCHLIST],
        "notes": "Current curated Kilo free-tier model; free and budget tracks can move quickly",  # noqa: E501
        "last_reviewed": "2026-03-19",
    },
    "kilo-sonnet": {
        "recommended_model": "anthropic/claude-sonnet-4.6",
        "aliases": ["anthropic/claude-sonnet-4.6", "kilo-auto/frontier", "kilo-auto/balanced"],  # noqa: E501
        "track": "stable",
        "offer_track": "gateway-paid",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://kilo.ai/docs/gateway/models-and-providers",
        "signup_url": "https://kilo.ai/",
        "watch_sources": [],
        "notes": (
            "Kilo paid Sonnet lane; useful as the workhorse path when you want "
            "Kilo credits to absorb balanced coding traffic"
        ),
        "last_reviewed": "2026-03-29",
    },
    "kilo-opus": {
        "recommended_model": "anthropic/claude-opus-4.6",
        "aliases": ["anthropic/claude-opus-4.6", "kilo-auto/frontier"],
        "track": "stable",
        "offer_track": "gateway-paid",
        "provider_type": "aggregator",
        "auth_modes": ["api_key", "byok"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://kilo.ai/docs/gateway/models-and-providers",
        "signup_url": "https://kilo.ai/",
        "watch_sources": [],
        "notes": ("Kilo paid Opus lane; useful when expiring Kilo credits should absorb premium reasoning traffic"),
        "last_reviewed": "2026-03-29",
    },
    "blackbox-free": {
        "recommended_model": "blackboxai/x-ai/grok-code-fast-1",
        "aliases": ["blackboxai/x-ai/grok-code-fast-1"],
        "track": "cheap",
        "offer_track": "credit",
        "provider_type": "aggregator",
        "auth_modes": ["api_key"],
        "volatility": "high",
        "evidence_level": "mixed",
        "official_source_url": "https://docs.blackbox.ai/api-reference/authentication",
        "signup_url": "https://cloud.blackbox.ai/",
        "watch_sources": [_COMMUNITY_WATCHLIST],
        "notes": (
            "Legacy provider id for the current low-cost BLACKBOX Grok Code Fast route; "  # noqa: E501
            "verify often because pricing and model availability can rotate"
        ),
        "last_reviewed": "2026-03-29",
    },
    "openai-gpt4o": {
        "recommended_model": "gpt-4o",
        "aliases": ["gpt-4o"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://platform.openai.com/docs/models",
        "signup_url": "https://platform.openai.com/",
        "watch_sources": [],
        "notes": "Balanced OpenAI multimodal path",
        "last_reviewed": "2026-03-19",
    },
    "openai-images": {
        "recommended_model": "gpt-image-1",
        "aliases": ["gpt-image-1"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://platform.openai.com/docs/models",
        "signup_url": "https://platform.openai.com/",
        "watch_sources": [],
        "notes": "OpenAI image generation and editing",
        "last_reviewed": "2026-03-19",
    },
    "anthropic-claude": {
        "recommended_model": "claude-opus-4-6",
        "aliases": ["claude-opus-4-6"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "signup_url": "https://console.anthropic.com/",
        "watch_sources": [],
        "notes": "Quality-first Anthropic default",
        "last_reviewed": "2026-03-19",
    },
    "anthropic-haiku": {
        "recommended_model": get_active_model_id("anthropic/haiku-4.5"),
        "aliases": ["claude-haiku-3-5"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "signup_url": "https://console.anthropic.com/",
        "watch_sources": [],
        "notes": "Fast and cheap Anthropic model",
        "last_reviewed": "2026-04-01",
    },
    "anthropic-sonnet": {
        "recommended_model": get_active_model_id("anthropic/sonnet-4.6"),
        "aliases": ["claude-sonnet-4-6"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "signup_url": "https://console.anthropic.com/",
        "watch_sources": [],
        "notes": "Balanced Anthropic model",
        "last_reviewed": "2026-04-01",
    },
    "gemini-pro-high": {
        "recommended_model": get_active_model_id("google/gemini-pro-high"),
        "aliases": ["gemini-3.1-pro"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": "High-quality Gemini Pro lane",
        "last_reviewed": "2026-04-01",
    },
    "gemini-pro-low": {
        "recommended_model": get_active_model_id("google/gemini-pro-low"),
        "aliases": ["gemini-3.1-pro"],
        "track": "stable",
        "offer_track": "direct",
        "provider_type": "direct",
        "auth_modes": ["api_key"],
        "volatility": "low",
        "evidence_level": "official",
        "official_source_url": "https://ai.google.dev/gemini-api/docs/models",
        "signup_url": "https://aistudio.google.com/",
        "watch_sources": [],
        "notes": "Balanced Gemini Pro lane",
        "last_reviewed": "2026-04-01",
    },
    "clawrouter": {
        "recommended_model": "auto",
        "aliases": ["auto", "eco", "premium", "free"],
        "track": "stable",
        "offer_track": "marketplace",
        "provider_type": "wallet-router",
        "auth_modes": ["wallet_x402"],
        "volatility": "medium",
        "evidence_level": "official",
        "official_source_url": "https://blockrun.ai/docs/products/routing/clawrouter",
        "signup_url": "https://blockrun.ai/",
        "watch_sources": [],
        "notes": "BlockRun ClawRouter uses wallet/x402 routing modes rather than a classic API key",  # noqa: E501
        "last_reviewed": "2026-03-19",
    },
}


def _normalize_catalog_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {str(key): value for key, value in entry.items()}


def _merge_catalog_entry(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:  # noqa: E501
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_catalog_entry(
                _normalize_catalog_entry(merged[key]),
                _normalize_catalog_entry(value),
            )
            continue
        merged[key] = value
    return merged


def _normalize_catalog_payload(payload: Any) -> dict[str, dict[str, Any]]:
    raw_catalog = payload.get("providers") if isinstance(payload, dict) else payload
    if not isinstance(raw_catalog, dict):
        return {}

    catalog: dict[str, dict[str, Any]] = {}
    for provider_name, entry in raw_catalog.items():
        normalized_name = str(provider_name or "").strip()
        normalized_entry = _normalize_catalog_entry(entry)
        if not normalized_name or not normalized_entry:
            continue
        catalog[normalized_name] = normalized_entry
    return catalog


def _load_catalog_payload(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_provider_metadata_snapshot(
    metadata_dir: str | Path,
    *,
    product: str = _DEFAULT_METADATA_PRODUCT,
) -> dict[str, Any]:
    root = Path(metadata_dir).expanduser()
    catalog_payload = _load_catalog_payload(root / _METADATA_CATALOG_RELATIVE_PATH)
    catalog = _normalize_catalog_payload(catalog_payload)

    product_name = str(product or _DEFAULT_METADATA_PRODUCT).strip() or _DEFAULT_METADATA_PRODUCT  # noqa: E501
    overlay_payload = _load_catalog_payload(root / "products" / product_name / "overlays.v1.json")  # noqa: E501
    overlay = _normalize_catalog_payload(overlay_payload)

    merged_catalog = dict(catalog)
    for provider_name, entry in overlay.items():
        merged_catalog[provider_name] = _merge_catalog_entry(
            merged_catalog.get(provider_name, {}),
            entry,
        )

    return {
        "schema_version": str(catalog_payload.get("schema_version") or "fusionaize-provider-catalog/v1"),
        "generated_at": str(catalog_payload.get("generated_at") or ""),
        "source_repo": str(catalog_payload.get("source_repo") or ""),
        "product": product_name,
        "providers": merged_catalog,
    }


def materialize_provider_metadata_snapshot(
    metadata_dir: str | Path,
    output_path: str | Path,
    *,
    product: str = _DEFAULT_METADATA_PRODUCT,
) -> dict[str, Any]:
    snapshot = build_provider_metadata_snapshot(metadata_dir, product=product)
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


def _load_external_provider_catalog() -> dict[str, dict[str, Any]]:
    metadata_path = str(os.environ.get(_EXTERNAL_CATALOG_ENV, "") or "").strip()
    if metadata_path:
        payload = _load_catalog_payload(metadata_path)
        return _normalize_catalog_payload(payload)

    metadata_dir = str(os.environ.get(_EXTERNAL_CATALOG_DIR_ENV, "") or "").strip()
    if not metadata_dir:
        return {}
    product = str(os.environ.get(_EXTERNAL_CATALOG_PRODUCT_ENV, _DEFAULT_METADATA_PRODUCT) or "")
    return _normalize_catalog_payload(build_provider_metadata_snapshot(metadata_dir, product=product))


def _get_catalog_source() -> dict[str, dict[str, Any]]:
    catalog = {name: dict(entry) for name, entry in _CATALOG.items()}
    for name, entry in _load_external_provider_catalog().items():
        merged = dict(catalog.get(name, {}))
        merged.update(entry)
        catalog[name] = merged
    return catalog


def _slugify_provider_name(provider_name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", provider_name.upper()).strip("_")


def _discovery_env_var(provider_name: str) -> str:
    token = _slugify_provider_name(provider_name)
    return f"FAIGATE_PROVIDER_LINK_{token}_URL"


def _build_discovery_metadata(provider_name: str, catalog_entry: dict[str, Any]) -> dict[str, Any]:  # noqa: E501
    env_var = _discovery_env_var(provider_name)
    operator_url = str(os.environ.get(env_var, "") or "").strip()
    signup_url = str(catalog_entry.get("signup_url", "") or "").strip()
    discovery_url = (
        operator_url or signup_url or str(catalog_entry.get("official_source_url", "") or "")  # noqa: E501
    )

    return {
        "signup_url": signup_url,
        "resolved_url": discovery_url,
        "link_source": "operator_override" if operator_url else "official",
        "operator_env_var": env_var,
        "disclosure": _DISCOVERY_DISCLOSURE,
        "disclosure_required": bool(operator_url),
    }


def get_provider_catalog() -> dict[str, dict[str, Any]]:
    """Return a shallow copy of the curated provider catalog."""
    payload: dict[str, dict[str, Any]] = {}
    for name, entry in _get_catalog_source().items():
        item = dict(entry)
        item["discovery"] = _build_discovery_metadata(name, entry)
        payload[name] = item
    return payload


def get_provider_catalog_entry(provider_name: str) -> dict[str, Any]:
    """Return one curated provider catalog entry with discovery metadata."""
    entry = _get_catalog_source().get(provider_name)
    if not entry:
        return {}
    item = dict(entry)
    item["discovery"] = _build_discovery_metadata(provider_name, entry)
    return item


def get_offerings_catalog() -> dict[str, Any]:
    """Return the loaded external offerings catalog (experimental)."""
    return _load_external_offerings()


def get_packages_catalog() -> dict[str, Any]:
    """Return the loaded external packages catalog (experimental)."""
    return _load_external_packages()


def get_offering_pricing(model_id: str, provider_id: str) -> dict[str, Any]:
    """Return pricing metadata for a specific model-provider offering.

    Looks up the offerings catalog for an offering matching the given model and provider.
    Returns the pricing dict if found, otherwise empty dict.
    """
    offerings = _load_external_offerings()
    for offering in offerings.values():
        if offering.get("model_id") == model_id and offering.get("provider_id") == provider_id:
            return offering.get("pricing", {})
    return {}


def _refresh_state_from_review(last_reviewed: str) -> tuple[str, int]:
    reviewed = str(last_reviewed or "").strip()
    if not reviewed:
        return "unknown", -1
    reviewed_on = date.fromisoformat(reviewed)
    age_days = max(0, (date.today() - reviewed_on).days)
    if age_days <= 7:
        return "fresh", age_days
    if age_days <= 21:
        return "aging", age_days
    return "stale", age_days


def build_provider_refresh_guidance(
    provider_names: list[str] | tuple[str, ...],
    *,
    freshness_overrides: dict[str, dict[str, Any]] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return curated refresh guidance for providers with aging or stale assumptions."""
    overrides = freshness_overrides or {}
    guidance: list[dict[str, Any]] = []
    seen: set[str] = set()

    for provider_name in provider_names:
        normalized_name = str(provider_name or "").strip()
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)

        catalog_entry = get_provider_catalog_entry(normalized_name)
        if not catalog_entry:
            continue

        override = dict(overrides.get(normalized_name) or {})
        freshness_status = str(override.get("freshness_status") or "").strip().lower()
        review_age_days_raw = override.get("review_age_days")
        review_age_days = int(review_age_days_raw) if review_age_days_raw not in (None, "") else -1  # noqa: E501
        freshness_hint = str(override.get("freshness_hint") or "").strip()

        if not freshness_status:
            freshness_status, review_age_days = _refresh_state_from_review(
                str(catalog_entry.get("last_reviewed") or "")
            )
        if freshness_status not in {"aging", "stale"}:
            continue

        discovery = dict(catalog_entry.get("discovery") or {})
        refresh_url = str(
            discovery.get("resolved_url")
            or catalog_entry.get("official_source_url")
            or catalog_entry.get("signup_url")
            or ""
        ).strip()
        action = "refresh-now" if freshness_status == "stale" else "review-soon"
        action_label = "refresh now" if action == "refresh-now" else "review soon"
        reason = freshness_hint or (
            "benchmark and cost assumptions are stale; review before trusting them heavily"  # noqa: E501
            if freshness_status == "stale"
            else "benchmark and cost assumptions are aging and worth rechecking soon"
        )
        if catalog_entry.get("volatility") in {"medium", "high"} and catalog_entry.get("offer_track") in {
            "free",
            "credit",
            "byok",
            "marketplace",
        }:
            reason += " This route also sits on a more volatile offer track."

        guidance.append(
            {
                "provider": normalized_name,
                "action": action,
                "action_label": action_label,
                "freshness_status": freshness_status,
                "review_age_days": review_age_days,
                "reason": reason,
                "refresh_url": refresh_url,
                "offer_track": str(catalog_entry.get("offer_track") or ""),
                "provider_type": str(catalog_entry.get("provider_type") or ""),
                "notes": str(catalog_entry.get("notes") or ""),
            }
        )

    guidance.sort(
        key=lambda item: (
            0 if item["action"] == "refresh-now" else 1,
            -int(item.get("review_age_days") or -1),
            str(item.get("provider") or ""),
        )
    )
    if limit is not None:
        return guidance[:limit]
    return guidance


def _alert(
    *,
    provider: str,
    severity: str,
    code: str,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "provider": provider,
        "severity": severity,
        "code": code,
        "message": message,
    }
    payload.update(extra)
    return payload


def _tracked_item(
    provider_name: str,
    provider: dict[str, Any],
    catalog_entry: dict[str, Any],
    *,
    today: date,
) -> dict[str, Any]:
    model = str(provider.get("model", "") or "").strip()
    recommended_model = str(catalog_entry["recommended_model"])
    aliases = list(catalog_entry.get("aliases", []))
    reviewed_on = date.fromisoformat(catalog_entry["last_reviewed"])
    age_days = (today - reviewed_on).days
    lane = dict(provider.get("lane") or get_provider_lane_binding(provider_name))
    canonical_catalog = get_canonical_model_catalog()
    canonical_entry = canonical_catalog.get(str(lane.get("canonical_model", "")), {})

    # Get pricing metadata
    pricing = _get_provider_pricing(provider_name)
    has_numeric_rates = (
        bool(pricing.get("input")) or bool(pricing.get("output")) or bool(pricing.get("cache_read"))  # noqa: E501
    )
    pricing_available = bool(pricing)

    return {
        "provider": provider_name,
        "configured_model": model,
        "tracked": True,
        "status": "tracked",
        "recommended_model": recommended_model,
        "track": catalog_entry.get("track", "stable"),
        "offer_track": catalog_entry.get("offer_track", "direct"),
        "provider_type": catalog_entry.get("provider_type", "direct"),
        "auth_modes": list(catalog_entry.get("auth_modes", ["api_key"])),
        "volatility": catalog_entry.get("volatility", "low"),
        "evidence_level": catalog_entry.get("evidence_level", "official"),
        "official_source_url": catalog_entry.get("official_source_url", ""),
        "signup_url": catalog_entry.get("signup_url", ""),
        "discovery": _build_discovery_metadata(provider_name, catalog_entry),
        "watch_sources": list(catalog_entry.get("watch_sources", [])),
        "notes": catalog_entry.get("notes", ""),
        "last_reviewed": catalog_entry["last_reviewed"],
        "catalog_age_days": age_days,
        "model_matches_recommendation": model == recommended_model or model in aliases,
        "canonical_model": lane.get("canonical_model", ""),
        "lane_family": lane.get("family", ""),
        "lane_name": lane.get("name", ""),
        "route_type": lane.get("route_type", ""),
        "lane_cluster": lane.get("cluster", ""),
        "benchmark_cluster": lane.get("benchmark_cluster", ""),
        "preferred_degrades": list(canonical_entry.get("preferred_degrades", lane.get("degrade_to", []))),
        "lane": lane,
        "pricing": pricing,
        "pricing_available": pricing_available,
        "has_numeric_rates": has_numeric_rates,
    }


def build_provider_catalog_report(config: Config) -> dict[str, Any]:
    """Compare configured providers against the curated provider catalog."""
    check_cfg = config.provider_catalog_check
    today = date.today()

    tracked = 0
    alerts: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    for provider_name, provider in sorted(config.providers.items()):
        model = str(provider.get("model", "") or "").strip()
        catalog_entry = get_provider_catalog_entry(provider_name)
        item: dict[str, Any] = {
            "provider": provider_name,
            "configured_model": model,
            "tracked": bool(catalog_entry),
        }

        if not catalog_entry:
            item["status"] = "untracked"
            items.append(item)
            if check_cfg.get("enabled") and check_cfg.get("warn_on_untracked"):
                alerts.append(
                    _alert(
                        provider=provider_name,
                        severity="warning",
                        code="untracked-provider",
                        message=(
                            f"Provider '{provider_name}' is not in the curated provider "  # noqa: E501
                            "catalog yet."
                        ),
                    )
                )
            continue

        tracked += 1
        item = _tracked_item(provider_name, provider, catalog_entry, today=today)
        items.append(item)

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_model_drift")
            and not item["model_matches_recommendation"]
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="warning",
                    code="model-drift",
                    message=(
                        f"Provider '{provider_name}' uses model '{model}', while the curated "  # noqa: E501
                        f"catalog recommends '{item['recommended_model']}'."
                    ),
                    recommended_model=item["recommended_model"],
                )
            )

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_unofficial_sources")
            and item["evidence_level"] != "official"
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="catalog-source-unofficial",
                    message=(
                        f"Catalog guidance for provider '{provider_name}' is backed by "
                        f"{item['evidence_level']} evidence; review the configured "
                        "model more often."
                    ),
                    official_source_url=item["official_source_url"],
                )
            )

        if (
            check_cfg.get("enabled")
            and check_cfg.get("warn_on_volatile_offers")
            and item["volatility"] in {"medium", "high"}
            and item["offer_track"] in {"free", "credit", "byok", "marketplace"}
        ):
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="volatile-offer-configured",
                    message=(
                        f"Provider '{provider_name}' is on the '{item['offer_track']}' track "  # noqa: E501
                        f"with {item['volatility']} volatility; limits, models, or "
                        "pricing may change quickly."
                    ),
                    offer_track=item["offer_track"],
                )
            )

        max_age_days = int(check_cfg.get("max_catalog_age_days", 30))
        if check_cfg.get("enabled") and item["catalog_age_days"] > max_age_days:
            alerts.append(
                _alert(
                    provider=provider_name,
                    severity="notice",
                    code="catalog-stale",
                    message=(
                        f"Catalog guidance for provider '{provider_name}' is {item['catalog_age_days']} days old."
                    ),
                    last_reviewed=item["last_reviewed"],
                )
            )

    # Calculate cost truth statistics
    cost_truth_stats = {
        "tracked_with_pricing": 0,
        "tracked_with_numeric_rates": 0,
        "pricing_freshness": {"fresh": 0, "aging": 0, "stale": 0, "unknown": 0},
        "missing_pricing": 0,
    }

    for item in items:
        if item.get("status") != "tracked":
            continue

        if item.get("pricing_available"):
            cost_truth_stats["tracked_with_pricing"] += 1

            # Check freshness from pricing metadata
            pricing = item.get("pricing", {})
            freshness = pricing.get("freshness_status", "unknown")
            if freshness in cost_truth_stats["pricing_freshness"]:
                cost_truth_stats["pricing_freshness"][freshness] += 1
            else:
                cost_truth_stats["pricing_freshness"]["unknown"] += 1

            if item.get("has_numeric_rates"):
                cost_truth_stats["tracked_with_numeric_rates"] += 1
        else:
            cost_truth_stats["missing_pricing"] += 1

    # Priority clusters based on catalog health
    priority_clusters = [
        {
            "id": "cost_truth",
            "name": "Cost truth",
            "description": "Provider pricing metadata completeness and freshness",
            "priority": "high",
            "item_count": cost_truth_stats["missing_pricing"],
            "total_items": tracked,
        },
        {
            "id": "tracked_provider_coverage",
            "name": "Tracked provider coverage",
            "description": "Providers not yet in the curated catalog",
            "priority": "medium",
            "item_count": len(config.providers) - tracked,
            "total_items": len(config.providers),
        },
        {
            "id": "provider_model_alignment",
            "name": "Provider model alignment",
            "description": "Configured models that don't match catalog recommendations",
            "priority": "medium",
            "item_count": sum(
                1
                for item in items
                if (
                    item.get("status") == "tracked" and not item.get("model_matches_recommendation")  # noqa: E501
                )
            ),
            "total_items": tracked,
        },
        {
            "id": "source_provenance_review",
            "name": "Source provenance review",
            "description": "Providers with unofficial evidence sources",
            "priority": "low",
            "item_count": sum(
                1
                for item in items
                if (item.get("status") == "tracked" and item.get("evidence_level") != "official")  # noqa: E501
            ),
            "total_items": tracked,
        },
        {
            "id": "volatile_offer_review",
            "name": "Volatile offer review",
            "description": "Providers on volatile offer tracks (free/credit/marketplace)",  # noqa: E501
            "priority": "low",
            "item_count": sum(
                1
                for item in items
                if item.get("status") == "tracked"
                and item.get("volatility") in {"medium", "high"}
                and item.get("offer_track") in {"free", "credit", "byok", "marketplace"}
            ),
            "total_items": tracked,
        },
        {
            "id": "catalog_freshness",
            "name": "Catalog freshness",
            "description": "Catalog entries older than max age threshold",
            "priority": "low",
            "item_count": sum(
                1
                for item in items
                if item.get("status") == "tracked"
                and item.get("catalog_age_days", 0) > int(check_cfg.get("max_catalog_age_days", 30))  # noqa: E501
            ),
            "total_items": tracked,
        },
    ]

    # Determine next priority (first cluster with item_count > 0)
    priority_next = None
    for cluster in priority_clusters:
        if cluster["item_count"] > 0:
            priority_next = cluster["id"]
            break

    # Generate actionable recommendations from priority clusters
    recommendations = []
    for cluster in priority_clusters:
        if cluster["item_count"] == 0:
            continue
        if cluster["id"] == "cost_truth":
            recommendations.append(
                {
                    "id": "improve_pricing_coverage",
                    "title": "Improve pricing metadata coverage",
                    "description": f"{cluster['item_count']} tracked providers lack numeric pricing rates.",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Add numeric pricing rates to external catalog for providers missing rates.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )
        elif cluster["id"] == "tracked_provider_coverage":
            recommendations.append(
                {
                    "id": "expand_catalog_coverage",
                    "title": "Expand catalog coverage",
                    "description": f"{cluster['item_count']} configured providers are not yet tracked in the catalog.",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Add catalog entries for untracked providers.",
                    "cluster_id": cluster["id"],
                }
            )
        elif cluster["id"] == "provider_model_alignment":
            recommendations.append(
                {
                    "id": "align_models_with_recommendations",
                    "title": "Align configured models with catalog recommendations",
                    "description": f"{cluster['item_count']} tracked providers have configured models that don't match catalog recommendations.",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Update provider model configurations to match catalog recommendations.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )
        elif cluster["id"] == "source_provenance_review":
            recommendations.append(
                {
                    "id": "review_evidence_sources",
                    "title": "Review evidence sources",
                    "description": f"{cluster['item_count']} tracked providers rely on unofficial evidence sources.",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Verify and potentially upgrade evidence sources to official documentation.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )
        elif cluster["id"] == "volatile_offer_review":
            recommendations.append(
                {
                    "id": "review_volatile_offers",
                    "title": "Review volatile offers",
                    "description": f"{cluster['item_count']} tracked providers are on volatile offer tracks (free/credit/marketplace).",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Monitor these providers for changes in pricing, availability, or terms.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )
        elif cluster["id"] == "catalog_freshness":
            recommendations.append(
                {
                    "id": "refresh_stale_catalog_entries",
                    "title": "Refresh stale catalog entries",
                    "description": f"{cluster['item_count']} catalog entries are older than the maximum age threshold.",  # noqa: E501
                    "priority": cluster["priority"],
                    "action": "Review and update catalog entries to ensure they reflect current provider offerings.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )
        else:
            recommendations.append(
                {
                    "id": cluster["id"],
                    "title": cluster["name"],
                    "description": cluster["description"],
                    "priority": cluster["priority"],
                    "action": f"Address {cluster['item_count']} items in this category.",  # noqa: E501
                    "cluster_id": cluster["id"],
                }
            )

    return {
        "enabled": bool(check_cfg.get("enabled")),
        "tracked_providers": tracked,
        "total_providers": len(config.providers),
        "alert_count": len(alerts),
        "cost_truth": cost_truth_stats,
        "offerings_count": len(_load_external_offerings()),
        "packages_count": len(_load_external_packages()),
        "priority_clusters": priority_clusters,
        "priority_next": priority_next,
        "recommendations": recommendations,
        "recommendation_policy": {
            "provider_links_affect_ranking": False,
            "ranking_basis": [
                "fit",
                "quality",
                "health",
                "capability",
                "cost_behavior",
            ],
            "disclosure": _DISCOVERY_DISCLOSURE,
        },
        "alerts": alerts,
        "items": items,
    }


def build_provider_discovery_view(
    config: Config,
    *,
    link_source: str | None = None,
    disclosed_only: bool = False,
    offer_track: str | None = None,
) -> dict[str, Any]:
    """Return a compact, disclosure-first provider discovery view."""
    report = build_provider_catalog_report(config)
    providers: list[dict[str, Any]] = []
    normalized_link_source = str(link_source or "").strip().lower() or None
    normalized_offer_track = str(offer_track or "").strip().lower() or None

    for item in report.get("items", []):
        discovery = item.get("discovery") or {}
        resolved_url = str(discovery.get("resolved_url", "") or "").strip()
        if not resolved_url:
            continue
        if normalized_link_source and discovery.get("link_source") != normalized_link_source:  # noqa: E501
            continue
        if disclosed_only and not discovery.get("disclosure_required", False):
            continue
        if normalized_offer_track and item.get("offer_track") != normalized_offer_track:
            continue
        providers.append(
            {
                "provider": item["provider"],
                "provider_type": item.get("provider_type", "direct"),
                "offer_track": item.get("offer_track", "direct"),
                "evidence_level": item.get("evidence_level", "official"),
                "official_source_url": item.get("official_source_url", ""),
                "signup_url": discovery.get("signup_url", ""),
                "resolved_url": resolved_url,
                "link_source": discovery.get("link_source", "official"),
                "operator_env_var": discovery.get("operator_env_var", ""),
                "disclosure": discovery.get("disclosure", ""),
                "disclosure_required": bool(discovery.get("disclosure_required", False)),  # noqa: E501
            }
        )

    return {
        "recommendation_policy": report.get("recommendation_policy", {}),
        "filters": {
            "link_source": normalized_link_source,
            "disclosed_only": disclosed_only,
            "offer_track": normalized_offer_track,
        },
        "providers": providers,
    }
