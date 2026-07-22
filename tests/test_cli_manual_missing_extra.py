"""Manual mode must fail fast when the optional ``[manual]`` extra is absent.

Playwright moved out of the base install into the ``[manual]`` extra. On a
base-only install, entering manual mode must raise an actionable install hint
*before* recording anything — otherwise it leaves a phantom ``manual`` run in
history that later "operate on the latest run" flows could target.
"""

import sys
from unittest.mock import MagicMock, patch

import click
import pytest

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
