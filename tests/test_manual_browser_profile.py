"""Manual capture in real Chrome uses a fresh profile, not the user's own.

The user's Chrome profile directory is only checked to see that Chrome is installed.
Nothing is copied from it, so the capture starts signed out and the message must say so.
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("playwright")  # ships in the [manual] extra only

from reverse_api.browser import ManualBrowser  # noqa: E402


def test_real_chrome_launches_with_a_fresh_profile_and_says_so(tmp_path):
    user_profile = tmp_path / "Chrome"
    user_profile.mkdir()
    browser = ManualBrowser(run_id="testrun", prompt="grab jobs", output_dir=str(tmp_path / "runs"))
    browser._playwright = MagicMock()
    browser._playwright.chromium.launch_persistent_context.return_value.pages = []

    with (
        patch("reverse_api.browser.get_chrome_profile_dir", return_value=user_profile),
        patch("reverse_api.browser.console") as console,
        patch.object(browser, "close", return_value=browser.har_path),
    ):
        browser._start_with_real_chrome()

    kwargs = browser._playwright.chromium.launch_persistent_context.call_args.kwargs
    assert kwargs["channel"] == "chrome"
    assert kwargs["user_data_dir"] != str(user_profile)
    assert not any(user_profile.iterdir())
    printed = " ".join(str(call.args[0]) for call in console.print.call_args_list if call.args)
    assert "fresh profile" in printed
    assert "profile copy" not in printed
