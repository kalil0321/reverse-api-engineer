"""Tests for the `engineer` click command wiring.

Specifically: --prompt and --fresh must combine the way the old `@id <run_id>
[--fresh] <prompt>` REPL syntax did. Without --fresh, --prompt is layered as
*additional instructions* so the captured run's original goal is preserved;
with --fresh, --prompt fully replaces the original goal.

Regression for chatgpt-codex-connector PR #63 review (P2).
"""

from unittest.mock import patch

from click.testing import CliRunner

from reverse_api.cli import engineer


class TestEngineerCommandPromptWiring:
    """`engineer <run_id> [--prompt] [--fresh]` flag combinations."""

    def test_no_prompt_no_fresh(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer") as mock_run:
            result = runner.invoke(engineer, ["abc123"])
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] is None
        assert kwargs["additional_instructions"] is None
        assert kwargs["is_fresh"] is False

    def test_prompt_without_fresh_is_additive(self):
        """Without --fresh, --prompt becomes additional_instructions so the
        run's original prompt is still loaded by run_engineer.
        """
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer") as mock_run:
            result = runner.invoke(engineer, ["abc123", "--prompt", "add pagination"])
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] is None, "must NOT pass user text as the main prompt without --fresh"
        assert kwargs["additional_instructions"] == "add pagination"
        assert kwargs["is_fresh"] is False

    def test_fresh_without_prompt(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer") as mock_run:
            result = runner.invoke(engineer, ["abc123", "--fresh"])
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] is None
        assert kwargs["additional_instructions"] is None
        assert kwargs["is_fresh"] is True

    def test_fresh_with_prompt_replaces_main(self):
        """With --fresh, --prompt fully replaces the run's original goal."""
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer") as mock_run:
            result = runner.invoke(
                engineer, ["abc123", "--fresh", "--prompt", "reverse engineer the auth flow only"]
            )
        assert result.exit_code == 0, result.output
        kwargs = mock_run.call_args.kwargs
        assert kwargs["prompt"] == "reverse engineer the auth flow only"
        assert kwargs["additional_instructions"] is None
        assert kwargs["is_fresh"] is True

    def test_engineer_accepts_model_ids_for_non_claude_sdks(self):
        runner = CliRunner()
        with patch("reverse_api.cli.run_engineer") as mock_run:
            result = runner.invoke(engineer, ["abc123", "--model", "openai/gpt-5.2"])

        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["model"] == "openai/gpt-5.2"
