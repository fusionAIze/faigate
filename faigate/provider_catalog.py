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
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import registry
from .catalog_views import split_catalog_facts
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


_CATALOG_RESOLVER: Any = None


def _resolve_catalog_via_chain() -> dict[str, Any]:
    """Return the provider entries of the single catalog chain.

    Kept as a thin alias so callers written against the earlier name keep
    working; it no longer runs a second, remote-first resolver chain (that chain
    made the same on-disk state resolve differently depending on the entry
    point). See :func:`_resolve_catalog_payload`.
    """
    return _resolve_catalog_payload().get("providers", {})


def _load_external_catalog() -> dict[str, Any]:
    """Return the resolved catalog's provider entries.

    Delegates to the single chain (:func:`_resolve_catalog_payload`). The
    mtime cache only memoises the cheap ``stat`` on the override file; the
    bundled snapshot has its own in-process cache in ``catalog_resolver``.
    """
    global _EXTERNAL_CATALOG_CACHE, _EXTERNAL_CATALOG_MTIME

    catalog_path = _get_external_catalog_path()

    # Fast path: memoise the file read while it exists and is unchanged.
    if _EXTERNAL_CATALOG_CACHE is not None and catalog_path.exists():
        current_mtime = catalog_path.stat().st_mtime
        if current_mtime <= _EXTERNAL_CATALOG_MTIME:
            return _EXTERNAL_CATALOG_CACHE
        _EXTERNAL_CATALOG_CACHE = None

    providers = _resolve_catalog_via_chain()
    if catalog_path.exists():
        _EXTERNAL_CATALOG_CACHE = providers
        _EXTERNAL_CATALOG_MTIME = catalog_path.stat().st_mtime
    return providers


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
                if isinstance(value, int | float) and value > 0 and field not in pricing:  # noqa: E501
                    pricing[field] = float(value)

    return pricing


def _get_pricing_for_provider_and_model(provider_name: str, model_id: str | None = None) -> dict[str, Any]:
    """Get pricing metadata for a provider and optional specific model.

    First tries the offerings catalog for the exact model-provider pair.
    If not found, falls back to provider-level pricing.
    """
    # If model_id is provided, try offerings catalog
    if model_id:
        offering_pricing = get_offering_pricing(model_id, provider_name)
        if offering_pricing:
            # Normalize field names (same mapping as in _get_provider_pricing)
            field_mapping = {
                "input_cost_per_1m": "input",
                "output_cost_per_1m": "output",
                "cache_read_cost_per_1m": "cache_read",
            }
            normalized = {}
            for src, dst in field_mapping.items():
                if src in offering_pricing and dst not in offering_pricing:
                    normalized[dst] = offering_pricing[src]
                elif dst in offering_pricing:
                    normalized[dst] = offering_pricing[dst]
            # Preserve other fields (source_type, freshness_status, etc.)
            for key, value in offering_pricing.items():
                if key not in normalized:
                    normalized[key] = value
            return normalized
    # Fall back to provider-level pricing
    return _get_provider_pricing(provider_name)


def _get_packages_for_provider(provider_name: str) -> list[dict[str, Any]]:
    """Return active packages for a provider from the packages catalog."""
    packages_catalog = get_packages_catalog()
    provider_packages = []
    for package_id, package in packages_catalog.items():
        if package.get("provider_id") == provider_name:
            provider_packages.append(package)
    return provider_packages


# Wiring only: the recommended_model that is derived at runtime from the lane
# registry. Every other field these providers used to carry inline is a fact
# and now lives in the bundled/external catalog snapshot. This table is no
# longer a provider knowledge table — it is the one remaining piece of runtime
# wiring that cannot be a catalog fact: which concrete model a canonical lane
# prefers to serve today is decided by :func:`faigate.lane_registry.get_active_model_id`,
# not by a data file.
# The lane a provider routes through, for the providers that route through one.
# Both values are wiring, not facts: they resolve against the lane registry at
# import time and change when the registry changes, which is why they cannot
# live in a published fact catalog.
_LANE_LABELS: dict[str, str] = {
    "deepseek-chat": "deepseek/chat",
    "deepseek-reasoner": "deepseek/reasoner",
    "gemini-flash": "google/gemini-flash",
    "gemini-flash-lite": "google/gemini-flash-lite",
}

