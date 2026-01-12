#!/usr/bin/env python3
"""Run markdown-code-runner on all documentation files.

This script processes all Markdown files in the docs/ directory that contain
CODE blocks, executing them and updating the OUTPUT sections.

Usage:
    python docs/run_markdown_code_runner.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Add the custom_components to the path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))
sys.path.insert(0, str(REPO_ROOT))


def find_markdown_files() -> list[Path]:
    """Find all Markdown files in the docs directory."""
    docs_dir = REPO_ROOT / "docs"
    return list(docs_dir.rglob("*.md"))


def has_code_blocks(file_path: Path) -> bool:
    """Check if a Markdown file has CODE blocks."""
    content = file_path.read_text()
    return (
        "<!-- CODE:START -->" in content or "```python markdown-code-runner" in content
    )


def run_markdown_code_runner(file_path: Path) -> bool:
    """Run markdown-code-runner on a single file."""
    try:
        result = subprocess.run(
            ["markdown-code-runner", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
            env={
                **subprocess.os.environ,
                "PYTHONPATH": f"{REPO_ROOT / 'custom_components'}:{REPO_ROOT}",
            },
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error: {e.stderr}")
        return False
    except FileNotFoundError:
        print(
            "  Error: markdown-code-runner not found. Install with: pip install markdown-code-runner"
        )
        return False


def main() -> int:
    """Process all Markdown files with CODE blocks."""
    print("Finding Markdown files with CODE blocks...")

    markdown_files = find_markdown_files()
    files_with_code = [f for f in markdown_files if has_code_blocks(f)]

    if not files_with_code:
        print("No files with CODE blocks found.")
        return 0

    print(f"Found {len(files_with_code)} files with CODE blocks:")

    success_count = 0
    failure_count = 0

    for file_path in sorted(files_with_code):
        relative_path = file_path.relative_to(REPO_ROOT)
        print(f"\nProcessing {relative_path}...")

        if run_markdown_code_runner(file_path):
            print("  ✓ Success")
            success_count += 1
        else:
            print("  ✗ Failed")
            failure_count += 1

    print(f"\n{'='*50}")
    print(f"Results: {success_count} succeeded, {failure_count} failed")

    return 1 if failure_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
