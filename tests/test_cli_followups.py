"""Tests for the issue #62 follow-up items.

Covers:
1. TTY-detect at REPL entry (no subcommand + non-TTY stdin → exit 2 + help)
2. `engineer --json` / `--no-interactive` parity with `agent --json`
"""

import json
import subprocess
from unittest.mock import patch

from click.testing import CliRunner

from reverse_api.cli import (
    AGENT_JSON_SCHEMA_VERSION,
    _build_engineer_payload,
    engineer,
    main,
)

EXPECTED_ENGINEER_KEYS = {
    "schema_version",
    "status",
    "run_id",
    "prompt",
    "fresh",
    "script_path",
    "usage",
    "error",
    "error_kind",
}


# ---------------------------------------------------------------------------
# Item #1: TTY-detect at REPL entry
# ---------------------------------------------------------------------------


class TestTtyDetectionAtReplEntry:
    """Without a TTY and no subcommand, the REPL must NOT block on prompt_toolkit."""

    def test_no_tty_no_subcommand_exits_2(self):
        """End-to-end: invoke the installed binary with stdin redirected from /dev/null."""
        result = subprocess.run(
            ["uv", "run", "reverse-api-engineer"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        assert "stdin is not a TTY" in result.stderr
        # Help is printed too so a wrapper can self-discover the subcommands
        assert "agent" in result.stderr
        assert "engineer" in result.stderr

    def test_no_tty_with_subcommand_does_not_trip(self):
        """Subcommands work fine without a TTY (this is the whole point of agent --json)."""
        result = subprocess.run(
            ["uv", "run", "reverse-api-engineer", "list", "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # list --json on empty history should succeed with []
        assert result.returncode == 0
        # Nothing about TTY in the output
        assert "TTY" not in result.stderr


# ---------------------------------------------------------------------------
# Item #2: engineer --json
# ---------------------------------------------------------------------------


class TestBuildEngineerPayload:
    """Stable shape for the `engineer --json` payload."""

    def test_success_shape(self):
        payload = _build_engineer_payload(
            {
                "script_path": "/abs/api_client.py",
                "usage": {"input_tokens": 1, "output_tokens": 2, "total_cost": 0.001},
            },
            run_id="abc123",
            prompt="add pagination",
            fresh=False,
        )
        assert payload["schema_version"] == AGENT_JSON_SCHEMA_VERSION
        assert payload["status"] == "ok"
        assert payload["run_id"] == "abc123"
        assert payload["prompt"] == "add pagination"
        assert payload["fresh"] is False
        assert payload["script_path"] == "/abs/api_client.py"
        # `total_cost` (legacy/Copilot key) is normalized to `total_cost_usd`
        assert payload["usage"]["total_cost_usd"] == 0.001
        assert payload["usage"]["raw"]["total_cost"] == 0.001
        assert payload["error"] is None
        assert payload["error_kind"] is None
        assert set(payload.keys()) == EXPECTED_ENGINEER_KEYS

    def test_none_result_is_error(self):
        payload = _build_engineer_payload(None, run_id="abc", prompt=None, fresh=False)
        assert payload["status"] == "error"
        assert payload["error"]
        assert payload["error_kind"] == "engine_failure"
        assert set(payload.keys()) == EXPECTED_ENGINEER_KEYS

    def test_explicit_error_overrides(self):
        payload = _build_engineer_payload(
            {"script_path": "/x.py"}, run_id="abc", prompt=None, fresh=False, error="boom"
        )
        assert payload["status"] == "error"
        assert payload["error"] == "boom"

    def test_inner_error_propagates(self):
        payload = _build_engineer_payload(
            {"error": "engine crashed"}, run_id="abc", prompt=None, fresh=False
        )
        assert payload["status"] == "error"
        assert payload["error"] == "engine crashed"


class TestEngineerCommandJson:
    """`engineer` click command --json wiring."""

    def test_json_emits_payload_on_success(self):
        runner = CliRunner()
        fake_result = {"script_path": "/abs/api_client.py", "usage": {"total_cost": 0.0}}
        with patch("reverse_api.cli.run_engineer", return_value=fake_result):
            result = runner.invoke(engineer, ["abc123", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "ok"
        assert payload["run_id"] == "abc123"
        assert payload["script_path"] == "/abs/api_client.py"
        assert set(payload.keys()) == EXPECTED_ENGINEER_KEYS

    def test_json_emits_error_on_not_found(self):
        runner = CliRunner()
        # run_engineer returns None when the run can't be located
        with patch("reverse_api.cli.run_engineer", return_value=None):
            result = runner.invoke(engineer, ["doesnotexist", "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["run_id"] == "doesnotexist"
        assert payload["error"]
        assert set(payload.keys()) == EXPECTED_ENGINEER_KEYS

    def test_json_emits_error_on_keyboard_interrupt(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", side_effect=KeyboardInterrupt):
            result = runner.invoke(engineer, ["abc123", "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["error"] == "interrupted"

    def test_json_emits_error_on_exception(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", side_effect=RuntimeError("boom")):
            result = runner.invoke(engineer, ["abc123", "--json"])
        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["status"] == "error"
        assert payload["error"] == "boom"

    def test_prompt_without_fresh_threaded_as_additional(self):
        """--prompt without --fresh must reach run_engineer as additional_instructions
        even on the JSON path (regression for the cubic-dev-ai catch on PR #63)."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}) as mock_run:
            result = runner.invoke(engineer, ["abc123", "--json", "-p", "add pagination"])
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] is None
        assert kwargs["additional_instructions"] == "add pagination"
        assert kwargs["is_fresh"] is False

    def test_fresh_with_prompt_threaded_as_main(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}) as mock_run:
            result = runner.invoke(
                engineer, ["abc123", "--json", "--fresh", "-p", "extract auth"]
            )
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] == "extract auth"
        assert kwargs["additional_instructions"] is None
        assert kwargs["is_fresh"] is True

    def test_no_interactive_flag_accepted(self):
        """--no-interactive is reserved for symmetry; should not crash."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}):
            result = runner.invoke(engineer, ["abc123", "--no-interactive"])
        assert result.exit_code == 0, result.output


class TestSchemaV2Normalization:
    """v2 helpers: _normalize_usage, _classify_error, --json-schema-version."""

    def test_normalize_usage_picks_stable_keys(self):
        """Claude SDK emits cache_creation_input_tokens / estimated_cost_usd;
        Copilot/OpenCode use different keys. Normalization gives a stable
        subset and parks everything under .raw."""
        from reverse_api.cli import _normalize_usage

        out = _normalize_usage({
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 200,
            "estimated_cost_usd": 0.05,
            "service_tier": "standard",
            "iterations": [],
        })
        assert out["input_tokens"] == 10
        assert out["output_tokens"] == 20
        assert out["cache_write_tokens"] == 100
        assert out["cache_read_tokens"] == 200
        assert out["total_cost_usd"] == 0.05
        # SDK extras are preserved under raw, not promoted to top level
        assert out["raw"]["service_tier"] == "standard"
        assert out["raw"]["iterations"] == []
        assert "service_tier" not in out  # stable subset only
        assert "iterations" not in out

    def test_normalize_usage_alt_legacy_keys(self):
        """`total_cost` (Copilot) and direct `cache_read_tokens` (already-normalized
        input) map cleanly through the same pipeline."""
        from reverse_api.cli import _normalize_usage

        out = _normalize_usage({"total_cost": 0.42, "cache_read_tokens": 5})
        assert out["total_cost_usd"] == 0.42
        assert out["cache_read_tokens"] == 5

    def test_normalize_usage_empty(self):
        from reverse_api.cli import _normalize_usage

        assert _normalize_usage(None) == {}
        assert _normalize_usage({}) == {}
        assert _normalize_usage("not a dict") == {}

    def test_classify_error_kinds(self):
        from reverse_api.cli import _classify_error

        assert _classify_error(None) is None
        assert _classify_error(KeyboardInterrupt()) == "interrupted"
        assert _classify_error(PermissionError("nope")) == "permission_denied"
        assert _classify_error(ConnectionError("DNS failed")) == "network"
        assert _classify_error(TimeoutError("timed out")) == "network"
        assert _classify_error("[Errno 13] Permission denied: '/x'") == "permission_denied"
        assert _classify_error("--prompt is required in non-interactive/--json mode") == "misuse"
        assert _classify_error("agent capture produced no run") == "engine_failure"
        assert _classify_error("connection refused") == "network"
        assert _classify_error("totally unrecognized message") == "unknown"
        # Caller can override the default
        assert _classify_error("totally unrecognized message", default="engine_failure") == "engine_failure"

    def test_misuse_payload_has_misuse_kind(self):
        """`agent --json` without --prompt → error_kind=misuse (not unknown)."""
        from reverse_api.cli import agent

        runner = CliRunner()
        result = runner.invoke(agent, ["--json"])
        payload = json.loads(result.stdout.strip())
        assert payload["error_kind"] == "misuse"

    def test_keyboard_interrupt_payload_has_interrupted_kind(self):
        from reverse_api.cli import agent

        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture", side_effect=KeyboardInterrupt):
            result = runner.invoke(agent, ["--json", "-p", "x"])
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["error_kind"] == "interrupted"
        assert payload["error"] == "interrupted"

    def test_permission_error_payload_has_permission_denied_kind(self):
        from reverse_api.cli import agent

        runner = CliRunner()
        with patch(
            "reverse_api.cli.run_agent_capture",
            side_effect=PermissionError(13, "Permission denied", "/forbidden"),
        ):
            result = runner.invoke(agent, ["--json", "-p", "x"])
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["error_kind"] == "permission_denied"


class TestJsonSchemaVersionFlag:
    """`--json-schema-version` exposes the version a wrapper can gate on."""

    def test_root_flag_emits_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--json-schema-version"])
        assert result.exit_code == 0
        from reverse_api.cli import AGENT_JSON_SCHEMA_VERSION as v
        assert result.stdout.strip() == str(v)

    def test_root_flag_advertised_in_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--json-schema-version" in result.output


class TestAgentDryRun:
    """`agent --dry-run` validates without launching the browser."""

    def test_dry_run_ok_path(self, tmp_path):
        """All checks pass → status=ok, exit 0, full payload + checks array."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        # Patch config_manager so we don't depend on the user's real config
        with patch("reverse_api.cli.config_manager") as cm, \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}, clear=False):
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "claude_code_model": "claude-sonnet-4-6",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(
                agent_cmd, ["--dry-run", "-p", "fetch jobs", "-u", "https://example.com"]
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout.strip())
        assert payload["status"] == "ok"
        assert payload["mode"] == "dry-run"
        assert payload["run_id"] is None
        assert payload["error"] is None
        assert payload["would_run"]["agent_provider"] == "auto"
        assert payload["would_run"]["sdk"] == "claude"
        assert payload["would_run"]["headless"] is False
        # Checks include prompt, url, agent_provider, sdk, node, output_dir
        check_names = {c["name"] for c in payload["checks"]}
        assert "prompt" in check_names
        assert "url" in check_names
        assert "agent_provider" in check_names
        assert "node" in check_names
        assert "output_dir" in check_names

    def test_dry_run_missing_prompt_is_misuse(self, tmp_path):
        """Missing --prompt → error_kind=misuse, exit 1, no browser launched."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["status"] == "error"
        assert payload["error_kind"] == "misuse"
        assert any(c["name"] == "prompt" and c["status"] == "error" for c in payload["checks"])

    def test_dry_run_bad_url_is_misuse(self, tmp_path):
        """A url that doesn't start with http(s):// is flagged."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run", "-p", "x", "-u", "ftp://nope"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["error_kind"] == "misuse"
        assert any(c["name"] == "url" and c["status"] == "error" for c in payload["checks"])

    def test_dry_run_unwritable_output_dir_is_config_invalid(self):
        """Unwritable output_dir → error_kind=config_invalid, not misuse."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": "/sys/forbidden",
            }.get(key, default)
            result = runner.invoke(
                agent_cmd, ["--dry-run", "-p", "x", "--output-dir", "/sys/forbidden"]
            )

        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["error_kind"] == "config_invalid"
        assert any(c["name"] == "output_dir" and c["status"] == "error" for c in payload["checks"])

    def test_dry_run_does_not_launch_browser(self, tmp_path):
        """--dry-run must NOT call run_agent_capture (no browser, no LLM, no cost)."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm, \
             patch("reverse_api.cli.run_agent_capture") as mock_run:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": str(tmp_path),
            }.get(key, default)
            runner.invoke(agent_cmd, ["--dry-run", "-p", "x", "-u", "https://example.com"])
        mock_run.assert_not_called()

    def test_dry_run_help_mentions_implies_json(self):
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        result = runner.invoke(agent_cmd, ["--help"])
        assert "--dry-run" in result.output
        # Click reflows whitespace, so "Implies\n--json" or "Implies --json"
        assert "Implies" in result.output and "--json" in result.output

    def test_dry_run_checks_npx_separately_from_node(self, tmp_path):
        """cubic-dev-ai PR #67 review (P2): MCP servers shell out to `npx`,
        so dry-run must check npx availability — not just node — otherwise
        a minimal Docker image with node-but-no-npx passes dry-run and then
        fails the real run."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()

        # Pretend npx is missing while node is present
        def fake_which(name):
            if name == "node":
                return "/usr/bin/node"
            if name == "npx":
                return None
            return None

        with patch("reverse_api.cli.config_manager") as cm, \
             patch("shutil.which", side_effect=fake_which):
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run", "-p", "x"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout.strip())
        assert payload["error_kind"] == "config_invalid"
        npx_check = next(c for c in payload["checks"] if c["name"] == "npx")
        assert npx_check["status"] == "error"
        assert "npx not found" in npx_check["message"]

    def test_dry_run_probe_does_not_clobber_existing_files(self, tmp_path):
        """cubic-dev-ai PR #67 review (P2): a fixed probe filename like
        `.dry_run_write_probe` could legitimately exist in a user's output
        dir and would be deleted by the probe. We use a unique filename
        with PID + random hex so collisions are astronomically unlikely,
        and refuse to touch any path that already exists."""
        from reverse_api.cli import agent as agent_cmd

        # Pre-populate the output dir with a file that would collide with
        # the OLD fixed probe name. The dry-run must not delete it.
        canary = tmp_path / ".dry_run_write_probe"
        canary.write_text("user data — do not delete")

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "claude",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run", "-p", "x"])

        assert result.exit_code == 0, result.output
        # The user's pre-existing file is untouched
        assert canary.exists()
        assert canary.read_text() == "user data — do not delete"

    def test_dry_run_resolves_correct_model_per_sdk(self, tmp_path):
        """cubic-dev-ai PR #67 review (P2): when sdk=opencode the live agent
        uses `opencode_model`, not `claude_code_model`. would_run.model must
        reflect what would actually run, otherwise the manifest lies."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()

        # Configure opencode SDK with a custom opencode_model
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "opencode",
                "opencode_model": "claude-opus-4-6-custom",
                "claude_code_model": "claude-sonnet-4-6-irrelevant",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run", "-p", "x"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout.strip())
        assert payload["would_run"]["sdk"] == "opencode"
        assert payload["would_run"]["model"] == "claude-opus-4-6-custom"
        # And NOT the claude_code_model that the old code would have grabbed
        assert "irrelevant" not in payload["would_run"]["model"]

    def test_dry_run_copilot_model_resolution(self, tmp_path):
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.config_manager") as cm:
            cm.get.side_effect = lambda key, default=None: {
                "agent_provider": "auto",
                "sdk": "copilot",
                "copilot_model": "gpt-5-custom",
                "output_dir": str(tmp_path),
            }.get(key, default)
            result = runner.invoke(agent_cmd, ["--dry-run", "-p", "x"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout.strip())
        assert payload["would_run"]["sdk"] == "copilot"
        assert payload["would_run"]["model"] == "gpt-5-custom"


class TestRootHelpMentionsScripted:
    """Item #6 partial: root --help should advertise scripted features."""

    def test_root_help_mentions_json_and_no_interactive(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--json" in result.output
        assert "--no-interactive" in result.output


# ---------------------------------------------------------------------------
# Follow-up suppression in non-interactive mode
# ---------------------------------------------------------------------------


class TestFollowUpPromptSuppressed:
    """Regression for chatgpt-codex-connector PR #65 review (P2):

    `BaseEngineer._prompt_follow_up()` blocks on `input("  > ")` after the
    first generation. In --json / --no-interactive mode the conversation loop
    must terminate immediately so stdin is never read; otherwise scripted
    invocations like `engineer <run_id> --json | jq` hang before emitting the
    payload.
    """

    def test_prompt_follow_up_returns_none_when_not_interactive(self, tmp_path):
        """The base engineer's follow-up prompt short-circuits when
        interactive=False, without ever touching stdin."""
        import asyncio

        from reverse_api.base_engineer import BaseEngineer

        class _Eng(BaseEngineer):
            def _build_prompts(self):
                return ("", "")

            async def analyze_and_generate(self):
                return None

        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_sm:
                    mock_sm.return_value.get_run.return_value = None
                    eng = _Eng(
                        run_id="test123",
                        har_path=har_path,
                        prompt="x",
                        interactive=False,
                    )

        # Patch input() at the builtin level — the test fails loudly if it's
        # ever reached, proving the short-circuit happens before stdin access.
        def _explode(*_args, **_kwargs):
            raise AssertionError("input() must not be called when interactive=False")

        with patch("builtins.input", side_effect=_explode):
            result = asyncio.run(eng._prompt_follow_up())

        assert result is None

    def test_engineer_default_interactive_true(self, tmp_path):
        """Sanity: the default value of interactive on BaseEngineer is True
        so existing REPL UX is unchanged."""
        from reverse_api.base_engineer import BaseEngineer

        class _Eng(BaseEngineer):
            def _build_prompts(self):
                return ("", "")

            async def analyze_and_generate(self):
                return None

        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager") as mock_sm:
                    mock_sm.return_value.get_run.return_value = None
                    eng = _Eng(run_id="test123", har_path=har_path, prompt="x")
        assert eng.interactive is True

    def test_engineer_command_threads_interactive_through_run_engineer(self):
        """`engineer --json` must pass interactive=False to run_engineer so
        BaseEngineer drops the follow-up loop in the SDK."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}) as mock_run:
            result = runner.invoke(engineer, ["abc123", "--json"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["interactive"] is False

    def test_engineer_command_no_interactive_threads_through(self):
        """`engineer --no-interactive` (without --json) also disables follow-up."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}) as mock_run:
            result = runner.invoke(engineer, ["abc123", "--no-interactive"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["interactive"] is False

    def test_engineer_default_threads_interactive_true(self):
        """Without flags, run_engineer is called with interactive=True
        (preserves the current REPL UX)."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer", return_value={"script_path": "/x.py"}) as mock_run:
            result = runner.invoke(engineer, ["abc123"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["interactive"] is True

    def test_agent_command_threads_interactive_through_run_agent_capture(self):
        """`agent --json` must propagate interactive=False so
        ClaudeAutoEngineer drops the follow-up loop too (same code path)."""
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch(
            "reverse_api.cli.run_agent_capture",
            return_value={"run_id": "abc", "mode": "auto", "script_path": None, "usage": {}},
        ) as mock_run:
            result = runner.invoke(agent_cmd, ["--json", "-p", "x"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["interactive"] is False


# ---------------------------------------------------------------------------
# --headless flag (CI / VPS / scripted)
# ---------------------------------------------------------------------------


class TestHeadlessFlag:
    """`--headless` wires through to auto-engineer constructors (agent only —
    manual mode is intentionally human-only and rejects --headless)."""

    def test_manual_rejects_headless_flag(self):
        """`manual --headless` must fail: manual mode requires a human and a
        visible browser; agents should use `agent --headless` instead."""
        from reverse_api.cli import manual as manual_cmd

        runner = CliRunner()
        result = runner.invoke(manual_cmd, ["-p", "x", "-u", "https://example.com", "--headless"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "--headless" in result.output

    def test_manual_help_mentions_human_only(self):
        """`manual --help` must make it explicit that the mode requires a
        human and is not scriptable (so agents inspecting --help self-route
        to `agent` instead)."""
        from reverse_api.cli import manual as manual_cmd

        runner = CliRunner()
        result = runner.invoke(manual_cmd, ["--help"])
        assert result.exit_code == 0
        out = result.output.lower()
        assert "human" in out
        assert "agent" in out  # tells the agent where to go instead

    def test_agent_command_threads_headless(self):
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture", return_value={"run_id": "x", "mode": "auto"}) as mock_run:
            result = runner.invoke(agent_cmd, ["-p", "x", "--json", "--headless"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["headless"] is True

    def test_agent_default_headless_false(self):
        from reverse_api.cli import agent as agent_cmd

        runner = CliRunner()
        with patch("reverse_api.cli.run_agent_capture", return_value={"run_id": "x", "mode": "auto"}) as mock_run:
            result = runner.invoke(agent_cmd, ["-p", "x", "--json"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["headless"] is False


class TestHeadlessMcpConfig:
    """ClaudeAutoEngineer._get_mcp_config arg construction for headed vs headless."""

    def _make(self, agent_provider: str, headless: bool, tmp_path):
        """Build a ClaudeAutoEngineer without invoking heavy init paths."""
        from reverse_api.auto_engineer import ClaudeAutoEngineer

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path):
            with patch("reverse_api.base_engineer.MessageStore"):
                with patch("reverse_api.base_engineer.SessionManager"):
                    with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path):
                        eng = ClaudeAutoEngineer(
                            run_id="r",
                            prompt="x",
                            model="claude-sonnet-4-6",
                            agent_provider=agent_provider,
                            headless=headless,
                        )
        return eng

    def test_chrome_mcp_headed_uses_autoconnect(self, tmp_path):
        eng = self._make("chrome-mcp", headless=False, tmp_path=tmp_path)
        _, cfg = eng._get_mcp_config()
        assert "--autoConnect" in cfg["args"]
        assert "--headless" not in cfg["args"]

    def test_chrome_mcp_headless_drops_autoconnect_adds_headless(self, tmp_path):
        eng = self._make("chrome-mcp", headless=True, tmp_path=tmp_path)
        _, cfg = eng._get_mcp_config()
        assert "--autoConnect" not in cfg["args"], "auto-connect cannot work without a real headed Chrome"
        assert "--headless" in cfg["args"]

    def test_playwright_headless_adds_flag(self, tmp_path):
        eng = self._make("auto", headless=True, tmp_path=tmp_path)
        _, cfg = eng._get_mcp_config()
        assert "--headless" in cfg["args"]

    def test_playwright_headed_no_headless_flag(self, tmp_path):
        eng = self._make("auto", headless=False, tmp_path=tmp_path)
        _, cfg = eng._get_mcp_config()
        assert "--headless" not in cfg["args"]
