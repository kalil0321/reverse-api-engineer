"""Tests for tui.py, collector_ui.py, opencode_ui.py - UI modules."""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from reverse_api.tui import (
    THEME_DIM,
    THEME_PRIMARY,
    TOOL_COLORS,
    TOOL_ICONS,
    ClaudeUI,
    display_banner,
    display_footer,
    get_model_choices,
)


class TestClaudeUI:
    """Test ClaudeUI class."""

    def _make_ui(self, verbose=True):
        """Create a ClaudeUI with a string buffer console."""
        console = Console(file=StringIO(), no_color=True)
        ui = ClaudeUI(verbose=verbose)
        ui.console = console
        return ui, console

    def test_init(self):
        """UI initializes with correct defaults."""
        ui = ClaudeUI()
        assert ui.verbose is True
        assert ui._tool_count == 0
        assert ui._tools_used == []

    def test_init_non_verbose(self):
        """UI can be initialized as non-verbose."""
        ui = ClaudeUI(verbose=False)
        assert ui.verbose is False

    def test_header(self):
        """Header displays run info."""
        ui, console = self._make_ui()
        ui.header("run123", "test prompt", "claude-sonnet-4-6", "claude")
        output = console.file.getvalue()
        assert "run123" in output
        assert "test prompt" in output

    def test_header_no_sdk(self):
        """Header without sdk shows model differently."""
        ui, console = self._make_ui()
        ui.header("run123", "test prompt", "claude-sonnet-4-6")
        output = console.file.getvalue()
        assert "run123" in output

    def test_start_analysis(self):
        """Start analysis displays message."""
        ui, console = self._make_ui()
        ui.start_analysis()
        output = console.file.getvalue()
        assert "decoding" in output

    def test_tool_start(self):
        """Tool start increments counter and displays."""
        ui, console = self._make_ui()
        ui.tool_start("Read", {"file_path": "/test/file.py"})
        assert ui._tool_count == 1
        assert "Read" in ui._tools_used

    def test_tool_result_error(self):
        """Tool result error displays error message."""
        ui, console = self._make_ui()
        ui.tool_result("Bash", is_error=True)
        output = console.file.getvalue()
        assert "failed" in output

    def test_tool_result_bash_output(self):
        """Bash tool result shows output."""
        ui, console = self._make_ui()
        ui.tool_result("Bash", is_error=False, output="hello world")
        output = console.file.getvalue()
        assert "hello world" in output

    def test_tool_result_bash_output_truncated(self):
        """Long bash output is truncated."""
        ui, console = self._make_ui()
        long_output = "\n".join([f"line {i}" for i in range(50)])
        ui.tool_result("Bash", is_error=False, output=long_output)
        output = console.file.getvalue()
        assert "more lines" in output

    def test_tool_result_non_verbose(self):
        """Non-verbose mode suppresses bash output."""
        ui, console = self._make_ui(verbose=False)
        ui.tool_result("Bash", is_error=False, output="hello")
        output = console.file.getvalue()
        # Non-verbose doesn't show bash output
        assert "hello" not in output

    def test_thinking_verbose(self):
        """Thinking displays text in verbose mode."""
        ui, console = self._make_ui()
        ui.thinking("I should analyze the authentication headers in the HAR file carefully")
        output = console.file.getvalue()
        assert "analyze" in output

    def test_thinking_short_text_skipped(self):
        """Short thinking text is skipped."""
        ui, console = self._make_ui()
        ui.thinking("ok")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_thinking_non_verbose(self):
        """Non-verbose mode skips thinking."""
        ui, console = self._make_ui(verbose=False)
        ui.thinking("I should analyze the authentication headers in the HAR file carefully")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_thinking_truncation(self):
        """Long thinking text is truncated."""
        ui, console = self._make_ui()
        long_text = "x" * 600
        ui.thinking(long_text)
        output = console.file.getvalue()
        assert "..." in output

    def test_thinking_block_shows_full_block(self):
        ui, console = self._make_ui()
        ui.thinking_block("First paragraph.\n\nSecond paragraph.")
        out = console.file.getvalue()
        assert "First paragraph" in out
        assert "Second paragraph" in out

    def test_thinking_block_skipped_non_verbose(self):
        ui, console = self._make_ui(verbose=False)
        ui.thinking_block("Hidden block text")
        assert console.file.getvalue().strip() == ""

    def test_thinking_block_short_skipped(self):
        ui, console = self._make_ui()
        ui.thinking_block("x")
        assert console.file.getvalue().strip() == ""

    def test_progress(self):
        """Progress displays message."""
        ui, console = self._make_ui()
        ui.progress("Processing HAR...")
        output = console.file.getvalue()
        assert "Processing HAR" in output

    def test_success(self):
        """Success displays paths."""
        ui, console = self._make_ui()
        ui.success("/output/api_client.py")
        output = console.file.getvalue()
        assert "complete" in output
        assert "api_client.py" in output

    def test_success_with_local_path(self):
        """Success shows local path when provided."""
        ui, console = self._make_ui()
        ui.success("/output/api_client.py", "/local/scripts/api_client.py")
        output = console.file.getvalue()
        assert "synced" in output

    def test_error(self):
        """Error displays error message."""
        ui, console = self._make_ui()
        ui.error("Connection refused")
        output = console.file.getvalue()
        assert "error" in output
        assert "Connection refused" in output

    def test_sync_started(self):
        """Sync started displays destination."""
        ui, console = self._make_ui()
        ui.sync_started("/local/scripts/test")
        output = console.file.getvalue()
        assert "sync" in output

    def test_sync_flash(self):
        """Sync flash displays message."""
        ui, console = self._make_ui()
        ui.sync_flash("Synced api_client.py")
        output = console.file.getvalue()
        assert "Synced" in output

    def test_sync_error(self):
        """Sync error displays error."""
        ui, console = self._make_ui()
        ui.sync_error("Permission denied")
        output = console.file.getvalue()
        assert "sync error" in output


