"""Helpers for local key availability overlays on top of provider source catalogs."""

from __future__ import annotations

import json
from typing import Any

from .config import load_config
from .provider_catalog_store import ProviderCatalogStore


def record_availability_from_health(
    store: ProviderCatalogStore,
    *,
    health_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Persist a light local availability overlay from the live /health payload."""
    if not health_payload:
        return []
    rows: list[dict[str, Any]] = []
    for route_name, payload in sorted((health_payload.get("providers") or {}).items()):
        request_readiness = dict(payload.get("request_readiness") or {})
        lane = dict(payload.get("lane") or {})
        provider_id = str(lane.get("family") or route_name.split("-", 1)[0] or route_name)
        store.record_availability_snapshot(
            provider_id,
            route_name,
            model_id=str(payload.get("model") or ""),
            available_for_key=bool(request_readiness.get("ready")),
            request_ready=bool(request_readiness.get("ready")),
            verified_via=str(request_readiness.get("verified_via") or ""),
            last_issue_type=str(request_readiness.get("runtime_issue_type") or ""),
            metadata={
                "status": request_readiness.get("status"),
                "reason": request_readiness.get("reason"),
                "compatibility": request_readiness.get("compatibility"),
                "profile": request_readiness.get("profile"),
            },
        )
        rows.append(
            {
                "provider_id": provider_id,
                "route_name": route_name,
                "model_id": str(payload.get("model") or ""),
                "request_ready": bool(request_readiness.get("ready")),
                "status": str(request_readiness.get("status") or ""),
            }
        )
    return rows


def load_health_payload(raw: str) -> dict[str, Any] | None:
    """Decode a serialized /health payload from a script environment."""
    token = str(raw or "").strip()
    if not token:
        return None
    return json.loads(token)


def configured_provider_families(config_path: str) -> dict[str, list[str]]:
    """Return configured provider names grouped by family-ish prefix."""
    config = load_config(config_path)
    rows: dict[str, list[str]] = {}
    for provider_name, provider in sorted(config.providers.items()):
        lane = dict(provider.get("lane") or {})
        family = str(lane.get("family") or provider_name.split("-", 1)[0] or "unknown")
        rows.setdefault(family, []).append(provider_name)
    return rows
