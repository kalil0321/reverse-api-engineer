"""Tests for the Codex CLI and per-run browser MCP adapter."""

import json
import os
import tomllib
from unittest.mock import MagicMock, patch

import pytest

import reverse_api.codex_engineer as codex_module
from reverse_api.codex_engineer import CodexAutoEngineer, CodexEngineer


def make_engineer(tmp_path, **kwargs):
    defaults = {
        "run_id": "codex-test",
        "har_path": tmp_path / "har" / "codex-test" / "recording.har",
        "prompt": "fetch public data",
        "output_dir": str(tmp_path),
        "verbose": False,
        "interactive": False,
    }
    defaults.update(kwargs)
    return CodexEngineer(**defaults)


def test_exec_args_use_workspace_sandbox_and_explicit_supported_default(tmp_path):
    eng = make_engineer(tmp_path)
    with patch("reverse_api.codex_engineer.resolve_codex_command", return_value=["node", "codex.js"]):
        args = eng._build_exec_args("read this HAR")

    assert args[:2] == ["node", "codex.js"]
    assert "--ignore-user-config" in args
    assert args[args.index("--sandbox") + 1] == "workspace-write"
    assert args[args.index("--cd") + 1] == str((tmp_path / "scripts" / "codex-test").parent.parent.resolve())
    assert args[args.index("--model") + 1] == "gpt-6-luna"
    assert args[-1] == "read this HAR"


def test_mcp_overrides_are_per_invocation_and_required(tmp_path):
    eng = make_engineer(tmp_path)
    overrides = eng._codex_mcp_overrides(
        "playwright",
        "cmd.exe",
        ["/d", "/s", "/c", "npx -y rae-playwright-mcp@0.0.9"],
        env={"PLAYWRIGHT_MCP_SAVE_HAR_PATH": str(tmp_path / "runs with spaces" / "har")},
    )
    parsed = {}
    for index, item in enumerate(overrides):
        if item == "--config":
            key, value = overrides[index + 1].split("=", 1)
            parsed[key.rsplit(".", 1)[-1]] = tomllib.loads(f"{key}={value}")["mcp_servers"]["playwright"][key.rsplit(".", 1)[-1]]

    assert parsed["command"] == "cmd.exe"
    assert parsed["args"] == ["/d", "/s", "/c", "npx -y rae-playwright-mcp@0.0.9"]
    assert parsed["required"] is True
    suffix = "runs with spaces\\har" if os.name == "nt" else "runs with spaces/har"
    assert parsed["env"]["PLAYWRIGHT_MCP_SAVE_HAR_PATH"].endswith(suffix)


def test_windows_prefers_codex_desktop_cli(tmp_path, monkeypatch):
    cli = tmp_path / "OpenAI" / "Codex" / "bin" / "desktop-build" / "codex.exe"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(codex_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(codex_module.shutil, "which", lambda _name: "C:/npm/codex.cmd")

    assert codex_module.resolve_codex_command() == [str(cli)]


def test_desktop_cli_uses_workspace_scoped_approval_review(tmp_path, monkeypatch):
    cli = tmp_path / "OpenAI" / "Codex" / "bin" / "desktop-build" / "codex.exe"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(codex_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    eng = make_engineer(tmp_path)
    with patch("reverse_api.codex_engineer.resolve_codex_command", return_value=[str(cli)]):
        args = eng._build_exec_args("browse public page")

    assert "--approve-for-me" in args
    assert "--sandbox" not in args


def test_codex_events_record_session_and_playwright_tool_call(tmp_path):
    eng = make_engineer(tmp_path)
    eng.ui = MagicMock()
    eng.message_store = MagicMock()
    eng.on_session = MagicMock()
    eng._handle_codex_event({"type": "thread.started", "thread_id": "thread-123"})
    eng._handle_codex_event({
        "type": "item.started",
        "item": {
            "id": "call-1",
            "type": "mcp_tool_call",
            "server": "playwright",
            "tool": "browser_navigate",
            "arguments": {"url": "https://openrouter.ai/rankings"},
        },
    })
    eng._handle_codex_event({
        "type": "item.completed",
        "item": {
            "id": "call-1",
            "type": "mcp_tool_call",
            "server": "playwright",
            "tool": "browser_navigate",
            "result": "Navigated",
        },
    })

    assert eng.sdk_session_id == "thread-123"
    eng.on_session.assert_called_once_with("thread-123")
    assert eng._mcp_tool_calls == ["mcp__playwright__browser_navigate"]
    eng.ui.tool_start.assert_called_once()
    eng.ui.tool_result.assert_called_once()


def test_auto_engineer_prompt_uses_shared_codegen_without_claude_only_tool(tmp_path):
    eng = CodexAutoEngineer(
        run_id="codex-auto",
        prompt="Capture rankings",
        output_dir=str(tmp_path),
        agent_provider="auto",
        start_url="https://openrouter.ai/rankings",
        headless=True,
        verbose=False,
        interactive=False,
    )

    system_prompt, user_prompt = eng._get_active_prompts()
    assert "Playwright MCP" in system_prompt
    assert "report_client_verified" not in system_prompt
    assert "https://openrouter.ai/rankings" in user_prompt
    assert "Do not install packages or execute the generated client" in user_prompt


def test_auto_capture_validation_requires_browser_tool_and_nonempty_har(tmp_path):
    eng = CodexAutoEngineer(
        run_id="codex-auto",
        prompt="Capture rankings",
        output_dir=str(tmp_path),
        agent_provider="auto",
        verbose=False,
        interactive=False,
    )
    eng.har_path.parent.mkdir(parents=True, exist_ok=True)
    eng.har_path.write_text(json.dumps({"log": {"entries": [{"request": {"method": "GET"}}]}}), encoding="utf-8")

    assert "without calling" in eng._validate_browser_capture()
    eng._mcp_tool_calls.append("mcp__playwright__browser_navigate")
    assert eng._validate_browser_capture() is None
    assert eng._har_entry_count == 1


def test_auto_capture_requires_har_preserving_provider(tmp_path):
    with pytest.raises(ValueError, match="agent_provider='auto'"):
        CodexAutoEngineer(
            run_id="codex-auto",
            prompt="Capture rankings",
            output_dir=str(tmp_path),
            agent_provider="chrome-mcp",
            verbose=False,
            interactive=False,
        )
