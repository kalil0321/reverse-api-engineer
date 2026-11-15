"""Tests for the Codex SDK backend: a fake app-server, with notifications built from the SDK's own models."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from reverse_api import codex_engineer, verification_mcp
from reverse_api.codex_engineer import (
    FILE_EDITS,
    INSTALL_HELP,
    SIGN_IN_HELP,
    CodexAutoEngineer,
    CodexEngineer,
    CodexSetupError,
    _command_text,
    codex_check,
    codex_config,
    codex_home,
)

openai_codex = pytest.importorskip("openai_codex")
from openai_codex.generated import v2_all as wire  # noqa: E402
from openai_codex.models import Notification  # noqa: E402
from openai_codex.types import ReasoningEffort  # noqa: E402

THREAD, TURN = "thread-1", "turn-1"


def note(method: str, model: Any, **fields: Any) -> Notification:
    """A notification as the SDK delivers it, validated from its wire form."""
    return Notification(method, model.model_validate({"threadId": THREAD, "turnId": TURN, **fields}))


def item(method: str, **fields: Any) -> Notification:
    model = wire.ItemStartedNotification if method == "item/started" else wire.ItemCompletedNotification
    return note(method, model, item=fields, startedAtMs=1, completedAtMs=2)


def turn_end(status: str = "completed", error: str | None = None) -> Notification:
    turn: dict[str, Any] = {"id": TURN, "items": [], "status": status}
    if error:
        turn["error"] = {"message": error}
    return Notification("turn/completed", wire.TurnCompletedNotification.model_validate({"threadId": THREAD, "turn": turn}))


class FakeTurn:
    def __init__(self, events: list[Notification], block: bool = False) -> None:
        self.events, self.block = events, block
        self.streaming = asyncio.Event()
        self.interrupted = False

    async def stream(self) -> Any:
        self.streaming.set()
        for event in self.events:
            yield event
        if self.block:
            await asyncio.Event().wait()

    async def interrupt(self) -> None:
        self.interrupted = True


class FakeCodex:
    """AsyncCodex with a signed-in account and scripted turns."""

    def __init__(self, turns: list[FakeTurn], account: Any = "account") -> None:
        self.turns, self.account_value = turns, account
        self.messages: list[str] = []
        self.efforts: list[Any] = []
        self.started: dict[str, Any] | None = None
        self.resumed: tuple[str, dict[str, Any]] | None = None
        self.entering, self.ready = asyncio.Event(), asyncio.Event()
        self.ready.set()
        self.closed = False

    async def __aenter__(self) -> FakeCodex:
        self.entering.set()
        await self.ready.wait()  # the app-server starting
        return self

    async def close(self) -> None:
        self.closed = True

    async def account(self) -> Any:
        return SimpleNamespace(account=self.account_value)

    async def thread_start(self, **options: Any) -> Any:
        self.started = options
        return self._thread()

    async def thread_resume(self, thread_id: str, **options: Any) -> Any:
        self.resumed = (thread_id, options)
        return self._thread()

    def _thread(self) -> Any:
        async def turn(message: str, effort: Any = None) -> FakeTurn:
            self.messages.append(message)
            self.efforts.append(effort)
            return self.turns.pop(0)

        return SimpleNamespace(id=THREAD, turn=turn)


@pytest.fixture
def fake_codex(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Installs a FakeCodex for the engineer to start; the Codex home stays untouched."""

    def install(turns: list[FakeTurn], **kwargs: Any) -> FakeCodex:
        fake = FakeCodex(turns, **kwargs)
        monkeypatch.setattr(openai_codex, "AsyncCodex", lambda config: fake)
        monkeypatch.setattr(codex_engineer, "codex_config", lambda home: None)
        return fake

    return install


def engineer(tmp_path: Path, cls: type[CodexEngineer] = CodexEngineer, **kwargs: Any) -> Any:
    options: dict[str, Any] = {"run_id": "run1", "prompt": "the jobs api", "output_dir": str(tmp_path), "sdk": "codex", "interactive": False}
    if cls is CodexEngineer:
        options["har_path"] = tmp_path / "recording.har"
    eng = cls(**{**options, **kwargs})
    eng.ui = MagicMock()
    return eng