_CATALOG: dict[str, Any] = {
    "deepseek-chat": get_active_model_id("deepseek/chat"),
    "deepseek-reasoner": get_active_model_id("deepseek/reasoner"),
    "gemini-flash-lite": get_active_model_id("google/gemini-flash-lite"),
    "gemini-flash": get_active_model_id("google/gemini-flash"),
    "anthropic-haiku": get_active_model_id("anthropic/haiku-4.5"),
    "anthropic-sonnet": get_active_model_id("anthropic/sonnet-4.6"),
    "gemini-pro-high": get_active_model_id("google/gemini-pro-high"),
    "gemini-pro-low": get_active_model_id("google/gemini-pro-low"),
}


def _normalize_model_version_separators(model_id: str) -> str:
    """Treat ``.`` and ``-`` as equal *inside digit groups*.

    A version like ``4.6`` and ``4-6`` name the same release, but ``gpt-4o``
    and ``gpt-4-o`` are different names. The rule therefore only rewrites a
    separator that sits between two digits (``4.6`` -> ``4-6``), never the
    ``4.o`` in a name suffix. This is the same idea the caps chain uses to
    normalise a requested trailing model id before lookup.
    """
    if not model_id:
        return model_id
    return re.sub(r"(\d)\.(\d)", r"\1-\2", model_id)


def _model_lookup_keys(candidate: str) -> list[str]:
    """Return the candidate spellings a cap lookup should try for one model id.

    The catalogs key caps by the trailing model id (``gpt-5.6-sol``) and by the
    full ``provider/model`` form. Both spellings are tried, each additionally
    normalised so ``claude-opus-4.6`` and ``claude-opus-4-6`` answer the same
    fact. Order matters: exact spelling first, normalised second, provider model
    form before its normalised variant.
    """
    tail = candidate.rsplit("/", 1)[-1]
    keys: list[str] = []
    for value in (tail, candidate):
        if value and value not in keys:
            keys.append(value)
        normalised = _normalize_model_version_separators(value)
        if normalised and normalised not in keys:
            keys.append(normalised)
    return keys


def _resolve_catalog_payload() -> dict[str, Any]:
    """Resolve the catalog payload through the one and only chain.

    ``env-override (FAIGATE_PROVIDER_METADATA_FILE) → metadata-dir
    (FAIGATE_PROVIDER_METADATA_DIR) → bundled snapshot``.

    This is the single implementation every catalog reader goes through. The
    previous shape had two competing chains for the same data — a provider-only
    loader that returned ``{}`` on a dead override, and a payload loader that
    read the bundled asset — so the same on-disk state produced different
    answers depending on which helper a caller used.

    A set-but-empty or non-existent override is a broken pointer, not a claim
    that the catalog is empty. Each link contributes only if it actually yields
    a payload; otherwise resolution continues to the next link, ending at the
    bundled snapshot shipped in ``faigate/assets/metadata/catalog.v1.json``. The
    chain therefore never returns ``{}`` unless even the bundled asset is
    unreadable (a packaging failure, not a missing configuration).
    """
    metadata_path = str(os.environ.get(_EXTERNAL_CATALOG_ENV, "") or "").strip()
    if metadata_path:
        payload = _load_catalog_payload(metadata_path)
        if payload:
            return payload

    metadata_dir = str(os.environ.get(_EXTERNAL_CATALOG_DIR_ENV, "") or "").strip()
    if metadata_dir:
        root = Path(metadata_dir).expanduser()
        payload = _load_catalog_payload(root / _METADATA_CATALOG_RELATIVE_PATH)
        if payload:
            return payload

    try:
        from .catalog_resolver import _load_bundled_snapshot
    except Exception:  # pragma: no cover - defensive
        return {}
    bundled = _load_bundled_snapshot()
    return bundled if isinstance(bundled, dict) else {}


