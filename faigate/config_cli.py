#!/usr/bin/env python3
"""faigate-config – Safe config workflows for fusionAIze Gate.

Usage:
    python -m faigate.config_cli preview <new-config.yaml>     # Preview changes
    python -m faigate.config_cli diff <new-config.yaml>        # Show detailed diff
    python -m faigate.config_cli apply <new-config.yaml>       # Apply with confirmation
    python -m faigate.config_cli validate <config.yaml>        # Validate config syntax
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from .config import ConfigError, load_config
from .wizard import build_config_change_summary

# Reuse color formatting from cli.py
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


def _load_yaml(path: str | Path) -> dict[str, Any]:
    """Load YAML file with error handling."""
    path = Path(path)
    if not path.exists():
        print(f"{_c('Error:', RED)} Config file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        print(f"{_c('Error:', RED)} Invalid YAML in {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{_c('Error:', RED)} Failed to read {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _get_current_config_path() -> Path:
    """Get path to current config from environment or default."""
    config_path = os.environ.get("FAIGATE_CONFIG_FILE")
    if config_path and Path(config_path).exists():
        return Path(config_path)

    # Try default locations
    default_paths = [
        Path("config.yaml"),
        Path("/etc/faigate/config.yaml"),
        Path.home() / ".config" / "faigate" / "config.yaml",
    ]

    for path in default_paths:
        if path.exists():
            return path

    print(
        f"{_c('Error:', RED)} No config file found. Set FAIGATE_CONFIG_FILE or place config.yaml in current directory.",
        file=sys.stderr,
    )
    sys.exit(1)


def cmd_preview(new_config_path: str, current_config_path: str | None = None):
    """Preview changes between current and new config."""
    if not current_config_path:
        current_config_path = str(_get_current_config_path())

    # Load both configs to validate syntax
    _ = _load_yaml(current_config_path)  # Validate current config
    new_config = _load_yaml(new_config_path)

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Config Change Preview", BOLD) + _c("          ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    print(_c(f"  Current config: {current_config_path}", DIM))
    print(_c(f"  New config:     {new_config_path}", DIM))
    print()

    try:
        summary = build_config_change_summary(
            config_path=current_config_path,
            updated_config=new_config,
        )

        # Display summary
        added_providers = summary.get("added_providers", [])
        replaced_models = summary.get("replaced_models", [])
        changed_profile_modes = summary.get("changed_profile_modes", [])
        fallback_additions = summary.get("fallback_additions", [])

        if not any([added_providers, replaced_models, changed_profile_modes, fallback_additions]):
            print(_c("  No significant changes detected.", GREEN))
            print(_c("  (Configs are identical or changes are outside tracked sections)", DIM))
            print()
            return

        if added_providers:
            print(_c("  ➕ Added providers:", GREEN))
            for provider in added_providers:
                print(f"    • {_c(provider, BOLD)}")
            print()

        if replaced_models:
            print(_c("  🔄 Changed provider models:", YELLOW))
            for change in replaced_models:
                provider = change["provider"]
                from_model = change["from_model"]
                to_model = change["to_model"]
                print(f"    • {_c(provider, BOLD)}: {from_model} → {to_model}")
            print()

        if changed_profile_modes:
            print(_c("  📋 Changed profile routing modes:", CYAN))
            for change in changed_profile_modes:
                profile = change["profile"]
                from_mode = change["from_mode"]
                to_mode = change["to_mode"]
                print(f"    • {_c(profile, BOLD)}: {from_mode} → {to_mode}")
            print()

        if fallback_additions:
            print(_c("  ⛓️  Added to fallback chain:", MAGENTA))
            for provider in fallback_additions:
                print(f"    • {_c(provider, BOLD)}")
            print()

        print(_c("  Next steps:", DIM))
        print(f"    {_c('View diff:', DIM)} {_c(f'faigate-config diff {new_config_path}', BOLD)}")
        print(f"    {_c('Apply changes:', DIM)} {_c(f'faigate-config apply {new_config_path}', BOLD)}")
        print()

    except Exception as e:
        print(f"{_c('Error:', RED)} Failed to analyze config changes: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_diff(new_config_path: str, current_config_path: str | None = None):
    """Show detailed diff between current and new config."""
    if not current_config_path:
        current_config_path = str(_get_current_config_path())

    try:
        current_content = Path(current_config_path).read_text(encoding="utf-8").splitlines(keepends=True)
        new_content = Path(new_config_path).read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:
        print(f"{_c('Error:', RED)} Failed to read config files: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Config Diff", BOLD) + _c("                 ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    print(_c(f"  --- {current_config_path}", RED))
    print(_c(f"  +++ {new_config_path}", GREEN))
    print()

    diff = difflib.unified_diff(
        current_content,
        new_content,
        fromfile=current_config_path,
        tofile=new_config_path,
        lineterm="",
    )

    diff_lines = list(diff)
    if not diff_lines:
        print(_c("  Configs are identical.", GREEN))
        print()
        return

    for line in diff_lines:
        if line.startswith("---"):
            print(_c(line, RED))
        elif line.startswith("+++"):
            print(_c(line, GREEN))
        elif line.startswith("@@"):
            print(_c(line, CYAN))
        elif line.startswith("-"):
            print(_c(line, RED))
        elif line.startswith("+"):
            print(_c(line, GREEN))
        else:
            print(line.rstrip())

    print()


def cmd_apply(new_config_path: str, current_config_path: str | None = None, force: bool = False):
    """Apply new config with safety checks."""
    if not current_config_path:
        current_config_path = str(_get_current_config_path())

    current_path = Path(current_config_path)
    new_path = Path(new_config_path)

    if not new_path.exists():
        print(f"{_c('Error:', RED)} New config file not found: {new_config_path}", file=sys.stderr)
        sys.exit(1)

    # Preview changes first
    _ = _load_yaml(current_path)  # Validate current config syntax
    new_config = _load_yaml(new_path)

    try:
        summary = build_config_change_summary(
            config_path=current_config_path,
            updated_config=new_config,
        )
    except Exception as e:
        print(f"{_c('Error:', RED)} Failed to analyze config changes: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Apply Config Changes", BOLD) + _c("         ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    print(_c(f"  Current config: {current_config_path}", DIM))
    print(_c(f"  New config:     {new_config_path}", DIM))
    print()

    # Show summary
    added_providers = summary.get("added_providers", [])
    replaced_models = summary.get("replaced_models", [])
    changed_profile_modes = summary.get("changed_profile_modes", [])
    fallback_additions = summary.get("fallback_additions", [])

    has_changes = any([added_providers, replaced_models, changed_profile_modes, fallback_additions])

    if not has_changes:
        print(_c("  No significant changes detected.", GREEN))
        print(_c("  Configs are identical or changes are outside tracked sections.", DIM))
        print()

    if added_providers:
        print(_c("  ➕ Will add providers:", GREEN))
        for provider in added_providers:
            print(f"    • {_c(provider, BOLD)}")

    if replaced_models:
        print(_c("  🔄 Will change provider models:", YELLOW))
        for change in replaced_models:
            provider = change["provider"]
            from_model = change["from_model"]
            to_model = change["to_model"]
            print(f"    • {_c(provider, BOLD)}: {from_model} → {to_model}")

    if changed_profile_modes:
        print(_c("  📋 Will change profile routing modes:", CYAN))
        for change in changed_profile_modes:
            profile = change["profile"]
            from_mode = change["from_mode"]
            to_mode = change["to_mode"]
            print(f"    • {_c(profile, BOLD)}: {from_mode} → {to_mode}")

    if fallback_additions:
        print(_c("  ⛓️  Will add to fallback chain:", MAGENTA))
        for provider in fallback_additions:
            print(f"    • {_c(provider, BOLD)}")

    print()

    if not force:
        print(_c("  ⚠️  Warning: Applying config changes will:", YELLOW))
        print(_c("     1. Replace the current config file", DIM))
        print(_c("     2. Require gateway restart to take effect", DIM))
        print()

        try:
            response = input(_c("  Continue? (y/N): ", BOLD)).strip().lower()
            if response not in ("y", "yes"):
                print(_c("  Cancelled.", DIM))
                print()
                return
        except KeyboardInterrupt:
            print()
            print(_c("  Cancelled.", DIM))
            print()
            return

    # Create backup
    backup_path = current_path.with_suffix(current_path.suffix + ".bak")
    try:
        import shutil

        shutil.copy2(current_path, backup_path)
        print(_c(f"  ✓ Created backup: {backup_path}", GREEN))
    except Exception as e:
        print(f"{_c('Warning:', YELLOW)} Failed to create backup: {e}")

    # Apply config
    try:
        new_content = new_path.read_text(encoding="utf-8")
        current_path.write_text(new_content, encoding="utf-8")
        print(_c(f"  ✓ Config applied: {current_path}", GREEN))
    except Exception as e:
        print(f"{_c('Error:', RED)} Failed to apply config: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print(_c("  Next steps:", DIM))
    print(_c("    1. Restart the gateway:", BOLD))
    print(_c("       systemctl restart faigate  # systemd", DIM))
    print(_c("       or kill -HUP $(pgrep -f 'faigate')  # reload if supported", DIM))
    print()
    print(_c("    2. Verify config:", BOLD))
    print(_c(f"       faigate-config validate {current_path}", DIM))
    print()


def cmd_validate(config_path: str):
    """Validate config syntax and semantics."""
    path = Path(config_path)
    if not path.exists():
        print(f"{_c('Error:', RED)} Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Config Validation", BOLD) + _c("           ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    print(_c(f"  Validating: {config_path}", DIM))
    print()

    # Try to load YAML first
    try:
        content = path.read_text(encoding="utf-8")
        _ = yaml.safe_load(content)  # Validate YAML syntax
        print(_c("  ✓ YAML syntax is valid", GREEN))
    except yaml.YAMLError as e:
        print(f"{_c('  ✗ YAML syntax error:', RED)} {e}")
        sys.exit(1)

    # Try to load as Config object
    try:
        config = load_config(config_path)
        print(_c("  ✓ Config structure is valid", GREEN))
    except ConfigError as e:
        print(f"{_c('  ✗ Config validation error:', RED)} {e}")
        sys.exit(1)
    except Exception as e:
        print(f"{_c('  ✗ Unexpected error:', RED)} {e}")
        sys.exit(1)

    # Basic checks
    issues = []

    # Check for required sections
    if not getattr(config, "providers", None):
        issues.append("No providers defined")

    if not getattr(config, "routing_modes", None):
        issues.append("No routing_modes defined")

    if not getattr(config, "client_profiles", None):
        issues.append("No client_profiles defined")

    if issues:
        print()
        print(_c("  ⚠️  Config warnings:", YELLOW))
        for issue in issues:
            print(f"    • {issue}")

    print()
    print(_c("  Validation passed successfully.", GREEN))
    print()


def cmd_discover(json_output: bool = False, no_scan: bool = False, no_grid: bool = False, timeout: float = 3.0):
    """Discover local workers and display results."""
    import asyncio

    from .local_discovery import discover_local_workers, generate_provider_config

    print()
    print(_c("  ╔══════════════════════════════════════╗", BLUE))
    print(_c("  ║", BLUE) + _c("  Local Worker Discovery", BOLD) + _c("    ║", BLUE))
    print(_c("  ╚══════════════════════════════════════╝", BLUE))
    print()

    workers = asyncio.run(
        discover_local_workers(scan_ports=not no_scan, check_grid=not no_grid, timeout_per_worker=timeout)
    )

    if json_output:
        import json

        result = [
            {
                "name": w["name"],
                "base_url": w["base_url"],
                "healthy": w["healthy"],
                "models": w["models"],
                "config": generate_provider_config(w),
            }
            for w in workers
        ]
        print(json.dumps(result, indent=2))
        return

    if not workers:
        print(_c("  No local workers discovered.", DIM))
        print()
        return

    print(_c(f"  Found {len(workers)} local worker(s):", GREEN))
    print()

    for i, worker in enumerate(workers, 1):
        status = _c("✓", GREEN) if worker["healthy"] else _c("✗", RED)
        name = _c(worker["name"], BOLD)
        base_url = worker["base_url"]
        models = worker["models"]

        print(f"  {i}. {status} {name} – {base_url}")

        if worker["healthy"]:
            if models:
                print(f"     {_c('Models:', DIM)} {', '.join(models[:3])}")
                if len(models) > 3:
                    print(f"     {_c('     ... and', DIM)} {len(models) - 3} more")
            else:
                print(f"     {_c('Models:', DIM)} Not discoverable")
        else:
            print(f"     {_c('Status:', DIM)} Health check failed")
        print()

    # Show configuration suggestions
    print(_c("  Configuration suggestions:", CYAN))
    print()

    for worker in workers:
        if worker["healthy"]:
            config = generate_provider_config(worker)
            provider_name = worker["name"]
            print(f"  To add {_c(provider_name, BOLD)} to config.yaml:")
            print(f"    {provider_name}:")
            print("      contract: local-worker")
            print(f"      backend: {config.get('backend', 'openai-compat')}")
            print(f"      base_url: {config['base_url']}")
            if "model" in config:
                print(f"      model: {config['model']}")
            print("      tier: local")
            print("      capabilities:")
            print("        local: true")
            print("        cloud: false")
            print("        network_zone: local")
            print("        cost_tier: local")
            print("        latency_tier: local")
            print()

    print(_c("  Next steps:", DIM))
    print(f"    {_c('Add a worker:', BOLD)} Edit config.yaml and add provider configuration")
    print(f"    {_c('Validate config:', BOLD)} faigate-config validate config.yaml")
    print(f"    {_c('Apply changes:', BOLD)} faigate-config apply config.yaml")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="faigate-config",
        description="Safe config workflows for fusionAIze Gate",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    # Preview command
    preview_parser = subparsers.add_parser("preview", help="Preview config changes")
    preview_parser.add_argument("new_config", help="Path to new config YAML file")
    preview_parser.add_argument("--current-config", help="Path to current config (default: auto-detect)")

    # Diff command
    diff_parser = subparsers.add_parser("diff", help="Show detailed config diff")
    diff_parser.add_argument("new_config", help="Path to new config YAML file")
    diff_parser.add_argument("--current-config", help="Path to current config (default: auto-detect)")

    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply config changes")
    apply_parser.add_argument("new_config", help="Path to new config YAML file")
    apply_parser.add_argument("--current-config", help="Path to current config (default: auto-detect)")
    apply_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate config syntax")
    validate_parser.add_argument("config", help="Path to config YAML file")

    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Discover local workers")
    discover_parser.add_argument("--json", action="store_true", help="Output as JSON")
    discover_parser.add_argument("--no-scan", action="store_true", help="Skip port scanning")
    discover_parser.add_argument("--no-grid", action="store_true", help="Skip Grid integration check")
    discover_parser.add_argument("--timeout", type=float, default=3.0, help="Timeout per worker in seconds")

    args = parser.parse_args()

    if args.command == "preview":
        cmd_preview(args.new_config, args.current_config)
    elif args.command == "diff":
        cmd_diff(args.new_config, args.current_config)
    elif args.command == "apply":
        cmd_apply(args.new_config, args.current_config, args.force)
    elif args.command == "validate":
        cmd_validate(args.config)
    elif args.command == "discover":
        cmd_discover(json_output=args.json, no_scan=args.no_scan, no_grid=args.no_grid, timeout=args.timeout)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
