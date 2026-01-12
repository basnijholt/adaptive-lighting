#!/usr/bin/env python3
# ruff: noqa: T201, S603, S607
"""Update all markdown files that use markdown-code-runner for auto-generation.

Run from repo root: uv run python docs/run_markdown_code_runner.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def find_markdown_files_with_code_blocks(docs_dir: Path) -> list[Path]:
    """Find all markdown files containing markdown-code-runner markers."""
    files_with_code = []
    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text()
        if "<!-- CODE:START -->" in content:
            files_with_code.append(md_file)
    return sorted(files_with_code)


def run_markdown_code_runner(files: list[Path], repo_root: Path) -> bool:
    """Run markdown-code-runner on all files. Returns True if all succeeded."""
    if not files:
        print("No files with CODE:START markers found.")
        return True

    print(f"Found {len(files)} file(s) with auto-generated content:")
    for f in files:
        print(f"  - {f.relative_to(repo_root)}")
    print()

    all_success = True
    for file in files:
        rel_path = file.relative_to(repo_root)
        print(f"Updating {rel_path}...", end=" ", flush=True)
        result = subprocess.run(
            ["markdown-code-runner", str(file)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✓")
        else:
            print("✗")
            print(f"  Error: {result.stderr}")
            all_success = False

    return all_success


def main() -> int:
    """Main entry point."""
    repo_root = Path(__file__).parent.parent

    # Also check README.md at repo root
    files = find_markdown_files_with_code_blocks(repo_root / "docs")
    readme = repo_root / "README.md"
    if readme.exists() and "<!-- CODE:START -->" in readme.read_text():
        files.append(readme)

    success = run_markdown_code_runner(files, repo_root)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