def _load_external_catalog_payload() -> dict[str, Any]:
    """Return the full resolved catalog payload (not just ``providers``).

    ``providers`` is only one top-level block of ``catalog.v1.json``. The model
    knowledge cut migrates input-token ceilings into a sibling top-level block,
    ``model_caps``, which a provider-only reader drops. This accessor preserves
    the whole payload so those sibling blocks stay reachable through the same
    chain every other catalog reader uses, without a second chain.
    """
    return _resolve_catalog_payload()


def _load_external_model_caps() -> dict[str, Any]:
    """Return the catalog's top-level ``model_caps`` block, or ``{}``.

    The block is model-keyed and optional. A catalog without it (or no catalog
    at all) yields ``{}``; the caller is responsible for deciding what to do
    when no cap is recorded (typically returning ``None``).
    """
    payload = _load_external_catalog_payload()
    model_caps = payload.get("model_caps")
    return model_caps if isinstance(model_caps, dict) else {}


def _model_caps_index() -> dict[str, int]:
    """Build a model-id → max_input_tokens index of *enforceable* caps.

    The ``model_caps`` block is model-keyed (unlike ``providers``, which is
    provider-keyed) — the input ceiling is a property of the concrete model, not
    of any single provider. Only caps that reach the ``enforceable`` view of
    :func:`faigate.catalog_views.split_catalog_facts` are indexed, and that is
    exactly the ``confirmed`` ones. A ``plausible`` cap is best-effort and an
    ``unconfirmed`` one is a non-claim, so neither belongs in an index whose
    consumers treat a hit as a hard boundary. A cap with a missing or
    unrecognised ``evidence`` block is unverified by construction and is
    therefore excluded as well — a hand-written or freshly imported entry is
    the shape that most often arrives without evidence, and it must not be
    enforced merely because nobody wrote down where it came from. The view
    split is the single definition of that boundary; this accessor keeps no
    second copy of the rule.

    A missing or empty block contributes nothing; the caller receives ``None``
    for any model absent from the catalog or present only with a non-
    enforceable cap.
    """
    index: dict[str, int] = {}
    model_caps = _load_external_model_caps()
    for model_id, fact in model_caps.items():
        if not isinstance(fact, dict):
            continue
        cap = fact.get("max_input_tokens")
        if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
            continue
        key = str(model_id)
        if key not in split_catalog_facts({key: fact}).enforceable:
            continue
        index[key] = cap
    return index


def get_model_max_input_tokens(model_id: str) -> int | None:
    """Return the enforceable max_input_tokens for a concrete model ID.

    The catalog's top-level ``model_caps`` block is the only source: a cap can
    be updated without a code change. When the catalog has no entry for the
    model, ``None`` is returned — no embedded fallback is consulted.

    A cap counts only when its ``evidence.level`` lets it reach the
    ``enforceable`` view: ``confirmed`` does, while ``plausible`` (best-effort)
    and ``unconfirmed`` (a non-claim) do not. The function is named for the
    boundary its consumers rely on — the router treats a hit as a hard filter
    and the capacity calculator treats it as a true ceiling — so it must not
    answer with a number the evidence does not support. For the raw fact use
    :func:`get_model_input_cap_fact`, which reports the level and leaves the
    view decision to the caller.

    Normalises the common ``provider/model`` form to the trailing model id, then
    tries the raw id, so both ``openrouter/gpt-5.6-sol`` and ``gpt-5.6-sol``
    resolve. Version separators are also normalised (``claude-opus-4.6`` ==
    ``claude-opus-4-6``) so a dot-form request answers from a hyphen-form
    catalog entry. Returns ``None`` when the catalog records no enforceable cap.
    """
    if not model_id:
        return None
    candidate = str(model_id).strip()
    if not candidate:
        return None
    keys = _model_lookup_keys(candidate)
    catalog_index = _model_caps_index()
    for key in keys:
        if key in catalog_index:
            return catalog_index[key]
    return None


