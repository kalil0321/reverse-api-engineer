"""Tests for the interactive settings navigation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest

from reverse_api import cli


@pytest.mark.parametrize("sdk,key,default", [
    ("claude", "claude_code_model", "claude-sonnet-4-6"),
    ("opencode", "opencode_model", cli.DEFAULT_OPENCODE_MODEL),
    ("copilot", "copilot_model", "gpt-5"),
    ("cursor", "cursor_model", "composer-2.5"),
])
@pytest.mark.parametrize("saved", [None, "", "custom-model"])
@pytest.mark.parametrize("infer_sdk", [False, True])
def test_default_model_handles_empty_settings(sdk, key, default, saved, infer_sdk):
    with patch.object(cli.config_manager, "get", side_effect=lambda name, fallback=None: {"sdk": sdk, key: saved}.get(name, fallback)):
        assert cli.default_model_for_configured_sdk(None if infer_sdk else sdk) == (saved or default)


def test_settings_stays_open_until_back():
    """Changing settings should return to settings, not the REPL."""
    with patch.object(cli, "_handle_settings_action", side_effect=[True, True, False]) as action:
        cli.handle_settings("magenta")

    assert action.call_count == 3


def test_selecting_codex_sets_compatible_browser_provider():
    with (
        patch.object(cli.questionary, "select", side_effect=[_answer("sdk"), _answer("codex")]),
        patch.object(cli.config_manager, "update") as update,
        patch.object(cli.config_manager, "set") as set_value,
    ):
        assert cli._handle_settings_action("magenta") is True
    update.assert_called_once_with({"sdk": "codex", "agent_provider": "auto"})
    set_value.assert_not_called()


@pytest.mark.parametrize("command", ["agent", "engineer"])
@pytest.mark.parametrize("model", ["gpt-6-luna", "custom-codex-model"])
def test_codex_model_flag_accepts_sdk_model_ids(command, model):
    import click

    with patch.object(cli.config_manager, "get", return_value="codex"):
        context = click.Context(getattr(cli, command))
        assert cli.ModelChoice().convert(model, None, context) == model


def test_claude_model_validation_still_rejects_codex_ids():
    import click

    with patch.object(cli.config_manager, "get", return_value="claude"):
        with pytest.raises(click.BadParameter):
            cli.ModelChoice().convert("gpt-6-luna", None, click.Context(cli.agent))


def _answer(value):
    question = MagicMock()
    question.ask.return_value = value
    return question


def _catalog():
    return {
        "default": {"opencode": "big-pickle"},
        "providers": [
            {
                "id": "opencode",
                "name": "OpenCode Zen",
                "models": {
                    "big-pickle": {
                        "name": "Big Pickle",
                        "status": "active",
                        "cost": {"input": 0, "output": 0},
                        "capabilities": {"toolcall": True},
                    },
                    "no-tools": {
                        "status": "active",
                        "capabilities": {"toolcall": False},
                    },
                },
            }
        ],
    }


def test_opencode_pair_picker_uses_live_tool_capable_catalog():
    """The picker only returns a provider/model pair exposed by OpenCode."""
    with patch.object(cli.console, "status") as loading:
        with patch.object(
            cli,
            "_load_opencode_catalog_for_settings",
            new=AsyncMock(return_value=_catalog()),
        ):
            with patch.object(
                cli.questionary,
                "select",
                side_effect=[_answer("opencode"), _answer("big-pickle")],
            ) as select:
                pair = cli._select_opencode_pair_for_settings("magenta")

    assert pair == ("opencode", "big-pickle")
    loading.assert_called_once_with(" Loading OpenCode providers and models...", spinner="dots")
    model_choices = select.call_args_list[1].kwargs["choices"]
    assert [choice.value for choice in model_choices] == ["big-pickle", "back"]
    assert "free" in model_choices[0].title
    assert select.call_args_list[0].kwargs["use_jk_keys"] is False
    assert select.call_args_list[1].kwargs["use_search_filter"] is True
    assert select.call_args_list[1].kwargs["use_jk_keys"] is False


def test_opencode_pair_is_saved_atomically():
    """Settings never persist only one half of a provider/model pair."""
    with patch.object(cli.questionary, "select", return_value=_answer("opencode_pair")):
        with patch.object(cli, "_select_opencode_pair_for_settings", return_value=("google", "gemini-3-flash")):
            with patch.object(cli.config_manager, "update") as update:
                assert cli._handle_settings_action("magenta") is True

    update.assert_called_once_with({"opencode_provider": "google", "opencode_model": "gemini-3-flash"})


def test_opencode_pair_picker_explains_server_authentication():
    """A password-protected server produces a settings-specific auth hint."""
    request = httpx.Request("GET", "http://127.0.0.1:4096/config/providers")
    response = httpx.Response(401, request=request)
    error = httpx.HTTPStatusError("unauthorized", request=request, response=response)
    with patch.object(
        cli,
        "_load_opencode_catalog_for_settings",
        new=AsyncMock(side_effect=error),
    ):
        with patch.object(cli.console, "print") as print_message:
            assert cli._select_opencode_pair_for_settings() is None

    output = " ".join(str(call.args[0]) for call in print_message.call_args_list)
    assert "OPENCODE_SERVER_PASSWORD" in output


def test_model_flag_accepts_retired_ids_but_lists_current_ones():
    from click.testing import CliRunner

    choice = cli.ModelChoice()
    assert choice.convert("claude-sonnet-4-6", None, None) == "claude-sonnet-4-6"
    assert choice.convert("claude-haiku-4-5", None, None) == "claude-haiku-4-5"
    assert choice.convert("claude-haiku-5-5", None, None) == "claude-haiku-5-5"
    help_text = CliRunner().invoke(cli.main, ["agent", "--help"]).output
    assert "claude-haiku-5-5" in help_text and "claude-sonnet-4-6" not in help_text
