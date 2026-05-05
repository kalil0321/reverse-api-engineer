"""Tests for the agent-friendly CLI surface (--json, --no-interactive, payload shape)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from reverse_api.cli import (
    AGENT_JSON_SCHEMA_VERSION,
    _build_agent_payload,
    agent,
    list_runs,
    main,
    show_run,
)
from reverse_api.session import SessionManager


EXPECTED_PAYLOAD_KEYS = {
    "schema_version",
    "status",
    "run_id",
    "prompt",
    "url",
    "mode",
    "har_path",
    "script_path",
    "usage",
    "error",
    "error_kind",
}


class TestBuildAgentPayload:
    """Stable shape for the `agent --json` payload."""

    def test_success_shape(self, tmp_path):
        payload = _build_agent_payload(
            {
                "run_id": "abc123",
                "mode": "auto",
                "script_path": str(tmp_path / "scripts" / "api_client.py"),
                # Mix of Claude SDK keys to exercise normalization (cache_creation_input_tokens
                # → cache_write_tokens, estimated_cost_usd → total_cost_usd).
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 50,
                    "estimated_cost_usd": 0.001,
                },
            },
            prompt="capture the X api",
            url="https://example.com",
        )
        assert payload["schema_version"] == AGENT_JSON_SCHEMA_VERSION
        assert set(payload.keys()) == EXPECTED_PAYLOAD_KEYS
        # No run produced a HAR yet on disk in this test, so har_path is None
        assert payload["status"] == "ok"
        assert payload["run_id"] == "abc123"
        assert payload["mode"] == "auto"
        assert payload["prompt"] == "capture the X api"
        assert payload["url"] == "https://example.com"
        # Stable normalized usage subset
        assert payload["usage"]["input_tokens"] == 1
        assert payload["usage"]["output_tokens"] == 2
        assert payload["usage"]["cache_write_tokens"] == 100
        assert payload["usage"]["cache_read_tokens"] == 50
        assert payload["usage"]["total_cost_usd"] == 0.001
        # Raw SDK shape still available for power users
        assert payload["usage"]["raw"]["cache_creation_input_tokens"] == 100
        assert payload["error"] is None
        assert payload["error_kind"] is None
        # Must be JSON-serializable (no Path objects sneaking through)
        json.dumps(payload)

    def test_no_run_id_is_error(self):
        payload = _build_agent_payload({}, prompt="x", url=None)
        assert payload["status"] == "error"
        assert payload["error"]
        assert payload["run_id"] is None
        assert payload["error_kind"] == "engine_failure"

    def test_explicit_error_overrides(self):
        payload = _build_agent_payload(
            {"run_id": "abc", "mode": "auto"},
            prompt="x",
            url=None,
            error="boom",
        )
        assert payload["status"] == "error"
        assert payload["error"] == "boom"

    def test_inner_error_propagates(self):
        payload = _build_agent_payload(
            {"run_id": "abc", "mode": "auto", "error": "inner"},
            prompt="x",
            url=None,
        )
        assert payload["status"] == "error"
        assert payload["error"] == "inner"

    def test_har_path_resolves_against_provided_output_dir(self, tmp_path):
        """har_path must use the user's --output-dir, not the default config root.

        Regression for cubic-dev-ai PR #61 review (P2).
        """
        run_id = "deadbeef0001"
        run_har_dir = tmp_path / "har" / run_id
        run_har_dir.mkdir(parents=True)
        (run_har_dir / "recording.har").write_text("{}")

        with patch("reverse_api.cli.get_har_dir") as gethar:
            gethar.side_effect = lambda rid, odir: tmp_path / "har" / rid
            payload = _build_agent_payload(
                {"run_id": run_id, "mode": "auto"},
                prompt="x",
                url=None,
                output_dir=str(tmp_path),
            )

        gethar.assert_called_with(run_id, str(tmp_path))
        assert payload["har_path"] == str(run_har_dir / "recording.har")


class TestAgentCommandJson:
    """`agent` click command's --json / --no-interactive behavior."""

    def test_json_without_prompt_exits_2(self):
        runner = CliRunner()
        result = runner.invoke(agent, ["--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stdout.strip())
        assert payload["status"] == "error"
        assert "prompt" in payload["error"].lower()

    def test_json_without_prompt_emits_full_schema(self):
        """Misuse JSON must contain every documented field (nulled), not a 3-key shortcut.

        Regression for cubic-dev-ai PR #61 review (P2).
        """
        runner = CliRunner()
        result = runner.invoke(agent, ["--json"])
        payload = json.loads(result.stdout.strip())
        assert set(payload.keys()) == EXPECTED_PAYLOAD_KEYS

    def test_no_interactive_without_prompt_exits_2(self):
        runner = CliRunner()
        result = runner.invoke(agent, ["--no-interactive"])
        assert result.exit_code == 2
        # Plain text on stderr, not JSON, since --json wasn't requested
        assert "prompt" in (result.stderr or result.output).lower()

    def test_json_emits_payload_on_success(self):
        runner = CliRunner()
        fake_result = {
            "run_id": "deadbeef0001",
            "mode": "auto",
            "script_path": None,
            "usage": {"total_cost": 0.0},
        }
        with patch("reverse_api.cli.run_agent_capture", return_value=fake_result):
            result = runner.invoke(agent, ["--json", "-p", "capture the X api"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "ok"
        assert payload["run_id"] == "deadbeef0001"
        assert payload["prompt"] == "capture the X api"

    def test_json_emits_error_payload_on_exception(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture", side_effect=RuntimeError("boom")):
            result = runner.invoke(agent, ["--json", "-p", "x"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["error"] == "boom"


class TestListJsonEmpty:
    """`list --json` should emit a JSON array even when there is no history."""

    def test_empty_history_emits_empty_array(self, tmp_path):
        runner = CliRunner()
        # Repoint session_manager.history to empty list for the test
        with patch("reverse_api.cli.session_manager") as sm:
            sm.history = []
            result = runner.invoke(list_runs, ["--json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout.strip()) == []


class TestShowJsonNotFound:
    """`show <id> --json` should emit a structured error and exit non-zero."""

    def test_unknown_run_id_emits_error(self):
        runner = CliRunner()
        with patch("reverse_api.cli.session_manager") as sm:
            sm.get_run.return_value = None
            sm.history = []
            result = runner.invoke(show_run, ["doesnotexist", "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert "error" in payload
        assert payload["run_id"] == "doesnotexist"


# ---------------------------------------------------------------------------
# `run` command: --no-interactive and --auto-install behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_script_env(tmp_path):
    """Fake a run with multiple .py scripts on disk so the picker would normally fire."""
    history_path = tmp_path / "history.json"
    sm = SessionManager(history_path)
    sm.add_run(
        "abc123def456",
        "capture the ashby jobs api",
        mode="manual",
        paths={"script_path": "/scripts/abc123def456/api_client.py"},
    )
    scripts_dir = tmp_path / "scripts" / "abc123def456"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "api_client.py").write_text("print('client')")
    (scripts_dir / "example_usage.py").write_text("print('example')")

    patches = [
        patch("reverse_api.cli.session_manager", sm),
        patch("reverse_api.cli.config_manager", MagicMock(get=MagicMock(return_value=None))),
        patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path),
    ]
    for p in patches:
        p.start()
    try:
        yield tmp_path, sm
    finally:
        for p in patches:
            p.stop()


class TestRunCommandNonInteractive:
    """`run` should never block on questionary when --no-interactive or --auto-install is set."""

    def test_multiple_scripts_with_no_interactive_errors(self, multi_script_env):
        runner = CliRunner()
        with patch("questionary.select") as mock_select:
            result = runner.invoke(main, ["run", "abc123def456", "--no-interactive"])
        assert result.exit_code != 0
        # Picker must NOT have been opened
        mock_select.assert_not_called()
        assert "multiple scripts" in result.output.lower() or "available" in result.output.lower()

    def test_multiple_scripts_with_auto_install_errors_on_picker(self, multi_script_env):
        """--auto-install also implies non-interactive for the picker."""
        runner = CliRunner()
        with patch("questionary.select") as mock_select:
            result = runner.invoke(main, ["run", "abc123def456", "--auto-install"])
        assert result.exit_code != 0
        mock_select.assert_not_called()

    def test_no_interactive_with_file_flag_runs(self, multi_script_env):
        """--file disambiguates and the script runs without prompting."""
        runner = CliRunner()
        ok = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=ok) as mock_sub, patch("questionary.select") as mock_select:
            result = runner.invoke(
                main, ["run", "abc123def456", "--file", "api_client.py", "--no-interactive"]
            )
        assert result.exit_code == 0
        mock_select.assert_not_called()
        assert mock_sub.called

    def test_auto_install_skips_questionary_confirm(self, multi_script_env):
        """When the script raises ModuleNotFoundError, --auto-install skips the confirm prompt."""
        runner = CliRunner()
        # First subprocess.run returns missing-module error; subsequent ones (venv setup, pip install, retry)
        # all succeed.
        first = MagicMock(returncode=1, stdout="", stderr="ModuleNotFoundError: No module named 'foo'")
        ok = MagicMock(returncode=0, stdout="", stderr="")

        def fake_subprocess(cmd, *args, **kwargs):
            # Detect the script execution call by looking for the .py path
            cmd_str = " ".join(str(c) for c in cmd)
            if cmd_str.endswith("api_client.py") or "api_client.py" in cmd_str:
                # First and second invocation of the script path
                fake_subprocess.script_calls += 1
                if fake_subprocess.script_calls == 1:
                    return first
            return ok

        fake_subprocess.script_calls = 0

        with patch("subprocess.run", side_effect=fake_subprocess), patch("questionary.confirm") as mock_confirm:
            result = runner.invoke(
                main, ["run", "abc123def456", "--file", "api_client.py", "--auto-install"]
            )
        # questionary.confirm must never have been called
        mock_confirm.assert_not_called()
        # Final exit code should be from the retry (success)
        assert result.exit_code == 0

    def test_no_interactive_skips_confirm_and_does_not_install(self, multi_script_env):
        """--no-interactive (without --auto-install) must NOT install missing deps; it surfaces the failure."""
        runner = CliRunner()
        first = MagicMock(returncode=1, stdout="", stderr="ModuleNotFoundError: No module named 'foo'")
        ok = MagicMock(returncode=0, stdout="", stderr="")

        def fake_subprocess(cmd, *args, **kwargs):
            cmd_str = " ".join(str(c) for c in cmd)
            if "api_client.py" in cmd_str:
                fake_subprocess.script_calls += 1
                if fake_subprocess.script_calls == 1:
                    return first
            # pip install must NOT happen — assert it
            if "pip" in cmd_str and "install" in cmd_str and "foo" in cmd_str:
                pytest.fail("pip should not have been called to install 'foo' under --no-interactive")
            return ok

        fake_subprocess.script_calls = 0

        with patch("subprocess.run", side_effect=fake_subprocess), patch("questionary.confirm") as mock_confirm:
            result = runner.invoke(
                main, ["run", "abc123def456", "--file", "api_client.py", "--no-interactive"]
            )
        mock_confirm.assert_not_called()
        # Exit propagates the original failure
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Agent --json: interruption + stdout-purity
# ---------------------------------------------------------------------------


class TestAgentJsonInterruption:
    def test_keyboard_interrupt_emits_error_payload(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture", side_effect=KeyboardInterrupt):
            result = runner.invoke(agent, ["--json", "-p", "x"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["error"] == "interrupted"

    def test_inner_keyboard_interrupt_does_not_silently_succeed(self):
        """When run_agent_capture returns a dict with `error: "interrupted"` (the
        scenario where KeyboardInterrupt is caught inside run_auto_capture rather
        than propagating up), the agent payload must report status=error.

        Regression for cubic-dev-ai PR #61 review (P1).
        """
        runner = CliRunner()
        captured = {
            "run_id": "abc12345",
            "mode": "auto",
            "script_path": None,
            "usage": {},
            "error": "interrupted",
        }
        with patch("reverse_api.cli.run_agent_capture", return_value=captured):
            result = runner.invoke(agent, ["--json", "-p", "x"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["error"] == "interrupted"
        assert payload["run_id"] == "abc12345"


class TestAgentJsonStdoutPurity:
    """Stdout should contain exactly one JSON line; Rich noise must go to stderr."""

    def test_rich_console_output_does_not_contaminate_stdout(self):
        from reverse_api.cli import console as cli_console

        # Click 8.2+ separates stdout/stderr by default
        runner = CliRunner()

        def fake_capture(**kwargs):
            cli_console.print("noisy human-readable status")
            return {"run_id": "abc", "mode": "auto", "script_path": None, "usage": {}}

        with patch("reverse_api.cli.run_agent_capture", side_effect=fake_capture):
            result = runner.invoke(agent, ["--json", "-p", "x"])

        assert result.exit_code == 0
        # stdout is exactly one JSON object — nothing else
        stdout = result.stdout.strip()
        payload = json.loads(stdout)
        assert payload["status"] == "ok"
        assert "noisy" not in stdout
        # The noise landed on stderr instead
        assert "noisy" in result.stderr
