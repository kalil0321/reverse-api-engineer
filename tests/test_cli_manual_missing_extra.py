"""Manual mode must fail fast when the optional ``[manual]`` extra is absent.

Playwright moved out of the base install into the ``[manual]`` extra. On a
base-only install, entering manual mode must raise an actionable install hint
*before* recording anything — otherwise it leaves a phantom ``manual`` run in
history that later "operate on the latest run" flows could target.
"""

import io
import sys
from unittest.mock import MagicMock, patch

import click
import pytest
from rich.console import Console
from rich.markup import escape

from reverse_api.cli import run_manual_capture


class TestManualModeMissingExtra:
    def _run(self):
        # `sys.modules[name] = None` makes `from .browser import ...` raise
        # ImportError, simulating a base-only install without Playwright.
        with patch.dict(sys.modules, {"reverse_api.browser": None}), patch(
            "reverse_api.cli.session_manager"
        ) as mock_session:
            with pytest.raises(click.ClickException) as excinfo:
                run_manual_capture(
                    prompt="fetch things",
                    url="http://example.com",
                    reverse_engineer=False,
                    output_dir="/tmp/rae-test-does-not-matter",
                )
            return excinfo.value, mock_session

    def test_raises_actionable_hint(self):
        err, _ = self._run()
        message = err.format_message()
        assert "reverse-api-engineer[manual]" in message
        # The pip command alone is insufficient — Chromium must also be fetched.
        assert "playwright install chromium" in message

    def test_records_no_run(self):
        _, mock_session = self._run()
        mock_session.add_run.assert_not_called()

    def test_extra_name_survives_rich_rendering(self):
        """The CLI prints errors through Rich, which parses `[manual]` as a
        markup tag and would drop it — leaving `pip install
        'reverse-api-engineer'` (wrong). The render path must escape the message
        so the extra name reaches the user intact.
        """
        err, _ = self._run()
        buf = io.StringIO()
        # Mirror the REPL error handler: exception text into a markup string.
        Console(file=buf, force_terminal=False, no_color=True).print(
            f" [red]error:[/red] {escape(str(err))}"
        )
        assert "reverse-api-engineer[manual]" in buf.getvalue()
