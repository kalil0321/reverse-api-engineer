"""Tests for opencode_ui.py - OpenCodeUI."""

from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from reverse_api.opencode_ui import OpenCodeUI


class TestOpenCodeUI:
    """Test OpenCodeUI class."""

    def _make_ui(self, verbose=True):
        """Create an OpenCodeUI with a string buffer console."""
        console = Console(file=StringIO(), no_color=True)
        ui = OpenCodeUI(console=console, verbose=verbose)
        return ui, console

    def test_init(self):
        """UI initializes with correct defaults."""
        ui, _ = self._make_ui()
        assert ui.verbose is True
        assert ui._live is None
        assert ui._current_text == ""
        assert ui._current_tool is None
        assert ui._session_status == "idle"
        assert ui._tools_used == []

    def test_header(self):
        """Header displays info."""
        ui, console = self._make_ui()
        ui.header("run123", "test prompt", "claude-opus-4-5", "opencode")
        output = console.file.getvalue()
        assert "run123" in output
        assert "test prompt" in output

    def test_header_no_sdk(self):
        """Header without sdk."""
        ui, console = self._make_ui()
        ui.header("run123", "test prompt", "claude-opus-4-5")
        output = console.file.getvalue()
        assert "run123" in output

    def test_start_analysis(self):
        """Start analysis shows message."""
        ui, console = self._make_ui()
        ui.start_analysis()
        output = console.file.getvalue()
        assert "decoding" in output

    def test_health_check(self):
        """Health check shows server version."""
        ui, console = self._make_ui()
        ui.health_check({"version": "1.2.3"})
        output = console.file.getvalue()
        assert "1.2.3" in output

    def test_session_created(self):
        """Session created shows truncated ID."""
        ui, console = self._make_ui()
        ui.session_created("abc123def456ghi789")
        output = console.file.getvalue()
        assert "abc123def456ghi7" in output

    def test_model_info(self):
        """Model info shows provider/model."""
        ui, console = self._make_ui()
        ui.model_info("anthropic", "claude-sonnet-4-5")
        output = console.file.getvalue()
        assert "anthropic" in output
        assert "claude-sonnet-4-5" in output

    def test_start_and_stop_streaming(self):
        """Streaming can be started and stopped."""
        ui, _ = self._make_ui()
        ui.start_streaming()
        assert ui._live is not None
        ui.stop_streaming()
        assert ui._live is None

    def test_stop_streaming_when_not_started(self):
        """Stopping when not streaming is safe."""
        ui, _ = self._make_ui()
        ui.stop_streaming()  # Should not raise

    def test_update_text_with_delta(self):
        """Text update with delta appends."""
        ui, _ = self._make_ui()
        ui.update_text("", delta="Hello ")
        assert ui._current_text == "Hello "
        ui.update_text("", delta="World")
        assert ui._current_text == "Hello World"

    def test_update_text_without_delta(self):
        """Text update without delta replaces."""
        ui, _ = self._make_ui()
        ui.update_text("Full text replacement")
        assert ui._current_text == "Full text replacement"

    def test_tool_start(self):
        """Tool start updates state and displays."""
        ui, console = self._make_ui()
        ui.tool_start("Read", {"path": "/test.py"})
        assert ui._current_tool == "Read"
        assert ui._tool_status == "running"
        assert "Read" in ui._tools_used

    def test_tool_result_success(self):
        """Tool result success clears current tool."""
        ui, _ = self._make_ui()
        ui._current_tool = "Read"
        ui.tool_result("Read", is_error=False)
        assert ui._current_tool is None
        assert ui._tool_status == "completed"

    def test_tool_result_error(self):
        """Tool result error shows error."""
        ui, console = self._make_ui()
        ui.tool_result("Bash", is_error=True, output="command not found")
        output = console.file.getvalue()
        assert "failed" in output

    def test_step_finish(self):
        """Step finish shows usage stats."""
        ui, console = self._make_ui()
        ui.step_finish(
            0.05,
            {"input": 1000, "output": 500, "reasoning": 200, "cache": {"read": 100, "write": 50}},
        )
        output = console.file.getvalue()
        assert "step" in output
        assert "0.05" in output

    def test_step_finish_low_cost(self):
        """Step finish with low cost shows just tokens."""
        ui, console = self._make_ui()
        ui.step_finish(0.0001, {"input": 100, "output": 50, "reasoning": 0, "cache": {"read": 0, "write": 0}})
        output = console.file.getvalue()
        assert "step" in output

    def test_step_finish_no_tokens(self):
        """Step finish with no tokens doesn't display."""
        ui, console = self._make_ui()
        ui.step_finish(0, {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}})
        output = console.file.getvalue()
        assert "step" not in output

    def test_session_summary(self):
        """Session summary shows usage."""
        ui, console = self._make_ui()
        ui.session_summary({
            "input_tokens": 10000,
            "output_tokens": 5000,
            "reasoning_tokens": 2000,
            "cache_read_tokens": 1000,
            "cache_creation_tokens": 500,
            "cost": 0.15,
        })
        output = console.file.getvalue()
        assert "10,000" in output
        assert "5,000" in output
        assert "0.15" in output

    def test_session_summary_empty(self):
        """Session summary with no usage is silent."""
        ui, console = self._make_ui()
        ui.session_summary({})
        output = console.file.getvalue()
        assert "Session Summary" not in output

    def test_session_status(self):
        """Session status updates internal state."""
        ui, _ = self._make_ui()
        ui.session_status("busy")
        assert ui._session_status == "busy"

    def test_thinking_no_live(self):
        """Thinking without live display shows text."""
        ui, console = self._make_ui()
        ui.thinking("I need to analyze the authentication headers in detail now")
        output = console.file.getvalue()
        assert "analyze" in output

    def test_thinking_short_text_skipped(self):
        """Short thinking text is skipped."""
        ui, console = self._make_ui()
        ui.thinking("ok")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_thinking_non_verbose(self):
        """Non-verbose thinking is skipped."""
        ui, console = self._make_ui(verbose=False)
        ui.thinking("I need to analyze the authentication headers in detail now")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_success(self):
        """Success displays paths."""
        ui, console = self._make_ui()
        ui.success("/output/api_client.py")
        output = console.file.getvalue()
        assert "complete" in output
        assert "api_client.py" in output

    def test_success_with_local_path(self):
        """Success with local path."""
        ui, console = self._make_ui()
        ui.success("/output/api_client.py", "/local/api_client.py")
        output = console.file.getvalue()
        assert "synced" in output

    def test_error_simple(self):
        """Simple error message."""
        ui, console = self._make_ui()
        ui.error("Something went wrong")
        output = console.file.getvalue()
        assert "error" in output
        assert "Something went wrong" in output

    def test_error_rich_markup(self):
        """Error with Rich markup passes through."""
        ui, console = self._make_ui()
        ui.error("[bold red]✗ Error[/bold red]\n  details here")
        output = console.file.getvalue()
        assert "Error" in output

    def test_permission_requested(self):
        """Permission requested shows title."""
        ui, console = self._make_ui()
        ui.permission_requested("file_write", "Write to /output/api_client.py")
        output = console.file.getvalue()
        assert "permission" in output

    def test_permission_approved(self):
        """Permission approved shows type."""
        ui, console = self._make_ui()
        ui.permission_approved("file_write")
        output = console.file.getvalue()
        assert "auto-approved" in output

    def test_todo_updated(self):
        """Todo updated shows status."""
        ui, console = self._make_ui()
        ui.todo_updated([
            {"status": "completed", "content": "Analyze HAR", "activeForm": "Analyzing"},
            {"status": "in_progress", "content": "Generate code", "activeForm": "Generating code"},
            {"status": "pending", "content": "Test output", "activeForm": "Testing"},
        ])
        output = console.file.getvalue()
        assert "1 active" in output
        assert "1 pending" in output
        assert "1 done" in output

    def test_todo_updated_empty(self):
        """Empty todo list is silent."""
        ui, console = self._make_ui()
        ui.todo_updated([])
        output = console.file.getvalue()
        assert "tasks" not in output

    def test_todo_updated_truncates_task(self):
        """Long task content is truncated."""
        ui, console = self._make_ui()
        ui.todo_updated([
            {"status": "in_progress", "content": "x" * 100, "activeForm": "y" * 100},
        ])
        output = console.file.getvalue()
        assert "..." in output

    def test_file_edited(self):
        """File edited shows path."""
        ui, console = self._make_ui()
        ui.file_edited("/output/api_client.py")
        output = console.file.getvalue()
        assert "api_client.py" in output

    def test_session_busy(self):
        """Session busy is a no-op."""
        ui, _ = self._make_ui()
        ui.session_busy()  # Should not raise

    def test_session_idle(self):
        """Session idle is a no-op."""
        ui, _ = self._make_ui()
        ui.session_idle()  # Should not raise

    def test_session_diff(self):
        """Session diff shows file changes."""
        ui, console = self._make_ui()
        ui.session_diff([
            {"file": "a.py", "additions": 10, "deletions": 3},
            {"file": "b.py", "additions": 5, "deletions": 0},
        ])
        output = console.file.getvalue()
        assert "2 files" in output
        assert "+15" in output
        assert "-3" in output

    def test_session_diff_empty(self):
        """Empty diff is silent."""
        ui, console = self._make_ui()
        ui.session_diff([])
        output = console.file.getvalue()
        assert "diff" not in output

    def test_session_compacted(self):
        """Session compacted shows message."""
        ui, console = self._make_ui()
        ui.session_compacted()
        output = console.file.getvalue()
        assert "compacted" in output

    def test_session_retry(self):
        """Session retry shows attempt."""
        ui, console = self._make_ui()
        ui.session_retry(2, "Rate limited")
        output = console.file.getvalue()
        assert "attempt 2" in output
        assert "Rate limited" in output

    def test_session_retry_no_message(self):
        """Session retry with no message shows default."""
        ui, console = self._make_ui()
        ui.session_retry(1, "")
        output = console.file.getvalue()
        assert "retrying" in output

    def test_sync_started(self):
        """Sync started displays."""
        ui, console = self._make_ui()
        ui.sync_started("/local/scripts/test")
        output = console.file.getvalue()
        assert "sync" in output

    def test_sync_flash(self):
        """Sync flash displays."""
        ui, console = self._make_ui()
        ui.sync_flash("Synced api_client.py")
        output = console.file.getvalue()
        assert "Synced" in output

    def test_sync_error(self):
        """Sync error displays."""
        ui, console = self._make_ui()
        ui.sync_error("Permission denied")
        output = console.file.getvalue()
        assert "sync error" in output

    def test_build_display_with_running_tool(self):
        """Build display shows running tool."""
        ui, _ = self._make_ui()
        ui._current_tool = "Read"
        ui._tool_status = "running"
        display = ui._build_display()
        assert "Read" in display.plain
        assert "running" in display.plain

    def test_build_display_no_running_tool(self):
        """Build display empty when no tool running."""
        ui, _ = self._make_ui()
        display = ui._build_display()
        assert display.plain == ""

    def test_update_text_with_live(self):
        """Text update refreshes live display."""
        ui, _ = self._make_ui()
        mock_live = MagicMock()
        ui._live = mock_live
        ui.update_text("test", delta="more")
        mock_live.update.assert_called_once()

    def test_tool_start_with_live(self):
        """Tool start refreshes live display."""
        ui, _ = self._make_ui()
        mock_live = MagicMock()
        ui._live = mock_live
        ui.tool_start("Read", {"file_path": "/test.py"})
        mock_live.update.assert_called_once()

    def test_tool_result_with_live(self):
        """Tool result refreshes live display."""
        ui, _ = self._make_ui()
        mock_live = MagicMock()
        ui._live = mock_live
        ui.tool_result("Read", is_error=False)
        mock_live.update.assert_called_once()

    def test_tool_result_error_with_output(self):
        """Tool result error shows output preview."""
        ui, console = self._make_ui()
        ui.tool_result("Bash", is_error=True, output="command not found\ndetails here")
        output = console.file.getvalue()
        assert "failed" in output
        assert "command not found" in output

    def test_thinking_long_text_truncated(self):
        """Long thinking text is truncated."""
        ui, console = self._make_ui()
        long_text = "x" * 200
        ui.thinking(long_text)
        output = console.file.getvalue()
        assert "..." in output


