"""Fetch and refresh provider model catalogs from official source pages."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .provider_availability import build_provider_availability_overlay
from .provider_catalog_store import ProviderCatalogStore
from .provider_sources import list_provider_sources


class TextFetcher(Protocol):
    """Protocol for fetching catalog source documents."""

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str: ...


class HttpxTextFetcher:
    """Default HTTP text fetcher."""

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str:
        timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text


@dataclass
class RefreshResult:
    provider_id: str
    endpoint_kind: str
    url: str
    ok: bool
    models_count: int = 0
    changes_count: int = 0
    error: str = ""


_SEVERITY_RANK = {
    "critical": 3,
    "warning": 2,
    "notice": 1,
    "info": 0,
}


def _source_due_severity(item: dict[str, Any]) -> str:
    """Escalate overdue source drift when it has lingered well past refresh cadence."""
    refresh_interval_seconds = max(
        int(item.get("refresh_interval_seconds") or 21600),
        1,
    )
    seconds_since_success = item.get("seconds_since_success")
    last_success_at = float(item.get("last_success_at") or 0.0)

    if seconds_since_success is None:
        return "warning"

    if not last_success_at and float(seconds_since_success or 0.0) <= 0.0:
        return "warning"

    age_seconds = float(seconds_since_success or 0.0)
    hard_overdue_threshold = max(refresh_interval_seconds * 3, 86400)
    if age_seconds >= hard_overdue_threshold:
        return "warning"
    return "notice"


def _catalog_alert_action(
    *,
    kind: str,
    severity: str,
    change_type: str = "",
) -> str:
    if kind == "source-refresh-error" or severity in {"critical", "warning"}:
        return "fix-now"
    if kind == "source-refresh-due":
        return "review-now"
    if kind == "catalog-change" and change_type in {"model-removed", "field-changed"}:
        return "review-now"
    return "inspect"


def _source_refresh_suggestion(item: dict[str, Any]) -> str:
    provider_id = str(item.get("provider_id") or "provider")
    if item.get("last_error"):
        return (
            "Run faigate-provider-catalog --refresh "
            f"--provider {provider_id} and verify the source URL, parser, or "
            "auth assumptions before trusting catalog data here."
        )
    return f"Refresh {provider_id} before relying on older model, pricing, or free-tier assumptions."


def _catalog_change_suggestion(event: dict[str, Any]) -> str:
    change_type = str(event.get("change_type") or "")
    provider_id = str(event.get("provider_id") or "provider")
    if change_type == "model-removed":
        return f"Review configured model ids and fallback mirrors for {provider_id}; one catalog entry disappeared."
    if change_type == "field-changed":
        return f"Recheck pricing, context, and routing weights for {provider_id}; a tracked field changed."
    if change_type == "model-added":
        return f"Review whether the newly listed {provider_id} model belongs in route additions or scenarios."
    return f"Review recent provider catalog changes for {provider_id}."


def _sync_alert_action(kind: str, severity: str) -> str:
    if severity in {"critical", "warning"} and kind in {"sync-invalid", "sync-auth"}:
        return "fix-now"
    if severity in {"critical", "warning"}:
        return "review-now"
    return "inspect"


def _build_sync_alert(tier: str, sync: dict[str, Any]) -> dict[str, Any] | None:
    status = str(sync.get("last_status") or "")
    last_error = str(sync.get("last_error") or "")
    seconds_since_success = sync.get("seconds_since_success")
    age = float(seconds_since_success) if seconds_since_success is not None else None

    kind = ""
    severity = ""
    headline = ""
    detail = ""
    suggestion = ""

    if status == "invalid":
        kind = "sync-invalid"
        severity = "critical"
        headline = f"Metadata catalog sync returned invalid {tier} payload"
        detail = last_error or "The latest remote payload failed validation and was not swapped into cache."
        suggestion = "Fix the remote catalog JSON/schema before trusting synced provider metadata."
    elif status == "auth_failed":
        kind = "sync-auth"
        severity = "warning"
        headline = f"Metadata catalog auth failed for {tier}"
        detail = last_error or "The metadata catalog request was rejected by the remote."
        suggestion = (
            "Check FAIGATE_METADATA_TOKEN permissions or remove the private URL/token if public metadata is enough."
        )
    elif age is not None and age > 7 * 86400:
        kind = "sync-stale"
        severity = "warning"
        headline = f"Metadata catalog cache is stale for {tier}"
        detail = f"The last successful metadata sync for {tier} was {int(age)}s ago."
        suggestion = "Run faigate-models update --diff and inspect remote catalog availability."
    elif status in {"error", "not_found"} and not sync.get("last_success_at"):
        kind = "sync-stale"
        severity = "warning"
        headline = f"Metadata catalog sync has not succeeded for {tier}"
        detail = last_error or f"Latest status: {status}"
        suggestion = "Run faigate-models update --diff and verify metadata catalog URLs."

    if not kind:
        return None
    return {
        "kind": kind,
        "severity": severity,
        "action": _sync_alert_action(kind, severity),
        "provider_id": f"metadata:{tier}",
        "headline": headline,
        "detail": detail,
        "suggestion": suggestion,
        "source_kind": "metadata-sync",
        "sync_tier": tier,
        "last_status": status,
    }


def build_catalog_alerts(
    summary: dict[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return structured provider source alerts ordered by urgency."""
    alerts: list[dict[str, Any]] = []
    for tier, entry in dict(summary.get("metadata_sync") or {}).items():
        sync = dict(entry.get("sync") or {})
        alert = _build_sync_alert(str(tier), sync)
        if alert is not None:
            alerts.append(alert)
    for item in list(summary.get("items") or []):
        provider_id = str(item.get("provider_id") or "")
        status = str(item.get("status") or "")
        local_availability = dict(item.get("local_availability") or {})
        if status == "error":
            action = _catalog_alert_action(
                kind="source-refresh-error",
                severity="warning",
            )
            alerts.append(
                {
                    "kind": "source-refresh-error",
                    "severity": "warning",
                    "action": action,
                    "provider_id": provider_id,
                    "headline": f"Provider source refresh failing for {provider_id}",
                    "detail": (
                        f"{provider_id} source snapshots are stale because the "
                        "latest refresh failed: "
                        f"{item.get('last_error') or 'unknown error'}"
                    ),
                    "suggestion": _source_refresh_suggestion(item),
                    "source_kind": "source",
                }
            )
        elif status == "due":
            severity = _source_due_severity(item)
            action = _catalog_alert_action(
                kind="source-refresh-due",
                severity=severity,
            )
            alerts.append(
                {
                    "kind": "source-refresh-due",
                    "severity": severity,
                    "action": action,
                    "provider_id": provider_id,
                    "headline": (
                        f"Provider source refresh overdue for {provider_id}"
                        if action == "fix-now"
                        else f"Provider source refresh due for {provider_id}"
                    ),
                    "detail": (
                        f"{provider_id} catalog data is due for refresh after "
                        f"{int(float(item.get('seconds_since_success') or 0.0))}s."
                    ),
                    "suggestion": _source_refresh_suggestion(item),
                    "source_kind": "source",
                }
            )
        if list(local_availability.get("key_model_mismatches") or []):
            mismatches = list(local_availability.get("key_model_mismatches") or [])
            mismatch = mismatches[0]
            alerts.append(
                {
                    "kind": "local-model-availability",
                    "severity": "warning",
                    "action": "fix-now",
                    "provider_id": provider_id,
                    "headline": (f"Configured route model not visible for local {provider_id} key"),
                    "detail": (
                        f"{mismatch.get('route_name')} expects "
                        f"{mismatch.get('model_id')}, but the latest local "
                        f"models endpoint did not list it "
                        f"({mismatch.get('visible_model_count')} visible models)."
                    ),
                    "suggestion": (
                        "Verify the configured model id and local key for "
                        f"{mismatch.get('route_name')} "
                        "before trusting this route as request-ready."
                    ),
                    "source_kind": "local-availability",
                }
            )
        if list(local_availability.get("configured_models_missing_globally") or []):
            missing_model = str(local_availability["configured_models_missing_globally"][0])
            alerts.append(
                {
                    "kind": "catalog-route-mismatch",
                    "severity": "warning",
                    "action": "review-now",
                    "provider_id": provider_id,
                    "headline": (f"Configured {provider_id} model missing from mirrored global catalog"),
                    "detail": (
                        f"The configured model '{missing_model}' is not present "
                        "in the latest "
                        f"mirrored {provider_id} source snapshot."
                    ),
                    "suggestion": (
                        f"Review whether {missing_model} is still the intended "
                        "model id or "
                        "whether the provider source mirror needs to be refreshed."
                    ),
                    "source_kind": "local-availability",
                }
            )
        if list(local_availability.get("local_only_models") or []):
            local_only = str(local_availability["local_only_models"][0])
            alerts.append(
                {
                    "kind": "local-model-drift",
                    "severity": "notice",
                    "action": "inspect",
                    "provider_id": provider_id,
                    "headline": (f"Local {provider_id} key exposes models missing from mirrored docs"),
                    "detail": (
                        f"The local models endpoint exposed '{local_only}', "
                        "which is not in the "
                        "latest mirrored global source snapshot."
                    ),
                    "suggestion": (
                        f"Inspect whether {provider_id} docs are lagging or "
                        "whether the local key "
                        "is on a newer provider track."
                    ),
                    "source_kind": "local-availability",
                }
            )
        if (
            int(local_availability.get("models_endpoint_routes") or 0) > 0
            and int(local_availability.get("free_models_visible_locally") or 0) == 0
            and list(local_availability.get("global_free_models") or [])
        ):
            free_model = str(local_availability["global_free_models"][0])
            alerts.append(
                {
                    "kind": "free-model-unavailable",
                    "severity": "notice",
                    "action": "review-now",
                    "provider_id": provider_id,
                    "headline": (f"Free {provider_id} catalog entries are not visible for this key"),
                    "detail": (
                        f"The mirrored global catalog still lists '{free_model}' "
                        "as free, but the latest local models endpoint did not "
                        "expose any mirrored free model."
                    ),
                    "suggestion": (
                        f"Treat free-tier assumptions for {provider_id} as "
                        "key-specific and verify "
                        "whether this route should stay in low-cost fallback chains."
                    ),
                    "source_kind": "local-availability",
                }
            )
    for event in list(summary.get("recent_events") or []):
        severity = str(event.get("severity") or "notice")
        change_type = str(event.get("change_type") or "")
        alerts.append(
            {
                "kind": "catalog-change",
                "severity": severity,
                "action": _catalog_alert_action(
                    kind="catalog-change",
                    severity=severity,
                    change_type=change_type,
                ),
                "provider_id": str(event.get("provider_id") or ""),
                "headline": (f"Catalog change detected for {event.get('provider_id')}: {event.get('change_type')}"),
                "detail": str(event.get("message") or "").strip() or "A provider catalog change was detected.",
                "suggestion": _catalog_change_suggestion(event),
                "source_kind": str(event.get("source_kind") or ""),
                "change_type": change_type,
                "model_id": str(event.get("model_id") or ""),
            }
        )
    alerts.sort(
        key=lambda alert: (
            _SEVERITY_RANK.get(str(alert.get("severity") or "notice"), 1),
            1 if alert.get("kind") == "source-refresh-error" else 0,
            str(alert.get("provider_id") or ""),
        ),
        reverse=True,
    )
    return alerts[:limit]


