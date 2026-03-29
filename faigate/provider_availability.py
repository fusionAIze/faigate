"""Helpers for local key availability overlays on top of provider source catalogs."""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from .config import load_config
from .provider_catalog_store import ProviderCatalogStore
from .provider_sources import get_provider_source, resolve_provider_source_id


class JsonFetcher(Protocol):
    """Protocol for fetching provider models-endpoint payloads."""

    def fetch_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class HttpxJsonFetcher:
    """Default JSON fetcher for provider models endpoints."""

    def fetch_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return dict(response.json() or {})


def _request_readiness_from_health(
    health_payload: dict[str, Any] | None,
    route_name: str,
) -> dict[str, Any]:
    providers = dict((health_payload or {}).get("providers") or {})
    return dict((providers.get(route_name) or {}).get("request_readiness") or {})


def _configured_provider_targets(config_path: str) -> list[dict[str, Any]]:
    config = load_config(config_path)
    targets: list[dict[str, Any]] = []
    for provider_name, provider in sorted(config.providers.items()):
        targets.append(
            {
                "provider_name": provider_name,
                "provider_id": resolve_provider_source_id(provider_name, provider),
                "provider": provider,
            }
        )
    return targets


def _join_base_url(base_url: str, path: str) -> str:
    base = str(base_url or "").rstrip("/")
    suffix = str(path or "").strip()
    if not base or not suffix:
        return ""
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    if suffix.startswith("/v1/") and base.endswith("/v1"):
        return base + suffix[len("/v1") :]
    if base.endswith(suffix):
        return base
    return base + suffix


def _parse_models_payload(payload: dict[str, Any]) -> list[str]:
    rows = payload.get("data")
    if rows is None and isinstance(payload.get("models"), list):
        rows = payload.get("models")
    if rows is None and isinstance(payload.get("items"), list):
        rows = payload.get("items")
    if not isinstance(rows, list):
        return []

    visible_models: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, str):
            token = row.strip()
        elif isinstance(row, dict):
            token = str(
                row.get("id") or row.get("name") or row.get("model") or ""
            ).strip()
        else:
            token = ""
        if not token or token in seen:
            continue
        seen.add(token)
        visible_models.append(token)
    return sorted(visible_models)


