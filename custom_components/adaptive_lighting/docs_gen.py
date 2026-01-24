"""Documentation generation utilities for Adaptive Lighting.

Provides functions to transform content for the documentation site.
Used by markdown-code-runner to generate documentation pages from README content.
"""

from __future__ import annotations

import re


def _transform_readme_links(content: str) -> str:
    """Transform README internal links to docs site links."""
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

    # Remove ToC link pattern [[ToC](#...)]
    return re.sub(r"\[\[ToC\]\([^)]+\)\]", "", content)
