"""CLI for the provider catalog updater.

Usage:
    faigate-models update               Force-refresh the cached catalog from remote.
    faigate-models update --check       Exit 0 if cache is fresh, 1 if stale, 2 on error.
    faigate-models update --diff        Show provider/model deltas vs current cache.
    faigate-models status               Print cache age, source, ETag, providers count.
    faigate-models probe-window         Probe context windows from recorded /models responses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .catalog_resolver import (
    CatalogResolver,
    ResolverConfig,
)


def _format_age(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 5400:
        return f"{int(seconds / 60)}m"
    if seconds < 86400 * 2:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _diff_providers(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    return {"added": added, "removed": removed, "changed": changed}


def cmd_update(args: argparse.Namespace) -> int:
    config = ResolverConfig.from_env()
    resolver = CatalogResolver(config=config)
    status_before = resolver.status()

    # Capture current cache for diff
    before_payload: dict[str, Any] = {}
    for tier in ("private", "public"):
        cached = resolver._cache.load(tier)  # noqa: SLF001 — intentional
        if cached is not None:
            before_payload = cached.payload
            break

    if args.check:
        # Don't fetch — just inspect TTL
        for tier in ("private", "public"):
            entry = status_before["tiers"].get(tier, {})
            if entry.get("present") and entry.get("age_seconds", 1e9) < config.refresh_interval_seconds:
                print(f"fresh ({tier}, age {_format_age(entry['age_seconds'])})")
                return 0
        print("stale or missing")
        return 1

    resolved = resolver.resolve(force_refresh=True)
    if resolved.source == "empty":
        print(f"ERROR: no catalog source available; notes={resolved.notes}", file=sys.stderr)
        return 2

    after_providers = resolved.payload.get("providers", {})
    print(f"updated: source={resolved.source} providers={len(after_providers)}")
    if resolved.etag:
        print(f"  etag: {resolved.etag}")

    if args.diff:
        before_providers = before_payload.get("providers", {}) if before_payload else {}
        diff = _diff_providers(before_providers, after_providers)
        if any(diff.values()):
            for label in ("added", "removed", "changed"):
                if diff[label]:
                    print(f"  {label}:")
                    for entry in diff[label]:
                        print(f"    - {entry}")
        else:
            print("  no provider-level changes")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    resolver = CatalogResolver()
    status = resolver.status()

    if args.json:
        print(json.dumps(status, indent=2, default=str))
        return 0

    print("Catalog cache status")
    print("-" * 40)
    for tier in ("private", "public"):
        entry = status["tiers"][tier]
        if not entry.get("present"):
            print(f"  {tier:8}  not cached")
            continue
        age = _format_age(entry.get("age_seconds"))
        etag = entry.get("etag") or "<none>"
        count = entry.get("providers_count", 0)
        print(f"  {tier:8}  age={age}  providers={count}  etag={etag}")

    bundled = "yes" if status.get("bundled_present") else "no"
    print(f"  bundled  present={bundled}", end="")
    if status.get("bundled_present"):
        print(f"  providers={status.get('bundled_providers_count', 0)}")
    else:
        print()
    return 0


def cmd_probe_window(args: argparse.Namespace) -> int:
    """Probe context windows from recorded /models responses and show the results.

    This is an offline operator command: it reads recorded ``GET /models`` JSON
    fixtures from *--fixtures-dir* (default: ``tests/fixtures/models_probe/``),
    probes every provider listed in ``_PROBE_FIELD_PATHS`` for which a fixture
    exists, and prints the enforceable/advisory view with before/after
    unconfirmed counts.

    Without a fixture file for a provider, that provider is skipped with a
    note — the probe never makes network calls.  A provider that has no entry
    in ``_PROBE_FIELD_PATHS`` is flagged as unlisted.
    """
    from .provider_catalog import (
        _PROBE_FIELD_PATHS,
        build_probed_window_view,
        probe_context_window_evidence,
    )

    fixtures_dir = Path(args.fixtures_dir)
    if not fixtures_dir.is_dir():
        print(f"ERROR: fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        return 2

    # Map provider names to fixture file stems.  Providers like
    # "deepseek-chat" and "deepseek-reasoner" share "deepseek_models.json".
    _FIXTURE_STEMS: dict[str, str] = {
        "byteplus": "byteplus",
        "deepseek-chat": "deepseek",
        "deepseek-reasoner": "deepseek",
        "openrouter-fallback": "openrouter",
        "mistral": "mistral",
    }

    probe_results: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    no_field_path: list[str] = []

    for name in _PROBE_FIELD_PATHS:
        stem = _FIXTURE_STEMS.get(name, name)
        fixture_path = fixtures_dir / f"{stem}_models.json"
        if not fixture_path.is_file():
            skipped.append(name)
            continue
        try:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: cannot read fixture for {name!r}: {exc}", file=sys.stderr)
            skipped.append(name)
            continue
        probe_results[name] = probe_context_window_evidence(name, data)

    # Also probe fixture files for providers that have no _PROBE_FIELD_PATHS
    # entry. These providers have a recorded /models response but no one has
    # configured a field path for them — the operator needs to see them named.
    probed_stems: set[str] = {_FIXTURE_STEMS.get(n, n) for n in _PROBE_FIELD_PATHS}
    for fixture_path in sorted(fixtures_dir.glob("*_models.json")):
        stem = fixture_path.stem.replace("_models", "")
        if stem in probed_stems:
            continue
        try:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: cannot read fixture {fixture_path.name!r}: {exc}", file=sys.stderr)
            continue
        # Use the stem as the probe name — these providers are not in
        # _PROBE_FIELD_PATHS, so probe_context_window_evidence returns
        # unknown_kind="unlisted" with probe_state="no_field_path".
        probe_results[stem] = probe_context_window_evidence(stem, data)
        no_field_path.append(stem)

    if not probe_results:
        print(
            "ERROR: no probe results — no fixture files found for any provider in _PROBE_FIELD_PATHS.",
            file=sys.stderr,
        )
        print(f"  fixtures directory: {fixtures_dir}", file=sys.stderr)
        print(f"  providers in field-path table: {sorted(_PROBE_FIELD_PATHS)}", file=sys.stderr)
        return 2

    # no_field_path is collected during the fixture scan above; pass it through
    # to the report so the operator sees providers with recordings but no mapping.
    # The summary also carries it, but the text report prints it explicitly.

    view = build_probed_window_view(probe_results)

    if args.json:
        output: dict[str, Any] = {
            "enforceable": view["enforceable"],
            "advisory": view["advisory"],
            "summary": view["summary"],
        }
        if skipped:
            output["skipped"] = skipped
        if no_field_path:
            output["no_field_path"] = no_field_path
        print(json.dumps(output, indent=2, default=str))
        return 0

    _print_probe_window_report(view, probe_results, skipped, no_field_path)
    return 0


def _print_probe_window_report(
    view: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
    skipped: list[str],
    no_field_path: list[str],
) -> None:
    summary = view["summary"]
    enforceable = view["enforceable"]

    print("Probed context-window view")
    print("=" * 60)

    # Summary
    print(f"  probed confirmed : {summary['probed_confirmed']}")
    print(f"  probed unlisted  : {summary['probed_unlisted']}")
    if summary.get("probed_no_field_path"):
        providers_str = ", ".join(summary["no_field_path_providers"])
        print(f"  probed no field path: {summary['probed_no_field_path']}  ({providers_str})")
    print(f"  conflicts        : {summary['conflict_count']}")
    print(f"  unconfirmed before : {summary['unconfirmed_before']}")
    print(f"  unconfirmed after  : {summary['unconfirmed_after']}")

    if skipped:
        print(f"\n  skipped (no fixture): {', '.join(skipped)}")

    if no_field_path:
        print(f"\n  no field path configured: {', '.join(no_field_path)}")
        print("    (recorded response exists but no entry in _PROBE_FIELD_PATHS)")

    # Per-provider details
    print(f"\n  Enforceable view ({len(enforceable)} providers):")
    if not enforceable:
        print("    (none)")
    else:
        for name in sorted(enforceable):
            fact = enforceable[name]
            ev = fact.get("evidence", {})
            probed_value = ev.get("probed_value", fact["context_window"])
            field_path = ev.get("field_path", "n/a")
            print(f"    {name:30s}  window={probed_value:>6d}  path={field_path}")

    # Conflicts
    if summary["conflicts"]:
        print("\n  Conflicts (probe disagrees with catalog):")
        for c in summary["conflicts"]:
            print(f"    {c['provider']:30s}  catalog={c['catalog_value']:>6d}  probe={c['probed_value']:>6d}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="faigate-models",
        description="Manage the faigate provider catalog cache.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="Refresh the cached catalog from remote.")
    p_update.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if cache is fresh, 1 if stale, 2 on error. No network.",
    )
    p_update.add_argument(
        "--diff",
        action="store_true",
        help="Show provider deltas after refresh.",
    )
    p_update.set_defaults(func=cmd_update)

    p_status = sub.add_parser("status", help="Show cache state.")
    p_status.add_argument("--json", action="store_true", help="Emit JSON.")
    p_status.set_defaults(func=cmd_status)

    p_probe = sub.add_parser("probe-window", help="Probe context windows from recorded /models responses.")
    p_probe.add_argument(
        "--fixtures-dir",
        default=str(Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "models_probe"),
        help="Directory with recorded GET /models JSON fixtures (default: tests/fixtures/models_probe/)",
    )
    p_probe.add_argument("--json", action="store_true", help="Emit JSON.")
    p_probe.set_defaults(func=cmd_probe_window)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