def get_model_input_cap_fact(model_id: str) -> dict[str, Any] | None:
    """Return one model's max_input_tokens as an evidence-tagged fact, or ``None``.

    Where :func:`get_model_max_input_tokens` answers only for caps the evidence
    lets the runtime enforce, this function reports the fact as recorded and
    leaves the level visible. The catalog is the only authority: a cap sourced
    from the catalog's ``model_caps`` block carries the block's own
    ``evidence.level``, whether that is ``confirmed`` (a sourced fact),
    ``plausible``, or ``unconfirmed``. An id absent from the catalog returns
    ``None`` — never the provider-wide 262144 floor, which is a placeholder, not
    a per-model truth.

    Version-separator spellings are normalised on lookup (``claude-opus-4.6`` ==
    ``claude-opus-4-6``) so a dot-form request answers the hyphen-form catalog
    entry.

    The returned dict is shaped for :func:`faigate.catalog_views.split_catalog_facts`,
    so a consumer can separate ``confirmed`` (hard) from ``plausible`` (advisory)
    facts with no second piece of view-splitting logic.
    """
    if model_id is None:
        return None
    candidate = str(model_id).strip()
    if not candidate:
        return None
    keys = _model_lookup_keys(candidate)

    model_caps = _load_external_model_caps()
    for key in keys:
        entry = model_caps.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("max_input_tokens"), int):
            cap = entry["max_input_tokens"]
            evidence = entry.get("evidence")
            if not isinstance(evidence, dict):
                evidence = {"level": "unconfirmed"}
            return {"max_input_tokens": cap, "evidence": dict(evidence)}

    return None


