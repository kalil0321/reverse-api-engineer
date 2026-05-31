"""Tests for --json-stream NDJSON CLI output."""

import asyncio
import json
from unittest.mock import patch

from click.testing import CliRunner

from reverse_api.cli import agent, engineer, main
from reverse_api.json_stream import StreamingUIWrapper


class TestJsonStreamAgent:
    def test_agent_json_stream_emits_ndjson_and_result(self):
        runner = CliRunner()
        fake_result = {
            "run_id": "abc123",
            "mode": "auto",
            "script_path": "/tmp/api_client.py",
            "usage": {},
        }

        def fake_capture(**kwargs):
            sink = kwargs.get("json_event_sink")
            if sink:
                sink({"event": "run_started", "run_id": "abc123", "sdk": "claude"})
            return fake_result

        with patch("reverse_api.cli.run_agent_capture", side_effect=fake_capture):
            result = runner.invoke(
                agent,
                ["--json-stream", "-p", "capture api", "-u", "https://example.com"],
            )

        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().split("\n") if ln]
        assert len(lines) >= 2
        events = [json.loads(ln) for ln in lines]
        assert events[0]["event"] == "run_started"
        assert events[-1]["event"] == "result"
        assert events[-1]["status"] == "ok"
        assert events[-1]["run_id"] == "abc123"

    def test_agent_json_stream_implies_no_interactive(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture") as mock_run:
            mock_run.return_value = {"run_id": "x", "mode": "auto", "usage": {}}
            runner.invoke(agent, ["--json-stream", "-p", "x"])
        assert mock_run.call_args.kwargs["interactive"] is False


class TestJsonStreamEngineer:
    def test_engineer_json_stream_emits_result_event(self):
        runner = CliRunner()
        def fake_engineer(run_id, **kwargs):
            sink = kwargs.get("json_event_sink")
            if sink:
                sink({"event": "run_started", "run_id": run_id, "sdk": "claude"})
            return {"script_path": "/tmp/c.py", "usage": {}}

        with patch("reverse_api.cli.run_engineer", side_effect=fake_engineer):
            result = runner.invoke(engineer, ["abc123", "--json-stream", "-p", "add tests"])

        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().split("\n") if ln]
        events = [json.loads(ln) for ln in lines]
        assert events[-1]["event"] == "result"
        assert events[-1]["run_id"] == "abc123"

    def test_help_lists_json_stream(self):
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "--help"])
        assert "--json-stream" in result.output

class TestJsonStreamContract:
    """The event payloads must stay machine-parseable."""

    def _wrapper(self):
        events: list[dict] = []

        class _Inner:
            def tool_start(self, *a, **k):
                pass

            def tool_result(self, *a, **k):
                pass

        return StreamingUIWrapper(_Inner(), events.append), events

    def test_ask_user_skip_emits_balanced_tool_end(self):
        # In non-interactive mode AskUserQuestion is auto-skipped and the SDK
        # never streams a tool result for it; the stream must still emit a
        # tool_end so every tool_start has a matching tool_end.
        from claude_agent_sdk import AssistantMessage, ToolUseBlock

        from reverse_api.engineer import ClaudeEngineer

        events: list[dict] = []

        class _Console:
            def print(self, *a, **k):
                pass

        class _Inner:
            console = _Console()

            def tool_start(self, *a, **k):
                pass

            def tool_result(self, *a, **k):
                pass

        eng = ClaudeEngineer.__new__(ClaudeEngineer)
        eng.interactive = False
        eng._json_event_sink = events.append
        eng.ui = StreamingUIWrapper(_Inner(), events.append)

        async def _receive():
            yield AssistantMessage(
                content=[ToolUseBlock(id="t1", name="AskUserQuestion", input={"questions": []})],
                model="claude",
            )

        class _Client:
            def receive_response(self):
                return _receive()

        asyncio.run(eng._stream_and_handle(_Client()))

        kinds = [(e["event"], e.get("name")) for e in events if e["event"].startswith("tool")]
        assert ("tool_start", "AskUserQuestion") in kinds
        assert ("tool_end", "AskUserQuestion") in kinds
        assert kinds.count(("tool_start", "AskUserQuestion")) == kinds.count(
            ("tool_end", "AskUserQuestion")
        )
        assert any(e["event"] == "ask_user_skipped" for e in events)

    def test_tool_start_input_is_structured_json_not_repr(self):
        wrapper, events = self._wrapper()
        payload = {"todos": [{"content": "x", "status": "pending"}], "flag": False}
        wrapper.tool_start("updateTodos", payload, call_id="C1")

        # The event survives a JSON round-trip with input as a nested object,
        # not a str(dict) repr (which would carry single quotes / Python False).
        roundtripped = json.loads(json.dumps(events[0]))
        assert roundtripped["input"] == payload
        assert isinstance(roundtripped["input"], dict)
        assert roundtripped["call_id"] == "C1"

    def test_tool_start_and_end_share_call_id(self):
        wrapper, events = self._wrapper()
        wrapper.tool_start("shell", {"command": "ls"}, call_id="abc")
        wrapper.tool_result("shell", False, "ok", call_id="abc")
        assert events[0]["event"] == "tool_start" and events[0]["call_id"] == "abc"
        assert events[1]["event"] == "tool_end" and events[1]["call_id"] == "abc"

    def test_cursor_collapses_running_deltas_to_one_tool_start(self):
        from reverse_api.cursor_engineer import CursorEngineer

        eng = CursorEngineer.__new__(CursorEngineer)
        eng._cursor_started_calls = set()
        eng.interactive = False
        eng._json_event_sink = None
        eng._cursor_thinking_acc = ""
        eng._cursor_assistant_acc = ""
        captured: list[tuple] = []

        class _UI:
            verbose = False

            class console:
                @staticmethod
                def print(*a, **k):
                    pass

            def todo_updated(self, todos):
                pass

            def tool_start(self, name, args, call_id=None):
                captured.append(("start", call_id))

            def tool_result(self, name, is_err, out, call_id=None):
                captured.append(("end", call_id))

        class _Store:
            def save_tool_start(self, *a):
                pass

            def save_tool_result(self, *a):
                pass

            def save_todos(self, *a):
                pass

        eng.ui = _UI()
        eng.message_store = _Store()

        async def run():
            for n in (1, 2, 3):  # growing args, same call
                await eng._dispatch_stream_event(
                    {
                        "type": "tool_call",
                        "name": "updateTodos",
                        "status": "running",
                        "callId": "T1",
                        "args": {"todos": [{"content": str(i)} for i in range(n)]},
                    }
                )
            await eng._dispatch_stream_event(
                {"type": "tool_call", "name": "updateTodos", "status": "completed", "callId": "T1", "result": "ok"}
            )

        asyncio.run(run())
        assert [c[0] for c in captured] == ["start", "end"]
        assert eng._cursor_started_calls == set()  # cleaned up on terminal event


class TestJsonStreamEngineerMisuse:
    def test_engineer_json_stream_missing_run_id_emits_result_event(self):
        runner = CliRunner()
        result = runner.invoke(engineer, ["--json-stream"])
        assert result.exit_code == 2
        payload = json.loads(result.output.strip())
        assert payload["event"] == "result"
        assert payload["status"] == "error"
        assert payload["error_kind"] == "misuse"
        assert "RUN_ID" in payload["error"]
