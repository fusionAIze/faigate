"""Operator-focused dashboard summaries for fusionAIze Gate."""

# ruff: noqa: E501

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .metrics import MetricsStore


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _format_usd(value: float) -> str:
    if value <= 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"


def _format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _format_latency_ms(value: float) -> str:
    if value <= 0:
        return "n/a"
    return f"{value:.0f}ms"


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"


def _format_ago(timestamp: float | None) -> str:
    if not timestamp:
        return "never"
    delta = max(0.0, time.time() - timestamp)
    if delta < 60:
        return f"{delta:.0f}s ago"
    if delta < 3600:
        return f"{delta / 60:.0f}m ago"
    if delta < 86400:
        return f"{delta / 3600:.1f}h ago"
    return f"{delta / 86400:.1f}d ago"


def _health_issue_category(last_error: str) -> str:
    lowered = (last_error or "").lower()
    if any(token in lowered for token in ("quota", "insufficient_quota", "billing hard limit")):
        return "quota-exhausted"
    if any(token in lowered for token in ("429", "rate limit", "rate-limit", "too many requests")):
        return "rate-limited"
    if any(token in lowered for token in ("model", "not found", "unsupported")):
        return "model-unavailable"
    return "unhealthy"


def _client_highlights(client_totals: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    if not client_totals:
        return {
            "top_requests": None,
            "top_tokens": None,
            "top_cost": None,
            "highest_failure_rate": None,
            "slowest_client": None,
        }

    rows = list(client_totals)
    failure_rows = [row for row in rows if _safe_int(row.get("failures")) > 0]
    return {
        "top_requests": max(
            rows,
            key=lambda row: (_safe_int(row.get("requests")), _safe_int(row.get("total_tokens"))),
        ),
        "top_tokens": max(
            rows,
            key=lambda row: (_safe_int(row.get("total_tokens")), _safe_int(row.get("requests"))),
        ),
        "top_cost": max(
            rows, key=lambda row: (_safe_float(row.get("cost_usd")), _safe_int(row.get("requests")))
        ),
        "highest_failure_rate": (
            max(
                failure_rows,
                key=lambda row: (
                    -_safe_float(row.get("success_pct") or 0),
                    _safe_int(row.get("failures")),
                    _safe_int(row.get("requests")),
                ),
            )
            if failure_rows
            else None
        ),
        "slowest_client": max(
            rows,
            key=lambda row: (
                _safe_float(row.get("avg_latency_ms")),
                _safe_int(row.get("requests")),
            ),
        ),
    }


def _recommended_scenario_for_client(client_profile: str, *, expensive: bool = False) -> str | None:
    mapping = {
        "opencode": "opencode-eco" if expensive else "opencode-balanced",
        "openclaw": "openclaw-balanced",
        "n8n": "n8n-eco" if expensive else "n8n-reliable",
        "cli": "cli-free" if expensive else "cli-balanced",
    }
    return mapping.get(client_profile)


def _stats_from_db(db_path: str) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {
            "totals": {},
            "providers": [],
            "routing": [],
            "clients": [],
            "client_totals": [],
            "client_highlights": _client_highlights([]),
            "operator_actions": [],
            "hourly": [],
            "daily": [],
        }

    metrics = MetricsStore(str(path))
    metrics.init()
    try:
        client_totals = metrics.get_client_totals()
        return {
            "totals": metrics.get_totals(),
            "providers": metrics.get_provider_summary(),
            "routing": metrics.get_routing_breakdown(),
            "clients": metrics.get_client_breakdown(),
            "client_totals": client_totals,
            "client_highlights": _client_highlights(client_totals),
            "operator_actions": metrics.get_operator_breakdown(),
            "hourly": metrics.get_hourly_series(24),
            "daily": metrics.get_daily_totals(30),
        }
    finally:
        metrics.close()


def build_dashboard_report(
    *,
    db_path: str,
    stats_payload: dict[str, Any] | None = None,
    health_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one operator-facing dashboard report from live or local metrics."""
    stats = stats_payload or _stats_from_db(db_path)
    source_mode = "live-api" if stats_payload else "db-only"
    if not stats.get("totals"):
        source_mode = "empty"

    totals = stats.get("totals") or {}
    providers = stats.get("providers") or []
    routing = stats.get("routing") or []
    client_totals = stats.get("client_totals") or []
    client_highlights = stats.get("client_highlights") or _client_highlights(client_totals)
    daily = stats.get("daily") or []
    hourly = stats.get("hourly") or []
    operator_actions = stats.get("operator_actions") or []

    total_requests = _safe_int(totals.get("total_requests"))
    total_failures = _safe_int(totals.get("total_failures"))
    success_pct = (
        ((total_requests - total_failures) * 100.0 / total_requests) if total_requests else 100.0
    )
    total_prompt_tokens = _safe_int(totals.get("total_prompt_tokens"))
    total_completion_tokens = _safe_int(totals.get("total_compl_tokens"))
    total_cost = _safe_float(totals.get("total_cost_usd"))
    avg_latency_ms = _safe_float(totals.get("avg_latency_ms"))

    fallback_requests = sum(
        _safe_int(item.get("requests"))
        for item in routing
        if str(item.get("layer") or "") == "fallback"
    )
    fallback_pct = (fallback_requests * 100.0 / total_requests) if total_requests else 0.0

    top_provider = max(
        providers,
        key=lambda row: (_safe_int(row.get("requests")), _safe_float(row.get("cost_usd"))),
        default=None,
    )
    top_provider_cost = max(
        providers,
        key=lambda row: (_safe_float(row.get("cost_usd")), _safe_int(row.get("requests"))),
        default=None,
    )

    total_cost_days = [
        _safe_float(day.get("cost_usd"))
        for day in daily
        if any(_safe_int(day.get(key)) for key in ("requests", "tokens", "failures"))
        or _safe_float(day.get("cost_usd"))
    ]
    avg_daily_cost = (sum(total_cost_days) / len(total_cost_days)) if total_cost_days else 0.0
    projected_monthly_cost = avg_daily_cost * 30 if total_cost_days else 0.0

    last_request = totals.get("last_request")
    first_request = totals.get("first_request")
    requests_24h = sum(_safe_int(row.get("requests")) for row in hourly)
    tokens_24h = sum(_safe_int(row.get("tokens")) for row in hourly)
    cost_24h = sum(_safe_float(row.get("cost_usd")) for row in hourly)

    healthy_provider_names: list[str] = []
    healthy_provider_tiers: dict[str, str] = {}
    unhealthy_providers: list[dict[str, str]] = []
    if health_payload:
        health_providers = health_payload.get("providers") or {}
        for provider_name, payload in health_providers.items():
            if payload.get("healthy"):
                healthy_provider_names.append(provider_name)
                healthy_provider_tiers[provider_name] = str(payload.get("tier") or "")
            else:
                unhealthy_providers.append(
                    {
                        "provider": provider_name,
                        "category": _health_issue_category(str(payload.get("last_error") or "")),
                        "detail": str(payload.get("last_error") or "").strip()
                        or "No error detail provided",
                    }
                )

    alerts: list[dict[str, str]] = []
    hints: list[str] = []
    decision_support: list[str] = []

    if health_payload:
        health_summary = health_payload.get("summary") or {}
        unhealthy_count = _safe_int(health_summary.get("providers_unhealthy"))
        total_health_providers = _safe_int(health_summary.get("providers_total"))
        if unhealthy_count:
            preview = ", ".join(item["provider"] for item in unhealthy_providers[:3])
            suffix = "" if unhealthy_count <= 3 else f" +{unhealthy_count - 3} more"
            alerts.append(
                {
                    "level": "warning",
                    "headline": "One or more live providers are unhealthy",
                    "detail": f"{preview}{suffix} currently look degraded out of {total_health_providers} health-checked providers.",
                    "suggestion": "Run Provider Probe next, then review provider-specific errors before routing more traffic there.",
                }
            )

    if total_requests == 0:
        alerts.append(
            {
                "level": "info",
                "headline": "No request traffic has been recorded yet",
                "detail": "The gateway is up, but the metrics store has not seen any routed client requests yet.",
                "suggestion": "Connect one client and send a small live request to turn the dashboard into an operational view.",
            }
        )
    elif success_pct < 95.0:
        alerts.append(
            {
                "level": "warning",
                "headline": "Failure rate is high enough to watch closely",
                "detail": f"Success is {_format_pct(success_pct)} across {total_requests} requests.",
                "suggestion": "Open Providers and Clients to isolate the unstable path before sending more production traffic.",
            }
        )
    elif total_failures > 0:
        alerts.append(
            {
                "level": "info",
                "headline": "Some requests have failed recently",
                "detail": f"{total_failures} requests have failed so far, even though the overall success rate is {_format_pct(success_pct)}.",
                "suggestion": "Check the top clients and providers before the failure pattern grows.",
            }
        )

    if fallback_pct >= 20.0:
        alerts.append(
            {
                "level": "warning",
                "headline": "Fallback routing is carrying a meaningful share of traffic",
                "detail": f"{fallback_requests} requests ({_format_pct(fallback_pct)}) have gone through fallback routing.",
                "suggestion": "Consider raising budget or priority for primary providers if this should not be the normal steady state.",
            }
        )
    elif fallback_requests:
        hints.append(
            f"Fallback routing has handled {fallback_requests} requests so far ({_format_pct(fallback_pct)} of total traffic)."
        )

    if last_request and (time.time() - float(last_request)) > 12 * 3600:
        alerts.append(
            {
                "level": "info",
                "headline": "Traffic is stale",
                "detail": f"The last recorded request was {_format_ago(float(last_request))}.",
                "suggestion": "Send one real client request before making spend or health decisions from old traffic.",
            }
        )

    if top_provider_cost and total_cost > 0:
        dominant_cost_share = (
            (_safe_float(top_provider_cost.get("cost_usd")) * 100.0 / total_cost)
            if total_cost
            else 0.0
        )
        if dominant_cost_share >= 60.0:
            hints.append(
                f"Most spend currently lands on {top_provider_cost.get('provider')} ({_format_pct(dominant_cost_share)} of total cost)."
            )
            cheaper_healthy = [
                name
                for name, tier in healthy_provider_tiers.items()
                if tier in {"cheap", "default", "fallback"}
                and name != str(top_provider_cost.get("provider") or "")
            ]
            if cheaper_healthy:
                decision_support.append(
                    "Budget hint: consider moving more general traffic toward "
                    + ", ".join(cheaper_healthy[:3])
                    + " before increasing spend on the current top-cost provider."
                )

    rate_limited = [item["provider"] for item in unhealthy_providers if item["category"] == "rate-limited"]
    quota_exhausted = [
        item["provider"] for item in unhealthy_providers if item["category"] == "quota-exhausted"
    ]
    if rate_limited:
        decision_support.append(
            "Rate-limit pressure: "
            + ", ".join(rate_limited[:3])
            + " currently look saturated. More budget, lower concurrency, or a stronger secondary path may help."
        )
    if quota_exhausted:
        decision_support.append(
            "Quota pressure: "
            + ", ".join(quota_exhausted[:3])
            + " appear quota-exhausted. Budget or quota changes are likely needed before those paths recover."
        )

    if healthy_provider_names:
        hints.append(
            f"Healthy providers right now: {', '.join(healthy_provider_names[:4])}"
            + (
                ""
                if len(healthy_provider_names) <= 4
                else f" +{len(healthy_provider_names) - 4} more"
            )
        )
    elif health_payload:
        hints.append("No healthy providers are currently reported by /health.")

    top_cost_client = client_highlights.get("top_cost")
    if top_cost_client:
        top_cost_client_name = str(
            top_cost_client.get("client_tag") or top_cost_client.get("client_profile") or "generic"
        )
        top_cost_client_profile = str(top_cost_client.get("client_profile") or "generic")
        cost_per_request = _safe_float(top_cost_client.get("cost_per_request_usd"))
        suggested_scenario = _recommended_scenario_for_client(
            top_cost_client_profile,
            expensive=cost_per_request >= 0.03,
        )
        if suggested_scenario:
            decision_support.append(
                f"Client hint: {top_cost_client_name} is the highest-spend client right now. Review {suggested_scenario} if you want a cheaper default posture."
            )

    hints.append(
        "Provider-specific quota reset windows are not available yet; today the dashboard can only infer quota or rate-limit pressure from live errors."
    )

    return {
        "source": {
            "mode": source_mode,
            "db_path": db_path,
            "live_health": bool(health_payload),
            "live_stats": bool(stats_payload),
        },
        "totals": totals,
        "health": health_payload or {},
        "providers": providers,
        "clients": client_totals,
        "routing": routing,
        "daily": daily,
        "hourly": hourly,
        "operator_actions": operator_actions,
        "client_highlights": client_highlights,
        "decision_support": decision_support,
        "cards": {
            "traffic": {
                "requests": total_requests,
                "success_pct": round(success_pct, 1),
                "avg_latency_ms": round(avg_latency_ms, 1),
                "last_request_ago": _format_ago(float(last_request)) if last_request else "never",
                "first_request_ago": _format_ago(float(first_request))
                if first_request
                else "never",
            },
            "spend": {
                "total_cost_usd": round(total_cost, 6),
                "projected_monthly_cost_usd": round(projected_monthly_cost, 6),
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
            },
            "health": {
                "status": (health_payload or {}).get("status")
                or ("live" if health_payload else "unknown"),
                "providers_healthy": _safe_int(
                    ((health_payload or {}).get("summary") or {}).get("providers_healthy")
                ),
                "providers_total": _safe_int(
                    ((health_payload or {}).get("summary") or {}).get("providers_total")
                ),
                "unhealthy": unhealthy_providers,
            },
            "drivers": {
                "top_provider": top_provider,
                "top_cost_provider": top_provider_cost,
                "top_client": client_highlights.get("top_requests"),
                "fallback_requests": fallback_requests,
                "fallback_pct": round(fallback_pct, 1),
                "requests_24h": requests_24h,
                "tokens_24h": tokens_24h,
                "cost_24h": round(cost_24h, 6),
            },
        },
        "alerts": alerts,
        "hints": hints,
    }


def _render_overview(report: dict[str, Any]) -> str:
    cards = report["cards"]
    top_provider = cards["drivers"]["top_provider"]
    top_client = cards["drivers"]["top_client"]
    lines = [
        "fusionAIze Gate Dashboard",
        "",
        f"Source: {report['source']['mode']} ({'live /health available' if report['source']['live_health'] else 'using local metrics only'})",
        "",
        "Global",
        f"  Requests            {cards['traffic']['requests']}",
        f"  Success             {_format_pct(cards['traffic']['success_pct'])}",
        f"  Avg latency         {_format_latency_ms(cards['traffic']['avg_latency_ms'])}",
        f"  Last request        {cards['traffic']['last_request_ago']}",
        "",
        "Spend + Tokens",
        f"  Cost total          {_format_usd(_safe_float(cards['spend']['total_cost_usd']))}",
        f"  Projected month     {_format_usd(_safe_float(cards['spend']['projected_monthly_cost_usd']))}",
        f"  Prompt tokens       {_format_tokens(_safe_int(cards['spend']['prompt_tokens']))}",
        f"  Completion tokens   {_format_tokens(_safe_int(cards['spend']['completion_tokens']))}",
        "",
        "Confidence",
        f"  Live providers      {cards['health']['providers_healthy']}/{cards['health']['providers_total']} healthy"
        if report["source"]["live_health"]
        else "  Live providers      unavailable (runtime health not reachable)",
        f"  Fallback traffic    {cards['drivers']['fallback_requests']} requests ({_format_pct(_safe_float(cards['drivers']['fallback_pct']))})",
        f"  24h activity        {cards['drivers']['requests_24h']} requests / {_format_usd(_safe_float(cards['drivers']['cost_24h']))} / {_format_tokens(_safe_int(cards['drivers']['tokens_24h']))}",
        "",
        "Traffic drivers",
        f"  Top provider        {top_provider.get('provider')} ({top_provider.get('requests')} req, {_format_usd(_safe_float(top_provider.get('cost_usd')))})"
        if top_provider
        else "  Top provider        no traffic yet",
        f"  Top client          {top_client.get('client_tag') or top_client.get('client_profile')} ({top_client.get('requests')} req, {_format_usd(_safe_float(top_client.get('cost_usd')))})"
        if top_client
        else "  Top client          no traffic yet",
    ]
    if report["alerts"]:
        alert = report["alerts"][0]
        lines.extend(
            [
                "",
                "Top alert",
                f"  {alert['headline']}",
                f"  {alert['detail']}",
            ]
        )
    elif report["hints"]:
        lines.extend(["", "Operator note", f"  {report['hints'][0]}"])
    if report["decision_support"]:
        lines.extend(["", "Decision support", f"  {report['decision_support'][0]}"])
    return "\n".join(lines) + "\n"


def _render_providers(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Providers"]
    rows = report["providers"][:8]
    unhealthy = {item["provider"]: item for item in report["cards"]["health"]["unhealthy"]}
    if not rows:
        lines.append("  No provider traffic has been recorded yet.")
    for row in rows:
        provider = str(row.get("provider") or "unknown")
        status = "live-healthy"
        if provider in unhealthy:
            status = unhealthy[provider]["category"]
        elif report["source"]["live_health"] and report["cards"]["health"]["providers_total"] == 0:
            status = "health-unavailable"
        lines.extend(
            [
                f"- {provider} [{status}]",
                f"  requests: {_safe_int(row.get('requests'))} | failures: {_safe_int(row.get('failures'))} | success: {_format_pct(100.0 - (_safe_int(row.get('failures')) * 100.0 / max(1, _safe_int(row.get('requests')))))}",
                f"  cost: {_format_usd(_safe_float(row.get('cost_usd')))} | latency: {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))} | tokens: {_format_tokens(_safe_int(row.get('total_tokens')))}",
            ]
        )
        if provider in unhealthy:
            lines.append(f"  live issue: {unhealthy[provider]['detail']}")
        lines.append("")
    if report["hints"]:
        lines.append("Operator hints")
        for hint in report["hints"][:3]:
            lines.append(f"- {hint}")
    if report["decision_support"]:
        lines.append("")
        lines.append("Budget + routing hints")
        for hint in report["decision_support"][:3]:
            lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def _render_clients(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Clients"]
    rows = report["clients"][:8]
    if not rows:
        lines.append("  No client traffic has been recorded yet.")
    for row in rows:
        client_name = str(row.get("client_tag") or row.get("client_profile") or "generic")
        lines.extend(
            [
                f"- {client_name}",
                f"  profile: {row.get('client_profile') or 'generic'} | requests: {_safe_int(row.get('requests'))} | success: {_format_pct(_safe_float(row.get('success_pct') or 0))}",
                f"  cost: {_format_usd(_safe_float(row.get('cost_usd')))} | latency: {_format_latency_ms(_safe_float(row.get('avg_latency_ms')))} | tokens: {_format_tokens(_safe_int(row.get('total_tokens')))}",
                f"  providers: {row.get('providers') or 'n/a'}",
                "",
            ]
        )
    highlights = report["client_highlights"] or {}
    top_cost = highlights.get("top_cost")
    slowest = highlights.get("slowest_client")
    if top_cost or slowest:
        lines.append("Decision support")
        if top_cost:
            lines.append(
                f"- Highest-spend client right now: {(top_cost.get('client_tag') or top_cost.get('client_profile'))} at {_format_usd(_safe_float(top_cost.get('cost_usd')))} total."
            )
        if slowest:
            lines.append(
                f"- Slowest client path right now: {(slowest.get('client_tag') or slowest.get('client_profile'))} at {_format_latency_ms(_safe_float(slowest.get('avg_latency_ms')))} average latency."
            )
    for hint in report["decision_support"][:2]:
        lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def _render_activity(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Activity"]
    lines.extend(
        [
            f"24h requests: {report['cards']['drivers']['requests_24h']}",
            f"24h tokens: {_format_tokens(_safe_int(report['cards']['drivers']['tokens_24h']))}",
            f"24h cost: {_format_usd(_safe_float(report['cards']['drivers']['cost_24h']))}",
            "",
            "Recent daily trend",
        ]
    )
    daily_rows = report["daily"][-7:]
    if not daily_rows:
        lines.append("  No daily history yet.")
    for row in daily_rows:
        lines.append(
            f"- {row.get('day')}: {_safe_int(row.get('requests'))} req | {_format_usd(_safe_float(row.get('cost_usd')))} | {_format_tokens(_safe_int(row.get('tokens')))} | {_safe_int(row.get('failures'))} fail"
        )
    lines.append("")
    lines.append("Operator actions")
    operator_rows = report["operator_actions"][:5]
    if not operator_rows:
        lines.append("  No operator actions have been recorded yet.")
    for row in operator_rows:
        status = row.get("status") or "n/a"
        update_type = row.get("update_type") or "n/a"
        lines.append(
            f"- {row.get('action') or row.get('event_type')}: {row.get('events')} events | status={status} | update_type={update_type}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_alerts(report: dict[str, Any]) -> str:
    lines = ["fusionAIze Gate Dashboard", "", "Alerts + Decision Support"]
    if not report["alerts"]:
        lines.append("No active operator alerts right now.")
    for alert in report["alerts"]:
        lines.extend(
            [
                f"- [{alert['level']}] {alert['headline']}",
                f"  detail: {alert['detail']}",
                f"  next: {alert['suggestion']}",
                "",
            ]
        )
    lines.append("Context")
    for hint in report["hints"][:5]:
        lines.append(f"- {hint}")
    for hint in report["decision_support"][:5]:
        lines.append(f"- {hint}")
    return "\n".join(lines).rstrip() + "\n"


def render_dashboard_text(report: dict[str, Any], *, view: str = "overview") -> str:
    """Render one human-readable dashboard view."""
    renderers = {
        "overview": _render_overview,
        "providers": _render_providers,
        "clients": _render_clients,
        "activity": _render_activity,
        "alerts": _render_alerts,
    }
    return renderers.get(view, _render_overview)(report)


def report_as_json(report: dict[str, Any]) -> str:
    """Serialize the report for shell helpers and tests."""
    return json.dumps(report, indent=2, sort_keys=True)
