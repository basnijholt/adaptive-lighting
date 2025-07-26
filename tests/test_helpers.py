"""Tests for helper functions."""

import pytest

from custom_components.adaptive_lighting.helpers import ensure_bool


class TestEnsureBool:
    """Test the ensure_bool function."""

    def test_boolean_values(self):
        """Test that boolean values are returned as-is."""
        assert ensure_bool(True, "test") is True
        assert ensure_bool(False, "test") is False

    def test_string_true_values(self):
        """Test that string representations of true are converted correctly."""
        assert ensure_bool("true", "test") is True
        assert ensure_bool("True", "test") is True
        assert ensure_bool("TRUE", "test") is True
        assert ensure_bool("on", "test") is True
        assert ensure_bool("On", "test") is True
        assert ensure_bool("ON", "test") is True
        assert ensure_bool("yes", "test") is True
        assert ensure_bool("Yes", "test") is True
        assert ensure_bool("YES", "test") is True
        assert ensure_bool("1", "test") is True

    def test_string_false_values(self):
        """Test that string representations of false are converted correctly."""
        assert ensure_bool("false", "test") is False
        assert ensure_bool("False", "test") is False
        assert ensure_bool("FALSE", "test") is False
        assert ensure_bool("off", "test") is False
        assert ensure_bool("Off", "test") is False
        assert ensure_bool("OFF", "test") is False
        assert ensure_bool("no", "test") is False
        assert ensure_bool("No", "test") is False
        assert ensure_bool("NO", "test") is False
        assert ensure_bool("0", "test") is False

    def test_invalid_values(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError, match="Parameter 'test' muss ein Boolean sein"):
            ensure_bool("invalid", "test")

        with pytest.raises(ValueError, match="Parameter 'test' muss ein Boolean sein"):
            ensure_bool(123, "test")

        with pytest.raises(ValueError, match="Parameter 'test' muss ein Boolean sein"):
            ensure_bool(None, "test")

        with pytest.raises(ValueError, match="Parameter 'test' muss ein Boolean sein"):
            ensure_bool([], "test")

        with pytest.raises(ValueError, match="Parameter 'test' muss ein Boolean sein"):
            ensure_bool({}, "test")

    def test_error_message_includes_value(self):
        """Test that error messages include the actual value."""
        with pytest.raises(ValueError, match="ist aber: 'invalid'"):
            ensure_bool("invalid", "test")

        with pytest.raises(ValueError, match="ist aber: 123"):
            ensure_bool(123, "test")
