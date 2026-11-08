"""Tests for the settings the session's /settings reads and offers."""

from unittest.mock import patch

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


def test_opencode_models_are_the_tool_capable_ones_with_free_and_default_marked():
    assert cli.opencode_model_choices(_catalog(), "opencode") == [("big-pickle", "big-pickle — Big Pickle  (free, default)")]


def test_a_malformed_provider_entry_is_skipped():
    catalog = {**_catalog(), "providers": [None, "opencode", *_catalog()["providers"]]}
    assert [provider_id for provider_id, _ in cli.opencode_provider_choices(catalog)] == ["opencode", "ollama"]


def test_opencode_providers_always_offer_ollama():
    """Ollama can start itself even when OpenCode's catalog does not list it yet."""
    assert cli.opencode_provider_choices(_catalog()) == [("opencode", "opencode — OpenCode Zen"), ("ollama", "ollama — installed local models")]
    assert cli.opencode_provider_choices({"providers": []}) == [("ollama", "ollama — installed local models")]


def test_model_flag_accepts_retired_ids_but_lists_current_ones():
    from click.testing import CliRunner

    choice = cli.ModelChoice()
    assert choice.convert("claude-sonnet-4-6", None, None) == "claude-sonnet-4-6"
    assert choice.convert("claude-haiku-4-5", None, None) == "claude-haiku-4-5"
    assert choice.convert("claude-haiku-5-5", None, None) == "claude-haiku-5-5"
    help_text = CliRunner().invoke(cli.main, ["agent", "--help"]).output
    assert "claude-haiku-5-5" in help_text and "claude-sonnet-4-6" not in help_text
