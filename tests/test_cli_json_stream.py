"""Tests for --json-stream NDJSON CLI output."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from reverse_api.cli import agent, engineer, main


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

    def test_engineer_json_stream_missing_run_id_emits_result_event(self):
        runner = CliRunner()
        result = runner.invoke(engineer, ["--json-stream"])
        assert result.exit_code == 2
        payload = json.loads(result.output.strip())
        assert payload["event"] == "result"
        assert payload["status"] == "error"
        assert payload["error_kind"] == "misuse"
        assert "RUN_ID" in payload["error"]