def _external_catalog_explicitly_configured() -> bool:
    """True when an operator set an explicit catalog override, not the fallback.

    When ``FAIGATE_PROVIDER_METADATA_FILE`` or ``FAIGATE_PROVIDER_METADATA_DIR``
    is set, the operator deliberately pointed at a catalog. Without either, the
    bundled snapshot is used. Retained as a public signal for callers that want
    to distinguish operator-driven catalogs from the shipped fallback.
    """
    if str(os.environ.get(_EXTERNAL_CATALOG_ENV, "") or "").strip():
        return True
    return bool(str(os.environ.get(_EXTERNAL_CATALOG_DIR_ENV, "") or "").strip())


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
    root = Path(metadata_dir).expanduser()
    source_catalog = (root / _METADATA_CATALOG_RELATIVE_PATH).resolve()
    destination = Path(output_path).expanduser().resolve()
    if destination == source_catalog:
        raise ValueError(
            "materializer refuses to overwrite the source catalog "
            f"{source_catalog}; choose a dedicated output path instead"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


def _load_external_provider_catalog() -> dict[str, dict[str, Any]]:
    """Return the provider entries of the resolved catalog.

    Same chain as every other catalog reader (:func:`_resolve_catalog_payload`);
    this accessor only projects the ``providers`` block. It used to have its own
    env-only chain that never consulted the bundled snapshot and returned ``{}``
    when the override pointed at nothing — see the chain tests.
    """
    metadata_dir = str(os.environ.get(_EXTERNAL_CATALOG_DIR_ENV, "") or "").strip()
    if metadata_dir and not str(os.environ.get(_EXTERNAL_CATALOG_ENV, "") or "").strip():
        # A metadata directory is a repository, not a bare catalog: apply the
        # product overlay the same way the sync/materializer path does. A dir
        # without a catalog file yields nothing here and falls through to the
        # bundled snapshot, exactly like the shared chain does.
        product = str(os.environ.get(_EXTERNAL_CATALOG_PRODUCT_ENV, _DEFAULT_METADATA_PRODUCT) or "")
        catalog = _normalize_catalog_payload(
            build_provider_metadata_snapshot(metadata_dir, product=product)
        )
        if catalog:
            return catalog
    return _normalize_catalog_payload(_resolve_catalog_payload())


def _get_catalog_source() -> dict[str, dict[str, Any]]:
    # The wiring table (:data:`_CATALOG`) holds only the lane-derived
    # ``recommended_model`` for providers that route through a canonical lane.
    # It is the *base*: the resolved catalog (bundled or external) then overlays
    # its facts on top, exactly as before the table shed its fact fields. That
    # keeps operator overrides authoritative — an external catalog that names a
    # ``recommended_model`` still wins over the lane-derived default, and a
    # provider the catalog does not carry is seeded from wiring alone.
    catalog: dict[str, dict[str, Any]] = {
        name: {"recommended_model": str(recommended_model)}
        for name, recommended_model in _CATALOG.items()
        if isinstance(recommended_model, (str, int, float))
    }
    for name, entry in _load_external_provider_catalog().items():
        merged = dict(catalog.get(name, {}))
        merged.update(entry)
        catalog[name] = merged

    # The active lane's label is resolved at read time, not at import time, and
    # it gets its own key. It used to be written into ``notes``, where it sat
    # beside static prose under the same name — one field, two meanings,
    # depending on which provider you looked at.
    for name, lane in _LANE_LABELS.items():
        if name in catalog:
            catalog[name]["active_model_label"] = get_active_model_label(lane)
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


def catalog_provider_identities() -> list[dict[str, Any]]:
    """Return the catalog's split identity fields, one dict per provider entry.

    The bundled/external catalog carries ``vendor`` / ``model`` (plus optional
    ``hop`` / ``variant``) per provider. This is the authoritative identity
    source: it is read through the same env-override → metadata-dir → bundled
    chain the caps use, so a provider that lives only in the catalog (and not in
    the static ``registry.ALL``) still contributes an identity. Entries without
    both ``vendor`` and ``model`` are skipped, never guessed.
    """
    payload = _load_external_catalog_payload()
    raw_catalog = payload.get("providers")
    if not isinstance(raw_catalog, dict):
        return []
    identities: list[dict[str, Any]] = []
    for entry in raw_catalog.values():
        if not isinstance(entry, dict):
            continue
        vendor = str(entry.get("vendor") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not vendor or not model:
            continue
        identities.append(
            {
                "vendor": vendor,
                "model": model,
                "hop": [str(seg) for seg in (entry.get("hop") or []) if str(seg)],
                "variant": str(entry.get("variant") or "").strip(),
            }
        )
    return identities


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


def _check_promotion_expiry(pricing: dict[str, Any], provider: str) -> dict[str, Any] | None:
    """Check if a promotion is about to expire and return an alert if needed."""
    expires_at = pricing.get("expires_at")
    if not expires_at:
        return None
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now = datetime.now(expiry.tzinfo) if expiry.tzinfo else datetime.now()
        days_left = (expiry - now).days
        if days_left < 0:
            return _alert(
                provider=provider,
                severity="notice",
                code="promotion-expired",
                message=(
                    f"Promotion '{pricing.get('promotion', 'unknown')}' for provider '{provider}' "
                    f"expired {abs(days_left)} days ago."
                ),
                promotion=pricing.get("promotion"),
                expires_at=expires_at,
                days_overdue=abs(days_left),
            )
        elif days_left <= 7:
            return _alert(
                provider=provider,
                severity="notice",
                code="promotion-expiring-soon",
                message=(
                    f"Promotion '{pricing.get('promotion', 'unknown')}' for provider '{provider}' "
                    f"expires in {days_left} days."
                ),
                promotion=pricing.get("promotion"),
                expires_at=expires_at,
                days_left=days_left,
            )
    except (ValueError, TypeError):
        # If date parsing fails, ignore
        pass
    return None


def _tracked_item(
    provider_name: str,
    provider: dict[str, Any],
    catalog_entry: dict[str, Any],
    *,
    today: date,
) -> dict[str, Any]:
    model = str(provider.get("model", "") or "").strip()
    recommended_model_raw = catalog_entry.get("recommended_model")
    recommended_model = str(recommended_model_raw) if recommended_model_raw else None
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
        "model_matches_recommendation": (
            None
            if recommended_model is None
            else (model == recommended_model or model in aliases)
        ),
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
            and item["model_matches_recommendation"] is False
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

        # Promotion expiry check
        if check_cfg.get("enabled") and item.get("pricing_available"):
            pricing = item.get("pricing", {})
            promotion_alert = _check_promotion_expiry(pricing, provider_name)
            if promotion_alert:
                alerts.append(promotion_alert)

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
                    item.get("status") == "tracked"
                    and item.get("model_matches_recommendation") is False
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
