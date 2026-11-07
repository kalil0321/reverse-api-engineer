"""Tests for the full-screen session: tool events to ledger entries, follow-ups, transcript capture, the bar."""

import asyncio
import io
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from rich.console import Console

from reverse_api.repl import bridge as bridge_mod
from reverse_api.repl.bridge import Bridge, LedgerUI, describe, short_name
from reverse_api.repl.transcript import Raw, Transcript, TranscriptWriter, raw_lines
from reverse_api.repl.view import LedgerView, SessionState, default_effort, first_definition, model_label, terminal_safe


def plain(transcript: Transcript) -> str:
    return "\n".join("".join(frag[1] for frag in line) for line in transcript.lines())


@pytest.fixture
def session():
    st = SessionState(model="claude-sonnet-5-5")
    t = Transcript(on_link=lambda _: None)
    view = LedgerView(st, t)
    b = Bridge(view, invalidate=lambda: None, ask_user=lambda spec: Future())
    return st, t, view, b


@pytest.fixture
def app_session(monkeypatch):
    """A Session on a fake config and history, so commands run without touching ~/.reverse-api."""
    from reverse_api import cli
    from reverse_api.repl.app import Session

    config = MagicMock()
    config.get.side_effect = lambda key, default=None: default
    history = MagicMock()
    monkeypatch.setattr(cli, "config_manager", config)
    monkeypatch.setattr(cli, "session_manager", history)
    monkeypatch.setattr(cli, "default_model_for_configured_sdk", lambda sdk: "claude-sonnet-5-5")
    return Session(), history


def pick(st: SessionState, value: str | None) -> None:
    p, st.picker = st.picker, None
    assert p is not None
    p.on_pick(value)


class TestDescribe:
    def test_mcp_prefix_is_dropped(self):
        assert short_name("mcp__chrome-devtools__navigate_page") == "navigate_page"
        assert short_name("Bash") == "Bash"

    def test_browser_and_file_tools(self):
        assert describe("navigate_page", {"url": "https://jobs.ashbyhq.com/openai"})[:3] == ("navigate", "https://jobs.ashbyhq.com/openai", "read")
        assert describe("list_network_requests", {"resourceTypes": ["fetch", "xhr"]})[:2] == ("network", "fetch, xhr")
        assert describe("Write", {"file_path": "/tmp/x/api_client.py"})[:3] == ("write", "api_client.py", "write")
        assert describe("Bash", {"command": "python api_client.py"})[:3] == ("run", "python api_client.py", "run")

    def test_plumbing_tools_are_hidden(self):
        assert describe("ToolSearch", {"query": "select:x"}) is None
        assert describe("AskUserQuestion", {}) is None

    def test_other_sdks_names_read_as_claude_codes(self):
        assert short_name("playwright-ses_43d6fa4a1ffe79iFCdR35sKO3F_browser_navigate") == "browser_navigate"
        assert short_name("chrome-devtools-browser_snapshot") == "browser_snapshot"
        assert describe(short_name("bash"), {"command": "ls"})[:2] == ("run", "ls")
        assert describe(short_name("read"), {"filePath": "/runs/har/x/recording.har"})[:2] == ("read", "recording.har")
        assert describe(short_name("create"), {"path": "/x/api_client.py", "file_text": "x = 1"})[:2] == ("write", "api_client.py")
        assert describe(short_name("glob"), {"globPattern": "**/*.py"})[:2] == ("search", "**/*.py")
        assert describe(short_name("Agent"), {"description": "Extract HAR API endpoints"})[:2] == ("subagent", "Extract HAR API endpoints")
        assert describe("mcp", {"providerIdentifier": "playwright", "toolName": "browser_navigate", "args": {"url": "https://a.dev"}})[:2] == (
            "navigate",
            "https://a.dev",
        )
        patch_text = "*** Begin Patch\n*** Add File: /x/api_client.py\n+a\n*** Update File: /x/README.md\n*** End Patch"
        assert describe("apply_patch", {"patchText": patch_text})[:2] == ("edit", "api_client.py +1")
        for todo_tool in ("TodoWrite", "todowrite", "todo_write", "write_todos", "update_todos", "updateTodos"):
            assert describe(short_name(todo_tool), {"todos": []}) is None, "a todo list shows as the plan"

    def test_playwright_runs_code_under_both_its_names(self):
        for name in ("browser_run_code", "browser_run_code_unsafe"):
            assert describe(name, {"code": "async (page) => page.title()"})[:2] == ("script", "async (page) => page.title()")

    def test_rae_desktop_tools(self):
        assert describe("traffic_overview", {})[:2] == ("overview", "captured traffic")
        assert describe("get_flow", {"id": "eaaa2798-b3f", "part": "both"})[:2] == ("request", "eaaa2798-b3f both")
        assert describe("replay_flow", {"id": "93ee", "url": "http://x/items?page=3", "method": "GET"})[:3] == ("replay", "93ee · method, url", "run")
        assert describe("wait_for_flows", {"after_seq": 284, "timeout_s": 3})[:2] == ("wait", "requests after 284")
        assert describe("browser_scroll", {"direction": "down", "pages": 5})[:2] == ("scroll", "down")

    def test_a_tool_without_wording_shows_its_name_and_main_argument_never_json(self):
        from reverse_api.repl.view import VERB_COL

        assert describe("readLints", {"paths": ["/x/api_client.py"]})[:2] == ("lint", "api_client.py")
        verb, target = describe("get_console_message", {"msgid": 3})[:2]
        assert (verb, target) == ("get", "console message · 3")
        verb, target = describe("someVeryLongToolName", {"options": {"deep": True}})[:2]
        assert len(verb) <= VERB_COL and "{" not in target


