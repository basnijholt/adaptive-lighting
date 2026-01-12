# Adaptive Lighting Documentation Site Plan

## Overview

Create a documentation site at **adaptive-lighting.nijho.lt** using the Zensical framework, heavily reusing content from the existing README.md through intelligent section extraction.

## Architecture

### Core Components

```
adaptive-lighting/
├── docs/                          # Documentation source
│   ├── index.md                   # Home page (intro + quick start)
│   ├── getting-started.md         # Installation guide
│   ├── configuration.md           # All config options (from README)
│   ├── services.md                # Service calls reference
│   ├── automation-examples.md     # Automation recipes
│   ├── troubleshooting.md         # Common issues & solutions
│   ├── advanced/
│   │   ├── brightness-modes.md    # Linear/tanh brightness ramps
│   │   ├── manual-control.md      # Take over control explained
│   │   └── sleep-mode.md          # Sleep mode deep dive
│   ├── assets/
│   │   ├── images/                # Graphs, screenshots
│   │   └── stylesheets/           # Custom CSS
│   └── overrides/                 # Zensical theme customizations
├── zensical.toml                  # Documentation config
├── custom_components/adaptive_lighting/
│   ├── _docs_helpers.py           # Existing table generators
│   └── docs_gen.py                # NEW: Section extraction + transforms
└── .github/workflows/
    └── docs.yml                   # Documentation deployment
```

### Content Reuse Strategy

**Three-tier approach** (going further than agent-cli):

1. **Section Extraction**: Mark sections in README with `<!-- SECTION:name:START/END -->` and extract directly
2. **Auto-generated Tables**: Existing `_docs_helpers.py` generates config/service tables from code
3. **Transform Functions**: New `docs_gen.py` functions that transform README content for docs context

## Implementation Steps

### Phase 1: Infrastructure Setup

#### 1.1 Create `zensical.toml`

```toml
[project]
name = "Adaptive Lighting"
site_url = "https://adaptive-lighting.nijho.lt"
repo_url = "https://github.com/basnijholt/adaptive-lighting"
repo_name = "basnijholt/adaptive-lighting"

[theme]
name = "material"
logo = "assets/logo.png"
favicon = "assets/favicon.png"
palette = [
    { scheme = "default", primary = "amber", accent = "orange", toggle = { icon = "lucide/sun", name = "Light mode" } },
    { scheme = "slate", primary = "amber", accent = "orange", toggle = { icon = "lucide/moon", name = "Dark mode" } },
]
features = [
    "content.code.copy",
    "content.code.annotate",
    "content.tabs.link",
    "navigation.instant",
    "navigation.tracking",
    "navigation.tabs",
    "navigation.sections",
    "navigation.top",
    "search.highlight",
    "search.suggest",
]

[[nav]]
"Home" = "index.md"
[[nav]]
"Getting Started" = "getting-started.md"
[[nav]]
"Configuration" = "configuration.md"
[[nav]]
"Services" = "services.md"
[[nav]]
"Automation Examples" = "automation-examples.md"
[[nav]]
"Troubleshooting" = "troubleshooting.md"
[[nav]]
"Advanced" = [
    { "Brightness Modes" = "advanced/brightness-modes.md" },
    { "Manual Control" = "advanced/manual-control.md" },
    { "Sleep Mode" = "advanced/sleep-mode.md" },
]

[markdown_extensions]
pymdownx_highlight = { anchor_linenums = true, line_spans = "__span", pygments_lang_class = true }
pymdownx_superfences = {}
pymdownx_tabbed = { alternate_style = true }
pymdownx_details = {}
admonition = {}
toc = { permalink = true }

[extra]
social = [
    { icon = "lucide/github", link = "https://github.com/basnijholt/adaptive-lighting" },
]
```

#### 1.2 Create `docs_gen.py` (Section Extraction Module)

