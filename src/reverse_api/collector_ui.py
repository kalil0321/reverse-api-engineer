"""Terminal UI for collector mode with streaming progress updates."""

from rich.console import Console

from .tui import THEME_DIM

COLLECTOR_COLOR = "#ffd700"  # Gold


class CollectorUI:
    """Terminal UI with real-time collection progress."""

    def __init__(self, verbose: bool = True):
        self.console = Console()
        self.verbose = verbose
        self._items_collected = 0

    def header(self, run_id: str, prompt: str, model: str | None = None) -> None:
        """Display the collector session header."""
        from . import __version__

        self.console.print()
        self.console.print(f" [white]reverse-api[/white] [dim]v{__version__}[/dim]")
        self.console.print(f" [dim]━[/dim] [white]{run_id}[/white]")
        self.console.print(f" [{COLLECTOR_COLOR}]collector[/{COLLECTOR_COLOR}] [dim]|[/dim] [dim]model[/dim] [white]{model or '---'}[/white]")
        self.console.print(f" [{COLLECTOR_COLOR}]task[/{COLLECTOR_COLOR}]      [white]{prompt[:80]}{'...' if len(prompt) > 80 else ''}[/white]")
        self.console.print()

    def start_collecting(self) -> None:
        """Display collection start message."""
        self.console.print(" [dim]planning collection strategy...[/dim]")
        self.console.print()

    def item_saved(self, preview: str) -> None:
        """Display when an item is saved."""
        self._items_collected += 1
        display_preview = preview[:50] + "..." if len(preview) > 50 else preview
        self.console.print(f"  [dim]>[/dim] ++ [white]item_saved[/white]   [dim]{display_preview}[/dim]")

    def thinking(self, text: str, max_length: int = 80) -> None:
        """Display agent thinking/response text."""
        if not self.verbose:
            return
        if len(text) < 20:
            return
        display_text = text[:max_length].replace("\n", " ").strip()
        if len(text) > max_length:
            display_text += "..."
        self.console.print(f"  [dim].. {display_text}[/dim]")

    def tool_start(self, tool_name: str, tool_input: dict) -> None:
        """Display when a tool starts execution."""
        icon_map = {
            "Write": "wr",
            "Read": "rd",
            "WebFetch": "wf",
            "WebSearch": "ws",
            "Bash": "sh",
        }
        icon = icon_map.get(tool_name, "> ")
        summary = self._summarize_input(tool_name, tool_input)
        self.console.print(f"  [dim]>[/dim] {icon} [white]{tool_name[:12]:12}[/white] {summary}")

    def tool_result(self, tool_name: str, is_error: bool = False, output: str | None = None) -> None:
        """Display when a tool completes."""
        if is_error:
            self.console.print(f"  [dim]![/dim] [red]{tool_name} failed[/red]")

    def _summarize_input(self, tool_name: str, tool_input: dict) -> str:
        """Create a brief summary of tool input."""
        if tool_name == "WebFetch":
            url = tool_input.get("url", "")
            return f"[dim]{url[:50]}{'...' if len(url) > 50 else ''}[/dim]"
        elif tool_name == "Write":
            path = tool_input.get("file_path", "")
            return f"[dim]{path}[/dim]"
        return ""

    def collection_complete(self, total_items: int, output_path: str) -> None:
        """Display collection complete message."""
        self.console.print()
        self.console.print(f" [{COLLECTOR_COLOR}]collection complete[/{COLLECTOR_COLOR}] [white]({total_items} items)[/white]")
        self.console.print(f" [dim]output:[/dim] [white]{output_path}[/white]")
        self.console.print()

    def error(self, message: str) -> None:
        """Display error message."""
        from .tui import ERROR_CTA
        self.console.print()
        self.console.print(f" [dim]![/dim] [red]error:[/red] {message}")
        self.console.print(f" [dim]{ERROR_CTA}[/dim]")

    def usage_summary(self, usage: dict) -> None:
        """Display usage/cost summary."""
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = usage.get("estimated_cost_usd", 0)

        if input_tokens > 0 or output_tokens > 0:
            self.console.print(f" [dim]usage:[/dim]")
            if input_tokens > 0:
                self.console.print(f" [dim]  input: {input_tokens:,} tokens[/dim]")
            if output_tokens > 0:
                self.console.print(f" [dim]  output: {output_tokens:,} tokens[/dim]")
            if cost > 0:
                self.console.print(f" [dim]  cost: ${cost:.4f}[/dim]")
