#!/usr/bin/env python3
"""Real-world test of router integration with offerings and packages catalogs."""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from faigate.provider_catalog import (
    _get_pricing_for_provider_and_model,
    _get_packages_for_provider,
    get_offerings_catalog,
    get_packages_catalog,
)
from faigate.lane_registry import get_active_model_id


def test_catalog_loading():
    """Test that catalogs load correctly."""
    print("=== Testing catalog loading ===")

    # Load catalogs
    offerings = get_offerings_catalog()
    packages = get_packages_catalog()

    print(f"Offerings catalog: {len(offerings)} entries")
    print(f"Packages catalog: {len(packages)} entries")

    # Check some specific entries
    test_offerings = ["deepseek-chat-direct", "anthropic-haiku-direct", "gemini-flash-lite-direct"]

    for offering_id in test_offerings:
        if offering_id in offerings:
            print(f"✓ Found {offering_id}")
            pricing = offerings[offering_id].get("pricing", {})
            print(f"  - Input: ${pricing.get('input_cost_per_1m', 0)}/1M")
            print(f"  - Output: ${pricing.get('output_cost_per_1m', 0)}/1M")
        else:
            print(f"✗ Missing {offering_id}")

    # Check packages
    test_providers = ["kilocode", "openai-gpt4o", "gemini-flash-lite", "anthropic-haiku"]
    for provider in test_providers:
        provider_packages = _get_packages_for_provider(provider)
        if provider_packages:
            print(f"✓ {provider}: {len(provider_packages)} package(s)")
            for pkg in provider_packages:
                print(f"  - {pkg.get('name')}: {pkg.get('remaining', 0)}/{pkg.get('total', 0)} credits")
        else:
            print(f"✗ {provider}: No packages")


def test_pricing_lookup():
    """Test pricing lookup with canonical models."""
    print("\n=== Testing pricing lookup ===")

    # Test cases: (provider_name, canonical_model_id)
    test_cases = [
        ("deepseek-chat", "deepseek/chat"),
        ("anthropic-haiku", "anthropic/haiku-4.5"),
        ("gemini-flash-lite", "google/gemini-flash-lite"),
        ("openai-gpt4o", "openai/gpt-4o"),
    ]

    for provider_name, canonical_model in test_cases:
        pricing = _get_pricing_for_provider_and_model(provider_name, canonical_model)
        if pricing:
            print(f"✓ {provider_name} ({canonical_model}):")
            print(f"  - Input: ${pricing.get('input', 0)}/1M")
            print(f"  - Output: ${pricing.get('output', 0)}/1M")
            if "source_type" in pricing:
                print(f"  - Source: {pricing.get('source_type')}")
        else:
            print(f"✗ {provider_name} ({canonical_model}): No pricing found")


def test_active_model_mapping():
    """Test that active model IDs match offering model IDs."""
    print("\n=== Testing active model mapping ===")

    # Get active model IDs for canonical models
    canonical_models = [
        "deepseek/chat",
        "anthropic/haiku-4.5",
        "google/gemini-flash-lite",
        "openai/gpt-4o",
    ]

    for canonical in canonical_models:
        active_id = get_active_model_id(canonical)
        print(f"{canonical} → {active_id}")


def calculate_sample_costs():
    """Calculate sample request costs using offering pricing."""
    print("\n=== Calculating sample costs ===")

    # Sample request: 1000 prompt tokens, 500 output tokens
    prompt_tokens = 1000
    output_tokens = 500

    test_providers = [
        ("deepseek-chat", "deepseek/chat"),
        ("gemini-flash-lite", "google/gemini-flash-lite"),
        ("anthropic-haiku", "anthropic/haiku-4.5"),
        ("openai-gpt4o", "openai/gpt-4o"),
    ]

    for provider_name, canonical_model in test_providers:
        pricing = _get_pricing_for_provider_and_model(provider_name, canonical_model)
        if pricing and "input" in pricing and "output" in pricing:
            input_cost = (prompt_tokens * pricing["input"]) / 1_000_000
            output_cost = (output_tokens * pricing["output"]) / 1_000_000
            total_cost = input_cost + output_cost
            print(f"{provider_name}: ${total_cost:.6f} for {prompt_tokens}+{output_tokens} tokens")
            print(f"  (Input: ${pricing['input']}/1M, Output: ${pricing['output']}/1M)")
        else:
            print(f"{provider_name}: Pricing not available")


def check_package_scoring():
    """Check package scoring logic."""
    print("\n=== Checking package scoring ===")

    from datetime import date

    test_providers = ["kilocode", "openai-gpt4o", "anthropic-haiku"]

    for provider in test_providers:
        packages = _get_packages_for_provider(provider)
        if not packages:
            continue

        print(f"\n{provider} packages:")
        for pkg in packages:
            total = pkg.get("total_credits")
            used = pkg.get("used_credits", 0)
            expiry = pkg.get("expiry_date")

            if total is not None and total > 0:
                remaining = total - used
                remaining_ratio = remaining / total
                remaining_score = min(5, int(remaining_ratio * 5))

                expiry_score = 0
                if expiry:
                    try:
                        expiry_date = date.fromisoformat(expiry)
                        days_left = (expiry_date - date.today()).days
                        if days_left > 0:
                            if days_left <= 7:
                                expiry_score = 5
                            elif days_left <= 30:
                                expiry_score = 2
                    except ValueError:
                        pass

                total_score = remaining_score + expiry_score

                print(f"  - {pkg.get('name')}:")
                print(f"    Credits: {remaining}/{total} ({remaining_ratio:.1%})")
                print(f"    Remaining score: {remaining_score}")
                print(f"    Expiry: {expiry or 'none'} (score: {expiry_score})")
                print(f"    Total score: {total_score}")


def main():
    """Run all tests."""
    print("Real-world test of router integration with offerings and packages")
    print("=" * 60)

    # Check if metadata directory is set
    metadata_dir = os.environ.get("FAIGATE_PROVIDER_METADATA_DIR", "")
    if not metadata_dir:
        print("WARNING: FAIGATE_PROVIDER_METADATA_DIR not set")
        print("Using default location or built-in fallback")

    test_catalog_loading()
    test_pricing_lookup()
    test_active_model_mapping()
    calculate_sample_costs()
    check_package_scoring()

    print("\n" + "=" * 60)
    print("Test completed")


if __name__ == "__main__":
    main()