```python
"""Documentation generation utilities for Adaptive Lighting.

Provides functions to extract sections from README.md and transform
content for the documentation site.
"""
from __future__ import annotations

import re
from pathlib import Path

# Path to README relative to this module
README_PATH = Path(__file__).parent.parent.parent / "README.md"


def readme_section(section_name: str, *, strip_heading: bool = False) -> str:
    """Extract a marked section from README.md.

    Sections are marked with:
    <!-- SECTION:section_name:START -->
    content
    <!-- SECTION:section_name:END -->

    Args:
        section_name: The name of the section to extract
        strip_heading: If True, remove the first heading from the section

    Returns:
        The content between the section markers
    """
    content = README_PATH.read_text()

    start_marker = f"<!-- SECTION:{section_name}:START -->"
    end_marker = f"<!-- SECTION:{section_name}:END -->"

    start_idx = content.find(start_marker)
    if start_idx == -1:
        raise ValueError(f"Section '{section_name}' not found in README.md")

    end_idx = content.find(end_marker)
    if end_idx == -1:
        raise ValueError(f"End marker for section '{section_name}' not found")

    section = content[start_idx + len(start_marker):end_idx].strip()

    if strip_heading:
        # Remove first heading (# or ##)
        section = re.sub(r'^#{1,3}\s+[^\n]+\n+', '', section, count=1)

    return section


def readme_section_between_headings(
    start_heading: str,
    end_heading: str | None = None,
    *,
    include_start: bool = True,
) -> str:
    """Extract content between two headings in README.md.

    Args:
        start_heading: The heading text to start from (e.g., "Features")
        end_heading: The heading text to end at (None = until next same-level heading)
        include_start: Whether to include the start heading in output

    Returns:
        The content between the headings
    """
    content = README_PATH.read_text()

    # Find the start heading
    start_pattern = rf'^(#{1,6})\s+:?\w*:?\s*{re.escape(start_heading)}'
    start_match = re.search(start_pattern, content, re.MULTILINE)

    if not start_match:
        raise ValueError(f"Heading '{start_heading}' not found in README.md")

    heading_level = len(start_match.group(1))
    start_pos = start_match.start() if include_start else start_match.end()

    # Find the end
    if end_heading:
        end_pattern = rf'^#{{{heading_level}}}\s+:?\w*:?\s*{re.escape(end_heading)}'
        end_match = re.search(end_pattern, content[start_match.end():], re.MULTILINE)
        if end_match:
            end_pos = start_match.end() + end_match.start()
        else:
            end_pos = len(content)
    else:
        # Find next heading at same or higher level
        next_heading = rf'^#{{1,{heading_level}}}\s+'
        end_match = re.search(next_heading, content[start_match.end():], re.MULTILINE)
        end_pos = start_match.end() + end_match.start() if end_match else len(content)

    return content[start_pos:end_pos].strip()


def transform_readme_links(content: str) -> str:
    """Transform README internal links to docs site links.

    Converts anchors like #configuration to proper doc page links.
    """
    # Map README anchors to doc pages
    link_map = {
        "#gear-configuration": "configuration.md",
        "#memo-options": "configuration.md#options",
        "#hammer_and_wrench-services": "services.md",
        "#robot-automation-examples": "automation-examples.md",
        "#sos-troubleshooting": "troubleshooting.md",
        "#bar_chart-graphs": "advanced/brightness-modes.md#graphs",
    }

    for old_link, new_link in link_map.items():
        content = content.replace(f"]({old_link})", f"]({new_link})")

    return content


def get_feature_list() -> str:
    """Get the features section formatted for docs."""
    return readme_section("features")


def get_automation_examples() -> str:
    """Get all automation examples from README."""
    return readme_section("automation-examples")


def get_troubleshooting() -> str:
    """Get the troubleshooting section."""
    return readme_section("troubleshooting")


def get_brightness_modes_explanation() -> str:
    """Get the brightness modes explanation with graphs."""
    return readme_section("brightness-modes")
```

#### 1.3 Add Section Markers to README.md

Add markers around key sections:

```markdown
<!-- SECTION:features:START -->
## :bulb: Features
...
<!-- SECTION:features:END -->

<!-- SECTION:automation-examples:START -->
## :robot: Automation examples
...
<!-- SECTION:automation-examples:END -->

<!-- SECTION:troubleshooting:START -->
## :sos: Troubleshooting
...
<!-- SECTION:troubleshooting:END -->

<!-- SECTION:brightness-modes:START -->
### Custom brightness ramps...
...
<!-- SECTION:brightness-modes:END -->
```

### Phase 2: Documentation Pages

