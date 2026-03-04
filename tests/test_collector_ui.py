"""Tests for collector_ui.py - CollectorUI."""

from io import StringIO

from rich.console import Console

from reverse_api.collector_ui import COLLECTOR_COLOR, CollectorUI


class TestCollectorUI:
    """Test CollectorUI class."""

    def _make_ui(self, verbose=True):
        """Create a CollectorUI with a string buffer console."""
        console = Console(file=StringIO(), no_color=True)
        ui = CollectorUI(verbose=verbose)
        ui.console = console
        return ui, console

    def test_init(self):
        """UI initializes with correct defaults."""
        ui = CollectorUI()
        assert ui.verbose is True
        assert ui._items_collected == 0

    def test_header(self):
        """Header displays collector info."""
        ui, console = self._make_ui()
        ui.header("run123", "collect startup data", "claude-sonnet-4-5")
        output = console.file.getvalue()
        assert "run123" in output
        assert "collect startup data" in output

    def test_header_truncates_long_prompt(self):
        """Header truncates prompts longer than 80 chars."""
        ui, console = self._make_ui()
        long_prompt = "x" * 100
        ui.header("run123", long_prompt, "claude-sonnet-4-5")
        output = console.file.getvalue()
        assert "..." in output

    def test_start_collecting(self):
        """Start collecting displays message."""
        ui, console = self._make_ui()
        ui.start_collecting()
        output = console.file.getvalue()
        assert "planning" in output

    def test_item_saved(self):
        """Item saved increments counter and displays."""
        ui, console = self._make_ui()
        ui.item_saved("Company: Acme Corp")
        assert ui._items_collected == 1
        output = console.file.getvalue()
        assert "item_saved" in output

    def test_item_saved_truncates(self):
        """Long preview is truncated."""
        ui, console = self._make_ui()
        ui.item_saved("x" * 100)
        output = console.file.getvalue()
        assert "..." in output

    def test_thinking_verbose(self):
        """Thinking displays in verbose mode."""
        ui, console = self._make_ui()
        ui.thinking("I need to search for more information about this topic carefully")
        output = console.file.getvalue()
        assert "search" in output

    def test_thinking_short_skipped(self):
        """Short thinking text is skipped."""
        ui, console = self._make_ui()
        ui.thinking("ok")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_thinking_non_verbose(self):
        """Thinking skipped in non-verbose mode."""
        ui, console = self._make_ui(verbose=False)
        ui.thinking("I need to search for more information about this topic carefully")
        output = console.file.getvalue()
        assert output.strip() == ""

    def test_thinking_truncation(self):
        """Long thinking text is truncated."""
        ui, console = self._make_ui()
        long_text = "x" * 200
        ui.thinking(long_text)
        output = console.file.getvalue()
        assert "..." in output

    def test_tool_start(self):
        """Tool start shows tool info."""
        ui, console = self._make_ui()
        ui.tool_start("WebFetch", {"url": "https://example.com"})
        output = console.file.getvalue()
        assert "wf" in output or "WebFetch" in output

    def test_tool_start_write(self):
        """Write tool shows path."""
        ui, console = self._make_ui()
        ui.tool_start("Write", {"file_path": "/output/items.jsonl"})
        output = console.file.getvalue()
        assert "items.jsonl" in output

    def test_tool_start_unknown(self):
        """Unknown tool shows default icon."""
        ui, console = self._make_ui()
        ui.tool_start("CustomTool", {})
        output = console.file.getvalue()
        assert "CustomTool" in output

    def test_tool_result_error(self):
        """Tool result error displays error."""
        ui, console = self._make_ui()
        ui.tool_result("WebFetch", is_error=True)
        output = console.file.getvalue()
        assert "failed" in output

    def test_tool_result_success(self):
        """Tool result success is silent."""
        ui, console = self._make_ui()
        ui.tool_result("WebFetch", is_error=False)
        output = console.file.getvalue()
        assert "failed" not in output

    def test_collection_complete(self):
        """Collection complete shows stats."""
        ui, console = self._make_ui()
        ui.collection_complete(42, "/output/collected/startups")
        output = console.file.getvalue()
        assert "42" in output
        assert "complete" in output

    def test_error(self):
        """Error displays error message."""
        ui, console = self._make_ui()
        ui.error("Something went wrong")
        output = console.file.getvalue()
        assert "error" in output
        assert "Something went wrong" in output

    def test_usage_summary(self):
        """Usage summary shows token stats."""
        ui, console = self._make_ui()
        ui.usage_summary({
            "input_tokens": 1000,
            "output_tokens": 500,
            "estimated_cost_usd": 0.05,
        })
        output = console.file.getvalue()
        assert "1,000" in output
        assert "500" in output
        assert "0.05" in output

    def test_usage_summary_empty(self):
        """Usage summary with no tokens is silent."""
        ui, console = self._make_ui()
        ui.usage_summary({})
        output = console.file.getvalue()
        assert "usage" not in output

    def test_summarize_input_webfetch(self):
        """WebFetch input shows URL."""
        ui, _ = self._make_ui()
        result = ui._summarize_input("WebFetch", {"url": "https://example.com"})
        assert "example.com" in result

    def test_summarize_input_write(self):
        """Write input shows path."""
        ui, _ = self._make_ui()
        result = ui._summarize_input("Write", {"file_path": "/output/file.json"})
        assert "file.json" in result

    def test_summarize_input_unknown(self):
        """Unknown tool returns empty string."""
        ui, _ = self._make_ui()
        result = ui._summarize_input("CustomTool", {})
        assert result == ""
