"""Resume across SDKs: each engine records its session and reopens it from the user's next message."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api import cli


@pytest.fixture
def har_path(tmp_path: Path) -> Path:
    p = tmp_path / "recording.har"
    p.write_text('{"log":{"entries":[]}}')
    return p


def _cursor(har_path: Path, tmp_path: Path):
    from reverse_api.cursor_engineer import CursorEngineer

    with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
        return CursorEngineer(run_id="abc123", har_path=har_path, prompt="jobs", cursor_model="composer-2", sdk="cursor", verbose=False)


class TestCursor:
    @pytest.mark.asyncio
    async def test_a_resumed_agent_gets_only_the_next_message(self, har_path, tmp_path):
        eng = _cursor(har_path, tmp_path)
        eng.resume_session = "agent-1"
        eng._prompt_follow_up = AsyncMock(side_effect=["now add pagination", None])  # type: ignore[method-assign]
        eng._one_turn = AsyncMock(return_value={"ok": True, "agentId": "agent-1"})  # type: ignore[method-assign]
        with patch.dict("os.environ", {"CURSOR_API_KEY": "k"}), patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            out = await eng.analyze_and_generate()
        assert out is not None and "script_path" in out
        first = eng._one_turn.await_args_list[0]
        assert first.args[0] == "now add pagination" and first.kwargs["resume_agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_a_new_run_sends_the_brief_and_records_the_agent(self, har_path, tmp_path):
        eng = _cursor(har_path, tmp_path)
        eng.interactive = False
        seen: list[str] = []
        eng.on_session = seen.append

        async def one_turn(prompt, *, mcp_servers, resume_agent_id):
            eng._record_session("agent-9")  # what the bridge's early "agent" line does
            return {"ok": True, "agentId": "agent-9"}

        eng._one_turn = AsyncMock(side_effect=one_turn)  # type: ignore[method-assign]
        with patch.dict("os.environ", {"CURSOR_API_KEY": "k"}), patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            await eng.analyze_and_generate()
        first = eng._one_turn.await_args_list[0]
        assert first.kwargs["resume_agent_id"] is None and "jobs" in first.args[0] and len(first.args[0]) > 200
        assert seen == ["agent-9"]


class TestCopilot:
    def _eng(self, har_path, tmp_path):
        from reverse_api.copilot_engineer import CopilotEngineer

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            return CopilotEngineer(run_id="abc123", har_path=har_path, prompt="jobs", copilot_model="gpt-5", sdk="copilot", verbose=False)

    @pytest.mark.asyncio
    async def test_resume_reopens_the_saved_session(self, har_path, tmp_path):
        eng = self._eng(har_path, tmp_path)
        seen: list[str] = []
        eng.on_session = seen.append
        client = MagicMock()
        client.resume_session = AsyncMock(return_value=MagicMock(session_id="cp-1"))
        client.create_session = AsyncMock()
        eng.resume_session = "cp-1"
        await eng._open_copilot_session(client, model="gpt-5")
        client.resume_session.assert_awaited_once_with("cp-1", model="gpt-5")
        client.create_session.assert_not_called()
        assert seen == [], "the reopened session is already on the run, with its cost so far"

    @pytest.mark.asyncio
    async def test_a_new_run_creates_one_and_records_it(self, har_path, tmp_path):
        eng = self._eng(har_path, tmp_path)
        seen: list[str] = []
        eng.on_session = seen.append
        client = MagicMock()
        client.create_session = AsyncMock(return_value=MagicMock(session_id="cp-2"))
        await eng._open_copilot_session(client, model="gpt-5")
        client.create_session.assert_awaited_once_with(model="gpt-5")
        assert seen == ["cp-2"]

    @pytest.mark.asyncio
    async def test_ending_a_resume_before_a_message_sends_nothing(self, har_path, tmp_path):
        pytest.importorskip("copilot")
        eng = self._eng(har_path, tmp_path)
        eng.resume_session = "cp-1"
        eng._prompt_follow_up = AsyncMock(return_value=None)  # type: ignore[method-assign]
        with patch("copilot.CopilotClient") as client:
            assert await eng.analyze_and_generate() == {}
        client.assert_not_called()

    @pytest.mark.asyncio
    async def test_events_stream_text_and_reasoning_and_add_up_usage(self, har_path, tmp_path):
        import asyncio
        from types import SimpleNamespace

        eng = self._eng(har_path, tmp_path)
        ui = MagicMock()
        eng.ui = ui
        done, errors = asyncio.Event(), []
        on_event = eng._event_handler(done, errors)

        def event(kind, **data):
            return SimpleNamespace(type=SimpleNamespace(value=kind), data=SimpleNamespace(**data))

        on_event(event("assistant.reasoning_delta", delta_content="Plan"))
        on_event(event("assistant.message_delta", delta_content="Hel"))
        on_event(event("assistant.message", content="Hello"))
        on_event(event("assistant.usage", input_tokens=100, output_tokens=5))
        on_event(event("assistant.usage", input_tokens=50, output_tokens=5, cache_read_tokens=None))
        on_event(event("session.error", message="No model available"))
        on_event(event("session.idle"))
        await asyncio.sleep(0)
        ui.stream_thinking.assert_called_once_with("Plan")
        ui.stream_text.assert_called_once_with("Hel")
        ui.thinking.assert_called_once_with("Hello")
        assert eng.usage_metadata == {"input_tokens": 150, "output_tokens": 10}
        assert errors == ["No model available"] and done.is_set()

    @pytest.mark.asyncio
    async def test_a_session_error_fails_the_run(self, har_path, tmp_path):
        pytest.importorskip("copilot")
        import asyncio
        from types import SimpleNamespace

        eng = self._eng(har_path, tmp_path)
        eng.ui = MagicMock()
        session = MagicMock(session_id="cp-3")
        handlers = []
        session.on = handlers.append

        async def send(prompt):
            for kind, data in (("session.error", {"message": "No model available"}), ("session.idle", {})):
                handlers[0](SimpleNamespace(type=SimpleNamespace(value=kind), data=SimpleNamespace(**data)))
            await asyncio.sleep(0)

        session.send = send
        client = MagicMock(start=AsyncMock(), stop=AsyncMock(), create_session=AsyncMock(return_value=session))
        with patch("copilot.CopilotClient", return_value=client):
            assert await eng.analyze_and_generate() is None
        eng.ui.error.assert_called_with("No model available")
        assert client.create_session.await_args.kwargs["model"] == "gpt-5"


def test_tool_output_text_reads_results_and_wire_dicts():
    from reverse_api.copilot_engineer import tool_output_text

    assert tool_output_text({"textResultForLlm": "200 OK", "resultType": "success"}) == "200 OK"
    assert tool_output_text(MagicMock(text_result_for_llm="12 jobs")) == "12 jobs"
    assert tool_output_text(None) is None


class TestOpenCode:
    def _eng(self, har_path, tmp_path):
        from reverse_api.opencode_engineer import OpenCodeEngineer

        with (
            patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"),
            patch("reverse_api.base_engineer.MessageStore"),
            patch("reverse_api.opencode_engineer.OpenCodeUI"),
        ):
            return OpenCodeEngineer(run_id="abc123", har_path=har_path, prompt="jobs", output_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_resume_checks_the_saved_session_instead_of_creating_one(self, har_path, tmp_path):
        eng = self._eng(har_path, tmp_path)
        eng.resume_session = "ses_1"
        client = MagicMock()
        client.get = AsyncMock(return_value=MagicMock(raise_for_status=MagicMock()))
        client.post = AsyncMock()
        assert await eng._open_session(client) == "ses_1"
        client.get.assert_awaited_once_with("/session/ses_1")
        client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_new_run_creates_a_session_and_records_it(self, har_path, tmp_path):
        eng = self._eng(har_path, tmp_path)
        seen: list[str] = []
        eng.on_session = seen.append
        response = MagicMock(raise_for_status=MagicMock())
        response.json.return_value = {"id": "ses_2"}
        client = MagicMock()
        client.post = AsyncMock(return_value=response)
        assert await eng._open_session(client) == "ses_2"
        assert seen == ["ses_2"]


class TestCli:
    @pytest.fixture
    def history(self, monkeypatch):
        sm = MagicMock()
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {"sdk": "claude", "real_time_sync": True}.get(key, default)
        monkeypatch.setattr(cli, "session_manager", sm)
        monkeypatch.setattr(cli, "config_manager", config)
        return sm

    def test_sessions_are_recorded_with_what_reopening_them_needs(self, history):
        cli._session_recorder("r1", "agent", "cursor", "composer-2.5", "/custom")("agent-1")
        history.update_run.assert_called_once_with(
            run_id="r1",
            sdk_session={
                "mode": "agent",
                "sdk": "cursor",
                "model": "composer-2.5",
                "output_dir": str(Path("/custom").resolve()),  # C:\custom on Windows
                "output_mode": "client",
                "id": "agent-1",
                "cost": 0.0,
            },
        )

    def test_the_cost_baseline_is_the_session_own_not_the_run_total(self, history):
        resume = {"usage": {"estimated_cost_usd": 5.0}, "sdk_session": {"id": "s-new", "cost": 0.5}}
        assert cli._resume_point(resume) == ("s-new", 0.5)
        older = {"usage": {"estimated_cost_usd": 1.0}, "sdk_session": {"id": "s-old"}}
        assert cli._resume_point(older) == ("s-old", 1.0), "sessions saved before they kept their own cost"
        history.get_run.return_value = {"sdk_session": {"id": "s-new", "cost": 0.5}}
        cli._keep_session_cost("r1", 0.5, {"estimated_cost_usd": 0.25})
        history.update_run.assert_called_once_with(run_id="r1", sdk_session={"id": "s-new", "cost": 0.75})

    def test_totals_add_every_counter_of_any_sdk(self):
        before = {"cost": 1.0, "reasoning_tokens": 10, "cache_write_tokens": 3, "input_tokens": 100, "model": "x", "is_estimate": True}
        now = {"cost": 0.25, "reasoning_tokens": 5, "cache_write_tokens": 2, "input_tokens": 50, "model": "x", "is_estimate": True}
        totals = cli._run_totals(before, now)
        assert totals == {"cost": 1.25, "reasoning_tokens": 15, "cache_write_tokens": 5, "input_tokens": 150, "model": "x", "is_estimate": True}

    def test_a_relative_output_folder_is_saved_absolute(self, history, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cli._session_recorder("r1", "agent", "claude", "claude-sonnet-5-5", "./outputs")("s-1")
        assert history.update_run.call_args.kwargs["sdk_session"]["output_dir"] == str((tmp_path / "outputs").resolve())

    def test_a_claude_session_keeps_the_effort_it_runs_at(self, history, monkeypatch):
        monkeypatch.setattr(cli, "build_sdk_effort", lambda model: {"effort": "xhigh"})
        cli._session_recorder("r1", "agent", "claude", "claude-sonnet-5-5", None)("s-1")
        assert history.update_run.call_args.kwargs["sdk_session"]["effort"] == "xhigh"
        monkeypatch.setattr(cli, "build_sdk_effort", lambda model: {})
        cli._session_recorder("r1", "agent", "claude", "claude-opus-5-5", None)("s-1")
        assert history.update_run.call_args.kwargs["sdk_session"]["effort"] == "medium", "the model's own default"
        cli._session_recorder("r1", "agent", "claude", "claude-haiku-4-5", None)("s-1")
        assert "effort" not in history.update_run.call_args.kwargs["sdk_session"]

    def test_a_reopened_session_is_not_recorded_again(self, tmp_path, har_path):
        eng = _cursor(har_path, tmp_path)
        seen: list[str] = []
        eng.on_session, eng.resume_session = seen.append, "agent-1"
        eng._record_session("agent-1")
        eng._record_session("agent-2")
        assert seen == ["agent-2"]

    def test_a_resume_uses_the_run_sdk_even_when_settings_changed(self):
        assert cli._session_sdk({"sdk_session": {"id": "s", "sdk": "copilot"}}) == "copilot"
        assert cli._session_sdk({"sdk_session": {"id": "s"}}) == "claude", "sessions saved before the sdk was recorded"
        assert cli._session_sdk(None) is None

    def test_run_engineer_reopens_a_cursor_session_with_cursor(self, history, tmp_path):
        run = {
            "run_id": "r1",
            "prompt": "jobs",
            "paths": {"har_dir": str(tmp_path)},
            "usage": {"estimated_cost_usd": 0.0},
            "sdk_session": {"id": "agent-1", "mode": "engineer", "sdk": "cursor"},
        }
        history.get_run.return_value = run
        with patch.object(cli, "run_reverse_engineering", return_value=None) as rre:
            cli.run_engineer("r1", resume=run)
        kwargs = rre.call_args.kwargs
        assert kwargs["sdk"] == "cursor" and kwargs["resume_session"] == "agent-1"
        kwargs["on_session"]("agent-2")
        session = history.update_run.call_args.kwargs["sdk_session"]
        assert (session["id"], session["sdk"], session["model"], session["mode"]) == ("agent-2", "cursor", "composer-2.5", "engineer")

    def test_run_reverse_engineering_hands_the_session_to_any_engine(self, har_path):
        from reverse_api.engineer import run_reverse_engineering

        record = MagicMock()
        engine = MagicMock()
        engine.analyze_and_generate = AsyncMock(return_value={"script_path": "x"})
        with patch("reverse_api.cursor_engineer.CursorEngineer", return_value=engine):
            run_reverse_engineering(run_id="r1", har_path=har_path, prompt="p", sdk="cursor", resume_session="agent-1", on_session=record)
        assert engine.resume_session == "agent-1" and engine.on_session is record


def test_opencode_resume_runs_in_the_classic_screen(monkeypatch):
    from reverse_api.repl.app import Session

    config = MagicMock()
    config.get.side_effect = lambda key, default=None: default
    history = MagicMock()
    history.get_run.return_value = {"run_id": "r1", "prompt": "jobs", "sdk_session": {"id": "ses_1", "mode": "agent", "sdk": "opencode"}}
    monkeypatch.setattr(cli, "config_manager", config)
    monkeypatch.setattr(cli, "session_manager", history)
    monkeypatch.setattr(cli, "default_model_for_configured_sdk", lambda sdk: "claude-sonnet-5-5")
    session = Session()
    session.app = MagicMock()
    with patch.object(session, "work") as work:
        session.run_command("/resume r1")
    work.assert_not_called()
    session.app.exit.assert_called_once()
    assert session.take_classic_job() is not None


class TestReviewedEdges:
    def test_an_empty_tool_result_shows_nothing(self):
        from reverse_api.copilot_engineer import tool_output_text

        assert tool_output_text(MagicMock(text_result_for_llm="")) is None

    @pytest.mark.asyncio
    async def test_a_copilot_error_ends_the_wait_without_idle(self, har_path, tmp_path):
        import asyncio
        from types import SimpleNamespace

        eng = TestCopilot()._eng(har_path, tmp_path)
        done, errors = asyncio.Event(), []
        eng._event_handler(done, errors)(SimpleNamespace(type=SimpleNamespace(value="session.error"), data=SimpleNamespace(message="quota")))
        await asyncio.sleep(0)
        assert done.is_set() and errors == ["quota"]

    def test_opencode_sessions_keep_their_provider(self, monkeypatch):
        history, config = MagicMock(), MagicMock()
        config.get.side_effect = lambda key, default=None: {"opencode_provider": "opencode"}.get(key, default)
        monkeypatch.setattr(cli, "session_manager", history)
        monkeypatch.setattr(cli, "config_manager", config)
        cli._session_recorder("r1", "agent", "opencode", "big-pickle", None)("ses_1")
        assert history.update_run.call_args.kwargs["sdk_session"]["provider"] == "opencode"
        assert cli._session_provider({"sdk_session": {"id": "s", "provider": "opencode"}}) == "opencode"
        assert cli._session_provider(None) is None

    def test_tool_results_are_logged_for_messages_without_the_session(self, har_path, tmp_path):
        from claude_agent_sdk.types import ToolResultBlock

        eng = _cursor(har_path, tmp_path)  # any engine with a message store
        from reverse_api.engineer import ClaudeEngineer

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            eng = ClaudeEngineer(run_id="r1", har_path=har_path, prompt="p", output_dir=str(tmp_path))
        eng._tool_names["t1"] = "Bash"
        eng.ui = MagicMock(shows_tool_results=False)
        eng._record_tool_results([ToolResultBlock(tool_use_id="t1", content="12 jobs", is_error=False)])
        eng.message_store.save_tool_result.assert_called_once_with("Bash", False, "12 jobs")
        eng.ui.tool_result.assert_not_called()

    def test_format_error_is_valid_markup_with_literal_exception_text(self):
        from io import StringIO

        from rich.console import Console

        from reverse_api.opencode_engineer import format_error

        console = Console(file=StringIO(), no_color=True, width=200)
        console.print(format_error(ValueError("bad [bold]x[/] [/oops]")))
        out = console.file.getvalue()
        assert "bad [bold]x[/] [/oops]" in out and "[bold red]" not in out


class TestReviewedResumeAgain:
    def test_a_headless_run_resumes_headless(self, monkeypatch):
        history, config = MagicMock(), MagicMock()
        config.get.side_effect = lambda key, default=None: default
        monkeypatch.setattr(cli, "session_manager", history)
        monkeypatch.setattr(cli, "config_manager", config)
        cli._session_recorder("r1", "agent", "claude", "claude-sonnet-5-5", None, headless=True)("s-1")
        session = history.update_run.call_args.kwargs["sdk_session"]
        assert session["headless"] is True
        history.get_run.return_value = {"run_id": "r1", "prompt": "jobs", "mode": "chrome-mcp", "sdk_session": session}
        with patch.object(cli, "run_auto_capture") as auto:
            cli.resume_run("r1")
        assert auto.call_args.kwargs["headless"] is True

    def test_esc_after_a_finished_turn_keeps_that_turns_result(self, har_path, tmp_path):
        import asyncio

        from reverse_api.engineer import ClaudeEngineer

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            eng = ClaudeEngineer(run_id="r1", har_path=har_path, prompt="p", output_dir=str(tmp_path))
        eng._process_streaming_response = AsyncMock(return_value={"script_path": "x/api_client.py", "usage": {"input_tokens": 5}})  # type: ignore[method-assign]
        eng._prompt_follow_up = AsyncMock(side_effect=asyncio.CancelledError)  # type: ignore[method-assign]
        client = MagicMock()
        client.return_value.__aenter__ = AsyncMock(return_value=client.return_value)
        client.return_value.__aexit__ = AsyncMock(return_value=False)
        client.return_value.query = AsyncMock()
        with patch("reverse_api.engineer.ClaudeSDKClient", client):
            out = asyncio.run(eng.analyze_and_generate())
        assert out == {"script_path": "x/api_client.py", "usage": {"input_tokens": 5}, "error": "interrupted"}

    def test_long_tool_output_is_saved_with_a_marker(self, har_path, tmp_path):
        from claude_agent_sdk.types import ToolResultBlock

        from reverse_api.engineer import ClaudeEngineer

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"), patch("reverse_api.base_engineer.MessageStore"):
            eng = ClaudeEngineer(run_id="r1", har_path=har_path, prompt="p", output_dir=str(tmp_path))
        eng._tool_names["t1"] = "Bash"
        eng._record_tool_results([ToolResultBlock(tool_use_id="t1", content="x" * 20005, is_error=False)])
        saved = eng.message_store.save_tool_result.call_args.args[2]
        assert saved.endswith("[5 more characters not saved]") and saved.startswith("x" * 20000)

    def test_usage_goes_only_to_the_session_ui(self, har_path, tmp_path):
        from reverse_api.repl.bridge import Bridge, LedgerUI
        from reverse_api.repl.transcript import Transcript
        from reverse_api.repl.view import LedgerView, SessionState

        eng = _cursor(har_path, tmp_path)
        eng.ui = MagicMock(shows_tool_results=True)
        eng._report_usage()
        eng.ui.usage.assert_not_called()
        st = SessionState(model="claude-sonnet-5-5")
        view = LedgerView(st, Transcript(on_link=lambda _: None))
        eng.ui = LedgerUI(Bridge(view, invalidate=lambda: None, ask_user=lambda spec: None))
        eng.usage_metadata = {"input_tokens": 7, "output_tokens": 3}
        eng._report_usage()
        assert st.tokens == 10


class TestStoppedEngineerRuns:
    @pytest.fixture
    def history(self, monkeypatch, tmp_path):
        sm, config = MagicMock(), MagicMock()
        config.get.side_effect = lambda key, default=None: {"sdk": "claude", "real_time_sync": True}.get(key, default)
        monkeypatch.setattr(cli, "session_manager", sm)
        monkeypatch.setattr(cli, "config_manager", config)
        (tmp_path / "recording.har").write_text("{}")
        sm.get_run.return_value = {"run_id": "r1", "prompt": "jobs", "paths": {"har_dir": str(tmp_path)}}
        return sm

    def test_a_run_stopped_before_its_first_turn_records_nothing(self, history):
        with patch.object(cli, "run_reverse_engineering", return_value={"error": "interrupted"}):
            assert cli.run_engineer("r1") == {"error": "interrupted"}
        history.update_run.assert_not_called()

    def test_a_run_stopped_after_a_turn_keeps_that_turn(self, history):
        result = {"script_path": "/tmp/scripts/r1/api_client.py", "usage": {"input_tokens": 5}, "error": "interrupted"}
        with patch.object(cli, "run_reverse_engineering", return_value=result):
            cli.run_engineer("r1")
        assert history.update_run.call_args.kwargs["paths"] == {"script_path": "/tmp/scripts/r1/api_client.py"}


def test_haiku_4_5_never_gets_an_effort():
    from reverse_api import utils

    with patch("reverse_api.config.ConfigManager.get", return_value="high"):
        assert utils.build_sdk_effort("claude-haiku-4-5") == {}
        assert utils.build_sdk_effort("claude-haiku-5-5") == {"effort": "high"}
