"""Rich Terminal UI for Claude SDK interactions."""

from rich.console import Console
from rich.text import Text

# Theme configuration
THEME_PRIMARY = "#ff5f50"  # Coral Red
THEME_SECONDARY = "white"
THEME_DIM = "#555555"
THEME_SUCCESS = "#ff5f50"
THEME_ERROR = "bold white on #ff5f50"

ERROR_CTA = "If an unexpected error occurred, please create an issue at https://github.com/kalil0321/reverse-api-engineer/issues/new"


MODE_COLORS = {
    "manual": "#ff5f50",  # Coral Red
    "engineer": "#5f9fff",  # Blue
    "agent": "#50ff9f",  # Green/Cyan
    "collector": "#ffd700",  # Gold
}


# Tool icons for visual clarity (minimalist text)
TOOL_ICONS = {
    "Read": "rd",
    "Write": "wr",
    "Edit": "ed",
    "Bash": "sh",
    "Glob": "ls",
    "Grep": "gp",
    "WebSearch": "ws",
    "WebFetch": "wf",
    "Task": "tk",
    "AskUserQuestion": "??",
    "default": "> ",
}

# Tool colors (minimalist)
TOOL_COLORS = {
    "Read": THEME_DIM,
    "Write": THEME_DIM,
    "Edit": THEME_DIM,
    "Bash": THEME_DIM,
    "Glob": THEME_DIM,
    "Grep": THEME_DIM,
    "WebSearch": THEME_DIM,
    "WebFetch": THEME_DIM,
    "default": THEME_DIM,
}