class TestLedgerUI:
    def test_a_todo_tool_shows_its_plan_once(self, session):
        st, t, _view, b = session
        ui = LedgerUI(b)
        todos = [{"content": "Find the API", "status": "in_progress", "activeForm": "Finding the API"}]
        ui.tool_start("updateTodos", {"todos": todos})
        ui.todo_updated(todos)  # Cursor reports its todo tool's list again
        text = plain(t)
        assert text.count("Finding the API") == 1 and "updateTodos" not in text and st.step == 0

    def test_steps_receipts_and_code(self, session, tmp_path):
        st, t, _view, b = session
        ui = LedgerUI(b)
        ui.header("abc123", "prompt", model="claude-sonnet-5-5", mode="agent")
        ui.tool_start("mcp__chrome-devtools__navigate_page", {"url": "https://jobs.ashbyhq.com/openai"})
        ui.tool_result("mcp__chrome-devtools__navigate_page", output="Successfully navigated")
        client = tmp_path / "api_client.py"
        ui.tool_start("Write", {"file_path": str(client), "content": "import requests\n\n\ndef get_jobs():\n    return []\n"})
        ui.tool_result("Write", output="File created successfully")
        text = plain(t)
        assert "run abc123 · agent" in text
        assert "01  navigate" in text and "Successfully navigated" in text
        assert "02  write" in text and "def get_jobs" in text
        assert "File created successfully" not in text
        assert st.host == "jobs.ashbyhq.com" and st.client_name == "api_client.py"
        assert st.verb == "writing the client"

    def test_agent_text_is_a_message_and_markup_is_literal(self, session):
        _st, t, view, b = session
        LedgerUI(b).thinking("The board uses /lst/<make>/<model> and [/x] in its URLs.")
        view.flush_live()
        assert "¶" in plain(t) and "/lst/<make>/<model>" in plain(t) and "[/x]" in plain(t)

    def test_success_shows_the_card_once_usage_arrives(self, session, tmp_path):
        st, t, _view, b = session
        ui = LedgerUI(b)
        ui.header("abc123", "prompt", model="claude-sonnet-5-5")
        client = tmp_path / "api_client.py"
        client.write_text("a\nb\nc\n", encoding="utf-8")
        ui.tool_start("mcp__verification__report_client_verified", {"summary": "listed 12 jobs"})
        ui.tool_result("mcp__verification__report_client_verified", output="Recorded")
        ui.success(str(client))
        assert "ready" not in plain(t)
        ui.usage({"input_tokens": 1000, "output_tokens": 200, "estimated_cost_usd": 0.12})
        text = plain(t)
        assert "api_client.py ready" in text and "1.2k tokens · $0.12" in text and "sonnet 5.5" in text
        assert st.cost == pytest.approx(0.12)

    def test_no_card_until_the_agent_verified_the_client(self, session, tmp_path):
        _st, t, _view, b = session
        ui = LedgerUI(b)
        ui.header("abc123", "prompt", model="claude-sonnet-5-5")
        client = tmp_path / "api_client.py"
        client.write_text("print('hi')\n", encoding="utf-8")
        ui.success(str(client))
        ui.usage({"input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.01})
        assert "ready" not in plain(t)
        ui.header("def456", "prompt", model="claude-sonnet-5-5")
        ui.tool_start("mcp__verification__report_client_verified", {"summary": "ok"})
        ui.success(str(tmp_path / "never_written.py"))
        ui.usage({"input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.01})
        assert "ready" not in plain(t), "a client path that does not exist gets no card"

    def test_verified_shows_where_the_files_are(self, session):
        _st, t, _view, b = session
        ui = LedgerUI(b)
        ui.header("abc123", "prompt", model="claude-sonnet-5-5")
        folder, copy = Path("/runs/abc123"), Path("/work/scripts/jobs")
        ui.workspace(folder, copy)
        for _ in range(2):
            ui.tool_start("mcp__verification__report_client_verified", {"summary": "ok"})
            ui.tool_result("mcp__verification__report_client_verified", output="Recorded")
        text = plain(t)
        assert text.count(f"└ in {folder.resolve()}") == 1 and text.count(f"└ copy {copy.resolve()}") == 1

    def test_no_folders_without_a_confirmed_verification(self, session, tmp_path):
        _st, t, _view, b = session
        ui = LedgerUI(b)
        ui.header("abc123", "prompt", model="claude-sonnet-5-5")
        ui.workspace(tmp_path / "runs" / "abc123", None)
        ui.tool_result("mcp__verification__report_client_verified", is_error=True, output="failed")
        assert "└ in" not in plain(t)
        ui.header("def456", "prompt", model="claude-sonnet-5-5")
        ui.tool_result("mcp__verification__report_client_verified", output="Recorded")
        assert "└ in" not in plain(t), "a new run forgets the last run's folder"

    def test_the_status_row_shows_the_run_id(self, session):
        _st, _t, view, b = session
        assert "run " not in "".join(text for _, text in view.status())
        LedgerUI(b).header("abc123", "prompt", model="claude-sonnet-5-5")
        assert "run abc123" in "".join(text for _, text in view.status())

    def test_a_run_id_that_does_not_fit_is_left_out(self, session, monkeypatch):
        from reverse_api.repl import view as view_module

        _st, _t, view, b = session
        LedgerUI(b).header("abc123", "prompt", model="claude-sonnet-5-5")
        monkeypatch.setattr(view_module, "width", lambda: 40)
        assert "run abc123" not in "".join(text for _, text in view.status())

    def test_folded_output_offers_ctrl_o(self, session):
        st, _t, view, b = session
        assert "expand" not in "".join(text for _, text in view.status())
        LedgerUI(b).tool_result("Bash", output="\n".join(f"line {i}" for i in range(10)))
        assert st.folded
        assert "⌃o expand" in "".join(text for _, text in view.status())


class TestFollowUps:
    def test_queued_message_is_delivered_first(self, session):
        st, t, _view, b = session
        st.queue.append("add a department filter")
        assert asyncio.run(b.follow_up()) == "add a department filter"
        assert "add a department filter" in plain(t)
        assert st.running and not st.waiting

    def test_waits_for_the_input_bar_and_none_ends_the_run(self, session):
        st, _t, _view, b = session

        async def scenario():
            waiter = asyncio.ensure_future(b.follow_up())
            while not st.waiting:
                await asyncio.sleep(0.01)
            threading.Thread(target=lambda: b.follow_ups.put("more filters")).start()
            first = await waiter
            waiter = asyncio.ensure_future(b.follow_up())
            while not st.waiting:
                await asyncio.sleep(0.01)
            b.follow_ups.put(None)
            return first, await waiter

        assert asyncio.run(scenario()) == ("more filters", None)
        assert not st.waiting


class TestTranscript:
    def test_writer_turns_prints_into_lines(self):
        seen: list[Raw] = []
        writer = TranscriptWriter(seen.append)
        writer.write("first line\nsecond")
        writer.write(" line\n")
        assert [line for raw in seen for line in raw.text.splitlines()] == ["first line", "second line"]
        assert not writer.isatty()

    def test_ansi_colors_survive(self):
        raw = raw_lines("\x1b[38;2;255;61;139mpink\x1b[0m plain")
        assert "".join(frag[1] for frag in raw.lines[0]) == "pink plain"
        assert "ff3d8b" in raw.lines[0][0][0]

    def test_width_change_rerenders(self, monkeypatch):
        t = Transcript(on_link=lambda _: None)
        t.add("word " * 30)
        monkeypatch.setattr("reverse_api.repl.transcript.width", lambda: 60)
        narrow = len(t.lines())
        monkeypatch.setattr("reverse_api.repl.transcript.width", lambda: 200)
        assert len(t.lines()) < narrow


class TestViewHelpers:
    def test_model_labels_and_default_effort(self):
        assert model_label("claude-sonnet-5-5") == "sonnet 5.5"
        assert model_label("gpt-5") == "gpt-5"
        assert default_effort("claude-opus-5-5") == "medium"
        assert default_effort("claude-haiku-5-5") == "medium"
        assert default_effort("claude-sonnet-5-5") == "high"

    def test_preview_starts_at_the_first_definition(self):
        source = '"""Doc."""\n\nimport requests\n\nURL = "x"\n\n\ndef get():\n    pass\n'
        assert first_definition(source) == 8
        assert first_definition("import os\n\nx = 1\n") == 3


class TestEngineHooks:
    def test_engines_use_the_session_ui_and_its_follow_ups(self, session, tmp_path):
        _st, _t, _view, b = session
        from reverse_api.engineer import ClaudeEngineer

        bridge_mod.activate(b)
        try:
            har = tmp_path / "x.har"
            har.touch()
            with (
                patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
                patch("reverse_api.base_engineer.MessageStore"),
            ):
                eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))
            assert isinstance(eng.ui, LedgerUI)
            b.follow_ups.put("next step")
            assert asyncio.run(eng._prompt_follow_up()) == "next step"
        finally:
            bridge_mod.activate(None)

    def test_classic_ui_without_a_session(self, tmp_path):
        from reverse_api.engineer import ClaudeEngineer
        from reverse_api.tui import ClaudeUI

        har = tmp_path / "x.har"
        har.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))
        assert type(eng.ui) is ClaudeUI

    def test_tool_results_from_user_messages_reach_the_session_ui(self, session, tmp_path):
        from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage

        _st, t, _view, b = session
        from reverse_api.engineer import ClaudeEngineer

        bridge_mod.activate(b)
        try:
            har = tmp_path / "x.har"
            har.touch()
            with (
                patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
                patch("reverse_api.base_engineer.MessageStore"),
            ):
                eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))

            class Client:
                async def receive_response(self):
                    yield AssistantMessage(content=[ToolUseBlock(id="t1", name="Bash", input={"command": "python api_client.py"})], model="m")
                    yield UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="Found 794 open positions", is_error=False)])

            asyncio.run(eng._process_streaming_response(Client()))
        finally:
            bridge_mod.activate(None)
        assert "Found 794 open positions" in plain(t)

    def test_classic_ui_ignores_user_message_results(self, tmp_path):
        from claude_agent_sdk import ToolResultBlock, UserMessage

        from reverse_api.engineer import ClaudeEngineer

        har = tmp_path / "x.har"
        har.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))

        class Client:
            async def receive_response(self):
                yield UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="noise", is_error=False)])

        with patch.object(eng.ui, "tool_result") as tool_result:
            asyncio.run(eng._process_streaming_response(Client()))
        tool_result.assert_not_called()


class TestSmoothStreaming:
    def test_deltas_reveal_gradually_then_settle(self, session):
        _st, t, view, b = session
        ui = LedgerUI(b)
        sentence = "Good, the page is loaded. Now let me check the network requests to capture the API calls."
        for word in sentence.split(" "):
            ui.stream_text(word + " ")
        view.tick()
        partial = plain(t)
        assert "▍" in partial and "calls." not in partial
        ui.thinking(sentence)
        for _ in range(200):
            view.tick()
        settled = plain(t)
        assert "calls." in settled and "▍" not in settled

    def test_items_wait_behind_the_live_message(self, session):
        _st, t, view, b = session
        ui = LedgerUI(b)
        ui.thinking("Now let's test the script.")
        ui.tool_start("Bash", {"command": "python api_client.py"})
        assert "01  run" not in plain(t)
        view.flush_live()
        text = plain(t)
        assert text.index("test the script") < text.index("01  run")

    def test_a_second_message_during_a_reveal_follows_the_first(self, session):
        _st, t, view, b = session
        ui = LedgerUI(b)
        ui.thinking("First, the client works as it is.")
        ui.tool_start("Bash", {"command": "python api_client.py --limit 3"})
        ui.thinking("Second, the limit flag is in.")
        for _ in range(300):
            view.tick()
        text = plain(t)
        assert text.count("First, the client works") == 1 and text.count("Second, the limit flag") == 1
        assert text.index("First") < text.index("01  run") < text.index("Second")

    def test_partial_messages_and_thinking_only_for_the_session(self, session):
        from reverse_api.repl.bridge import stream_options

        _st, _t, _view, b = session
        assert stream_options("claude-sonnet-5-5") == {}
        bridge_mod.activate(b)
        try:
            summarized = {"type": "adaptive", "display": "summarized"}
            assert stream_options("claude-sonnet-5-5") == {"include_partial_messages": True, "thinking": summarized}
            assert stream_options("claude-haiku-4-5") == {"include_partial_messages": True}
            assert stream_options("claude-sonnet-4-5") == {"include_partial_messages": True}
            assert stream_options("claude-opus-4-6")["thinking"] == summarized
            assert stream_options("sonnet") == {"include_partial_messages": True}
        finally:
            bridge_mod.activate(None)

    def test_thinking_streams_in_the_margin_then_settles_folded(self, session):
        st, t, view, b = session
        ui = LedgerUI(b)
        note = "**Planning the capture**\n\nFirst open the board.\nThen watch the requests.\nThen find the jobs endpoint.\nLast, write the client."
        for piece in note.split(" "):
            ui.stream_thinking(piece + " ")
        for _ in range(200):
            view.tick()
        live = plain(t)
        assert "┊" in live and "Planning the capture" not in live, "while streaming the note shows its latest lines"
        assert st.verb == "thinking"
        ui.thinking_note(note)
        ui.stream_text("Opening the board now.")
        view.flush_live()
        text = plain(t)
        assert "Planning the capture" in text and "**" not in text and "+2 lines" in text
        assert text.index("Planning the capture") < text.index("Opening the board now.")
        assert st.folded

    def test_engine_forwards_text_deltas(self, tmp_path):
        from claude_agent_sdk.types import StreamEvent

        from reverse_api.engineer import ClaudeEngineer

        har = tmp_path / "x.har"
        har.touch()
        with (
            patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
            patch("reverse_api.base_engineer.MessageStore"),
        ):
            eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))
        seen: list[str] = []
        eng.ui.stream_text = seen.append  # type: ignore[attr-defined]

        def delta(kind: str, **fields: str) -> StreamEvent:
            return StreamEvent(uuid="u", session_id="s", event={"type": "content_block_delta", "delta": {"type": kind, **fields}})

        class Client:
            async def receive_response(self):
                yield delta("text_delta", text="Hel")
                yield delta("text_delta", text="lo")
                yield delta("input_json_delta", partial_json="{")

        asyncio.run(eng._process_streaming_response(Client()))
        assert seen == ["Hel", "lo"]

    def test_engine_forwards_thinking(self, tmp_path):
        from claude_agent_sdk import AssistantMessage, ThinkingBlock
        from claude_agent_sdk.types import StreamEvent

        from reverse_api.engineer import ClaudeEngineer

        har = tmp_path / "x.har"
        har.touch()
        with (
            patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
            patch("reverse_api.base_engineer.MessageStore"),
        ):
            eng = ClaudeEngineer(run_id="r1", har_path=har, prompt="p", output_dir=str(tmp_path))
        deltas: list[str] = []
        notes: list[str] = []
        eng.ui.stream_thinking = deltas.append  # type: ignore[attr-defined]
        eng.ui.thinking_note = notes.append  # type: ignore[attr-defined]

        class Client:
            async def receive_response(self):
                delta = {"type": "thinking_delta", "thinking": "Plan"}
                yield StreamEvent(uuid="u", session_id="s", event={"type": "content_block_delta", "delta": delta})
                yield AssistantMessage(content=[ThinkingBlock(thinking="Plan it", signature="sig")], model="claude-sonnet-5-5")

        asyncio.run(eng._process_streaming_response(Client()))
        assert deltas == ["Plan"] and notes == ["Plan it"]


