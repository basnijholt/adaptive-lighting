"""Documentation generation utilities for Adaptive Lighting.

Provides functions to extract sections from README.md and transform
content for the documentation site. Used by markdown-code-runner
to generate documentation pages from README content.
"""

from __future__ import annotations

import re
from pathlib import Path

# Path to README relative to this module
_MODULE_DIR = Path(__file__).parent
README_PATH = _MODULE_DIR.parent.parent / "README.md"


def readme_section(section_name: str, *, strip_heading: bool = False) -> str:
    """Extract a marked section from README.md.

    Sections are marked with HTML comments:
    <!-- SECTION:section_name:START -->
    content
    <!-- SECTION:section_name:END -->

    Args:
        section_name: The name of the section to extract
        strip_heading: If True, remove the first heading from the section

    Returns:
        The content between the section markers

    Raises:
        ValueError: If the section is not found in README.md

    """
    content = README_PATH.read_text()

    start_marker = f"<!-- SECTION:{section_name}:START -->"
    end_marker = f"<!-- SECTION:{section_name}:END -->"

    start_idx = content.find(start_marker)
    if start_idx == -1:
        msg = f"Section '{section_name}' not found in README.md"
        raise ValueError(msg)

    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        msg = f"End marker for section '{section_name}' not found"
        raise ValueError(msg)

    section = content[start_idx + len(start_marker) : end_idx].strip()

    if strip_heading:
        # Remove first heading (# or ## or ###)
        section = re.sub(r"^#{1,3}\s+[^\n]+\n+", "", section, count=1)

    return transform_readme_links(section)


def transform_readme_links(content: str) -> str:
    """Transform README internal links to docs site links.

    Converts anchors like #configuration to proper doc page links.
    """
    # Map README anchors to doc pages
    link_map = {
        "#gear-configuration": "configuration.md",
        "#memo-options": "configuration.md#all-options",
        "#hammer_and_wrench-services": "services.md",
        "#adaptive_lightingapply": "services.md#adaptive_lightingapply",
        "#adaptive_lightingset_manual_control": "services.md#adaptive_lightingset_manual_control",
        "#adaptive_lightingchange_switch_settings": "services.md#adaptive_lightingchange_switch_settings",
        "#robot-automation-examples": "automation-examples.md",
        "#sos-troubleshooting": "troubleshooting.md",
        "#exclamation-common-problems--solutions": "troubleshooting.md#common-problems-solutions",
        "#bar_chart-graphs": "advanced/brightness-modes.md#graphs",
        "#bulb-features": "index.md#features",
        "#control_knobs-regain-manual-control": "advanced/manual-control.md",
        "#eyes-see-also": "see-also.md",
    }

    for old_link, new_link in link_map.items():
        content = content.replace(f"]({old_link})", f"]({new_link})")

    # Also handle the ToC link pattern [[ToC](#...)]
    content = re.sub(r"\[\[ToC\]\([^)]+\)\]", "", content)

    return content


def get_feature_list() -> str:
    """Get the features section formatted for docs."""
    return readme_section("features", strip_heading=True)


def get_manual_control_intro() -> str:
    """Get the manual control introduction section."""
    return readme_section("manual-control", strip_heading=True)


def get_automation_examples() -> str:
    """Get all automation examples from README."""
    return readme_section("automation-examples", strip_heading=True)


def get_troubleshooting_intro() -> str:
    """Get just the troubleshooting intro (debug logging)."""
    return readme_section("troubleshooting-intro", strip_heading=True)


def get_common_problems() -> str:
    """Get the common problems section."""
    return readme_section("common-problems", strip_heading=True)


def get_brightness_modes() -> str:
    """Get the brightness modes explanation with graphs."""
    return readme_section("brightness-modes", strip_heading=True)


def get_graphs() -> str:
    """Get the graphs section."""
    return readme_section("graphs", strip_heading=True)


def get_see_also() -> str:
    """Get the see also section."""
    return readme_section("see-also", strip_heading=True)


def get_config_example_full() -> str:
    """Get the full configuration example."""
    return readme_section("config-example-full", strip_heading=False)


def get_change_switch_settings_docs() -> str:
    """Get the change_switch_settings service documentation."""
    return readme_section("change-switch-settings", strip_heading=True)