#### 2.1 `docs/index.md` - Home Page

```markdown
---
icon: lucide/sun
---

# Adaptive Lighting

Enhance Your Home's Atmosphere with Smart, Sun-Synchronized Lighting

![Adaptive Lighting Logo](https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/adaptive_lighting/icon@2x.png){ width="200" }

[Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting) intelligently adjusts the brightness and color of your lights based on the sun's position.

[:material-download: Install via HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=basnijholt&repository=adaptive-lighting&category=integration){ .md-button .md-button--primary }
[:material-web: Try the Simulator](https://basnijholt.github.io/adaptive-lighting){ .md-button }

## Features

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting.docs_gen import get_feature_list -->
<!-- print(get_feature_list()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## Quick Start

1. Install via [HACS](https://hacs.xyz/)
2. Add `adaptive_lighting:` to your `configuration.yaml`
3. Go to **Settings** → **Devices & Services** → **Add Integration** → **Adaptive Lighting**
4. Select your lights and enjoy!

[Get Started →](getting-started.md){ .md-button }
```

#### 2.2 `docs/configuration.md` - Configuration Reference

```markdown
---
icon: lucide/settings
---

# Configuration

Adaptive Lighting supports configuration through both YAML and the UI.

## Basic Example

\`\`\`yaml
adaptive_lighting:
  lights:
    - light.living_room_lights
\`\`\`

!!! note
    If you plan to strictly use the UI, the `adaptive_lighting:` entry must still be added to YAML.

## All Options

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_config_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## Full Example

\`\`\`yaml
adaptive_lighting:
- name: "default"
  lights: []
  prefer_rgb_color: false
  transition: 45
  # ... (full example from README)
\`\`\`
```

#### 2.3 `docs/services.md` - Services Reference

```markdown
---
icon: lucide/zap
---

# Services

Adaptive Lighting provides three services for programmatic control.

## adaptive_lighting.apply

Applies current Adaptive Lighting settings to lights on demand.

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_apply_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## adaptive_lighting.set_manual_control

Mark or unmark a light as "manually controlled".

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting import _docs_helpers -->
<!-- print(_docs_helpers.generate_set_manual_control_markdown_table()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## adaptive_lighting.change_switch_settings

Change configuration options dynamically via service call.

!!! warning
    These settings are not persisted and will reset on Home Assistant restart!
```

#### 2.4 `docs/automation-examples.md`

```markdown
---
icon: lucide/bot
---

# Automation Examples

Real-world automation examples for Adaptive Lighting.

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting.docs_gen import get_automation_examples -->
<!-- print(get_automation_examples()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->
```

#### 2.5 `docs/troubleshooting.md`

```markdown
---
icon: lucide/life-buoy
---

# Troubleshooting

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting.docs_gen import get_troubleshooting -->
<!-- print(get_troubleshooting()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->
```

### Phase 3: GitHub Actions Workflow

#### 3.1 `.github/workflows/docs.yml`

```yaml
name: Documentation

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'
      - 'README.md'
      - 'zensical.toml'
      - 'custom_components/adaptive_lighting/_docs_helpers.py'
      - 'custom_components/adaptive_lighting/docs_gen.py'
      - '.github/workflows/docs.yml'
  pull_request:
    paths:
      - 'docs/**'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install zensical markdown-code-runner
          pip install -e .  # Install adaptive-lighting for docs_gen imports

      - name: Run markdown-code-runner
        run: |
          for f in docs/*.md docs/**/*.md; do
            [ -f "$f" ] && markdown-code-runner "$f"
          done

      - name: Build documentation
        run: zensical build

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./site

  deploy:
    if: github.ref == 'refs/heads/main'
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

#### 3.2 `docs/CNAME`

```
adaptive-lighting.nijho.lt
```

### Phase 4: Assets & Theming

#### 4.1 Download Logo

```bash
curl -o docs/assets/logo.png \
  "https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/adaptive_lighting/icon@2x.png"
```

#### 4.2 Custom Styles `docs/assets/stylesheets/extra.css`

```css
/* Sun-themed accents */
:root {
  --md-primary-fg-color: #FF9800;
  --md-accent-fg-color: #FFC107;
}

/* Hero section styling */
.md-content__inner > h1:first-child {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
}