class TestTerminalSafe:
    def test_flags_and_joiners_are_dropped(self):
        assert terminal_safe("🇨🇭 Switzerland · 🇩🇪 Germany") == "Switzerland · Germany"
        assert terminal_safe("ok ✔\ufe0f done 👍🏽") == "ok ✔ done 👍"
        assert terminal_safe("plain text, café") == "plain text, café"

    def test_agent_messages_and_receipts_are_cleaned(self, session):
        _st, t, view, b = session
        ui = LedgerUI(b)
        ui.tool_start("Bash", {"command": "python api_client.py"})
        ui.tool_result("Bash", output="🇨🇭 Zürich: 12 jobs")
        ui.thinking("Found jobs in 🇨🇭 and 🇩🇪.")
        view.flush_live()
        assert "\U0001f1e8" not in plain(t) and "Zürich: 12 jobs" in plain(t)


class TestCommands:
    def test_commands_are_echoed(self, app_session):
        session, _history = app_session
        session.run_command("/help")
        assert "› /help" in plain(session.transcript)

    def test_quit_and_commands_are_aliases(self, app_session, monkeypatch):
        session, _history = app_session
        quits = []
        monkeypatch.setattr(session, "quit", lambda: quits.append(True))
        session.run_command("/quit")
        assert quits == [True]
        session.run_command("/commands")
        assert "› /help" in plain(session.transcript) and "unknown command" not in plain(session.transcript)

    def test_help_says_what_rae_does_and_lists_modes_commands_and_keys(self, app_session):
        from reverse_api.repl.app import COMMANDS, KEYS, MODES

        session, _history = app_session
        session.run_command("/help")
        text = plain(session.transcript)
        assert "turns a website into an API client" in text and "reverseapi.dev/docs" in text
        for name in [*MODES, *COMMANDS, *(key for key, _ in KEYS)]:
            assert name in text, name
        assert "/messages" not in text

    def test_messages_is_gone(self, app_session):
        session, _history = app_session
        session.run_command("/messages abc123")
        assert "unknown command /messages" in plain(session.transcript)
        session.buf.text = "/me"
        assert session.palette_items() == []

    def test_lists_go_around_from_either_end(self, app_session):
        from reverse_api.repl.app import around

        session, _history = app_session
        session.open_picker("choose a mode", [("a", "a", ""), ("b", "b", ""), ("c", "c", "")], "c", lambda value: None)
        session.move_in_picker(1)
        assert session.st.picker.index == 0
        session.move_in_picker(-1)
        assert session.st.picker.index == 2
        assert around(-1, 4) == 3 and around(4, 4) == 0 and around(3, 0) == 0

    def test_a_blank_line_parts_the_conversation_from_the_bar(self, app_session):
        session, _history = app_session
        def last_rows() -> list[str]:
            shown = "".join(text for _, text, *_ in session.transcript_view(MagicMock(render_info=None)))
            return [row.rstrip() for row in shown.split("\n")][-3:]

        session.view.notice("the last line")
        assert last_rows()[1:] == ["   the last line", ""]
        session.view.out("")
        assert last_rows() == ["", "   the last line", ""], "a line already blank is not doubled"

    def test_the_menu_finds_commands_by_alias(self, app_session):
        session, _history = app_session
        session.buf.text = "/qu"
        assert [c for c, _ in session.palette_items()] == ["/exit"]
        session.buf.text = "/c"
        assert {c for c, _ in session.palette_items()} == {"/clear", "/help"}

    def test_an_exact_command_wins_over_longer_ones(self, app_session):
        session, _history = app_session
        session.buf.text = "/mode"
        assert session.palette_items()[0][0] == "/mode"
        assert {c for c, _ in session.palette_items()} == {"/mode", "/model"}

    def test_pickers_echo_once_something_is_picked(self, app_session):
        session, history = app_session
        session.run_command("/model")
        assert "/model" not in plain(session.transcript)
        history.get_history.return_value = [{"run_id": "abc123", "prompt": "p", "timestamp": "2026-10-25T15:47:18"}]
        history.get_run.return_value = history.get_history.return_value[0]
        session.run_command("/history")
        assert "/history" not in plain(session.transcript)
        pick(session.st, "abc123")
        assert "› /history abc123" in plain(session.transcript)

    def test_clear_forgets_the_run_id(self, app_session):
        session, _history = app_session
        session.st.run_id = "abc123"
        session.run_command("/clear")
        assert session.st.run_id is None

    def test_clear_starts_over_with_no_usage(self, app_session):
        session, _history = app_session
        st = session.st
        session.view.user("all jobs on example.com")
        st.cost, st.tokens, st.step, st.folded, st.last_client = 1.25, 9000, 4, True, Path("api_client.py")
        session.run_command("/clear")
        assert session.transcript.items == []
        assert (st.cost, st.tokens, st.step, st.folded, st.last_client) == (0.0, 0, 0, False, None)
        assert "$" not in "".join(text for _, text in session.view.status())

    def test_clear_ends_a_waiting_run_and_waits_for_a_running_one(self, app_session):
        session, _history = app_session
        st = session.st
        st.waiting = True
        session.run_command("/clear")
        assert session.bridge.follow_ups.get_nowait() is None
        st.waiting, st.running = False, True
        session.view.user("keep me")
        session.run_command("/clear")
        assert "keep me" in plain(session.transcript) and "a run is in progress" in plain(session.transcript)

    def test_history_shows_a_run_and_offers_actions(self, app_session, tmp_path):
        session, history = app_session
        client = tmp_path / "api_client.py"
        client.write_text("x = 1\n", encoding="utf-8")
        run = {
            "run_id": "abc123def456",
            "prompt": "all open jobs on jobs.ashbyhq.com/openai",
            "timestamp": "2026-10-25T15:47:18.5",
            "model": "claude-sonnet-5-5",
            "mode": "chrome-mcp",
            "usage": {"estimated_cost_usd": 0.42, "input_tokens": 9000, "output_tokens": 1000},
            "paths": {"script_path": str(client)},
        }
        history.get_history.return_value = [run]
        history.get_run.return_value = run
        session.run_command("/history")
        assert session.st.picker is not None and session.st.picker.items[0][0] == "abc123def456"
        pick(session.st, "abc123def456")
        text = plain(session.transcript)
        assert "› /history" in text and "abc123def456" in text and "sonnet 5.5" in text
        assert "$0.42 · 10.0k tokens · api_client.py" in text
        assert [value for value, _, _ in session.st.picker.items] == ["engineer", ""]

    def test_history_with_no_runs(self, app_session):
        session, history = app_session
        history.get_history.return_value = []
        session.run_command("/history")
        assert session.st.picker is None and "no runs yet" in plain(session.transcript)

    def test_a_resumed_run_shows_the_agents_messages_whole(self, app_session):
        session, history = app_session
        history.get_run.return_value = {"run_id": "abc123", "prompt": "all jobs", "sdk_session": {"id": "s", "mode": "agent"}}
        long_message = "The jobs come from a **GraphQL** call. " + "Each page holds twenty jobs and a cursor. " * 8 + "The end."
        log = [
            {"type": "prompt", "content": "all jobs", "timestamp": "2026-10-25T15:47:18"},
            {
                "type": "tool_start",
                "content": {"name": "mcp__chrome-devtools__navigate_page", "input": {"url": "https://example.com"}},
                "timestamp": "2026-10-25T15:47:20",
            },
            {"type": "tool_result", "content": {"name": "Bash", "is_error": True, "output": "Traceback"}, "timestamp": "2026-10-25T15:47:21"},
            {"type": "thinking", "content": long_message, "timestamp": "2026-10-25T15:47:22"},
        ]
        with patch("reverse_api.repl.app.MessageStore") as store, patch.object(session, "work"):
            store.return_value.load.return_value = log
            session.run_command("/resume abc123")
        text = plain(session.transcript)
        assert "› all jobs" in text and "01  navigate  https://example.com" in text and "Traceback" in text
        assert "GraphQL" in text and "**" not in text and "The end." in text, "the agent's message is shown whole"
        assert "+" not in text.split("The end.")[1], "nothing is folded away"

    def test_an_older_log_without_tool_results_still_ends_on_its_client_card(self, app_session, tmp_path):
        session, history = app_session
        client = tmp_path / "api_client.py"
        client.write_text("import requests\n")
        history.get_run.return_value = {
            "run_id": "a1",
            "prompt": "quotes",
            "usage": {"estimated_cost_usd": 0.23},
            "sdk_session": {"id": "s", "mode": "agent"},
        }
        verify = {"name": "mcp__verification__report_client_verified", "input": {"summary": "ok"}}
        log = [
            {"type": "prompt", "content": "quotes", "timestamp": "2026-11-01T19:14:19"},
            {"type": "tool_start", "content": verify, "timestamp": "2026-11-01T19:17:20"},
            {"type": "result", "content": {"script_path": str(client)}, "timestamp": "2026-11-01T19:17:26"},
        ]
        with patch("reverse_api.repl.app.MessageStore") as store, patch.object(session, "work"):
            store.return_value.load.return_value = log
            session.run_command("/resume a1")
        assert "api_client.py ready" in plain(session.transcript)
        assert not session.bridge.verified

    def test_classic_screens_wait_for_a_running_agent(self, app_session):
        session, _history = app_session
        session.app = MagicMock()
        session.st.running = True
        session.classic(lambda: None)
        session.app.exit.assert_not_called()
        assert session.take_classic_job() is None