class TestSummarizeInput:
    """Test _summarize_input method."""

    def _make_ui(self):
        ui = ClaudeUI()
        return ui

    def test_read_input(self):
        """Read tool shows file path."""
        ui = self._make_ui()
        result = ui._summarize_input("Read", {"file_path": "/test/file.py"})
        assert "file.py" in result

    def test_write_input(self):
        """Write tool shows file path with arrow."""
        ui = self._make_ui()
        result = ui._summarize_input("Write", {"file_path": "/test/file.py"})
        assert "→" in result
        assert "file.py" in result

    def test_edit_input(self):
        """Edit tool shows file path."""
        ui = self._make_ui()
        result = ui._summarize_input("Edit", {"file_path": "/test/file.py"})
        assert "file.py" in result

    def test_bash_input(self):
        """Bash tool shows command."""
        ui = self._make_ui()
        result = ui._summarize_input("Bash", {"command": "python test.py"})
        assert "python test.py" in result

    def test_bash_long_command(self):
        """Long bash command is truncated."""
        ui = self._make_ui()
        result = ui._summarize_input("Bash", {"command": "x" * 100})
        assert "..." in result

    def test_grep_input(self):
        """Grep tool shows pattern."""
        ui = self._make_ui()
        result = ui._summarize_input("Grep", {"pattern": "def test_"})
        assert "def test_" in result

    def test_websearch_input(self):
        """WebSearch shows query."""
        ui = self._make_ui()
        result = ui._summarize_input("WebSearch", {"query": "python api client"})
        assert "python api client" in result

    def test_webfetch_input(self):
        """WebFetch shows URL."""
        ui = self._make_ui()
        result = ui._summarize_input("WebFetch", {"url": "https://example.com"})
        assert "example.com" in result

    def test_unknown_tool(self):
        """Unknown tool returns empty string."""
        ui = self._make_ui()
        result = ui._summarize_input("UnknownTool", {})
        assert result == ""

    def test_mcp_tool_url(self):
        ui = self._make_ui()
        r = ui._summarize_input("mcp_playwright_navigate", {"url": "https://example.com/y"})
        assert "url" in r
        assert "example.com" in r

    def test_todo_write_summary(self):
        ui = self._make_ui()
        r = ui._summarize_input("TodoWrite", {"todos": [{"content": "a", "status": "pending"}]})
        assert "1 item" in r


class TestTodoUpdated:
    def test_todo_updated_lists(self):
        console = Console(file=StringIO(), no_color=True)
        ui = ClaudeUI(verbose=True)
        ui.console = console
        ui.todo_updated(
            [
                {"content": "First", "status": "completed"},
                {"content": "Second", "status": "in_progress"},
            ]
        )
        out = console.file.getvalue()
        assert "todos" in out
        assert "First" in out
        assert "Second" in out
    """Test _truncate_path method."""

    def test_short_path(self):
        """Short path is not truncated."""
        ui = ClaudeUI()
        assert ui._truncate_path("/short/path.py") == "/short/path.py"

    def test_long_path(self):
        """Long path is truncated with ellipsis."""
        ui = ClaudeUI()
        long_path = "/very/long/path/" + "x" * 100 + "/file.py"
        result = ui._truncate_path(long_path)
        assert result.startswith("...")
        assert len(result) <= 60


class TestToolIcons:
    """Test TOOL_ICONS and TOOL_COLORS dictionaries."""

    def test_icons_have_defaults(self):
        """TOOL_ICONS has a default entry."""
        assert "default" in TOOL_ICONS

    def test_icons_for_common_tools(self):
        """Common tools have icons."""
        for tool in ["Read", "Write", "Bash", "Glob", "Grep"]:
            assert tool in TOOL_ICONS

    def test_colors_have_defaults(self):
        """TOOL_COLORS has a default entry."""
        assert "default" in TOOL_COLORS


class TestGetModelChoices:
    """Test get_model_choices function."""

    def test_returns_list(self):
        """Returns a list of choices."""
        choices = get_model_choices()
        assert isinstance(choices, list)
        assert len(choices) > 0

    def test_choices_have_name_and_value(self):
        """Each choice has 'name' and 'value' keys."""
        for choice in get_model_choices():
            assert "name" in choice
            assert "value" in choice

    def test_includes_sonnet(self):
        """Includes Sonnet model."""
        values = [c["value"] for c in get_model_choices()]
        assert "claude-sonnet-4-6" in values

    def test_includes_opus(self):
        """Includes Opus model."""
        values = [c["value"] for c in get_model_choices()]
        assert "claude-opus-4-6" in values


class TestDisplayBanner:
    """Test display_banner function."""

    def test_basic_banner(self):
        """Banner displays without error."""
        console = Console(file=StringIO(), no_color=True)
        display_banner(console)
        output = console.file.getvalue()
        assert "rae" in output
        assert "Turn websites into APIs" in output

    def test_banner_with_sdk_and_model(self):
        """Banner with SDK and model info."""
        console = Console(file=StringIO(), no_color=True)
        display_banner(console, sdk="claude", model="claude-sonnet-4-6")
        output = console.file.getvalue()
        assert "claude" in output


class TestDisplayFooter:
    """Test display_footer function."""

    def test_footer(self):
        """Footer displays version and time."""
        console = Console(file=StringIO(), no_color=True)
        display_footer(console)
        output = console.file.getvalue()
        assert "via cli" in output
        assert "*" in output