def logged(eng: CodexEngineer, kind: str) -> list[dict[str, Any]]:
    return [m for m in eng.message_store.load() if m["type"] == kind]


class TestConversation:
    async def test_a_new_thread_gets_raes_instructions_and_runs_unsandboxed(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()])])
        sessions: list[str] = []
        eng = engineer(tmp_path, codex_model="gpt-6.1-sol")
        eng.on_session = sessions.append
        result = await eng.analyze_and_generate()

        assert result is not None and result["script_path"].endswith("api_client.py")
        system_prompt, user_message = eng._build_prompts()
        assert fake.started is not None and fake.started["developer_instructions"] == system_prompt + FILE_EDITS
        assert "report_client_verified" in system_prompt + user_message
        assert fake.messages == [user_message]
        assert fake.started["sandbox"] is openai_codex.Sandbox.full_access
        assert fake.started["approval_mode"] is openai_codex.ApprovalMode.deny_all
        assert fake.started["model"] == "gpt-6.1-sol"
        assert fake.started["config"] == {"mcp_servers": {"verification": verification_mcp.server_config()}}
        assert fake.started["cwd"] == str(eng.scripts_dir)
        assert sessions == [THREAD] and fake.closed

    async def test_no_model_or_effort_leaves_the_choice_to_codex(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()])])
        await engineer(tmp_path, codex_model="", codex_effort="").analyze_and_generate()
        assert fake.started is not None and fake.started["model"] is None
        assert fake.efforts == [None]

    async def test_every_turn_runs_at_the_chosen_effort(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()]), FakeTurn([turn_end()])])
        eng = engineer(tmp_path, codex_effort="xhigh", interactive=True)
        eng._prompt_follow_up = AsyncMock(side_effect=["add auth", None])
        await eng.analyze_and_generate()
        assert fake.efforts == [ReasoningEffort.xhigh, ReasoningEffort.xhigh]

    @pytest.mark.parametrize("cls,provider", [(CodexEngineer, None), (CodexAutoEngineer, "agent-browser")])
    def test_codex_asks_in_its_reply_not_with_claudes_ask_tool(self, tmp_path, cls, provider):
        from reverse_api.auto_engineer import ClaudeAutoEngineer

        eng = engineer(tmp_path, cls, **({"agent_provider": provider} if provider else {}))
        prompts = "".join(ClaudeAutoEngineer._build_auto_prompts(eng) if provider else eng._build_prompts())
        assert "AskUserQuestion" not in prompts and "ask in your reply and end your turn" in prompts

    async def test_docs_mode_is_not_asked_to_verify_a_client(self, tmp_path, fake_codex):
        fake_codex([FakeTurn([turn_end()])])
        eng = engineer(tmp_path, output_mode="docs")
        assert "report_client_verified" not in eng._get_codegen_instructions()

    async def test_resuming_reopens_the_thread_and_starts_from_the_users_message(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()])])
        eng = engineer(tmp_path)
        eng.resume_session = "thread-0"
        eng._prompt_follow_up = AsyncMock(side_effect=["now add pagination", None])
        await eng.analyze_and_generate()
        assert fake.started is None and fake.resumed is not None and fake.resumed[0] == "thread-0"
        assert "developer_instructions" not in fake.resumed[1]
        assert fake.messages == ["now add pagination"]

    async def test_without_a_sign_in_no_thread_starts(self, tmp_path, fake_codex):
        fake = fake_codex([], account=None)
        eng = engineer(tmp_path)
        assert await eng.analyze_and_generate() is None
        eng.ui.error.assert_called_once_with(SIGN_IN_HELP)
        assert fake.started is None and fake.resumed is None

    async def test_a_missing_sdk_says_how_to_install_it(self, tmp_path, monkeypatch):
        monkeypatch.setattr(codex_engineer, "codex_installed", lambda: False)
        eng = engineer(tmp_path)
        assert await eng.analyze_and_generate() is None
        eng.ui.error.assert_called_once_with(INSTALL_HELP)

    async def test_a_failed_turn_shows_codexs_reason(self, tmp_path, fake_codex):
        fake_codex([FakeTurn([turn_end("failed", "You've hit your usage limit.")])])
        eng = engineer(tmp_path)
        assert await eng.analyze_and_generate() is None
        eng.ui.error.assert_called_once_with("You've hit your usage limit.")
        assert logged(eng, "error")[0]["content"] == "You've hit your usage limit."

    async def test_a_runtime_that_fails_to_start_is_an_error_not_a_crash(self, tmp_path, monkeypatch):
        def broken(config: Any) -> Any:
            raise FileNotFoundError("Codex binary not found")

        monkeypatch.setattr(openai_codex, "AsyncCodex", broken)
        monkeypatch.setattr(codex_engineer, "codex_config", lambda home: None)
        eng = engineer(tmp_path)
        assert await eng.analyze_and_generate() is None
        eng.ui.error.assert_called_once_with("Codex binary not found")

    async def test_a_failed_follow_up_keeps_the_last_client(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()]), FakeTurn([turn_end("failed", "boom")])])
        eng = engineer(tmp_path, interactive=True)
        eng._prompt_follow_up = AsyncMock(side_effect=["add auth", None])
        result = await eng.analyze_and_generate()
        assert result is not None and result["script_path"].endswith("api_client.py")
        assert fake.messages[1] == "add auth" and logged(eng, "prompt")[-1]["content"] == "add auth"

    async def test_stopping_interrupts_codex_and_keeps_the_finished_turn(self, tmp_path, fake_codex):
        stuck = FakeTurn([], block=True)
        fake = fake_codex([FakeTurn([turn_end()]), stuck])
        eng = engineer(tmp_path, interactive=True)
        eng._prompt_follow_up = AsyncMock(return_value="keep going")
        task = asyncio.create_task(eng.analyze_and_generate())
        await asyncio.wait_for(stuck.streaming.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as stopped:
            await task
        assert stuck.interrupted and fake.closed
        assert stopped.value.partial_result["script_path"].endswith("api_client.py")  # type: ignore[attr-defined]

    async def test_stopping_while_codex_starts_still_closes_it_once_started(self, tmp_path, fake_codex):
        fake = fake_codex([])
        fake.ready.clear()
        task = asyncio.create_task(engineer(tmp_path).analyze_and_generate())
        await asyncio.wait_for(fake.entering.wait(), 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "waits for the start the SDK runs on in its worker thread"
        fake.ready.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert fake.closed and fake.started is None

    async def test_a_resumed_thread_counts_only_this_runs_tokens(self, tmp_path, fake_codex):
        def usage(total_input: int, total_cached: int, total_output: int, last_input: int, last_cached: int, last_output: int) -> Notification:
            def breakdown(i: int, c: int, o: int) -> dict[str, int]:
                return {"inputTokens": i, "cachedInputTokens": c, "outputTokens": o, "reasoningOutputTokens": 0, "totalTokens": i + o}

            tokens = {"total": breakdown(total_input, total_cached, total_output), "last": breakdown(last_input, last_cached, last_output)}
            return note("thread/tokenUsage/updated", wire.ThreadTokenUsageUpdatedNotification, tokenUsage=tokens)

        # The thread had used 5000 input (4000 cached) and 300 output tokens before this run.
        fake_codex([FakeTurn([usage(6000, 4800, 340, 1000, 800, 40), usage(7200, 5700, 400, 1200, 900, 60), turn_end()])])
        eng = engineer(tmp_path)
        eng.resume_session = "thread-0"
        eng._prompt_follow_up = AsyncMock(side_effect=["go on", None])
        result = await eng.analyze_and_generate()
        assert result is not None
        assert result["usage"] == {"input_tokens": 2200 - 1700, "cache_read_tokens": 1700, "output_tokens": 100}


class TestNotifications:
    """Each Codex item becomes the step, receipt or message the other SDKs' runs show."""

    @pytest.fixture
    def eng(self, tmp_path: Path) -> Any:
        return engineer(tmp_path)

    def run(self, eng: Any, *events: Notification) -> None:
        for event in events:
            eng._on_event(event.method, event.payload)

    def test_a_command_shows_without_its_login_shell(self, eng):
        command = {"id": "c1", "type": "commandExecution", "command": "/bin/zsh -lc 'python api_client.py'", "commandActions": [], "cwd": "/tmp"}
        self.run(
            eng,
            item("item/started", **command, status="inProgress"),
            item("item/completed", **command, status="completed", exitCode=0, aggregatedOutput="200 OK\n"),
        )
        eng.ui.tool_start.assert_called_once_with("Bash", {"command": "python api_client.py"}, call_id="c1")
        eng.ui.tool_result.assert_called_once_with("Bash", False, "200 OK\n", call_id="c1")
        assert logged(eng, "tool_start")[0]["content"]["name"] == "Bash"

    def test_a_command_that_exits_non_zero_failed(self, eng):
        command = {"id": "c1", "type": "commandExecution", "command": "false", "commandActions": [], "cwd": "/tmp"}
        self.run(eng, item("item/completed", **command, status="completed", exitCode=1, aggregatedOutput="Traceback"))
        eng.ui.tool_result.assert_called_once_with("Bash", True, "Traceback", call_id="c1")

    def test_a_patch_shows_each_file_it_changed(self, eng):
        changes = [
            {"path": "/runs/scripts/run1/api_client.py", "kind": {"type": "add"}, "diff": "import requests\n"},
            {"path": "/runs/scripts/run1/README.md", "kind": {"type": "update", "move_path": None}, "diff": "@@ -1 +1 @@\n-a\n+b\n"},
            {"path": "/runs/scripts/run1/old.py", "kind": {"type": "delete"}, "diff": ""},
        ]
        self.run(eng, item("item/completed", id="p1", type="fileChange", status="completed", changes=changes))
        starts = [(c.args, c.kwargs) for c in eng.ui.tool_start.call_args_list]
        assert starts == [
            (("Write", {"file_path": "/runs/scripts/run1/api_client.py", "content": "import requests\n"}), {"call_id": "p1:0"}),
            (("Edit", {"file_path": "/runs/scripts/run1/README.md"}), {"call_id": "p1:1"}),
            (("Delete", {"file_path": "/runs/scripts/run1/old.py"}), {"call_id": "p1:2"}),
        ]
        assert [c.args[1] for c in eng.ui.tool_result.call_args_list] == [False, False, False]

    def test_a_patch_that_did_not_apply_failed(self, eng):
        change = {"path": "/x.py", "kind": {"type": "add"}, "diff": "x"}
        self.run(eng, item("item/completed", id="p1", type="fileChange", status="failed", changes=[change]))
        assert eng.ui.tool_result.call_args.args[1] is True

    def test_a_browser_tool_reads_as_its_mcp_name_with_its_text(self, eng):
        call = {"id": "m1", "type": "mcpToolCall", "server": "chrome-devtools", "tool": "navigate_page", "arguments": {"url": "https://jobs.example"}}
        result = {"content": [{"type": "text", "text": "navigated"}, {"type": "image", "data": "…", "mimeType": "image/png"}]}
        self.run(
            eng,
            item("item/started", **call, status="inProgress"),
            item("item/completed", **call, status="completed", result=result),
        )
        eng.ui.tool_start.assert_called_once_with("mcp__chrome-devtools__navigate_page", {"url": "https://jobs.example"}, call_id="m1")
        eng.ui.tool_result.assert_called_once_with("mcp__chrome-devtools__navigate_page", False, "navigated", call_id="m1")

    def test_a_failed_browser_tool_shows_its_error(self, eng):
        call = {"id": "m1", "type": "mcpToolCall", "server": "playwright", "tool": "browser_click", "arguments": {}}
        self.run(eng, item("item/completed", **call, status="failed", error={"message": "element not found"}))
        eng.ui.tool_result.assert_called_once_with("mcp__playwright__browser_click", True, "element not found", call_id="m1")

    def test_a_verified_client_is_reported_once_before_its_step_shows(self, eng):
        events: list[dict[str, Any]] = []
        eng._json_event_sink = events.append
        eng._report_workspace = MagicMock(side_effect=lambda: eng.ui.tool_result.assert_not_called())
        call = {"type": "mcpToolCall", "server": "verification", "tool": "report_client_verified", "arguments": {"summary": "200 OK"}}
        result = {"content": [{"type": "text", "text": verification_mcp.RECORDED}]}
        self.run(
            eng,
            item("item/completed", id="v1", **call, status="completed", result=result),
            item("item/completed", id="v2", **call, status="completed", result=result),
        )
        eng._report_workspace.assert_called_once()
        assert events == [{"event": "client_executed", "script_path": str(eng.scripts_dir / "api_client.py")}]
        assert eng.ui.tool_result.call_args.args[:2] == ("mcp__verification__report_client_verified", False)

    def test_a_failed_verify_call_reports_nothing(self, eng):
        events: list[dict[str, Any]] = []
        eng._json_event_sink = events.append
        call = {"id": "v1", "type": "mcpToolCall", "server": "verification", "tool": "report_client_verified", "arguments": {}}
        self.run(eng, item("item/completed", **call, status="failed", error={"message": "server exited"}))
        assert events == []

    def test_the_final_answer_shows_whole_and_commentary_as_a_note(self, eng):
        self.run(
            eng,
            item("item/completed", id="a1", type="agentMessage", phase="commentary", text="Opening the jobs page."),
            item("item/completed", id="a2", type="agentMessage", phase="final_answer", text="The client is ready."),
        )
        eng.ui.thinking.assert_called_once_with("Opening the jobs page.")
        eng.ui.thinking_block.assert_called_once_with("The client is ready.")
        assert [m["content"] for m in logged(eng, "thinking")] == ["Opening the jobs page.", "The client is ready."]

    def test_text_and_reasoning_stream_then_settle(self, eng):
        self.run(
            eng,
            note("item/agentMessage/delta", wire.AgentMessageDeltaNotification, itemId="a1", delta="Open"),
            note("item/reasoning/summaryTextDelta", wire.ReasoningSummaryTextDeltaNotification, itemId="r1", delta="Look", summaryIndex=0),
            item("item/completed", id="r1", type="reasoning", summary=["Look at the network tab."], content=[]),
        )
        eng.ui.stream_text.assert_called_once_with("Open")
        eng.ui.stream_thinking.assert_called_once_with("Look")
        eng.ui.thinking_note.assert_called_once_with("Look at the network tab.")

    def test_the_plan_uses_the_status_names_of_the_other_sdks(self, eng):
        plan = [{"step": "Open the site", "status": "completed"}, {"step": "Write the client", "status": "inProgress"}]
        self.run(eng, note("turn/plan/updated", wire.TurnPlanUpdatedNotification, plan=plan))
        todos = [{"content": "Open the site", "status": "completed"}, {"content": "Write the client", "status": "in_progress"}]
        eng.ui.todo_updated.assert_called_once_with(todos)
        assert logged(eng, "todos")[0]["content"] == todos

    def test_usage_counts_cached_input_apart(self, eng):
        breakdown = {"cachedInputTokens": 900, "inputTokens": 1000, "outputTokens": 50, "reasoningOutputTokens": 20, "totalTokens": 1050}
        usage = {"last": breakdown, "total": breakdown}
        self.run(eng, note("thread/tokenUsage/updated", wire.ThreadTokenUsageUpdatedNotification, tokenUsage=usage))
        assert eng.usage_metadata == {"input_tokens": 100, "cache_read_tokens": 900, "output_tokens": 50}

    def test_a_retried_error_is_progress_not_a_failure(self, eng):
        error = {"message": "stream disconnected, retrying"}
        self.run(eng, note("error", wire.ErrorNotification, error=error, willRetry=True))
        eng.ui.progress.assert_called_once_with("codex retries: stream disconnected, retrying")
        eng.ui.error.assert_not_called()

    def test_web_steps_name_their_query_or_the_page_codex_opened(self, eng):
        web = {"type": "webSearch", "query": ""}
        self.run(
            eng,
            item("item/completed", id="w1", **web, action={"type": "search", "query": "browserbase careers"}),
            item("item/completed", id="w2", **web, action={"type": "openPage", "url": "https://www.browserbase.com/careers"}),
            item("item/completed", id="w3", **web, action={"type": "findInPage", "url": "https://jobs.example", "pattern": "Engineer"}),
        )
        assert [c.args[:2] for c in eng.ui.tool_start.call_args_list] == [
            ("WebSearch", {"query": "browserbase careers"}),
            ("WebFetch", {"url": "https://www.browserbase.com/careers"}),
            ("WebSearch", {"query": "Engineer on https://jobs.example"}),
        ]

    def test_items_rae_does_not_show_are_skipped(self, eng):
        self.run(eng, item("item/completed", id="u1", type="userMessage", content=[{"type": "text", "text": "hi", "text_elements": []}]))
        eng.ui.tool_start.assert_not_called()
        eng.ui.thinking.assert_not_called()


class TestBrowserServers:
    def test_playwright_runs_the_pinned_mcp_with_the_runs_id(self, tmp_path):
        from reverse_api.config import PLAYWRIGHT_MCP_PACKAGE

        eng = engineer(tmp_path, CodexAutoEngineer, agent_provider="auto", headless=True)
        server = eng._browser_servers()["playwright"]
        assert server["command"] == "npx"
        assert server["args"] == ["-y", PLAYWRIGHT_MCP_PACKAGE, "run-mcp-server", "--run-id", "run1", "--headless"]
        assert server["startup_timeout_sec"] == codex_engineer.MCP_STARTUP_TIMEOUT_SEC

    @pytest.mark.parametrize("headless,flag", [(False, "--autoConnect"), (True, "--headless")])
    def test_chrome_mcp_attaches_to_the_users_chrome_unless_headless(self, tmp_path, headless, flag):
        from reverse_api.chrome_mcp import CHROME_DEVTOOLS_MCP_PACKAGE

        eng = engineer(tmp_path, CodexAutoEngineer, agent_provider="chrome-mcp", headless=headless)
        assert eng._browser_servers()["chrome-devtools"]["args"] == ["-y", CHROME_DEVTOOLS_MCP_PACKAGE, "--no-usage-statistics", flag]

    def test_agent_browser_has_no_mcp_server(self, tmp_path):
        assert engineer(tmp_path, CodexAutoEngineer, agent_provider="agent-browser")._browser_servers() == {}

    async def test_agent_mode_registers_the_browser_and_the_verify_tool(self, tmp_path, fake_codex):
        fake = fake_codex([FakeTurn([turn_end()])])
        eng = engineer(tmp_path, CodexAutoEngineer, agent_provider="auto")
        await eng.analyze_and_generate()
        servers = {**eng._browser_servers(), "verification": verification_mcp.server_config()}
        assert fake.started is not None and fake.started["config"] == {"mcp_servers": servers}
        assert "report_client_verified" in fake.started["developer_instructions"] + fake.messages[0]


class TestCodexHome:
    @pytest.fixture
    def homes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        app, user = tmp_path / "app", tmp_path / "user-codex"
        user.mkdir()
        monkeypatch.setattr(codex_engineer, "get_app_dir", lambda: app)
        monkeypatch.setenv("CODEX_HOME", str(user))
        return app / "codex", user

    def test_raes_home_links_to_the_users_sign_in(self, homes):
        home, user = homes
        (user / "auth.json").write_text("{}")
        assert codex_home() == home
        assert (home / "auth.json").is_symlink() and (home / "auth.json").resolve() == (user / "auth.json").resolve()

    def test_without_a_users_sign_in_there_is_nothing_to_link(self, homes):
        home, _user = homes
        codex_home()
        assert not (home / "auth.json").exists() and not (home / "auth.json").is_symlink()

    def test_a_link_left_dangling_by_a_sign_out_is_kept_for_the_next_sign_in(self, homes):
        home, user = homes
        (user / "auth.json").write_text("{}")
        codex_home()
        (user / "auth.json").unlink()
        codex_home()
        assert (home / "auth.json").is_symlink()

    def test_the_link_follows_codex_home_when_it_moves(self, homes, tmp_path, monkeypatch):
        home, user = homes
        (user / "auth.json").write_text("{}")
        codex_home()
        moved = tmp_path / "moved-codex"
        moved.mkdir()
        (moved / "auth.json").write_text("{}")
        monkeypatch.setenv("CODEX_HOME", str(moved))
        codex_home()
        assert (home / "auth.json").resolve() == (moved / "auth.json").resolve()
        assert [p.name for p in home.iterdir()] == ["auth.json"], "no staged link is left behind"

    def test_a_relative_codex_home_links_by_its_absolute_path(self, homes, tmp_path, monkeypatch):
        home, user = homes
        (user / "auth.json").write_text("{}")
        monkeypatch.chdir(user.parent)
        monkeypatch.setenv("CODEX_HOME", user.name)
        codex_home()
        assert Path(os.readlink(home / "auth.json")) == user / "auth.json"

    def test_a_sign_in_made_in_raes_home_is_kept(self, homes):
        home, user = homes
        (user / "auth.json").write_text('{"theirs": true}')
        home.mkdir(parents=True)
        (home / "auth.json").write_text('{"raes": true}')
        codex_home()
        assert not (home / "auth.json").is_symlink() and (home / "auth.json").read_text() == '{"raes": true}'

    def test_a_link_another_run_just_made_is_fine(self, homes):
        home, user = homes
        (user / "auth.json").write_text("{}")
        home.mkdir(parents=True)
        (home / "auth.json").symlink_to(user / "auth.json")
        assert codex_home() == home and (home / "auth.json").is_symlink()

    def test_a_configured_home_is_used_as_it_is(self, homes, tmp_path):
        home, user = homes
        (user / "auth.json").write_text("{}")
        assert codex_home(str(tmp_path / "mine")) == tmp_path / "mine"
        assert not home.exists() and not (tmp_path / "mine").exists()

    def test_a_link_that_cannot_be_made_says_how_to_share_the_users_home(self, homes, monkeypatch):
        _home, user = homes
        (user / "auth.json").write_text("{}")

        def denied(self: Path, target: Path) -> None:
            raise OSError("symbolic link privilege not held")

        monkeypatch.setattr(Path, "symlink_to", denied)
        with pytest.raises(CodexSetupError, match='set "codex_home"'):
            codex_home()

    def test_only_raes_home_pins_the_file_store_and_hides_the_users_skills_and_apps(self, homes, tmp_path):
        home, _user = homes
        own = codex_config()
        assert own.env == {"CODEX_HOME": str(home)}
        assert own.config_overrides == ('cli_auth_credentials_store="file"', "skills.include_instructions=false", "features.apps=false")
        assert own.client_name == "reverse_api_engineer"
        mine = codex_config(str(tmp_path / "mine"))
        assert mine.env == {"CODEX_HOME": str(tmp_path / "mine")} and mine.config_overrides == ()

    def test_the_dry_run_check_finds_the_sign_in_without_starting_codex(self, homes):
        _home, user = homes
        assert codex_check()["status"] == "warn"
        (user / "auth.json").write_text("{}")
        assert codex_check()["status"] == "ok"

    def test_the_dry_run_check_reports_a_missing_sdk(self, monkeypatch):
        monkeypatch.setattr(codex_engineer, "codex_installed", lambda: False)
        assert codex_check() == {"name": "sdk:codex", "status": "error", "message": INSTALL_HELP}


@pytest.mark.parametrize(
    "command,shown",
    [
        ("/bin/zsh -lc 'cat notes.txt'", "cat notes.txt"),
        ("/bin/bash -c \"python api_client.py --page 2\"", "python api_client.py --page 2"),
        ("powershell.exe -NoProfile -Command Get-Content x", "powershell.exe -NoProfile -Command Get-Content x"),
        ("/bin/zsh -lc 'unbalanced", "/bin/zsh -lc 'unbalanced"),
    ],
)
def test_command_text_drops_only_the_login_shell(command, shown):
    assert _command_text(command) == shown