class FakeConfig:
    """A config_manager over a dict, so settings can be changed and read back."""

    def __init__(self, **values: Any) -> None:
        from reverse_api.config import DEFAULT_CONFIG

        self.config = {**DEFAULT_CONFIG, **values}

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value

    def update(self, values: dict[str, Any]) -> None:
        self.config.update(values)

    def load(self) -> None:
        pass


@pytest.fixture
def settings_session(monkeypatch):
    from reverse_api import cli
    from reverse_api.repl.app import Session

    config = FakeConfig(sdk="claude", claude_code_model="claude-sonnet-5-5")
    monkeypatch.setattr(cli, "config_manager", config)
    monkeypatch.setattr(cli, "session_manager", MagicMock())
    session = Session()
    session.app = MagicMock()
    monkeypatch.setattr(session, "call_soon", lambda fn: fn())
    return session, config


class TestSettings:
    def test_settings_open_in_the_session_with_each_value(self, settings_session):
        session, _config = settings_session
        session.run_command("/settings")
        p = session.st.picker
        assert p is not None and p.title.startswith("settings")
        assert ("sdk", "sdk", "claude") in p.items and ("real_time_sync", "real-time sync", "on") in p.items
        assert ("claude_code_model", "claude model", "sonnet 5.5") in p.items
        session.app.exit.assert_not_called()  # the session stays on screen

    def test_a_choice_changes_in_place_and_comes_back_to_the_list(self, settings_session):
        session, config = settings_session
        session.run_command("/settings")
        pick(session.st, "sdk")
        assert [v for v, _, _ in session.st.picker.items] == ["claude", "copilot", "cursor", "opencode"]
        pick(session.st, "opencode")
        assert config.get("sdk") == "opencode" and session.st.sdk == "opencode"
        assert "◇ sdk  claude → opencode" in plain(session.transcript)
        p = session.st.picker
        assert p.title.startswith("settings") and p.items[p.index][0] == "sdk"

    def test_a_toggle_flips_at_once(self, settings_session):
        session, config = settings_session
        session.run_command("/settings")
        pick(session.st, "real_time_sync")
        assert config.get("real_time_sync") is False and "real-time sync  on → off" in plain(session.transcript)
        assert session.st.picker.title.startswith("settings")

    def test_enter_on_an_empty_bar_keeps_a_custom_model(self, settings_session):
        session, config = settings_session
        config.set("cursor_model", "my-cursor-model")
        session.run_command("/settings")
        pick(session.st, "cursor_model")
        p = session.st.picker
        assert p.items[p.index][0] == "my-cursor-model"
        session.choose()
        assert config.get("cursor_model") == "my-cursor-model"

    def test_typing_a_filter_highlights_the_first_match(self, settings_session):
        session, _config = settings_session
        session.run_command("/settings")
        session.st.picker.index = 3
        session.buf.text = "out"
        p = session.st.picker
        assert session.picker_items(p)[p.index][0] == "output_language"

    def test_a_typed_value_is_saved(self, settings_session):
        session, config = settings_session
        session.run_command("/settings")
        pick(session.st, "copilot_model")
        assert session.st.picker.typed and session.st.picker.hint
        session.buf.text = "gpt-4.1-mini"
        session.choose()
        assert config.get("copilot_model") == "gpt-4.1-mini" and session.buf.text == ""

    def test_the_default_output_directory_is_none(self, settings_session):
        session, config = settings_session
        config.set("output_dir", "/data/rae")
        session.run_command("/settings")
        pick(session.st, "output_dir")
        pick(session.st, "")
        assert config.get("output_dir") is None

    def test_esc_in_a_choice_goes_back_to_the_list(self, settings_session):
        session, config = settings_session
        session.run_command("/settings")
        pick(session.st, "output_language")
        pick(session.st, None)
        assert config.get("output_language") == "python" and session.st.picker.title.startswith("settings")

    def test_opencode_models_come_from_its_server_and_can_be_searched(self, settings_session, monkeypatch):
        from reverse_api import cli
        from reverse_api.repl import app

        session, config = settings_session

        class Inline:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        catalog = {
            "default": {"google": "gemini-3-flash"},
            "providers": [
                {"id": "opencode", "name": "OpenCode Zen", "models": {"big-pickle": {"status": "active", "capabilities": {"toolcall": True}}}},
                {
                    "id": "google",
                    "name": "Google",
                    "models": {
                        "gemini-3-flash": {"status": "active", "capabilities": {"toolcall": True}},
                        "gemini-3-pro": {"status": "active", "capabilities": {"toolcall": True}},
                    },
                },
            ],
        }
        monkeypatch.setattr(app.threading, "Thread", Inline)
        monkeypatch.setattr(cli, "_load_opencode_catalog_for_settings", AsyncMock(return_value=catalog))
        session.run_command("/settings")
        pick(session.st, "opencode")
        p = session.st.picker
        assert p.search and [v for v, _, _ in p.items] == ["opencode", "google", "ollama"]
        session.buf.text = "goo"
        assert [v for v, _, _ in session.picker_items(p)] == ["google"]
        session.choose()
        assert session.buf.text == "" and [v for v, _, _ in session.st.picker.items] == ["gemini-3-flash", "gemini-3-pro"]
        pick(session.st, "gemini-3-pro")
        assert (config.get("opencode_provider"), config.get("opencode_model")) == ("google", "gemini-3-pro")
        assert "opencode provider / model  opencode / big-pickle → google / gemini-3-pro" in plain(session.transcript)
        assert session.st.picker.title.startswith("settings")

    def test_typing_while_opencode_loads_is_no_prompt_and_esc_gives_up_on_it(self, settings_session, monkeypatch):
        from reverse_api import cli
        from reverse_api.repl import app

        session, _config = settings_session
        loads = []

        class Later:
            def __init__(self, target, **kwargs):
                loads.append(target)

            def start(self):
                pass

        monkeypatch.setattr(app.threading, "Thread", Later)
        monkeypatch.setattr(cli, "_load_opencode_catalog_for_settings", AsyncMock(return_value={"providers": []}))
        session.run_command("/settings")
        pick(session.st, "opencode")
        loading = session.st.picker
        assert loading.items == [("", "loading…", "")]
        session.buf.text = "open"
        session.choose()
        assert session.st.picker is loading and not session.st.running
        pick(session.st, None)
        loads[0]()  # the catalog arrives after esc
        assert session.st.picker.title.startswith("settings")

    @pytest.fixture
    def inline_threads(self, monkeypatch):
        from reverse_api.repl import app

        class Inline:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(app.threading, "Thread", Inline)

    def test_a_password_protected_opencode_says_which_variable_to_set(self, settings_session, inline_threads, monkeypatch):
        import httpx2 as httpx

        from reverse_api import cli

        session, _config = settings_session
        request = httpx.Request("GET", "http://127.0.0.1:4096/config/providers")
        denied = httpx.HTTPStatusError("unauthorized", request=request, response=httpx.Response(401, request=request))
        monkeypatch.setattr(cli, "_load_opencode_catalog_for_settings", AsyncMock(side_effect=denied))
        session.run_command("/settings")
        pick(session.st, "opencode")
        assert "OPENCODE_SERVER_PASSWORD" in plain(session.transcript)
        assert session.st.picker.title.startswith("settings")

    def test_ollama_lists_the_installed_models_that_fit(self, settings_session, inline_threads, monkeypatch):
        from reverse_api import cli
        from reverse_api.ollama_runtime import OllamaModel, OllamaStatus

        session, config = settings_session
        model = OllamaModel(name="qwen3:8b", size=5_000_000_000, capabilities=("completion", "tools"), context_length=131_072, parameter_size="8B")
        monkeypatch.setattr(cli, "_load_opencode_catalog_for_settings", AsyncMock(return_value={"providers": []}))
        monkeypatch.setattr("reverse_api.ollama_runtime.ensure_ollama_models", AsyncMock(return_value=OllamaStatus(base_url="", models=(model,))))
        session.run_command("/settings")
        pick(session.st, "opencode")
        pick(session.st, "ollama")
        assert session.st.picker.items == [("qwen3:8b", "qwen3:8b", "8B · 128k context")]
        pick(session.st, "qwen3:8b")
        assert (config.get("opencode_provider"), config.get("opencode_model")) == ("ollama", "qwen3:8b")

    def test_a_failing_classic_screen_reports_and_returns(self, app_session):
        session, _history = app_session

        def broken() -> None:
            raise RuntimeError("questionary blew up")

        session.classic(broken, pause=False)
        job = session.take_classic_job()
        assert job is not None
        job()
        assert "questionary blew up" in plain(session.transcript)


