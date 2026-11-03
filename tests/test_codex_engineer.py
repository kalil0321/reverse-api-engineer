"""Tests for the Codex CLI and per-run browser MCP adapter."""

import json
import os
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_resume_keeps_exec_only_options_before_the_subcommand(tmp_path):
    eng = make_engineer(tmp_path)
    eng.resume_session = "thread-123"
    with patch("reverse_api.codex_engineer.resolve_codex_command", return_value=["codex"]):
        args = eng._build_exec_args("refine")
    assert args[-3:] == ["resume", "thread-123", "refine"]
    assert args.index("--sandbox") < args.index("resume")
    assert args.index("--cd") < args.index("resume")


def test_windows_prefers_codex_desktop_cli(tmp_path, monkeypatch):
    cli = tmp_path / "OpenAI" / "Codex" / "bin" / "desktop-build" / "codex.exe"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(codex_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(codex_module.shutil, "which", lambda _name: "C:/npm/codex.cmd")

    assert codex_module.resolve_codex_command() == [str(cli)]


def test_desktop_cli_uses_explicit_writable_workspace(tmp_path, monkeypatch):
    cli = tmp_path / "OpenAI" / "Codex" / "bin" / "desktop-build" / "codex.exe"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(codex_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    eng = make_engineer(tmp_path)
    with patch("reverse_api.codex_engineer.resolve_codex_command", return_value=[str(cli)]):
        args = eng._build_exec_args("browse public page")

    assert "--approve-for-me" in args
    assert 'sandbox_mode="workspace-write"' in args
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


def test_unrelated_capture_has_no_rankings_or_first_fifteen_instructions(tmp_path):
    eng = CodexAutoEngineer(run_id="weather", prompt="Fetch all 48 hourly weather records", output_dir=str(tmp_path), interactive=False)
    _, prompt = eng._get_active_prompts()
    assert "Fetch all 48 hourly weather records" in prompt
    assert "rankings GET" not in prompt
    assert "first 15" not in prompt


@pytest.mark.parametrize("headless", [False, True])
def test_browser_launch_honors_headless_on_both_platforms(tmp_path, monkeypatch, headless):
    eng = CodexAutoEngineer(run_id="browser", prompt="Fetch weather", output_dir=str(tmp_path), headless=headless, interactive=False)
    # Construct paths before mocking os.name: pathlib uses the real host type.
    for platform in ("nt", "posix"):
        with monkeypatch.context() as patcher:
            patcher.setattr(codex_module.os, "name", platform)
            args = " ".join(eng._playwright_mcp_overrides())
        assert ("--headless" in args) is headless


@pytest.mark.parametrize("auto", [False, True])
def test_relative_paths_are_absolute_in_prompts_and_browser_environment(tmp_path, monkeypatch, auto):
    monkeypatch.chdir(tmp_path)
    if auto:
        eng = CodexAutoEngineer(run_id="relative", prompt="Fetch weather", output_dir="runs", interactive=False)
        _, prompt = eng._get_active_prompts()
        assert str((tmp_path / "runs" / "har").resolve()).replace("\\", "\\\\") in " ".join(eng._playwright_mcp_overrides())
    else:
        eng = make_engineer(tmp_path, output_dir="runs", har_path=Path("runs/har/relative/recording.har"))
        _, prompt = eng._build_prompts()
    assert eng.scripts_dir.is_absolute()
    assert eng.har_path.is_absolute()
    assert str(eng.scripts_dir) in prompt
    assert str(eng.har_path) in prompt


@pytest.mark.parametrize("auto", [False, True])
@pytest.mark.parametrize("resumed", [False, True])
async def test_followups_resume_same_session_and_keep_latest_success(tmp_path, auto, resumed):
    eng = (CodexAutoEngineer(run_id="turns", prompt="Fetch weather", output_dir=str(tmp_path)) if auto else make_engineer(tmp_path, interactive=True))
    eng.resume_session = "thread-original" if resumed else None
    messages = ["resume request", "refine", "try again", None] if resumed else ["refine", "try again", None]
    eng._prompt_follow_up = AsyncMock(side_effect=messages)
    eng.ui = MagicMock()
    eng.message_store = MagicMock()
    calls = []
    results = [{"script_path": "first"}, {"script_path": "refined"}, None]

    async def turn(prompt, *args, **kwargs):
        calls.append((prompt, eng.resume_session))
        eng._record_session("thread-original")
        return results[len(calls) - 1]

    eng._run_codex = turn
    result = await eng.analyze_and_generate()
    assert result == {"script_path": "refined"}
    assert calls[1:] == [("refine", "thread-original"), ("try again", "thread-original")]
    eng.message_store.save_prompt.assert_any_call("refine")


def test_codex_usage_separates_cached_input_from_uncached_input(tmp_path):
    eng = make_engineer(tmp_path)
    for _ in range(2):
        eng._handle_codex_event({"type": "turn.completed", "usage": {"input_tokens": 18542, "cached_input_tokens": 11776, "output_tokens": 5}})
    assert eng.usage_metadata["input_tokens"] == 13532
    assert eng.usage_metadata["cache_read_tokens"] == 23552
    assert eng.usage_metadata["output_tokens"] == 10


@pytest.mark.parametrize("relative", [False, True])
async def test_capture_subprocess_artifacts_and_code_only_followup(tmp_path, monkeypatch, relative):
    monkeypatch.chdir(tmp_path)
    output = "runs with spaces" if relative else str(tmp_path / "runs with spaces")
    eng = CodexAutoEngineer(run_id="process", prompt="Fetch weather", output_dir=output, interactive=False)
    eng.ui = MagicMock()
    eng.message_store = MagicMock()
    child = tmp_path / "controlled_child.py"
    child.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "scripts, har = Path(sys.argv[1]), Path(sys.argv[2])\n"
        "if sys.argv[3] == 'capture':\n"
        "    scripts.mkdir(parents=True, exist_ok=True)\n"
        "    (scripts / 'api_client.py').write_text('# generated client')\n"
        "    har.parent.mkdir(parents=True, exist_ok=True)\n"
        "    har.write_text(json.dumps({'log': {'entries': [{'request': {'method': 'GET'}}]}}))\n"
        "    print(json.dumps({'type': 'item.started', 'item': {'type': 'mcp_tool_call', "
        "'id': 'nav', 'server': 'playwright', 'tool': 'browser_navigate'}}))\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': 'process-thread'}))\n"
        "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 20, 'cached_input_tokens': 10, 'output_tokens': 2}}))\n",
        encoding="utf-8",
    )
    eng._build_exec_args = lambda prompt, overrides: [codex_module.sys.executable, str(child), str(eng.scripts_dir), str(eng.har_path), prompt]
    first = await eng._run_codex("capture", eng._playwright_mcp_overrides(), mode="agent")
    assert first is not None
    assert first["har_entries"] == 1
    assert Path(first["script_path"]).is_file()
    assert Path(first["har_path"]).is_file()
    assert not (tmp_path / "runs with spaces" / "runs with spaces").exists()
    # A refinement can reuse the verified capture without calling browser MCP again.
    eng.resume_session = "process-thread"
    followup = await eng._run_codex("edit only", eng._playwright_mcp_overrides(), mode="agent")
    assert followup is not None
    assert followup["har_entries"] == 1
    assert followup["usage"]["input_tokens"] == 20


async def test_noninteractive_stops_after_one_turn(tmp_path):
    eng = make_engineer(tmp_path)
    eng._run_codex = AsyncMock(return_value={"script_path": "first"})
    assert await eng.analyze_and_generate() == {"script_path": "first"}
    eng._run_codex.assert_awaited_once()
