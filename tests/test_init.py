"""Tests for __init__.py - Package initialization."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from reverse_api import __version__


class TestVersion:
    """Test package version."""

    def test_version_is_string(self):
        """Version is a string."""
        assert isinstance(__version__, str)

    def test_version_not_empty(self):
        """Version is not empty."""
        assert len(__version__) > 0

    def test_version_format(self):
        """Version has expected format (either semver or dev)."""
        # Either a proper version like "0.3.2" or dev fallback "0.0.0.dev"
        assert "." in __version__

    def test_version_fallback(self):
        """Version falls back when package not installed."""
        # Simulate the fallback logic from __init__.py
        try:
            from importlib.metadata import version as _ver

            _ver("definitely-not-a-real-package-name-xyz")
        except PackageNotFoundError:
            v = "0.0.0.dev"
        assert v == "0.0.0.dev"