/* Feature cards */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}

.feature-card {
  padding: 1rem;
  border-radius: 8px;
  background: var(--md-code-bg-color);
}
```

### Phase 5: Advanced Documentation

#### 5.1 `docs/advanced/brightness-modes.md`

```markdown
---
icon: lucide/trending-up
---

# Brightness Modes

Enhance your control over brightness transitions during sunrise and sunset.

<!-- CODE:START -->
<!-- from homeassistant.components.adaptive_lighting.docs_gen import get_brightness_modes_explanation -->
<!-- print(get_brightness_modes_explanation()) -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- OUTPUT:END -->

## Interactive Simulator

Try the [Adaptive Lighting Simulator](https://basnijholt.github.io/adaptive-lighting) to visualize how different settings affect your lighting!
```

#### 5.2 `docs/advanced/manual-control.md`

Deep dive into the take_over_control and detect_non_ha_changes features.

#### 5.3 `docs/advanced/sleep-mode.md`

Comprehensive sleep mode documentation.

## Content Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         README.md                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ SECTION:features │  │ SECTION:trouble  │  │ CODE blocks    │ │
│  │ START...END      │  │ shooting         │  │ (markdown-     │ │
│  └────────┬─────────┘  └────────┬─────────┘  │ code-runner)   │ │
│           │                     │            └───────┬────────┘ │
└───────────┼─────────────────────┼────────────────────┼──────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                        docs_gen.py                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ readme_section │  │ transform_     │  │ _docs_helpers.py   │   │
│  │ ("features")   │  │ readme_links() │  │ (table generators) │   │
│  └───────┬────────┘  └───────┬────────┘  └─────────┬──────────┘   │
└──────────┼───────────────────┼─────────────────────┼──────────────┘
           │                   │                     │
           ▼                   ▼                     ▼
┌───────────────────────────────────────────────────────────────────┐
│                         docs/*.md                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐    │
│  │ index.md    │  │ services.md  │  │ configuration.md       │    │
│  │ (features)  │  │ (tables)     │  │ (options table)        │    │
│  └─────────────┘  └──────────────┘  └────────────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
           │
           ▼
┌───────────────────────────────────────────────────────────────────┐
│                    GitHub Actions                                  │
│  markdown-code-runner → zensical build → GitHub Pages deploy      │
└───────────────────────────────────────────────────────────────────┘
           │
           ▼
    https://adaptive-lighting.nijho.lt
```

## Key Innovations Beyond Agent-CLI

1. **Section Markers + Transform Functions**: More flexible than just `readme_section()` - can transform content for different contexts

2. **Heading-based Extraction**: `readme_section_between_headings()` allows extracting content without adding markers everywhere

3. **Link Transformation**: `transform_readme_links()` converts README anchors to proper doc site links

4. **Existing Infrastructure Reuse**: Leverages the existing `_docs_helpers.py` module for auto-generated tables

5. **Minimal README Changes**: Section markers are invisible in GitHub rendering

## Migration Checklist

- [ ] Create `docs/` directory structure
- [ ] Create `zensical.toml` configuration
- [ ] Create `docs_gen.py` module with section extraction
- [ ] Add section markers to README.md
- [ ] Create documentation pages with CODE blocks
- [ ] Download/create logo assets
- [ ] Create custom stylesheet
- [ ] Set up GitHub Actions workflow
- [ ] Create CNAME file
- [ ] Configure GitHub Pages in repository settings
- [ ] Test build locally with `zensical serve`
- [ ] Deploy and verify at adaptive-lighting.nijho.lt

## Estimated Effort

| Phase | Description | Files |
|-------|-------------|-------|
| 1 | Infrastructure Setup | 3 |
| 2 | Documentation Pages | 8 |
| 3 | GitHub Actions | 2 |
| 4 | Assets & Theming | 3 |
| 5 | Advanced Docs | 3 |

**Total: ~19 files to create/modify**

## Benefits

1. **Single Source of Truth**: README remains the canonical documentation
2. **Zero Drift**: Auto-generated content from code + README extraction
3. **Better UX**: Full-featured docs site with search, navigation, dark mode
4. **SEO**: Proper URLs, metadata, and structure for discoverability
5. **Maintainability**: Changes to README automatically reflected in docs
