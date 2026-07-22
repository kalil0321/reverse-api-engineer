"""Tests for the interactive settings navigation."""

from unittest.mock import patch

from reverse_api import cli


def test_settings_stays_open_until_back():
    """Changing settings should return to settings, not the REPL."""
    with patch.object(cli, "_handle_settings_action", side_effect=[True, True, False]) as action:
        cli.handle_settings("magenta")

    assert action.call_count == 3