def test_card_path_is_a_link(session, tmp_path):
    _st, t, view, _b = session
    client = tmp_path / "api_client.py"
    view.card(Path(client), 3, "python")
    handlers = [frag for line in t.lines() for frag in line if len(frag) == 3]
    assert handlers, "the client name in the card should be clickable"


def test_a_long_step_stays_on_one_line_at_any_width(session, monkeypatch):
    from reverse_api.repl import transcript, view

    _st, t, _view, b = session
    for cols in (60, 80, 140):
        monkeypatch.setattr(view, "width", lambda cols=cols: cols)
        monkeypatch.setattr(transcript, "width", lambda cols=cols: cols, raising=False)
        t.clear()
        LedgerUI(b).tool_start("Bash", {"command": "python /var/folders/bp/4wpy6h8d7s9f9btrd1sbplx40000gn/T/tmp1w10rt4r/api_client.py --limit 5"})
        lines = [line for line in plain(t).splitlines() if line.strip()]
        assert len(lines) == 1 and len(lines[0]) <= cols, (cols, lines)


def test_long_errors_notices_and_prompts_wrap_under_their_own_text(session, monkeypatch):
    from reverse_api.repl import transcript, view

    _st, t, ledger, _b = session
    monkeypatch.setattr(view, "width", lambda: 60)
    monkeypatch.setattr(transcript, "width", lambda: 60, raising=False)
    words = "Claude Code no longer has this run's conversation on this machine · start a new run"
    for show, indent in ((ledger.error, 5), (ledger.notice, 3), (ledger.user, 3)):
        t.clear()
        show(words)
        lines = [line for line in plain(t).splitlines() if line.strip()]
        assert len(lines) > 1 and all(line.startswith(" " * indent) for line in lines[1:]), lines


class Loop:
    """Runs call_soon_threadsafe callbacks at once, standing in for the app's loop."""

    def call_soon_threadsafe(self, fn):
        fn()


class TestRunLifecycle:
    def test_ending_a_waiting_run_stays_busy_until_it_wraps_up(self, app_session):
        session, _history = app_session
        session.loop = Loop()
        st = session.st
        st.waiting = True
        session.run_command("/new")
        assert session.bridge.follow_ups.get_nowait() is None
        assert st.running and not st.waiting and st.verb == "wrapping up"
        with patch.object(session, "start") as start:
            session.submit("the next capture")
            assert st.queue == ["the next capture"] and not start.called
            session.finish({"script_path": "x"})
        start.assert_called_once_with("the next capture")
        assert not st.running

    def test_a_cut_stream_settles_when_the_run_ends(self, app_session):
        session, _history = app_session
        ui = session.bridge.ui()
        ui.stream_text("Looking at the network ")
        session.view.error("connection lost")
        assert "connection lost" not in plain(session.transcript)
        session.finish(None)
        text = plain(session.transcript)
        assert "Looking at the network" in text and "connection lost" in text

    def test_a_stopped_run_takes_its_question_with_it(self, app_session):
        session, _history = app_session
        session.loop = Loop()
        st = session.st
        typed = session.ask_user({"question": "Which board?", "options": []})
        assert st.question is typed
        typed.cancel()
        session.ask_user({"question": "Which region?", "options": [("EU", "")]})
        assert st.picker is not None and st.picker.question
        session.finish(None)
        assert st.question is None and st.picker is None
        with patch.object(session, "start") as start:
            session.submit("all jobs on example.com")
        start.assert_called_once_with("all jobs on example.com")

    def test_typing_while_the_options_show_answers_in_ones_own_words(self, app_session):
        session, _history = app_session
        session.loop = Loop()
        fut = session.ask_user({"question": "Which board?", "options": [("openai", ""), ("anthropic", "")]})
        session.buf.text = "ramp"
        session.choose()
        assert fut.result() == "ramp" and session.buf.text == "" and session.st.picker is None
        fut = session.ask_user({"question": "Which board?", "options": [("openai", ""), ("anthropic", "")]})
        session.st.picker.index = 1
        session.choose()
        assert fut.result() == "anthropic"

    def test_a_question_stopped_before_it_shows_stays_away(self, app_session):
        session, _history = app_session
        shown = []
        session.loop = type("Later", (), {"call_soon_threadsafe": lambda self, fn: shown.append(fn)})()
        fut = session.ask_user({"question": "Which board?", "options": []})
        fut.cancel()
        shown[0]()
        assert session.st.question is None

    def test_relative_tool_paths_render_without_a_link(self, session):
        _st, t, _view, b = session
        LedgerUI(b).tool_start("Read", {"file_path": "api_client.py"})
        assert "read" in plain(t) and "api_client.py" in plain(t)

    def test_windows_file_links_become_drive_and_unc_paths(self, monkeypatch):
        import nturl2path

        from reverse_api.repl import app

        monkeypatch.setattr(app.sys, "platform", "win32")
        monkeypatch.setattr(app, "url2pathname", nturl2path.url2pathname)
        assert app.file_path("file:///C:/Users/test/api_client.py") == "C:\\Users\\test\\api_client.py"
        assert app.file_path("file://server/share/api_client.py") == "\\\\server\\share\\api_client.py"
        opened: list[str] = []
        monkeypatch.setattr(app.os, "startfile", opened.append, raising=False)
        app.open_target("file:///C:/Users/test/api_client.py")
        assert opened == ["C:\\Users\\test\\api_client.py"]