class TestOpenCodeUISummarizeInput:
    """Test _summarize_input method."""

    def _make_ui(self):
        console = Console(file=StringIO(), no_color=True)
        return OpenCodeUI(console=console)

    def test_read_input(self):
        """Read tool shows path."""
        ui = self._make_ui()
        result = ui._summarize_input("Read", {"file_path": "/test.py"})
        assert "test.py" in result

    def test_file_read_input(self):
        """file_read tool shows path."""
        ui = self._make_ui()
        result = ui._summarize_input("file_read", {"path": "/test.py"})
        assert "test.py" in result

    def test_write_input(self):
        """Write tool shows path with arrow."""
        ui = self._make_ui()
        result = ui._summarize_input("Write", {"file_path": "/test.py"})
        assert "→" in result

    def test_bash_input(self):
        """Bash tool shows command."""
        ui = self._make_ui()
        result = ui._summarize_input("Bash", {"command": "python test.py"})
        assert "python test.py" in result

    def test_glob_input(self):
        """Glob tool shows pattern."""
        ui = self._make_ui()
        result = ui._summarize_input("Glob", {"pattern": "*.py"})
        assert "*.py" in result

    def test_webfetch_input(self):
        """WebFetch tool shows URL."""
        ui = self._make_ui()
        result = ui._summarize_input("WebFetch", {"url": "https://example.com"})
        assert "example.com" in result

    def test_todowrite_input(self):
        """TodoWrite shows count."""
        ui = self._make_ui()
        result = ui._summarize_input("todowrite", {"todos": [1, 2, 3]})
        assert "3 items" in result

    def test_unknown_tool(self):
        """Unknown tool returns empty string."""
        ui = self._make_ui()
        result = ui._summarize_input("UnknownTool", {})
        assert result == ""


class TestOpenCodeUITruncatePath:
    """Test _truncate_path method."""

    def test_short_path(self):
        """Short path not truncated."""
        ui = OpenCodeUI()
        assert ui._truncate_path("/short") == "/short"

    def test_long_path(self):
        """Long path truncated."""
        ui = OpenCodeUI()
        long_path = "/" + "x" * 100
        result = ui._truncate_path(long_path)
        assert result.startswith("...")
        assert len(result) <= 50