def build_catalog_alert_summary(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact operator-facing counts and intervention status."""
    severity_counts = {"critical": 0, "warning": 0, "notice": 0, "info": 0}
    action_counts = {"fix-now": 0, "review-now": 0, "inspect": 0}
    for alert in alerts:
        severity = str(alert.get("severity") or "notice")
        action = str(alert.get("action") or "inspect")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1

    status = "clear"
    if action_counts.get("fix-now", 0) > 0:
        status = "intervention-needed"
    elif action_counts.get("review-now", 0) > 0:
        status = "review-needed"
    elif action_counts.get("inspect", 0) > 0:
        status = "informational"

    top_alert = alerts[0] if alerts else {}
    return {
        "status": status,
        "total": len(alerts),
        "fix_now": action_counts.get("fix-now", 0),
        "review_now": action_counts.get("review-now", 0),
        "inspect": action_counts.get("inspect", 0),
        "severity": severity_counts,
        "top_headline": str(top_alert.get("headline") or ""),
        "top_suggestion": str(top_alert.get("suggestion") or ""),
    }


def build_catalog_summary(
    store: ProviderCatalogStore,
    *,
    provider_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a compact source-catalog summary for CLI and operator surfaces."""
    now = time.time()
    sources = store.list_sources()
    if provider_ids:
        allowed = set(provider_ids)
        sources = [item for item in sources if item["provider_id"] in allowed]

    items: list[dict[str, Any]] = []
    due_count = 0
    error_count = 0
    for source in sources:
        provider_id = str(source.get("provider_id") or "")
        latest_models = store.get_latest_models(provider_id, "models")
        latest_pricing = store.get_latest_models(provider_id, "pricing")
        latest_docs_index = store.get_latest_models(provider_id, "docs-index")
        global_catalog_model_ids = {
            str(item.get("model_id") or "").strip()
            for item in latest_models + latest_pricing
            if str(item.get("model_id") or "").strip()
        }
        global_free_model_ids = {
            str(item.get("model_id") or "").strip()
            for item in latest_pricing
            if bool(item.get("is_free")) and str(item.get("model_id") or "").strip()
        }
        local_availability = build_provider_availability_overlay(
            store,
            provider_id=provider_id,
            global_model_ids=global_catalog_model_ids,
            global_free_model_ids=global_free_model_ids,
        )
        last_success_at = float(source.get("last_success_at") or 0)
        last_checked_at = float(source.get("last_checked_at") or 0)
        refresh_interval_seconds = int(source.get("refresh_interval_seconds") or 21600)
        seconds_since_success = (now - last_success_at) if last_success_at else None
        due = (
            not last_success_at
            or refresh_interval_seconds <= 0
            or (seconds_since_success or 0.0) >= refresh_interval_seconds
        )
        status = "current"
        if str(source.get("last_error") or "").strip():
            status = "error"
            error_count += 1
        elif due:
            status = "due"
            due_count += 1
        items.append(
            {
                "provider_id": provider_id,
                "display_name": source.get("display_name", provider_id),
                "last_checked_at": last_checked_at,
                "last_success_at": last_success_at,
                "last_error": source.get("last_error", ""),
                "refresh_interval_seconds": refresh_interval_seconds,
                "seconds_since_success": seconds_since_success,
                "status": status,
                "models_count": len(latest_models),
                "pricing_count": len(latest_pricing),
                "docs_index_count": len(latest_docs_index),
                "sample_models": [str(item.get("model_id") or "") for item in (latest_pricing or latest_models)[:5]],
                "local_availability": local_availability,
                "billing_notes": str(source.get("billing_notes") or ""),
                "account_profile": store.get_account_profile(provider_id),
            }
        )

    selected_provider_id = provider_ids[0] if provider_ids and len(provider_ids) == 1 else None
    recent_events = store.get_recent_change_events(
        provider_id=selected_provider_id,
        limit=20,
    )
    priority_next = {}
    if error_count:
        top_error = next((item for item in items if item["status"] == "error"), None)
        priority_next = {
            "path": "Provider Catalog Refresh",
            "why": (
                "one or more source refreshes are failing"
                + (f", starting with {top_error['provider_id']}" if top_error else "")
                + "."
            ),
        }
    elif due_count:
        top_due = next((item for item in items if item["status"] == "due"), None)
        priority_next = {
            "path": "Provider Catalog Refresh",
            "why": (
                "one or more provider source snapshots are due for refresh"
                + (f", starting with {top_due['provider_id']}" if top_due else "")
                + "."
            ),
        }
    elif recent_events:
        priority_next = {
            "path": "Provider Catalog Review",
            "why": ("recent provider catalog changes were detected and should be reviewed."),
        }

    alerts = build_catalog_alerts(
        {
            "items": items,
            "recent_events": recent_events,
        }
    )
    return {
        "tracked_sources": len(items),
        "error_sources": error_count,
        "due_sources": due_count,
        "recent_changes": len(recent_events),
        "items": items,
        "recent_events": recent_events,
        "alerts": alerts,
        "alert_summary": build_catalog_alert_summary(alerts),
        "priority_next": priority_next,
    }


def render_catalog_summary_text(
    summary: dict[str, Any],
    *,
    heading: str = "Provider source catalog",
) -> str:
    """Render a compact provider source catalog summary."""
    lines = [heading]
    items = list(summary.get("items") or [])
    if not items:
        lines.append("  no provider source snapshots yet")
        return "\n".join(lines) + "\n"
    lines.append(f"  tracked sources: {int(summary.get('tracked_sources') or 0)}")
    lines.append(
        "  state: "
        + f"errors={int(summary.get('error_sources') or 0)} | "
        + f"due={int(summary.get('due_sources') or 0)} | "
        + f"recent changes={int(summary.get('recent_changes') or 0)}"
    )
    alert_summary = dict(summary.get("alert_summary") or build_catalog_alert_summary(list(summary.get("alerts") or [])))
    lines.append(
        "  alert summary: "
        + f"status={alert_summary.get('status') or 'clear'} | "
        + f"fix-now={int(alert_summary.get('fix_now') or 0)} | "
        + f"review-now={int(alert_summary.get('review_now') or 0)} | "
        + f"inspect={int(alert_summary.get('inspect') or 0)}"
    )
    for item in items:
        lines.append(
            "  - "
            + f"{item['provider_id']}: models={item['models_count']} "
            + f"pricing={item['pricing_count']} docs={item['docs_index_count']} "
            + f"[{item['status']}]"
        )
        sample_models = list(item.get("sample_models") or [])
        if sample_models:
            lines.append("    sample: " + ", ".join(sample_models))
        if item.get("billing_notes"):
            lines.append(f"    billing: {item['billing_notes']}")
        if item.get("refresh_interval_seconds"):
            lines.append(f"    refresh interval: {int(item['refresh_interval_seconds'])}s")
        if item.get("seconds_since_success") is not None:
            lines.append(f"    age: {int(float(item['seconds_since_success']))}s since last success")
        profile = dict(item.get("account_profile") or {})
        if profile:
            profile_bits = [str(profile.get("billing_mode") or "")]
            if profile.get("subscription_name"):
                profile_bits.append(str(profile["subscription_name"]))
            if profile.get("quota_window"):
                profile_bits.append(f"window={profile['quota_window']}")
            if profile.get("quota_remaining") is not None:
                profile_bits.append(f"remaining={profile['quota_remaining']}")
            lines.append("    local account: " + " | ".join(bit for bit in profile_bits if bit))
        local_availability = dict(item.get("local_availability") or {})
        if local_availability:
            lines.append(
                "    local availability: "
                + f"routes={int(local_availability.get('local_routes') or 0)} | "
                + f"ready={int(local_availability.get('request_ready_routes') or 0)} | "
                + "models-endpoint="
                + f"{int(local_availability.get('models_endpoint_routes') or 0)} | "
                + "visible-models="
                + f"{int(local_availability.get('visible_model_count') or 0)}"
            )
            if local_availability.get("configured_models_missing_globally"):
                lines.append(
                    "    catalog mismatch: " + ", ".join(local_availability["configured_models_missing_globally"][:3])
                )
            if local_availability.get("key_model_mismatches"):
                lines.append(
                    "    key mismatch: "
                    + ", ".join(
                        f"{item['route_name']} -> {item['model_id']}"
                        for item in local_availability["key_model_mismatches"][:3]
                    )
                )
            if local_availability.get("local_only_models"):
                lines.append("    local-only models: " + ", ".join(local_availability["local_only_models"][:3]))
        if item.get("last_error"):
            lines.append(f"    last error: {item['last_error']}")
    events = list(summary.get("recent_events") or [])
    if events:
        lines.append("  recent changes:")
        for event in events[:5]:
            lines.append(
                "    - " + f"{event['provider_id']} / {event['source_kind']} / "
                f"{event['change_type']}: " + f"{event['message']}"
            )
    alerts = list(summary.get("alerts") or build_catalog_alerts(summary, limit=5))
    if alerts:
        lines.append("  alerts:")
        for alert in alerts[:5]:
            lines.append(
                "    - "
                + f"[{alert['severity']}] {alert['provider_id']}: "
                + f"{alert['headline']} ({alert.get('action') or 'inspect'})"
            )
            if alert.get("suggestion"):
                lines.append("      next: " + str(alert["suggestion"]))
    priority_next = dict(summary.get("priority_next") or {})
    if priority_next:
        lines.append("  priority next:")
        lines.append(f"    - path: {priority_next.get('path')}")
        lines.append(f"    - why : {priority_next.get('why')}")
    return "\n".join(lines) + "\n"


def due_provider_ids(
    store: ProviderCatalogStore,
    *,
    provider_ids: list[str] | None = None,
    now: float | None = None,
) -> list[str]:
    """Return provider ids whose source snapshots should be refreshed now."""
    now = float(now or time.time())
    source_rows = {row["provider_id"]: row for row in store.list_sources()}
    due: list[str] = []
    for source in list_provider_sources(provider_ids):
        provider_id = str(source.get("provider_id") or "")
        stored = dict(source_rows.get(provider_id) or {})
        last_success_at = float(stored.get("last_success_at") or 0)
        refresh_interval_seconds = int(
            stored.get("refresh_interval_seconds") or source.get("refresh_interval_seconds") or 21600
        )
        if not last_success_at or refresh_interval_seconds <= 0:
            due.append(provider_id)
            continue
        if (now - last_success_at) >= refresh_interval_seconds:
            due.append(provider_id)
    return due


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_price(value: str) -> float | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.lower() == "free":
        return 0.0
    token = token.replace("$", "").replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _parse_context_length(value: str) -> int | None:
    token = str(value or "").strip().replace(",", "")
    if not token:
        return None
    try:
        return int(token)
    except ValueError:
        return None


def parse_markdown_pricing_table(text: str) -> list[dict[str, Any]]:
    """Parse a markdown pricing table with Model ID, costs, and context length."""
    rows: list[dict[str, Any]] = []
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 5:
            continue
        if parts[0].lower() == "**model name**" or parts[1].lower() == "**model id**":
            continue
        if set(parts[0]) == {"-"}:
            continue
        model_id = parts[1]
        if "/" not in model_id and "-" not in model_id:
            continue
        input_cost = _parse_price(parts[2])
        output_cost = _parse_price(parts[3])
        rows.append(
            {
                "model_name": parts[0],
                "model_id": model_id,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "context_length": _parse_context_length(parts[4]),
                "is_free": input_cost == 0.0 and output_cost == 0.0,
            }
        )
    return rows


def parse_llms_index(text: str) -> list[dict[str, Any]]:
    """Parse a docs llms.txt index into pseudo-model records for source discovery."""
    pages: list[dict[str, Any]] = []
    for line in text.splitlines():
        token = line.strip()
        if not token.startswith("http"):
            continue
        pages.append(
            {
                "model_name": token.rsplit("/", 1)[-1],
                "model_id": token,
                "input_cost": None,
                "output_cost": None,
                "context_length": None,
                "is_free": False,
            }
        )
    return pages


def parse_regex_model_refs(
    text: str,
    *,
    model_prefixes: list[str] | None = None,
    model_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract model ids from docs text using prefixes and regex patterns."""
    found: set[str] = set()
    rows: list[dict[str, Any]] = []
    prefix_patterns = [re.escape(prefix) + r"[a-zA-Z0-9.\-:\/]+" for prefix in (model_prefixes or [])]
    for pattern in prefix_patterns + list(model_patterns or []):
        for match in re.findall(pattern, text):
            token = str(match).strip("`*.,)('\"")
            if not token or token in found:
                continue
            found.add(token)
            rows.append(
                {
                    "model_name": token,
                    "model_id": token,
                    "input_cost": None,
                    "output_cost": None,
                    "context_length": None,
                    "is_free": token.endswith(":free"),
                }
            )
    rows.sort(key=lambda item: str(item["model_id"]))
    return rows


def parse_billing_keywords(text: str) -> list[dict[str, Any]]:
    """Extract billing hints from docs text as pseudo-model records."""
    billing_modes = []
    lowered = text.lower()
    for keyword in ("byok", "wallet", "credit", "free", "subscription", "quota"):
        if keyword in lowered:
            billing_modes.append(keyword)
    return [
        {
            "model_name": "billing-modes",
            "model_id": "billing-modes",
            "input_cost": None,
            "output_cost": None,
            "context_length": None,
            "is_free": "free" in billing_modes,
            "metadata": {"billing_modes": billing_modes},
        }
    ]


def _parse_endpoint(endpoint: dict[str, Any], text: str) -> list[dict[str, Any]]:
    parser_type = str(endpoint.get("parser_type") or "")
    if parser_type == "markdown-pricing-table":
        return parse_markdown_pricing_table(text)
    if parser_type == "llms-index":
        return parse_llms_index(text)
    if parser_type == "regex-model-refs":
        return parse_regex_model_refs(
            text,
            model_prefixes=list(endpoint.get("model_prefixes") or []),
            model_patterns=list(endpoint.get("model_patterns") or []),
        )
    if parser_type == "billing-keywords":
        return parse_billing_keywords(text)
    raise ValueError(f"Unsupported provider source parser: {parser_type}")


def _diff_model_sets(
    provider_id: str,
    source_kind: str,
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now = time.time()
    previous_by_id = {str(item.get("model_id") or ""): item for item in previous}
    current_by_id = {str(item.get("model_id") or ""): item for item in current}
    events: list[dict[str, Any]] = []
    for model_id in sorted(current_by_id.keys() - previous_by_id.keys()):
        events.append(
            {
                "provider_id": provider_id,
                "detected_at": now,
                "source_kind": source_kind,
                "change_type": "model-added",
                "severity": "notice",
                "model_id": model_id,
                "field_name": "model_id",
                "old_value": "",
                "new_value": model_id,
                "message": (f"{provider_id}: model '{model_id}' appeared in {source_kind}."),
            }
        )
    for model_id in sorted(previous_by_id.keys() - current_by_id.keys()):
        events.append(
            {
                "provider_id": provider_id,
                "detected_at": now,
                "source_kind": source_kind,
                "change_type": "model-removed",
                "severity": "warning",
                "model_id": model_id,
                "field_name": "model_id",
                "old_value": model_id,
                "new_value": "",
                "message": (f"{provider_id}: model '{model_id}' disappeared from {source_kind}."),
            }
        )
    for model_id in sorted(current_by_id.keys() & previous_by_id.keys()):
        previous_item = previous_by_id[model_id]
        current_item = current_by_id[model_id]
        for field_name in ("input_cost", "output_cost", "context_length"):
            if previous_item.get(field_name) == current_item.get(field_name):
                continue
            events.append(
                {
                    "provider_id": provider_id,
                    "detected_at": now,
                    "source_kind": source_kind,
                    "change_type": "field-changed",
                    "severity": "notice",
                    "model_id": model_id,
                    "field_name": field_name,
                    "old_value": str(previous_item.get(field_name) or ""),
                    "new_value": str(current_item.get(field_name) or ""),
                    "message": (
                        f"{provider_id}: {field_name} for '{model_id}' changed from "
                        f"{previous_item.get(field_name)} to "
                        f"{current_item.get(field_name)}."
                    ),
                }
            )
    return events


class ProviderCatalogRefresher:
    """Refresh provider source catalogs and write snapshots plus change events."""

    def __init__(
        self,
        store: ProviderCatalogStore,
        *,
        fetcher: TextFetcher | None = None,
    ) -> None:
        self._store = store
        self._fetcher = fetcher or HttpxTextFetcher()

    def refresh(
        self,
        *,
        provider_ids: list[str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> list[RefreshResult]:
        results: list[RefreshResult] = []
        for source in list_provider_sources(provider_ids):
            self._store.upsert_source(source)
            provider_id = str(source.get("provider_id") or "")
            for endpoint in list(source.get("endpoints") or []):
                url = str(endpoint.get("url") or "")
                kind = str(endpoint.get("kind") or "")
                if not url or not kind:
                    continue
                try:
                    text = self._fetcher.fetch_text(
                        url,
                        timeout_seconds=timeout_seconds,
                    )
                    parsed = _parse_endpoint(endpoint, text)
                    raw_hash = _hash_text(text)
                    normalized = [
                        {
                            **item,
                            "raw_source_hash": raw_hash,
                        }
                        for item in parsed
                    ]
                    previous = self._store.get_latest_models(provider_id, kind)
                    changes = _diff_model_sets(provider_id, kind, previous, normalized)
                    self._store.replace_model_snapshot(provider_id, kind, normalized)
                    self._store.record_change_events(changes)
                    self._store.mark_source_check(provider_id, success=True)
                    results.append(
                        RefreshResult(
                            provider_id=provider_id,
                            endpoint_kind=kind,
                            url=url,
                            ok=True,
                            models_count=len(normalized),
                            changes_count=len(changes),
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive runtime path
                    self._store.mark_source_check(
                        provider_id,
                        success=False,
                        error=str(exc),
                    )
                    results.append(
                        RefreshResult(
                            provider_id=provider_id,
                            endpoint_kind=kind,
                            url=url,
                            ok=False,
                            error=str(exc),
                        )
                    )
        return results
