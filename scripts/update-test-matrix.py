#!/usr/bin/env python3
"""Update the pytest workflow matrix with latest HA Core versions.

This script fetches the latest Home Assistant Core release versions from GitHub
and updates the pytest workflow matrix to test against them.

Usage:
    python scripts/update-test-matrix.py
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

# Minimum HA Core version to include in the test matrix
# This should be the oldest version we want to support
MIN_VERSION = (2024, 12)


def get_ha_core_versions() -> list[str]:
    """Fetch latest stable HA Core versions from GitHub API."""
    all_tags = []
    page = 1

    # Paginate through all tags to ensure we get older versions too
    while True:
        url = f"https://api.github.com/repos/home-assistant/core/tags?per_page=100&page={page}"
        with urllib.request.urlopen(url) as response:  # noqa: S310
            tags = json.loads(response.read().decode())

        if not tags:
            break

        all_tags.extend(tags)

        # Check if we've gone far enough back
        # Stop if we've found versions older than our minimum
        oldest_in_page = None
        for t in tags:
            if re.match(r"^\d+\.\d+\.\d+$", t["name"]):
                parts = t["name"].split(".")
                year, month = int(parts[0]), int(parts[1])
                if oldest_in_page is None or (year, month) < oldest_in_page:
                    oldest_in_page = (year, month)

        if oldest_in_page and oldest_in_page < MIN_VERSION:
            break

        page += 1
        if page > 10:  # Safety limit
            break

    # Filter to stable releases only (no beta/rc)
    stable_pattern = re.compile(r"^\d+\.\d+\.\d+$")
    versions = [t["name"] for t in all_tags if stable_pattern.match(t["name"])]

    # Group by minor version and get latest patch for each
    latest: dict[str, str] = {}
    for version in versions:
        parts = version.split(".")
        year, month = int(parts[0]), int(parts[1])
        # Only include versions >= MIN_VERSION
        if (year, month) >= MIN_VERSION:
            minor_key = f"{parts[0]}.{parts[1]}"
            # Keep the one with highest patch number
            if minor_key not in latest:
                latest[minor_key] = version
            else:
                current_patch = int(latest[minor_key].split(".")[2])
                new_patch = int(parts[2])
                if new_patch > current_patch:
                    latest[minor_key] = version

    # Sort by version
    return sorted(latest.values(), key=lambda v: [int(x) for x in v.split(".")])


def get_python_version(ha_version: str) -> str:
    """Determine Python version based on HA Core version."""
    parts = ha_version.split(".")
    year, month = int(parts[0]), int(parts[1])
    # 2024.x and 2025.1 use Python 3.12, 2025.2+ use Python 3.13
    if year == 2024 or (year == 2025 and month == 1):
        return "3.12"
    return "3.13"


def generate_matrix_yaml(versions: list[str]) -> str:
    """Generate the YAML matrix include block."""
    lines = []
    for version in versions:
        python_ver = get_python_version(version)
        lines.append(f'          - core-version: "{version}"')
        lines.append(f'            python-version: "{python_ver}"')
    # Add dev version
    lines.append('          - core-version: "dev"')
    lines.append('            python-version: "3.13"')
    return "\n".join(lines)


def update_workflow_file(workflow_path: Path, new_matrix: str) -> bool:
    """Update the workflow file with new matrix. Returns True if changed."""
    content = workflow_path.read_text()

    # Pattern to match the matrix include block
    # Matches from "include:" to just before "    steps:"
    pattern = re.compile(
        r"(        include:\n)(.*?)(    steps:)",
        re.DOTALL,
    )

    def replacer(match: re.Match) -> str:
        return f"{match.group(1)}{new_matrix}\n{match.group(3)}"

    new_content = pattern.sub(replacer, content)

    if new_content == content:
        return False

    workflow_path.write_text(new_content)
    return True


def main() -> None:
    """Main entry point."""
    print("Fetching latest HA Core versions...")  # noqa: T201
    versions = get_ha_core_versions()
    print(f"Found {len(versions)} versions: {', '.join(versions)}")  # noqa: T201

    print("\nGenerating matrix...")  # noqa: T201
    matrix = generate_matrix_yaml(versions)
    print(matrix)  # noqa: T201

    workflow_path = Path(__file__).parent.parent / ".github/workflows/pytest.yaml"
    print(f"\nUpdating {workflow_path}...")  # noqa: T201

    if update_workflow_file(workflow_path, matrix):
        print("Workflow updated successfully!")  # noqa: T201
    else:
        print("No changes needed.")  # noqa: T201


if __name__ == "__main__":
    main()
