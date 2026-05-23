"""CLI branding — text logo and display helpers.

SVG cannot be rendered faithfully in most terminals. Rich can show raster images
(PNG) in iTerm2, Kitty, WezTerm, etc., but that needs a bundled PNG and still
fails on plain SSH sessions. A fixed-width text logo works everywhere.
"""

from __future__ import annotations

from rich.console import Console

from .theme import THEME_PRIMARY, THEME_SECONDARY


def print_cli_logo(console: Console) -> None:
    """Print the bundled text logo (evokes site * rae lockup)."""
    console.print(f"  [{THEME_PRIMARY}]*[/{THEME_PRIMARY}]")
    console.print(f"  [{THEME_SECONDARY}]rae[/{THEME_SECONDARY}]")