class ClaudeUI:
    """Interactive terminal UI for Claude SDK operations."""

    def __init__(self, verbose: bool = True):
        self.console = Console()
        self.verbose = verbose
        self._tool_count = 0
        self._tools_used: list[str] = []

    def header(self, run_id: str, prompt: str, model: str | None = None, sdk: str | None = None) -> None:
        """Display the session header."""
        from . import __version__

        self.console.print()
        self.console.print(f" [white]reverse-api[/white] [dim]v{__version__}[/dim]")
        self.console.print(f" [dim]━[/dim] [white]{run_id}[/white]")
        if sdk:
            self.console.print(f" [red]sdk[/red] [red]{sdk}[/red] [red]|[/red] [red]model[/red] [red]{model or '---'}[/red]")
        else:
            self.console.print(f" [dim]model[/dim] [white]{model or '---'}[/white]")
        self.console.print(f" [{THEME_PRIMARY}]task[/{THEME_PRIMARY}]   [white]{prompt}[/white]")
        self.console.print()

    def start_analysis(self) -> None:
        """Display analysis start message."""
        self.console.print(" [dim]decoding starting...[/dim]")
        self.console.print()

    def tool_start(self, tool_name: str, tool_input: dict) -> None:
        """Display when a tool starts execution."""
        self._tool_count += 1
        self._tools_used.append(tool_name)

        icon = TOOL_ICONS.get(tool_name, TOOL_ICONS["default"])

        # Build input summary
        input_summary = self._summarize_input(tool_name, tool_input)

        # Compact single-line format
        self.console.print(f"  [dim]>[/dim] {icon} [white]{tool_name.lower():8}[/white] {input_summary}")

    def tool_result(self, tool_name: str, is_error: bool = False, output: str | None = None) -> None:
        """Display when a tool completes."""
        if is_error:
            self.console.print(f"  [dim]![/dim] [red]{tool_name.lower()} failed[/red]")
        elif tool_name == "Bash" and output and self.verbose:
            # Display bash output
            output_str = str(output).strip()
            if output_str:
                output_lines = output_str.split("\n")
                max_lines = 30
                for line in output_lines[:max_lines]:
                    self.console.print(f"  [dim]│[/dim] [dim]{line}[/dim]")
                if len(output_lines) > max_lines:
                    self.console.print(f"  [dim]│[/dim] [dim]... ({len(output_lines) - max_lines} more lines)[/dim]")

    def thinking(self, text: str, max_length: int = 100) -> None:
        """Display Claude's thinking/response text."""
        if not self.verbose:
            return

        # Only show substantial thinking (skip short status updates)
        if len(text) < 20:
            return

        # Truncate and clean
        display_text = text[:max_length].replace("\n", " ").strip()
        if len(text) > max_length:
            display_text += "..."

        self.console.print(f"  [dim].. {display_text}[/dim]")

    def progress(self, message: str) -> None:
        """Display a progress message."""
        self.console.print(f"  [dim italic]{message}[/dim italic]")

    def success(self, script_path: str, local_path: str | None = None) -> None:
        """Display success message with generated script path."""
        self.console.print()
        self.console.print(" [dim]decoding complete[/dim]")
        self.console.print(f" [dim]internal:[/dim] [white]{script_path}[/white]")
        if local_path:
            self.console.print(f" [dim]synced:[/dim]   [white]{local_path}[/white]")
        self.console.print()

    def error(self, message: str) -> None:
        """Display error message."""
        self.console.print()
        self.console.print(f" [dim]![/dim] [red]error:[/red] {message}")
        self.console.print(f" [dim]{ERROR_CTA}[/dim]")

    def _summarize_input(self, tool_name: str, tool_input: dict) -> str:
        """Create a brief summary of tool input."""
        if tool_name == "Read":
            path = tool_input.get("file_path", "")
            return f"[dim]{self._truncate_path(path)}[/dim]"
        elif tool_name == "Write":
            path = tool_input.get("file_path", "")
            return f"[dim]→ {self._truncate_path(path)}[/dim]"
        elif tool_name == "Edit":
            path = tool_input.get("file_path", "")
            return f"[dim]{self._truncate_path(path)}[/dim]"
        elif tool_name == "Bash":
            cmd = tool_input.get("command", "")
            cmd = cmd.replace("\n", " ").strip()
            return f"[dim]$ {cmd[:60]}{'...' if len(cmd) > 60 else ''}[/dim]"
        elif tool_name in ("Grep", "Glob"):
            pattern = tool_input.get("pattern", "")
            return f"[dim]'{pattern}'[/dim]"
        elif tool_name == "WebSearch":
            query = tool_input.get("query", "")
            return f"[dim]'{query[:50]}{'...' if len(query) > 50 else ''}'[/dim]"
        elif tool_name == "WebFetch":
            url = tool_input.get("url", "")
            return f"[dim]{url[:60]}{'...' if len(url) > 60 else ''}[/dim]"
        return ""

    def _truncate_path(self, path: str, max_len: int = 60) -> str:
        """Truncate a path for display."""
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len - 3) :]

    def sync_started(self, dest_dir: str) -> None:
        """Display when file sync starts."""
        self.console.print(f"  [dim]⟳ sync: active → {dest_dir}[/dim]")

    def sync_flash(self, message: str) -> None:
        """Display a brief sync notification."""
        self.console.print(f"  [dim]✓ {message}[/dim]")

    def sync_error(self, message: str) -> None:
        """Display a sync error."""
        self.console.print(f"  [dim]![/dim] [yellow]sync error:[/yellow] {message}")


def get_model_choices() -> list[dict]:
    """Get available model choices for questionary."""
    return [
        {"name": "Sonnet 4.5 [Balanced]", "value": "claude-sonnet-4-5"},
        {"name": "Opus 4.5 [Power]", "value": "claude-opus-4-5"},
        {"name": "Haiku 4.5 [Speed]", "value": "claude-haiku-4-5"},
    ]


def display_banner(console: Console, sdk: str | None = None, model: str | None = None):
    """Display ultra-minimalist banner."""
    console.print()
    console.print("  [bold white]reverse-api[/bold white]")
    console.print(f"  [bold {THEME_PRIMARY}]━━[/bold {THEME_PRIMARY}]")
    if sdk and model:
        console.print(f"  [red]sdk[/red] [red]{sdk}[/red] [red]|[/red] [red]model[/red] [red]{model}[/red]")
    console.print()
    console.print("  [dim white]AI agents for API reverse engineering.[/dim white]")
    console.print()


def display_footer(console: Console):
    """Display minimalist footer."""
    from datetime import datetime

    from . import __version__

    time_str = datetime.now().strftime("%H:%M")

    footer = Text()
    footer.append(f"\n v{__version__} ", style=THEME_DIM)
    footer.append(f" {time_str} ", style=THEME_DIM)
    footer.append(" VIA CLI ", style=THEME_DIM)

    console.print(footer)
    console.print()
