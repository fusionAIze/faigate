#!/usr/bin/env python3
"""faigate-stats – CLI dashboard for fusionAIze Gate metrics.

Usage:
    python -m faigate.cli              # Full overview
    python -m faigate.cli --recent 20  # Last 20 requests
    python -m faigate.cli --daily      # Daily cost breakdown
    python -m faigate.cli --json       # JSON output (pipe-friendly)
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from .config import _safe_db_path, load_config
from .metrics import MetricsStore
from .provider_catalog import get_offerings_catalog
from .cost import estimate_provider_cost


# ── Dashboard URL generation ──────────────────────────────────

DEFAULT_DASHBOARD_URL = os.environ.get("FAIGATE_DASHBOARD_URL", "http://localhost:8000/dashboard")

VALID_VIEWS = {
    "overview": "Overview",
    "providers": "Providers",
    "clients": "Clients",
    "routes": "Routes",
    "analytics": "Analytics",
    "catalog": "Catalog",
    "integrations": "Integrations",
}


def generate_dashboard_url(
    view: str = "overview",
    provider: str = "",
    modality: str = "",
    client_profile: str = "",
    client_tag: str = "",
    layer: str = "",
    success: str = "",
    saved_view: str = "",
) -> str:
    """Generate a dashboard deep-link URL with the given filters."""
    params = {}
    if provider:
        params["provider"] = provider
    if modality:
        params["modality"] = modality
    if client_profile:
        params["client_profile"] = client_profile
    if client_tag:
        params["client_tag"] = client_tag
    if layer:
        params["layer"] = layer
    if success:
        params["success"] = success
    if saved_view:
        params["saved_view"] = saved_view
    if view and view != "overview":
        params["view"] = view

    url = DEFAULT_DASHBOARD_URL
    if params:
        url += "?" + urlencode(params)
    return url


def cmd_dashboard_link(
    view: str = "overview",
    provider: str = "",
    modality: str = "",
    client_profile: str = "",
    client_tag: str = "",
    layer: str = "",
    success: str = "",
    saved_view: str = "",
    copy: bool = False,
):
    """Generate and display a dashboard deep-link URL."""
    # Validate view
    if view not in VALID_VIEWS:
        print(_c(f"Error: Invalid view '{view}'. Valid views are:", RED))
        for v, desc in VALID_VIEWS.items():
            print(f"  {v:12} - {desc}")
        return

    url = generate_dashboard_url(
        view=view,
        provider=provider,
        modality=modality,
        client_profile=client_profile,
        client_tag=client_tag,
        layer=layer,
        success=success,
        saved_view=saved_view,
    )

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Dashboard Deep Link", BOLD) + _c("            ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    # Show parameters
    params_used = []
    if view != "overview":
        params_used.append(f"view={view}")
    if provider:
        params_used.append(f"provider={provider}")
    if modality:
        params_used.append(f"modality={modality}")
    if client_profile:
        params_used.append(f"client_profile={client_profile}")
    if client_tag:
        params_used.append(f"client_tag={client_tag}")
    if layer:
        params_used.append(f"layer={layer}")
    if success:
        params_used.append(f"success={success}")
    if saved_view:
        params_used.append(f"saved_view={saved_view}")

    if params_used:
        print(_c("  Parameters:", DIM))
        for param in params_used:
            print(f"    {param}")
        print()

    print(_c("  URL:", DIM))
    print(f"    {url}")
    print()

    # Platform-specific copy instructions
    if copy:
        import platform
        import subprocess

        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["pbcopy"], input=url.encode(), check=False)
                print(_c("  ✓ URL copied to clipboard (macOS pbcopy)", GREEN))
            elif system == "Linux":
                # Try xclip first, then xsel
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"], input=url.encode(), check=False)
                    print(_c("  ✓ URL copied to clipboard (Linux xclip)", GREEN))
                except FileNotFoundError:
                    try:
                        subprocess.run(["xsel", "--clipboard", "--input"], input=url.encode(), check=False)
                        print(_c("  ✓ URL copied to clipboard (Linux xsel)", GREEN))
                    except FileNotFoundError:
                        print(_c("  Note: Install xclip or xsel for clipboard support", YELLOW))
            elif system == "Windows":
                subprocess.run(["clip"], input=url.encode(), check=False)
                print(_c("  ✓ URL copied to clipboard (Windows clip)", GREEN))
            else:
                print(_c(f"  Note: Clipboard not supported on {system}", YELLOW))
        except Exception as e:
            print(_c(f"  Note: Could not copy to clipboard: {e}", YELLOW))

    print(_c("  Open in browser:", DIM))
    print(f"    {_c('open', BOLD)} '{url}'")
    print()


# ── Formatting helpers ─────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RED = "\033[31m"
WHITE = "\033[37m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def _usd(n: float | None) -> str:
    if n is None or n == 0:
        return _c("$0.0000", DIM)
    return _c(f"${n:.4f}", GREEN)


def _tok(n: int | None) -> str:
    if not n:
        return _c("0", DIM)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _ms(n: float | None) -> str:
    if not n:
        return _c("—", DIM)
    return f"{n:.0f}ms"


def _ago(ts: float | None) -> str:
    if not ts:
        return "—"
    delta = time.time() - ts
    if delta < 60:
        return f"{delta:.0f}s ago"
    if delta < 3600:
        return f"{delta / 60:.0f}m ago"
    if delta < 86400:
        return f"{delta / 3600:.1f}h ago"
    return f"{delta / 86400:.1f}d ago"


def _bar(ratio: float, width: int = 20, char: str = "█") -> str:
    filled = int(ratio * width)
    return _c(char * filled, CYAN) + _c("░" * (width - filled), DIM)


def _table(headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None):
    """Print a simple aligned table."""
    if not col_widths:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) + 2 for i, h in enumerate(headers)]

    # Header
    hdr = ""
    for i, h in enumerate(headers):
        hdr += _c(h.upper().ljust(col_widths[i]), DIM)
    print(hdr)
    print(_c("─" * sum(col_widths), DIM))

    # Rows
    for row in rows:
        line = ""
        for i, cell in enumerate(row):
            line += str(cell).ljust(col_widths[i])
        print(line)


# ── Commands ───────────────────────────────────────────────────


def cmd_overview(metrics: MetricsStore, **filters):
    totals = metrics.get_totals(**filters)
    providers = metrics.get_provider_summary(**filters)
    routing = metrics.get_routing_breakdown(**filters)
    clients = metrics.get_client_breakdown(**filters)

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  fusionAIze Gate Stats", BOLD) + _c("       ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    # Totals
    tr = totals.get("total_requests", 0) or 0
    tc = totals.get("total_cost_usd", 0) or 0
    pt = totals.get("total_prompt_tokens", 0) or 0
    ct = totals.get("total_compl_tokens", 0) or 0
    fl = totals.get("total_failures", 0) or 0
    al = totals.get("avg_latency_ms", 0) or 0

    print(
        f"  {_c('Requests:', DIM)}  {_c(str(tr), BOLD)}     "
        f"{_c('Cost:', DIM)}  {_usd(tc)}     "
        f"{_c('Tokens:', DIM)}  {_tok(pt)} in / {_tok(ct)} out     "
        f"{_c('Failures:', DIM)}  {_c(str(fl), RED if fl else DIM)}"
    )
    print(
        f"  {_c('Avg latency:', DIM)}  {_ms(al)}     "
        f"{_c('First:', DIM)}  {_ago(totals.get('first_request'))}     "
        f"{_c('Last:', DIM)}  {_ago(totals.get('last_request'))}"
    )
    print()

    # Provider breakdown
    if providers:
        print(_c("  ── Providers ──────────────────────────", DIM))
        max_req = max(p["requests"] for p in providers) if providers else 1
        rows = []
        for p in providers:
            ratio = p["requests"] / max_req if max_req else 0
            rows.append(
                [
                    _c(p["provider"], BOLD),
                    str(p["requests"]),
                    _tok(p.get("total_tokens", 0)),
                    _usd(p.get("cost_usd", 0)),
                    str(p.get("failures", 0)),
                    _ms(p.get("avg_latency_ms", 0)),
                    _bar(ratio, 15),
                ]
            )
        _table(
            ["Provider", "Reqs", "Tokens", "Cost", "Fail", "Latency", "Share"],
            rows,
            [22, 8, 10, 12, 6, 10, 18],
        )
        print()

    # Routing breakdown
    if routing:
        print(_c("  ── Routing Rules ─────────────────────", DIM))
        rows = []
        for r in routing[:12]:
            layer_color = {
                "static": MAGENTA,
                "heuristic": GREEN,
                "direct": YELLOW,
                "llm-classify": CYAN,
                "fallback": RED,
            }.get(r["layer"], WHITE)
            rows.append(
                [
                    _c(r["layer"], layer_color),
                    r["rule_name"],
                    r["provider"],
                    str(r["requests"]),
                    _usd(r.get("cost_usd", 0)),
                ]
            )
        _table(["Layer", "Rule", "Provider", "Reqs", "Cost"], rows, [14, 24, 22, 8, 12])
        print()

    if clients:
        print(_c("  ── Clients ───────────────────────────", DIM))
        rows = []
        for c in clients[:12]:
            rows.append(
                [
                    c.get("client_profile", ""),
                    c.get("client_tag", "") or "—",
                    c.get("provider", ""),
                    c.get("layer", ""),
                    str(c.get("requests", 0)),
                    _usd(c.get("cost_usd", 0)),
                ]
            )
        _table(["Profile", "Client", "Provider", "Layer", "Reqs", "Cost"], rows)
        print()

    # Dashboard link
    print(_c("  ── Dashboard ───────────────────────────", DIM))
    url = generate_dashboard_url(**filters)
    print(f"  {_c('View in browser:', DIM)} {_c('open', BOLD)} '{url}'")

    # Build CLI command suggestion with filters
    filter_args = []
    for key, value in filters.items():
        if key == "success":
            filter_args.append(f"--success {str(value).lower()}")
        else:
            filter_args.append(f"--{key.replace('_', '-')} {value}")
    filter_str = " ".join(filter_args)
    print(f"  {_c('Generate deep link:', DIM)} {_c(f'faigate-stats --link --view overview {filter_str}', DIM)}")
    print()


def cmd_recent(metrics: MetricsStore, limit: int, **filters):
    recent = metrics.get_recent(limit, **filters)
    if not recent:
        print(_c("  No requests recorded yet.", DIM))
        return

    print()
    print(_c(f"  ── Last {limit} Requests ──", DIM))
    rows = []
    for r in recent:
        ok = "✓" if r.get("success") else _c("✗", RED)
        rows.append(
            [
                _ago(r.get("timestamp")),
                r.get("provider", ""),
                r.get("layer", ""),
                r.get("rule_name", ""),
                _tok((r.get("prompt_tok", 0) or 0) + (r.get("compl_tok", 0) or 0)),
                _usd(r.get("cost_usd", 0)),
                _ms(r.get("latency_ms", 0)),
                ok,
            ]
        )
    _table(
        ["When", "Provider", "Layer", "Rule", "Tokens", "Cost", "Latency", "OK"],
        rows,
        [12, 20, 12, 20, 8, 12, 10, 4],
    )
    print()

    # Dashboard link
    print(_c("  ── Dashboard ───────────────────────────", DIM))
    url = generate_dashboard_url(**filters)
    print(f"  {_c('View in browser:', DIM)} {_c('open', BOLD)} '{url}'")

    # Build CLI command suggestion with filters
    filter_args = []
    for key, value in filters.items():
        if key == "success":
            filter_args.append(f"--success {str(value).lower()}")
        else:
            filter_args.append(f"--{key.replace('_', '-')} {value}")
    filter_str = " ".join(filter_args)
    print(f"  {_c('See more recent:', DIM)} {_c(f'faigate-stats --link --view overview {filter_str}', DIM)}")
    print()


def cmd_daily(metrics: MetricsStore, days: int, **filters):
    daily = metrics.get_daily_totals(days)
    if not daily:
        print(_c("  No data for the selected period.", DIM))
        return

    print()
    print(_c(f"  ── Daily Breakdown (last {days}d) ──", DIM))
    max_cost = max((d.get("cost_usd", 0) or 0) for d in daily) if daily else 1
    rows = []
    for d in daily:
        cost = d.get("cost_usd", 0) or 0
        ratio = cost / max_cost if max_cost else 0
        rows.append(
            [
                d.get("day", ""),
                str(d.get("requests", 0)),
                _tok(d.get("tokens", 0)),
                _usd(cost),
                str(d.get("failures", 0)),
                _bar(ratio, 20),
            ]
        )
    _table(["Day", "Reqs", "Tokens", "Cost", "Fail", "Cost Bar"], rows, [14, 8, 10, 12, 6, 24])

    total_cost = sum((d.get("cost_usd", 0) or 0) for d in daily)
    avg_daily = total_cost / len(daily) if daily else 0
    print()
    print(
        f"  {_c('Total:', DIM)} {_usd(total_cost)}   "
        f"{_c('Avg/day:', DIM)} {_usd(avg_daily)}   "
        f"{_c('Projected/month:', DIM)} {_usd(avg_daily * 30)}"
    )
    print()

    # Dashboard link
    print(_c("  ── Dashboard ───────────────────────────", DIM))
    url = generate_dashboard_url(view="analytics")
    print(f"  {_c('View analytics:', DIM)} {_c('open', BOLD)} '{url}'")
    print(f"  {_c('Generate deep link:', DIM)} {_c('faigate-stats --link --view analytics', DIM)}")
    print()


def cmd_project(
    tokens_input: int,
    tokens_output: int,
    model: str,
    include_credits: bool = True,
):
    """Project costs for a given token usage and model."""
    print()
    print(_c("  ── Cost Projection ──", DIM))
    print()

    # Get all providers that offer this model
    offerings = get_offerings_catalog()
    providers_for_model = set()
    for offering in offerings.values():
        if offering.get("model_id") == model:
            providers_for_model.add(offering.get("provider_id"))

    if not providers_for_model:
        print(_c(f"  No providers found offering model '{model}'.", RED))
        print(_c("  Check offerings catalog or try a different model.", DIM))
        return

    results = []
    for provider_id in providers_for_model:
        estimate = estimate_provider_cost(provider_id, model, tokens_input, tokens_output)
        results.append(estimate)

    # Sort by total cost ascending
    results.sort(key=lambda x: x["total_cost"])

    # Display results
    for i, estimate in enumerate(results):
        color = GREEN if i == 0 else WHITE  # highlight cheapest
        provider = estimate["provider"]
        total_cost = estimate["total_cost"]
        credits = estimate["credits_remaining"]
        cost_after = estimate["cost_after_credits"]

        print(f"  {_c(provider, color)}")
        print(
            f"    Input:  {_tok(tokens_input)} tokens × ${estimate['input_cost_per_1m']:.4f}/1M"
            f" = {_usd(estimate['input_cost'])}"
        )
        print(
            f"    Output: {_tok(tokens_output)} tokens × ${estimate['output_cost_per_1m']:.4f}/1M"
            f" = {_usd(estimate['output_cost'])}"
        )
        print(f"    Total:  {_usd(total_cost)}")
        if credits > 0 and include_credits:
            print(f"    Credits: {_usd(credits)} remaining")
            print(f"    After credits: {_usd(cost_after)}")
        if estimate.get("packages"):
            pkg_count = len(estimate["packages"])
            print(f"    Packages: {pkg_count} available")
            for pkg in estimate["packages"][:2]:
                name = pkg.get("name", "unknown")
                remaining = pkg.get("remaining", 0)
                total = pkg.get("total_credits", 0)
                expiry = pkg.get("expiry_date", "none")
                print(f"      - {name}: {remaining}/{total} credits (expires {expiry})")
        print()

    # Summary
    if len(results) > 1:
        cheapest = results[0]
        most_expensive = results[-1]
        print(_c("  ── Summary ──", DIM))
        print(f"  Cheapest: {_c(cheapest['provider'], GREEN)} at {_usd(cheapest['total_cost'])}")
        print(f"  Most expensive: {_c(most_expensive['provider'], RED)} at {_usd(most_expensive['total_cost'])}")
        if cheapest["total_cost"] > 0:
            ratio = most_expensive["total_cost"] / cheapest["total_cost"]
            print(f"  Price ratio: {ratio:.1f}x")
        print()


def cmd_trends(metrics: MetricsStore, days: int, **filters):
    """Show cost trends over time."""
    daily = metrics.get_daily_totals(days)
    if not daily:
        print(_c("  No data for the selected period.", DIM))
        return

    print()
    print(_c(f"  ── Cost Trends (last {days}d) ──", DIM))

    # Find max cost for scaling
    max_cost = max((d.get("cost_usd", 0) or 0) for d in daily) if daily else 1
    total_cost = sum((d.get("cost_usd", 0) or 0) for d in daily)
    avg_daily = total_cost / len(daily) if daily else 0

    rows = []
    for d in daily:
        day = d.get("day", "")
        cost = d.get("cost_usd", 0) or 0
        requests = d.get("requests", 0) or 0
        tokens = d.get("tokens", 0) or 0
        ratio = cost / max_cost if max_cost else 0
        rows.append(
            [
                day,
                str(requests),
                _tok(tokens),
                _usd(cost),
                _bar(ratio, 20),
            ]
        )
    _table(["Day", "Reqs", "Tokens", "Cost", "Cost Bar"], rows, [14, 8, 10, 12, 24])

    print()
    print(
        f"  {_c('Total:', DIM)} {_usd(total_cost)}   "
        f"{_c('Avg/day:', DIM)} {_usd(avg_daily)}   "
        f"{_c('Projected/month:', DIM)} {_usd(avg_daily * 30)}"
    )
    print()

    # Dashboard link
    print(_c("  ── Dashboard ───────────────────────────", DIM))
    url = generate_dashboard_url(view="analytics", **filters)
    print(f"  {_c('View analytics:', DIM)} {_c('open', BOLD)} '{url}'")
    print(f"  {_c('Generate deep link:', DIM)} {_c('faigate-stats --link --view analytics', DIM)}")
    print()


def cmd_suggest(metrics: MetricsStore, **filters):
    """Suggest relevant CLI commands based on metrics analysis."""
    totals = metrics.get_totals(**filters)
    providers = metrics.get_provider_summary(**filters)
    recent = metrics.get_recent(20, **filters)

    total_requests = totals.get("total_requests", 0) or 0
    total_failures = totals.get("total_failures", 0) or 0
    total_cost = totals.get("total_cost_usd", 0) or 0

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  CLI Command Suggestions", BOLD) + _c("      ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    suggestions = []

    # Analyze failures
    failure_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    if failure_rate > 10:  # More than 10% failure rate
        suggestions.append(
            {
                "priority": "high",
                "description": f"High failure rate ({failure_rate:.1f}%)",
                "command": "faigate-stats --recent 20 --success false",
                "reason": "Investigate recent failed requests",
            }
        )

    # Analyze provider distribution
    if providers:
        top_provider = max(providers, key=lambda p: p.get("requests", 0)) if providers else None
        if top_provider:
            provider_name = top_provider.get("provider", "")
            provider_requests = top_provider.get("requests", 0)
            provider_share = (provider_requests / total_requests * 100) if total_requests > 0 else 0

            if provider_share > 50:  # One provider handles >50% of traffic
                suggestions.append(
                    {
                        "priority": "medium",
                        "description": f"Provider concentration: {provider_name} ({provider_share:.1f}% of traffic)",
                        "command": f"faigate-stats --provider {provider_name}",
                        "reason": "Focus on dominant provider",
                    }
                )

    # Analyze cost
    if total_cost > 10:  # More than $10 total cost
        suggestions.append(
            {
                "priority": "medium",
                "description": f"Significant cost detected (${total_cost:.2f})",
                "command": "faigate-stats --daily --days 30",
                "reason": "Review daily cost breakdown",
            }
        )

    # Analyze recent activity
    if recent:
        recent_failures = sum(1 for r in recent if not r.get("success"))
        if recent_failures > 0:
            suggestions.append(
                {
                    "priority": "medium",
                    "description": f"Recent failures ({recent_failures} in last 20 requests)",
                    "command": "faigate-stats --recent 20",
                    "reason": "Check recent request log",
                }
            )

    # Always suggest dashboard link
    suggestions.append(
        {
            "priority": "low",
            "description": "Open dashboard for visual analysis",
            "command": "faigate-stats --link",
            "reason": "Interactive exploration",
        }
    )

    # Sort by priority (high > medium > low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda x: priority_order[x["priority"]])

    if not suggestions:
        print(_c("  No specific suggestions based on current metrics.", DIM))
        print(_c("  Try:", DIM))
        print(_c("    • faigate-stats --overview", DIM))
        print(_c("    • faigate-stats --link", DIM))
        print()
        return

    for i, suggestion in enumerate(suggestions, 1):
        priority_color = {
            "high": RED,
            "medium": YELLOW,
            "low": GREEN,
        }.get(suggestion["priority"], WHITE)

        print(f"  {i}. {_c(suggestion['description'], priority_color)}")
        print(f"     {_c('Command:', DIM)} {_c(suggestion['command'], BOLD)}")
        print(f"     {_c('Reason:', DIM)} {suggestion['reason']}")
        print()

    print(_c("  Tip: Use filters to focus analysis:", DIM))
    print(_c("    • --provider <name>   Filter by provider", DIM))
    print(_c("    • --success false     Show only failures", DIM))
    print(_c("    • --days 7            Limit to last 7 days", DIM))
    print()


# ── Main ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="faigate-stats",
        description="CLI dashboard for fusionAIze Gate metrics",
    )
    parser.add_argument("--db", help="Path to metrics DB (default: from config)")
    parser.add_argument("--recent", type=int, metavar="N", help="Show last N requests")
    parser.add_argument("--daily", action="store_true", help="Show daily cost breakdown")
    parser.add_argument("--days", type=int, default=30, help="Days for --daily (default: 30)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--project", action="store_true", help="Project costs for token usage")
    parser.add_argument(
        "--tokens-input", type=int, default=0, help="Input tokens for projection (required with --project)"
    )
    parser.add_argument(
        "--tokens-output", type=int, default=0, help="Output tokens for projection (required with --project)"
    )
    parser.add_argument(
        "--model", type=str, default="deepseek/chat", help="Model ID for projection (e.g., 'deepseek/chat')"
    )
    parser.add_argument("--no-credits", action="store_true", help="Exclude package credits from projection")
    parser.add_argument("--trends", action="store_true", help="Show cost trends over time")
    parser.add_argument("--trend-days", type=int, default=30, help="Days for --trends (default: 30)")
    parser.add_argument("--suggest", action="store_true", help="Suggest relevant CLI commands based on metrics")

    # Dashboard link arguments
    parser.add_argument("--link", action="store_true", help="Generate dashboard deep-link URL")
    parser.add_argument(
        "--view",
        type=str,
        default="overview",
        help="Dashboard view (overview, providers, clients, routes, analytics, catalog, integrations)",
    )
    parser.add_argument("--provider", type=str, default="", help="Filter by provider")
    parser.add_argument("--modality", type=str, default="", help="Filter by modality")
    parser.add_argument("--client-profile", type=str, default="", help="Filter by client profile")
    parser.add_argument("--client-tag", type=str, default="", help="Filter by client tag")
    parser.add_argument("--layer", type=str, default="", help="Filter by layer")
    parser.add_argument("--success", type=str, default="", help="Filter by success (true/false)")
    parser.add_argument("--saved-view", type=str, default="", help="Use saved view ID")
    parser.add_argument("--copy", action="store_true", help="Copy URL to clipboard")

    args = parser.parse_args()

    # Build filters dict from filter arguments (for metrics queries)
    filters = {}
    if args.provider:
        filters["provider"] = args.provider
    if args.modality:
        filters["modality"] = args.modality
    if args.client_profile:
        filters["client_profile"] = args.client_profile
    if args.client_tag:
        filters["client_tag"] = args.client_tag
    if args.layer:
        filters["layer"] = args.layer
    if args.success:
        # Convert string "true"/"false" to boolean, otherwise pass as-is
        lower = args.success.lower()
        if lower == "true":
            filters["success"] = True
        elif lower == "false":
            filters["success"] = False
        else:
            filters["success"] = args.success

    # Handle dashboard link mode
    if args.link:
        cmd_dashboard_link(
            view=args.view,
            provider=args.provider,
            modality=args.modality,
            client_profile=args.client_profile,
            client_tag=args.client_tag,
            layer=args.layer,
            success=args.success,
            saved_view=args.saved_view,
            copy=args.copy,
        )
        return

    # Handle projection mode
    if args.project:
        if args.tokens_input <= 0 or args.tokens_output <= 0:
            print("Error: --tokens-input and --tokens-output must be positive with --project", file=sys.stderr)
            sys.exit(1)
        cmd_project(
            tokens_input=args.tokens_input,
            tokens_output=args.tokens_output,
            model=args.model,
            include_credits=not args.no_credits,
        )
        return

    # Find DB
    db_path = args.db
    if not db_path:
        try:
            cfg = load_config()
            db_path = cfg.metrics.get("db_path", _safe_db_path())
        except FileNotFoundError:
            db_path = _safe_db_path()

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Run the dispatcher first to create the database.", file=sys.stderr)
        sys.exit(1)

    metrics = MetricsStore(db_path)
    metrics.init()

    if args.json:
        data = {
            "totals": metrics.get_totals(**filters),
            "providers": metrics.get_provider_summary(**filters),
            "routing": metrics.get_routing_breakdown(**filters),
            "clients": metrics.get_client_breakdown(**filters),
            "daily": metrics.get_daily_totals(args.days),
            "recent": metrics.get_recent(args.recent or 20, **filters),
        }
        print(json.dumps(data, indent=2, default=str))
        metrics.close()
        return

    if args.recent:
        cmd_recent(metrics, args.recent, **filters)
    elif args.daily:
        cmd_daily(metrics, args.days)
    elif args.trends:
        cmd_trends(metrics, args.trend_days, **filters)
    elif args.suggest:
        cmd_suggest(metrics, **filters)
    else:
        cmd_overview(metrics, **filters)

    metrics.close()


if __name__ == "__main__":
    main()
