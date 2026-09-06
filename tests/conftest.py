"""Pytest configuration for adaptive-lighting tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_template_deprecation_issue():
    """Mock the template deprecation issue creation.

    The template component's legacy platform syntax creates deprecation
    issues that require translations. Since adaptive-lighting tests use
    template lights as test fixtures (not testing the template integration
    itself), we mock the issue creation to avoid translation validation errors.
    """
    # Patch the create_legacy_template_issue function in the template helpers
    # to be a no-op when called for the deprecated_legacy_templates issue
    try:
        with patch(
            "homeassistant.components.template.helpers.create_legacy_template_issue",
        ):
            yield
    except (ImportError, ModuleNotFoundError, AttributeError):
        # Older HA versions don't have this function
        yield