class TestResume:
    def _auto(self, tmp_path):
        from reverse_api.auto_engineer import ClaudeAutoEngineer

        with (
            patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"),
            patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
            patch("reverse_api.base_engineer.MessageStore"),
        ):
            return ClaudeAutoEngineer(run_id="r1", prompt="jobs", model="claude-sonnet-5-5", output_dir=str(tmp_path))

    @staticmethod
    def _result(session: str, cost: float):
        from claude_agent_sdk import ResultMessage

        return ResultMessage(
            subtype="success",
            duration_ms=0,
            duration_api_ms=0,
            is_error=False,
            num_turns=1,
            session_id=session,
            total_cost_usd=cost,
            usage={"input_tokens": 10, "output_tokens": 2},
        )

    def test_the_engine_reports_its_session_once(self, tmp_path):
        from claude_agent_sdk import SystemMessage

        eng = self._auto(tmp_path)
        seen: list[str] = []
        eng.on_session = seen.append
        result = self._result("s-1", 0.4)

        class Client:
            async def receive_response(self):
                yield SystemMessage(subtype="init", data={"session_id": "s-1"})
                yield result

        out = asyncio.run(eng._process_streaming_response(Client()))
        assert seen == ["s-1"] and eng.sdk_session_id == "s-1"
        assert out is not None and out["usage"]["estimated_cost_usd"] == pytest.approx(0.4)

    def test_a_resumed_run_reopens_the_session_and_starts_from_the_next_message(self, tmp_path):
        eng = self._auto(tmp_path)
        eng.resume_session, eng.cost_before = "s-1", 1.0
        replies = iter(["now add pagination", None])
        eng._prompt_follow_up = AsyncMock(side_effect=lambda: next(replies))  # type: ignore[method-assign]
        queries: list[str] = []
        result = self._result("s-1", 1.25)

        class Client:
            def __init__(self, options):
                self.options = options

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def query(self, text):
                queries.append(text)

            async def receive_response(self):
                yield result

        made: list[Client] = []

        def make(options):
            made.append(Client(options))
            return made[-1]

        with patch("reverse_api.auto_engineer.ClaudeSDKClient", side_effect=make):
            out = asyncio.run(eng.analyze_and_generate())
        assert made[0].options.resume == "s-1"
        assert queries == ["now add pagination"], "the run's brief is not sent again"
        assert out is not None and out["usage"]["estimated_cost_usd"] == pytest.approx(0.25), "only this stretch's cost"

    def test_ending_a_resumed_run_before_a_message_is_not_an_error(self, tmp_path):
        eng = self._auto(tmp_path)
        eng.resume_session = "s-1"
        eng._prompt_follow_up = AsyncMock(return_value=None)  # type: ignore[method-assign]
        client = MagicMock()
        client.return_value.__aenter__ = AsyncMock(return_value=client.return_value)
        client.return_value.__aexit__ = AsyncMock(return_value=False)
        client.return_value.query = AsyncMock()
        with patch("reverse_api.auto_engineer.ClaudeSDKClient", client):
            assert asyncio.run(eng.analyze_and_generate()) == {}
        client.return_value.query.assert_not_called()

    def test_resume_run_picks_the_engine_from_the_saved_session(self, monkeypatch):
        from reverse_api import cli

        agent = {
            "run_id": "a1",
            "prompt": "jobs",
            "mode": "chrome-mcp",
            "model": "claude-sonnet-4-6",
            "sdk_session": {"id": "s-a", "mode": "agent", "model": "claude-opus-5-5", "output_dir": "/custom"},
        }
        engineer_run = {
            "run_id": "e1",
            "prompt": "cars",
            "mode": "manual",
            "model": None,
            "sdk_session": {"id": "s-e", "mode": "engineer", "output_dir": "/runs", "output_mode": "docs"},
        }
        runs = {"a1": agent, "e1": engineer_run, "old": {"run_id": "old", "prompt": "x", "mode": "auto"}}
        history = MagicMock()
        history.get_run.side_effect = runs.get
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: default
        monkeypatch.setattr(cli, "session_manager", history)
        monkeypatch.setattr(cli, "config_manager", config)
        with patch.object(cli, "run_auto_capture") as auto, patch.object(cli, "run_engineer") as engineer:
            cli.resume_run("a1")
            cli.resume_run("e1")
            assert cli.resume_run("old") is None
        auto.assert_called_once_with(
            prompt="jobs", url=None, model="claude-opus-5-5", output_dir="/custom", agent_provider="chrome-mcp", headless=False, resume=agent
        )
        engineer.assert_called_once_with("e1", model=None, output_dir="/runs", output_mode="docs", resume=engineer_run)

    def test_run_totals_add_up_across_a_resume(self):
        from reverse_api.cli import _run_totals

        before = {"input_tokens": 100, "output_tokens": 10, "estimated_cost_usd": 1.0, "service_tier": "standard"}
        now = {"input_tokens": 50, "output_tokens": 5, "estimated_cost_usd": 0.25}
        totals = {"input_tokens": 150, "output_tokens": 15, "estimated_cost_usd": 1.25, "service_tier": "standard"}
        assert _run_totals(before, now) == totals

    def test_resume_lists_only_runs_with_a_session_and_reopens_the_pick(self, app_session):
        session, history = app_session
        run = {"run_id": "a1", "prompt": "jobs on example.com", "timestamp": "2026-10-25T16:00:00", "sdk_session": {"id": "s", "mode": "agent"}}
        history.history = [run, {"run_id": "old", "prompt": "x", "timestamp": "2026-10-24T10:00:00"}]
        history.get_history.side_effect = lambda limit=10: history.history[:limit]
        history.get_run.side_effect = {"a1": run}.get
        session.run_command("/resume")
        assert [v for v, _, _ in session.st.picker.items] == ["a1"]
        with patch.object(session, "work") as work:
            pick(session.st, "a1")
        work.assert_called_once()
        assert session.st.running and session.st.verb == "reopening"
        assert "› /resume a1" in plain(session.transcript)

    def test_history_offers_resume_only_when_the_run_has_a_session(self, app_session):
        session, history = app_session
        run = {"run_id": "a1", "prompt": "jobs", "timestamp": "2026-10-25T16:00:00", "sdk_session": {"id": "s", "mode": "agent"}}
        history.get_run.return_value = run
        session.show_run("a1")
        assert session.st.picker.items[0][0] == "resume"
        run.pop("sdk_session")
        session.st.picker = None
        session.show_run("a1")
        assert "resume" not in [v for v, _, _ in session.st.picker.items]

    def test_a_resumed_run_replays_its_conversation(self, app_session, tmp_path):
        session, history = app_session
        client = tmp_path / "api_client.py"
        client.write_text("import requests\n\n\nclass Quotes:\n    pass\n")
        history.get_run.return_value = {
            "run_id": "a1",
            "prompt": "quotes",
            "model": "claude-haiku-4-5",
            "sdk": "claude",
            "usage": {"input_tokens": 8000, "output_tokens": 400, "cache_read_input_tokens": 10000, "estimated_cost_usd": 0.23},
            "paths": {"script_path": str(client)},
            "sdk_session": {"id": "s", "mode": "agent", "effort": "xhigh"},
        }
        verify = "mcp__verification__report_client_verified"
        log = [
            {"type": "prompt", "content": "brief <mission>all quotes on quotes.toscrape.com</mission>", "timestamp": "2026-11-01T19:14:19"},
            {
                "type": "tool_start",
                "content": {"name": "mcp__chrome-devtools__navigate_page", "input": {"url": "https://quotes.toscrape.com/scroll"}},
                "timestamp": "2026-11-01T19:14:25",
            },
            {"type": "thinking", "content": "The quotes come from **GET /api/quotes**.", "timestamp": "2026-11-01T19:16:36"},
            {"type": "tool_start", "content": {"name": verify, "input": {"summary": "fetched 10 quotes"}}, "timestamp": "2026-11-01T19:17:20"},
            {"type": "tool_result", "content": {"name": verify, "is_error": False, "output": "recorded"}, "timestamp": "2026-11-01T19:17:20"},
            {"type": "result", "content": {"script_path": str(client)}, "timestamp": "2026-11-01T19:17:26"},
        ]
        with patch("reverse_api.repl.app.MessageStore") as store, patch.object(session, "work") as work:
            store.return_value.load.return_value = log
            session.run_command("/resume a1")
        text = plain(session.transcript)
        assert "› all quotes on quotes.toscrape.com" in text and "brief" not in text
        assert "navigate" in text and "quotes.toscrape.com/scroll" in text and "GET /api/quotes" in text
        assert "api_client.py ready" in text and "$0.23" in text and "haiku 4.5" in text and "3m07s" in text
        assert "18.4k tokens" in text, "cache tokens count, as on the live card"
        assert "effort xhigh" in text, "the effort the run thought at"
        # The replay draws the past run's numbers without making them this session's.
        assert session.st.cost == 0 and session.st.step == 0 and not session.bridge.verified
        assert session.st.running and session.st.verb == "reopening"
        work.assert_called_once()

    def test_a_runs_duration_leaves_out_the_days_it_was_set_aside(self):
        from reverse_api.repl.app import run_duration

        stamps = ["2026-11-01T19:14:19", "2026-11-01T19:16:19", "2026-11-04T10:00:00", "2026-11-04T10:01:00"]
        assert run_duration([{"timestamp": s} for s in stamps]) == 180
        assert run_duration([{"timestamp": "bad"}]) == 0

    def test_a_runs_messages_are_read_from_its_own_folder(self, app_session):
        from reverse_api.repl.app import run_output_dir

        assert run_output_dir({"sdk_session": {"output_dir": "/data/rae"}, "paths": {"har_dir": "/other/har/a1"}}) == "/data/rae"
        assert run_output_dir({"paths": {"har_dir": "/data/rae/har/a1"}}) == str(Path("/data/rae"))
        assert run_output_dir({"run_id": "a1"}) is None and run_output_dir(None) is None

        session, history = app_session
        history.get_run.return_value = {"run_id": "a1", "prompt": "jobs", "sdk_session": {"id": "s", "mode": "agent", "output_dir": "/data/rae"}}
        with patch("reverse_api.repl.app.MessageStore") as store, patch.object(session, "work"):
            store.return_value.load.return_value = []
            session.run_command("/resume a1")
        assert store.call_args_list == [call("a1", "/data/rae")]

    def test_an_opencode_resume_replays_in_the_plain_terminal_before_its_prompt(self, app_session):
        import io

        from rich.console import Console

        session, history = app_session
        history.get_run.return_value = {"run_id": "a1", "prompt": "jobs", "sdk_session": {"id": "s", "mode": "agent", "sdk": "opencode"}}
        log = [{"type": "thinking", "content": "the jobs come from GraphQL", "timestamp": "2026-10-25T15:47:00"}]
        with patch("reverse_api.repl.app.MessageStore") as store, patch.object(session, "classic") as classic:
            store.return_value.load.return_value = log
            session.run_command("/resume a1")
        buf = io.StringIO()
        with patch.object(session.cli, "console", Console(file=buf, width=120)), patch.object(session.cli, "resume_run") as resume_run:
            classic.call_args.args[0]()
        assert "GraphQL" in buf.getvalue()
        resume_run.assert_called_once_with("a1")

    def test_resume_switches_from_a_conversation_that_waits(self, app_session):
        session, history = app_session
        history.get_run.return_value = {"run_id": "a1", "prompt": "jobs", "sdk_session": {"id": "s", "mode": "agent"}}
        session.st.waiting = True
        with (
            patch("reverse_api.repl.app.MessageStore") as store,
            patch.object(session, "work") as work,
            patch.object(session, "call_soon", side_effect=lambda fn: fn()),
        ):
            store.return_value.load.return_value = []
            session.run_command("/resume a1")
            assert session.bridge.follow_ups.get_nowait() is None and session.st.verb == "wrapping up"
            work.assert_not_called()
            session.finish({})  # the open conversation has wrapped up
        work.assert_called_once()
        assert "a run is open" not in plain(session.transcript)

    def test_resume_waits_for_a_run_in_progress(self, app_session):
        session, history = app_session
        history.get_run.return_value = {"run_id": "a1", "prompt": "jobs", "sdk_session": {"id": "s", "mode": "agent"}}
        session.st.running = True
        with patch.object(session, "work") as work:
            session.run_command("/resume a1")
        work.assert_not_called()
        assert session.after_run is None and "a run is in progress · esc stops it" in plain(session.transcript)

    def test_a_run_made_in_rae_desktop_is_continued_there(self, app_session):
        session, history = app_session
        desktop = {"run_id": "d1", "prompt": "quotes", "mode": "desktop-browse", "sdk_session": {"id": "s", "mode": "desktop-browse"}}
        history.get_run.return_value = desktop
        with patch.object(session, "work") as work:
            session.run_command("/resume d1")
        work.assert_not_called()
        assert "run d1 was made in rae desktop" in plain(session.transcript)
        history.history = [desktop]
        history.get_history.return_value = [desktop]
        session.run_command("/resume")
        assert session.st.picker is None, "the picker lists only runs this session can continue"

    def test_the_cli_does_not_reopen_a_desktop_run_without_its_tools(self, monkeypatch):
        from reverse_api import cli

        history = MagicMock()
        history.get_run.return_value = {"run_id": "d1", "mode": "desktop-capture", "sdk_session": {"id": "s", "mode": "engineer"}}
        monkeypatch.setattr(cli, "session_manager", history)
        with patch.object(cli, "run_engineer") as engineer, patch.object(cli, "run_auto_capture") as agent:
            assert cli.resume_run("d1") is None
        engineer.assert_not_called()
        agent.assert_not_called()

    def test_a_failure_the_engine_reported_is_not_repeated(self, app_session):
        session, _history = app_session

        def failed():
            session.bridge.ui().error("Not logged in · Please run /login")
            return {"error": "Agent analysis produced no result."}

        session.work(failed)
        session.worker.join(5)
        text = plain(session.transcript)
        assert text.count("Not logged in") == 1 and "produced no result" not in text

    def test_an_error_in_an_earlier_turn_does_not_hide_how_the_run_ends(self, app_session):
        session, _history = app_session
        session.bridge.ui().error("rate limited")
        session.bridge.follow_ups.put("try again")
        assert asyncio.run(session.bridge.follow_up()) == "try again"
        session.finish({"error": "cursor bridge exited with code 3"})
        assert "cursor bridge exited with code 3" in plain(session.transcript)

    def test_a_resume_asked_for_while_a_run_wraps_up_comes_before_a_queued_prompt(self, app_session):
        session, _history = app_session
        reopened, started = [], []
        session.st.running, session.st.queue = True, ["follow-up text"]
        session.after_run = lambda: reopened.append(True)
        with patch.object(session, "call_soon", side_effect=lambda fn: fn()), patch.object(session, "start", side_effect=started.append):
            session.finish({})
        assert reopened == [True] and started == [] and session.after_run is None
        assert session.st.queue == ["follow-up text"], "the resumed conversation takes it as its next message"

    def test_new_and_quit_drop_a_pending_resume(self, app_session):
        session, _history = app_session
        session.after_run = lambda: None
        session.run_command("/new")
        assert session.after_run is None
        session.after_run = lambda: None
        session.quit()
        assert session.after_run is None

    def test_esc_while_a_run_wraps_up_drops_the_queued_prompts(self, app_session):
        session, _history = app_session
        session.st.running, session.bridge.stopping, session.st.queue = True, True, ["next"]
        session.stop()
        assert session.st.queue == [] and "still wrapping up" in plain(session.transcript)

    def test_a_second_esc_does_not_cut_a_closing_run_short(self, app_session):
        session, _history = app_session
        bridge = session.bridge
        bridge.loop, bridge.task = MagicMock(), MagicMock(done=MagicMock(return_value=False))
        session.st.waiting = True
        session.stop()  # ends the conversation that waited for a follow-up
        session.stop()
        bridge.loop.call_soon_threadsafe.assert_not_called()
        session.st.running, session.st.waiting, bridge.stopping = True, False, False
        session.stop()  # a working run is cancelled once, however often esc is pressed
        session.stop()
        assert bridge.loop.call_soon_threadsafe.call_count == 1
        assert "cannot be stopped" not in plain(session.transcript)


