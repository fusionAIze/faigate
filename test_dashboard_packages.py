#!/usr/bin/env python3
"""Test dashboard package details integration."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from faigate.dashboard import build_dashboard_report, render_dashboard_text

# Set metadata directory
os.environ["FAIGATE_PROVIDER_METADATA_DIR"] = "/Users/andrelange/Documents/repositories/github/fusionaize-metadata"

# Build report with empty database (no metrics)
report = build_dashboard_report(db_path="/tmp/does_not_exist.db")

print("=== Dashboard report keys ===")
print(list(report.keys()))

print("\n=== Metadata catalogs card ===")
metadata = report["cards"]["metadata_catalogs"]
print(f"Offerings total: {metadata['offerings_total']}")
print(f"Packages total: {metadata['packages_total']}")
print(f"Packages expiring soon: {metadata['packages_expiring_soon']}")
print(f"Packages detail count: {len(metadata.get('packages_detail', []))}")

if metadata.get("packages_detail"):
    print("\n=== Package details ===")
    for pkg in metadata["packages_detail"]:
        print(f"- {pkg['provider_id']}: {pkg['name']}")
        print(f"  Credits: {pkg['remaining_credits']}/{pkg['total_credits']} ({pkg['remaining_pct']:.0f}%)")
        if pkg["expiry_date"]:
            print(f"  Expiry: {pkg['expiry_date']} (days left: {pkg['days_left']})")

print("\n=== Overview rendering ===")
overview = render_dashboard_text(report, view="overview")
print(overview[:2000])  # First part

# Check that package details appear in overview
if "Package details" in overview:
    print("\n✓ Package details section found in overview")
else:
    print("\n✗ Package details section NOT found in overview")
    # Print the overview lines around metadata catalogs
    lines = overview.split("\n")
    for i, line in enumerate(lines):
        if "Metadata catalogs" in line:
            print(f"Line {i}: {line}")
            for j in range(i + 1, min(i + 10, len(lines))):
                print(f"Line {j}: {lines[j]}")