def record_availability_from_config(
    store: ProviderCatalogStore,
    *,
    config_path: str,
    health_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Persist one route-state snapshot per configured provider route."""
    rows: list[dict[str, Any]] = []
    for target in _configured_provider_targets(config_path):
        provider_name = str(target["provider_name"])
        provider_id = str(target["provider_id"])
        provider = dict(target["provider"] or {})
        readiness = _request_readiness_from_health(health_payload, provider_name)
        source = get_provider_source(provider_id)
        ready = bool(readiness.get("ready"))
        store.record_availability_snapshot(
            provider_id,
            provider_name,
            source_name="route-state",
            model_id=str(provider.get("model") or ""),
            available_for_key=ready,
            request_ready=ready,
            verified_via=str(readiness.get("verified_via") or "health"),
            last_issue_type=str(readiness.get("runtime_issue_type") or ""),
            metadata={
                "status": readiness.get("status"),
                "reason": readiness.get("reason"),
                "compatibility": readiness.get("compatibility"),
                "profile": readiness.get("profile"),
                "base_url": str(provider.get("base_url") or ""),
                "backend": str(provider.get("backend") or ""),
                "catalog_provider_id": provider_id,
                "supports_models_endpoint": bool(
                    (source.get("availability") or {}).get("supports_models_endpoint")
                ),
            },
        )
        rows.append(
            {
                "provider_id": provider_id,
                "route_name": provider_name,
                "model_id": str(provider.get("model") or ""),
                "request_ready": ready,
                "status": str(readiness.get("status") or ""),
            }
        )
    return rows


def record_availability_from_health(
    store: ProviderCatalogStore,
    *,
    config_path: str | None = None,
    health_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Persist a local availability overlay from the live /health payload."""
    if not health_payload:
        return []
    if config_path:
        return record_availability_from_config(
            store,
            config_path=config_path,
            health_payload=health_payload,
        )

    rows: list[dict[str, Any]] = []
    for route_name, payload in sorted((health_payload.get("providers") or {}).items()):
        request_readiness = dict(payload.get("request_readiness") or {})
        lane = dict(payload.get("lane") or {})
        provider_id = resolve_provider_source_id(route_name, {"lane": lane})
        store.record_availability_snapshot(
            provider_id,
            route_name,
            source_name="route-state",
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


def refresh_local_model_availability(
    store: ProviderCatalogStore,
    *,
    config_path: str,
    provider_ids: list[str] | None = None,
    fetcher: JsonFetcher | None = None,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """Refresh local models-endpoint visibility for configured routes."""
    fetcher = fetcher or HttpxJsonFetcher()
    allowed_provider_ids = set(provider_ids or [])
    results: list[dict[str, Any]] = []

    for target in _configured_provider_targets(config_path):
        provider_name = str(target["provider_name"])
        provider_id = str(target["provider_id"])
        if allowed_provider_ids and provider_id not in allowed_provider_ids:
            continue

        source = get_provider_source(provider_id)
        availability = dict(source.get("availability") or {})
        if not availability.get("supports_models_endpoint"):
            continue

        provider = dict(target["provider"] or {})
        base_url = str(provider.get("base_url") or "").strip()
        api_key = str(provider.get("api_key") or "").strip()
        if not base_url or not api_key:
            continue

        configured_model = str(provider.get("model") or "").strip()
        models_paths = list(availability.get("models_paths") or [])
        visible_models: list[str] = []
        resolved_url = ""
        last_error = ""

        for models_path in models_paths:
            resolved_url = _join_base_url(base_url, str(models_path))
            if not resolved_url:
                continue
            try:
                payload = fetcher.fetch_json(
                    resolved_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                    timeout_seconds=timeout_seconds,
                )
                visible_models = _parse_models_payload(payload)
                if visible_models:
                    last_error = ""
                    break
                last_error = "empty models payload"
            except Exception as exc:  # pragma: no cover - defensive runtime path
                last_error = str(exc)

        available_for_key = bool(
            configured_model and configured_model in visible_models
        )
        last_issue_type = ""
        if configured_model and visible_models and not available_for_key:
            last_issue_type = "model-unavailable"
        elif last_error:
            last_issue_type = "models-endpoint-error"

        store.record_availability_snapshot(
            provider_id,
            provider_name,
            source_name="models-endpoint",
            model_id=configured_model,
            available_for_key=available_for_key,
            request_ready=available_for_key,
            verified_via=resolved_url or "models-endpoint",
            last_issue_type=last_issue_type,
            metadata={
                "catalog_provider_id": provider_id,
                "base_url": base_url,
                "models_endpoint_url": resolved_url,
                "visible_models": visible_models,
                "visible_model_count": len(visible_models),
                "last_error": last_error,
            },
        )
        results.append(
            {
                "provider_id": provider_id,
                "route_name": provider_name,
                "model_id": configured_model,
                "available_for_key": available_for_key,
                "visible_model_count": len(visible_models),
                "last_error": last_error,
            }
        )
    return results


def build_provider_availability_overlay(
    store: ProviderCatalogStore,
    *,
    provider_id: str,
    global_model_ids: set[str] | None = None,
    global_free_model_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Compare local route and key visibility against global catalog data."""
    route_rows = store.get_latest_availability(
        provider_id=provider_id,
        source_name="route-state",
    )
    endpoint_rows = store.get_latest_availability(
        provider_id=provider_id,
        source_name="models-endpoint",
    )
    endpoint_by_route = {str(row.get("route_name") or ""): row for row in endpoint_rows}
    visible_models: set[str] = set()
    key_model_mismatches: list[dict[str, Any]] = []

    for row in endpoint_rows:
        metadata = dict(row.get("metadata") or {})
        route_visible_models = {
            str(item).strip()
            for item in list(metadata.get("visible_models") or [])
            if str(item).strip()
        }
        visible_models.update(route_visible_models)
        configured_model = str(row.get("model_id") or "")
        if (
            configured_model
            and route_visible_models
            and configured_model not in route_visible_models
        ):
            key_model_mismatches.append(
                {
                    "route_name": str(row.get("route_name") or ""),
                    "model_id": configured_model,
                    "visible_model_count": len(route_visible_models),
                }
            )

    configured_models = {
        str(row.get("model_id") or "").strip()
        for row in route_rows
        if str(row.get("model_id") or "").strip()
    }
    global_models = set(global_model_ids or set())
    global_free_models = set(global_free_model_ids or set())

    configured_models_missing_globally = sorted(
        model_id
        for model_id in configured_models
        if global_models and model_id not in global_models
    )
    local_only_models = sorted(
        model_id
        for model_id in visible_models
        if global_models and model_id not in global_models
    )
    free_models_missing_locally = sorted(
        model_id
        for model_id in global_free_models
        if visible_models and model_id not in visible_models
    )

    status = "clear"
    if key_model_mismatches:
        status = "intervention-needed"
    elif configured_models_missing_globally or free_models_missing_locally:
        status = "review-needed"
    elif local_only_models:
        status = "informational"

    route_details: list[dict[str, Any]] = []
    for row in route_rows:
        endpoint_row = endpoint_by_route.get(str(row.get("route_name") or ""))
        endpoint_meta = dict((endpoint_row or {}).get("metadata") or {})
        route_meta = dict(row.get("metadata") or {})
        route_details.append(
            {
                "route_name": str(row.get("route_name") or ""),
                "model_id": str(row.get("model_id") or ""),
                "request_ready": bool(row.get("request_ready")),
                "status": str(route_meta.get("status") or ""),
                "available_for_key": bool(
                    (endpoint_row or {}).get("available_for_key")
                ),
                "visible_model_count": int(
                    endpoint_meta.get("visible_model_count") or 0
                ),
                "models_endpoint_error": str(endpoint_meta.get("last_error") or ""),
            }
        )

    return {
        "status": status,
        "local_routes": len(route_rows),
        "request_ready_routes": sum(
            1 for row in route_rows if row.get("request_ready")
        ),
        "models_endpoint_routes": len(endpoint_rows),
        "visible_model_count": len(visible_models),
        "visible_models": sorted(visible_models),
        "configured_models": sorted(configured_models),
        "configured_models_missing_globally": configured_models_missing_globally,
        "key_model_mismatches": key_model_mismatches,
        "local_only_models": local_only_models,
        "global_free_models": sorted(global_free_models),
        "free_models_visible_locally": len(global_free_models & visible_models),
        "free_models_missing_locally": free_models_missing_locally,
        "route_details": route_details,
    }


def load_health_payload(raw: str) -> dict[str, Any] | None:
    """Decode a serialized /health payload from a script environment."""
    token = str(raw or "").strip()
    if not token:
        return None
    return json.loads(token)


def configured_provider_families(config_path: str) -> dict[str, list[str]]:
    """Return configured provider names grouped by source-catalog family."""
    rows: dict[str, list[str]] = {}
    for target in _configured_provider_targets(config_path):
        rows.setdefault(str(target["provider_id"] or "unknown"), []).append(
            str(target["provider_name"])
        )
    return rows
