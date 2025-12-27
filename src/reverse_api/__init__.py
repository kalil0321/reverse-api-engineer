"""Reverse API - Browser traffic capture for API reverse engineering."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("reverse-api-engineer")
except PackageNotFoundError:
    # Package is not installed, use a fallback version
    __version__ = "0.0.0.dev"