class TestEntry:
    def test_a_subcommand_run_starts_once_the_app_is_up(self, app_session):
        session, _history = app_session
        run = MagicMock()
        session.first = ("jobs on example.com", run)
        with patch.object(session, "work") as work, patch("reverse_api.utils.check_for_updates", return_value=None):
            session.start_first()
            session.start_first()
        work.assert_called_once_with(run)
        assert "jobs on example.com" in plain(session.transcript) and session.st.running

    def test_plain_terminal_modes_hand_the_run_to_the_classic_screen(self, app_session):
        session, _history = app_session
        session.app = MagicMock()
        session.st.mode = "collector"
        run = MagicMock()
        session.first = ("companies hiring", run)
        with patch("reverse_api.utils.check_for_updates", return_value=None):
            session.start_first()
        session.app.exit.assert_called_once()
        assert session.take_classic_job() is not None

    def test_an_update_shows_as_a_notice(self, app_session):
        session, _history = app_session
        threads = []
        with patch("reverse_api.repl.app.threading.Thread", side_effect=lambda target, **_: threads.append(target) or MagicMock()):
            session.start_first()
        with patch("reverse_api.utils.check_for_updates", return_value="update available: 0.14.0 → 0.15.0"):
            threads[0]()
        assert "update available: 0.14.0 → 0.15.0" in plain(session.transcript)


class TestSubcommands:
    def test_agent_in_a_terminal_opens_the_session_with_every_option(self, monkeypatch):
        from click.testing import CliRunner

        from reverse_api import cli

        monkeypatch.setattr(cli, "_in_terminal", lambda: True)
        with patch.object(cli, "open_session") as session, patch.object(cli, "run_agent_capture") as capture:
            CliRunner().invoke(cli.main, ["agent", "-p", "jobs", "-u", "https://example.com", "--headless"])
            mode, model, prompt, run, runner = session.call_args.args
            run()
            runner("later task", "claude-opus-5-5")
        assert (mode, model, prompt) == ("agent", None, "jobs")
        assert capture.call_args_list[0].kwargs == {
            "prompt": "jobs",
            "url": "https://example.com",
            "model": None,
            "output_dir": None,
            "headless": True,
        }
        assert capture.call_args_list[1].kwargs == {"prompt": "later task", "model": "claude-opus-5-5", "output_dir": None, "headless": True}

    def test_engineer_keeps_its_output_dir_for_later_prompts(self, monkeypatch):
        from click.testing import CliRunner

        from reverse_api import cli

        monkeypatch.setattr(cli, "_in_terminal", lambda: True)
        with patch.object(cli, "open_session") as session, patch.object(cli, "engineer_from_prompt") as later:
            CliRunner().invoke(cli.main, ["engineer", "abc123", "-o", "/out"])
            runner = session.call_args.args[4]
            runner("add pagination", None)
        later.assert_called_once_with("add pagination", None, "/out")

    def test_an_engineer_prompt_is_a_run_id_or_an_instruction_for_the_latest_capture(self, monkeypatch):
        from reverse_api import cli

        history = MagicMock()
        history.get_run.side_effect = lambda text: {"run_id": text} if text == "abc123" else None
        history.get_history.return_value = [{"run_id": "collect1", "mode": "collector"}, {"run_id": "capture1", "mode": "agent"}]
        monkeypatch.setattr(cli, "session_manager", history)
        with patch.object(cli, "run_engineer") as engineer:
            cli.engineer_from_prompt("abc123", "m", "/out")
            cli.engineer_from_prompt("add pagination", "m", "/out")
        assert engineer.call_args_list[0] == call("abc123", model="m", output_dir="/out")
        assert engineer.call_args_list[1] == call("capture1", model="m", output_dir="/out", additional_instructions="add pagination")
        history.get_history.return_value = history.get_history.return_value[:1]
        with pytest.raises(RuntimeError, match="no captured runs yet"):
            cli.engineer_from_prompt("add pagination")

    def test_without_a_terminal_a_prompt_is_required(self, monkeypatch):
        from click.testing import CliRunner

        from reverse_api import cli

        monkeypatch.setattr(cli, "_in_terminal", lambda: False)
        with patch.object(cli, "open_session") as session:
            agent = CliRunner().invoke(cli.main, ["agent"])
            collector = CliRunner().invoke(cli.main, ["collector"])
        session.assert_not_called()
        assert agent.exit_code == 2 and collector.exit_code == 2

    def test_json_never_opens_the_session(self, monkeypatch):
        from click.testing import CliRunner

        from reverse_api import cli

        monkeypatch.setattr(cli, "_in_terminal", lambda: True)
        with patch.object(cli, "open_session") as session, patch.object(cli, "run_agent_capture", return_value={}):
            CliRunner().invoke(cli.main, ["agent", "-p", "jobs", "--json"])
        session.assert_not_called()


class TestEffortIsClaudeOnly:
    def test_other_sdks_show_no_effort(self, app_session):
        session, _history = app_session
        st = session.st
        st.sdk, st.model = "copilot", "gpt-5"
        assert not st.has_effort
        assert "effort" not in "".join(text for row in session.view.header_rows(0.0) for _, text in row)
        assert "⌃e" not in "".join(text for _, text in session.view.status())
        session.cycle_effort()
        assert st.effort is None
        session.run_command("/effort")
        assert st.picker is None and "effort is a claude setting" in plain(session.transcript)

    def test_a_claude_model_without_effort_says_so(self, app_session):
        session, _history = app_session
        st = session.st
        st.sdk, st.model = "claude", "claude-haiku-4-5"
        session.run_command("/effort")
        text = plain(session.transcript)
        assert st.picker is None and "haiku 4.5 has no effort setting" in text and "is a claude setting" not in text

    def test_claude_keeps_its_effort(self, app_session):
        session, _history = app_session
        st = session.st
        st.sdk, st.model = "claude", "claude-opus-5-5"
        assert st.has_effort and "⌃e" in "".join(text for _, text in session.view.status())
        st.model = "claude-haiku-4-5"
        assert not st.has_effort


def test_tiny_costs_read_as_under_a_cent(session):
    from reverse_api.repl.view import money

    st, _t, view, _b = session
    assert (money(0.004), money(0.0), money(0.07)) == ("<$0.01", "$0.00", "$0.07")
    st.cost = 0.004
    assert "<$0.01" in "".join(text for _, text in view.status())


