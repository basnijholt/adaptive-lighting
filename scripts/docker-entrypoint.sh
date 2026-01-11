#!/usr/bin/env bash
# Entrypoint script for Docker container
# Sets up symlinks at runtime (needed because volume mount overwrites build-time symlinks)

set -e

# Create symlinks with absolute paths so they work after volume mount
ln -sfn /app/custom_components/adaptive_lighting /core/homeassistant/components/adaptive_lighting
ln -sfn /app/tests /core/tests/components/adaptive_lighting

# Run pytest with all arguments
exec python3 -X dev -m pytest \
    -vvv \
    --timeout=9 \
    --durations=10 \
    --cov='homeassistant' \
    --cov-report=xml \
    --cov-report=html \
    --cov-report=term \
    --color=yes \
    -o console_output_style=count \
    "$@"
