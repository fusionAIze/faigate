#!/usr/bin/env python3
"""Test dashboard metadata catalogs summary."""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from faigate.dashboard import _metadata_catalogs_summary


def main():
    """Test metadata catalogs summary."""
    print("Testing dashboard metadata catalogs summary")
    print("=" * 60)

    # Check if metadata directory is set
    metadata_dir = os.environ.get("FAIGATE_PROVIDER_METADATA_DIR", "")
    if not metadata_dir:
        print("WARNING: FAIGATE_PROVIDER_METADATA_DIR not set")
        print("Using default location or built-in fallback")
    else:
        print(f"Using metadata directory: {metadata_dir}")

    # Get summary
    summary = _metadata_catalogs_summary()

    print(f"\nOfferings summary:")
    print(f"  Total: {summary['offerings']['total']}")
    print(f"  Fresh: {summary['offerings']['freshness']['fresh']}")
    print(f"  Aging: {summary['offerings']['freshness']['aging']}")
    print(f"  Stale: {summary['offerings']['freshness']['stale']}")
    print(f"  Unknown: {summary['offerings']['freshness']['unknown']}")

    print(f"\nPackages summary:")
    print(f"  Total: {summary['packages']['total']}")
    print(f"  Expiring soon (≤7 days): {summary['packages']['expiring_soon']}")
    print(f"  Types: {summary['packages']['types']}")

    # Check that counts match what we expect
    expected_offerings = 6  # Based on our catalog
    expected_packages = 4  # Based on our catalog

    if summary["offerings"]["total"] == expected_offerings:
        print(f"\n✓ Offerings count matches expected: {expected_offerings}")
    else:
        print(f"\n✗ Offerings count mismatch: expected {expected_offerings}, got {summary['offerings']['total']}")

    if summary["packages"]["total"] == expected_packages:
        print(f"✓ Packages count matches expected: {expected_packages}")
    else:
        print(f"✗ Packages count mismatch: expected {expected_packages}, got {summary['packages']['total']}")

    # Check for expiring packages
    if summary["packages"]["expiring_soon"] > 0:
        print(f"\n⚠️  {summary['packages']['expiring_soon']} package(s) expiring soon")
    else:
        print(f"\n✓ No packages expiring soon")

    print("\n" + "=" * 60)
    print("Test completed")


if __name__ == "__main__":
    main()