class TestReviewedSession:
    def test_later_prompts_keep_the_subcommand_options(self, app_session):
        session, _history = app_session
        runner = MagicMock()
        session.runners["agent"] = runner
        with patch.object(session, "work") as work:
            session.start("all jobs on example.com")
            work.call_args.args[0]()
        runner.assert_called_once_with("all jobs on example.com", "claude-sonnet-5-5")

    def test_a_resumed_run_does_not_change_the_next_runs_model(self, session):
        st, _t, view, b = session
        LedgerUI(b).header("r1", "p", model="gpt-5", sdk="copilot")
        assert st.model == "claude-sonnet-5-5" and st.live_model_label == "gpt-5" and st.run_effort is None
        assert "gpt-5" in "".join(text for _, text in view.seam())

    def test_finishing_clears_the_runs_own_model(self, app_session):
        session, _history = app_session
        LedgerUI(session.bridge).header("r1", "p", model="gpt-5", sdk="copilot")
        session.finish(None)
        assert session.st.run_model is None and session.st.live_model_label == "sonnet 5.5"

    def test_a_model_change_mid_run_says_it_waits_for_the_next_run(self, app_session):
        session, _history = app_session
        session.st.waiting = True
        session.set_model("claude-opus-5-5")
        assert "from the next run" in plain(session.transcript)

    def test_the_model_picker_keeps_a_current_model_that_left_the_list(self, app_session):
        session, _history = app_session
        session.st.model = "claude-sonnet-4-6"
        session.run_command("/model")
        assert session.st.picker.items[0][0] == "claude-sonnet-4-6" and session.st.picker.index == 0

    def test_quitting_waits_for_the_run_to_wrap_up(self, app_session):
        session, _history = app_session
        session.worker = threading.Thread(target=lambda: __import__("time").sleep(0.3))
        session.worker.start()
        session.wait_for_run(timeout=5)
        assert not session.worker.is_alive()

    def test_a_stopped_engineer_run_reads_as_interrupted(self, app_session):
        session, _history = app_session

        def stopped():
            raise asyncio.CancelledError

        session.work(stopped)
        session.worker.join(5)
        text = plain(session.transcript)
        assert "interrupted" in text and "CancelledError" not in text

    def test_a_prompt_typed_while_finishing_waits_for_the_queued_one(self, app_session):
        session, _history = app_session
        session.loop = Loop()
        session.st.running, session.st.queue = True, ["queued first"]
        with patch.object(session, "start") as start:
            session.finish(None)
        start.assert_called_once_with("queued first")

    def test_several_answers_are_sent_together(self, app_session):
        session, _history = app_session
        session.loop = Loop()
        fut = session.ask_user({"question": "Which boards?", "options": [("openai", ""), ("anthropic", ""), ("ramp", "")], "multi": True})
        picker = session.st.picker
        assert picker.multi
        session.toggle()
        picker.index = 2
        session.toggle()
        session.choose()
        assert fut.result() == "openai, ramp"

    def test_typing_resets_the_command_menu_to_the_first_match(self, app_session):
        session, _history = app_session
        session.st.palette_index = 3
        session.buf.text = "/mo"
        assert session.st.palette_index == 0

    def test_open_works_for_a_client_the_card_does_not_show(self, session, tmp_path):
        st, t, _view, b = session
        client = tmp_path / "api_client.py"
        client.write_text("x = 1\n", encoding="utf-8")
        LedgerUI(b).success(str(client))
        assert st.last_client == client and "ready" not in plain(t)

    def test_a_failed_verification_gets_no_card(self, session, tmp_path):
        st, t, _view, b = session
        client = tmp_path / "api_client.py"
        client.write_text("x = 1\n", encoding="utf-8")
        ui = LedgerUI(b)
        ui.header("r1", "p", model="claude-sonnet-5-5")
        ui.tool_start("mcp__verification__report_client_verified", {"summary": "ok"})
        ui.tool_result("mcp__verification__report_client_verified", is_error=True, output="failed")
        ui.success(str(client))
        ui.usage({"input_tokens": 1, "output_tokens": 1, "estimated_cost_usd": 0.01})
        assert "ready" not in plain(t)

    def test_full_output_keeps_every_line_whole(self, session):
        _st, t, _view, b = session
        lines = [f"line {i} " + "x" * 300 for i in range(500)]
        LedgerUI(b).tool_result("Bash", output="\n".join(lines))
        console = Console(file=io.StringIO(), width=400, color_system=None)
        for item in t.full:
            console.print(item)
        out = console.file.getvalue()
        assert all(f"line {i} " + "x" * 300 in out for i in range(500))

    def test_usage_counts_other_sdks_cache_tokens(self, session):
        st, _t, _view, b = session
        LedgerUI(b).usage({"input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 100, "cache_write_tokens": 20})
        assert st.tokens == 135

    def test_blank_lines_from_prints_are_kept(self):
        got: list[Raw] = []
        writer = TranscriptWriter(got.append)
        writer.write("a\n\nb\n")
        writer.write("\n")
        assert [len(r.lines) for r in got] == [3, 1]

    def test_the_capture_has_no_file_descriptor(self):
        with pytest.raises(io.UnsupportedOperation):
            TranscriptWriter(lambda raw: None).fileno()

    def test_dated_model_ids_get_no_adaptive_thinking(self):
        from reverse_api.repl.bridge import adaptive_thinking

        assert not adaptive_thinking("claude-sonnet-4-20250514") and not adaptive_thinking("claude-opus-4-1")
        assert adaptive_thinking("claude-sonnet-4-6") and adaptive_thinking("claude-opus-5-5")

    def test_links_with_brackets_stay_whole(self, session):
        from reverse_api.repl.view import link

        _st, t, view, _b = session
        markup = link("jobs", "https://example.com/jobs?filter[status]=open")
        assert "filter%5Bstatus%5D=open" in markup
        view.out(markup)
        assert "jobs" in plain(t) and "]=open" not in plain(t)

    def test_reasoning_keeps_dunder_names(self):
        from reverse_api.repl.view import strip_markdown

        assert strip_markdown("**Plan** call __init__ in my_module") == "Plan call __init__ in my_module"

    def test_history_shows_tiny_costs_as_under_a_cent(self):
        from reverse_api.repl.view import run_summary

        assert run_summary({"timestamp": "2026-10-26T10:00", "prompt": "p", "usage": {"estimated_cost_usd": 0.002}}).endswith("<$0.01")

    def test_history_shows_the_cost_of_opencode_runs_that_kept_it_as_cost(self):
        from reverse_api.repl.view import run_summary

        assert run_summary({"timestamp": "2026-10-26T10:00", "prompt": "p", "usage": {"cost": 0.5}}).endswith("$0.50")

    def test_width_is_the_real_terminal_width(self, monkeypatch):
        import os

        from reverse_api.repl import style

        monkeypatch.setattr(style.shutil, "get_terminal_size", lambda *a, **k: os.terminal_size((30, 10)))
        assert style.width() == 30


class TestReviewedAgain:
    def test_the_full_output_is_styled_only_when_shown(self, session):
        from reverse_api.repl.view import Deferred

        _st, t, _view, b = session
        LedgerUI(b).tool_result("Bash", output="\n".join(f"line {i}" for i in range(50)))
        full = t.full[-1]
        assert isinstance(full, Deferred) and full._built is None
        console = Console(file=io.StringIO(), width=200, color_system=None)
        console.print(full)
        assert "line 49" in console.file.getvalue() and full._built is not None

    def test_the_run_effort_follows_the_runs_own_model(self, session):
        st, _t, _view, b = session
        st.effort = None
        LedgerUI(b).header("r1", "p", model="claude-opus-5-5")
        assert st.run_effort == "medium"
        st.effort = "max"
        LedgerUI(b).header("r2", "p", model="claude-opus-5-5")
        assert st.run_effort == "max"

    def test_the_menu_stays_shut_while_the_agent_awaits_a_typed_answer(self, app_session):
        session, _history = app_session
        session.buf.text = "/tmp/capture"
        assert session.palette_active()
        session.st.question = Future()
        assert not session.palette_active()

    def test_quitting_drops_queued_prompts(self, app_session):
        session, _history = app_session
        session.st.queue = ["later"]
        session.quit()
        assert session.st.queue == []

    def test_collector_mode_runs_and_shows_its_own_model(self, app_session):
        session, _history = app_session
        st = session.st
        st.mode, st.collector_model = "collector", "claude-haiku-5-5"
        assert st.live_model_label == "haiku 5.5"
        session.set_model("claude-opus-5-5")
        assert st.collector_model == "claude-opus-5-5" and st.model == "claude-sonnet-5-5"
        session.cli.config_manager.set.assert_called_with("collector_model", "claude-opus-5-5")
        with patch.object(session, "classic") as classic:
            session.start("companies hiring")
        with patch.object(session.cli, "run_collector") as run:
            classic.call_args.args[0]()
        assert run.call_args.kwargs["model"] == "claude-opus-5-5"

    def test_a_collector_runner_gets_the_collectors_model(self, app_session):
        session, _history = app_session
        st = session.st
        st.mode, st.collector_model = "collector", "claude-haiku-5-5"
        runner = MagicMock()
        session.runners["collector"] = runner
        with patch.object(session, "classic") as classic:
            session.start("companies hiring")
            classic.call_args.args[0]()
        runner.assert_called_once_with("companies hiring", "claude-haiku-5-5")


def test_collector_mode_effort_follows_the_collectors_model(app_session):
    session, _history = app_session
    st = session.st
    st.mode, st.collector_model = "collector", "claude-haiku-4-5"
    assert not st.has_effort
    st.collector_model = "claude-opus-5-5"
    assert st.has_effort and st.effort_label == "medium"
