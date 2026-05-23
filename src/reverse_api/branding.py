"""CLI branding — text logo and display helpers.

SVG cannot be rendered faithfully in most terminals. Rich can show raster images
(PNG) in iTerm2, Kitty, WezTerm, etc., but that needs a bundled PNG and still
fails on plain SSH sessions. A fixed-width text logo works everywhere.
"""

from __future__ import annotations

from rich.console import Console

from .theme import THEME_DIM, THEME_PRIMARY, THEME_SECONDARY


def print_cli_logo(console: Console, *, inner_width: int = 38) -> None:
    """Print the bundled text logo inside a banner frame (evokes site * rae lockup)."""
    rows: tuple[tuple[str, int], ...] = (
        (f"              [{THEME_PRIMARY}]*[/{THEME_PRIMARY}]", 15),
        (f"            [{THEME_SECONDARY}]rae[/{THEME_SECONDARY}]", 15),
    )
    for content, visible_len in rows:
        pad = " " * (inner_width - visible_len)
        console.print(f"  [{THEME_DIM}]│[/{THEME_DIM}] {content}{pad} [{THEME_DIM}]│[/{THEME_DIM}]")
