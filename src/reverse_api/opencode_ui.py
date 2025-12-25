"""OpenCode-specific Terminal UI with live streaming updates."""

from typing import Optional, Dict, Any
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner
from rich.table import Table
from rich.panel import Panel

# Theme configuration (matching tui.py)
THEME_PRIMARY = "#ff5f50"
THEME_SECONDARY = "white"
THEME_DIM = "#555555"
THEME_SUCCESS = "#ff5f50"


class OpenCodeUI:
    """Terminal UI for OpenCode with live streaming support."""
    
    def __init__(self, console: Optional[Console] = None, verbose: bool = True):
        self.console = console or Console()
        self.verbose = verbose
        self._live: Optional[Live] = None
        self._current_text = ""
        self._current_tool: Optional[str] = None
        self._tool_status: str = ""
        self._session_status: str = "idle"
        self._tools_used: list[str] = []
    
    def header(self, run_id: str, prompt: str, model: Optional[str] = None) -> None:
        """Display the session header."""
        self.console.print()
        self.console.print(f" [white]reverse-api[/white] [dim]v0.1.0[/dim]")
        self.console.print(f" [dim]━[/dim] [white]{run_id}[/white]")
        self.console.print(f" [dim]model[/dim] [white]{model or '---'}[/white]")
        self.console.print(f" [{THEME_PRIMARY}]task[/{THEME_PRIMARY}]   [white]{prompt}[/white]")
        self.console.print()
    
    def start_analysis(self) -> None:
        """Display analysis start message."""
        self.console.print(f" [dim]decoding starting...[/dim]")
        self.console.print()
    
    def session_created(self, session_id: str) -> None:
        """Display session creation."""
        self.console.print(f"  [dim]session: {session_id[:16]}...[/dim]")
    
    def start_streaming(self) -> None:
        """Start the live display for streaming updates."""
        self._live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()
    
    def stop_streaming(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None
    
    def _build_display(self) -> Text:
        """Build the current display state."""
        display = Text()
        
        # Show current tool if running
        if self._current_tool and self._tool_status == "running":
            display.append(f"  ⟳ ", style=THEME_PRIMARY)
            display.append(f"{self._current_tool}", style="white")
            display.append(" running...\n", style=THEME_DIM)
        
        # Show streaming text (last 200 chars)
        if self._current_text:
            text_preview = self._current_text[-200:].replace("\n", " ").strip()
            if len(self._current_text) > 200:
                text_preview = "..." + text_preview
            display.append(f"  {text_preview}\n", style=THEME_DIM)
        
        return display
    
    def update_text(self, text: str, delta: Optional[str] = None) -> None:
        """Update the streaming text display."""
        if delta:
            self._current_text += delta
        else:
            self._current_text = text
        
        if self._live:
            self._live.update(self._build_display())
    
    def tool_start(self, tool_name: str, tool_input: Optional[Dict] = None) -> None:
        """Display when a tool starts execution."""
        self._current_tool = tool_name
        self._tool_status = "running"
        self._tools_used.append(tool_name)
        
        # Print tool start (this stays in terminal)
        input_summary = self._summarize_input(tool_name, tool_input or {})
        self.console.print(f"  [dim]>[/dim] {tool_name.lower():12} {input_summary}")
        
        if self._live:
            self._live.update(self._build_display())
    
    def tool_result(self, tool_name: str, is_error: bool = False, output: Optional[str] = None) -> None:
        """Display when a tool completes."""
        self._current_tool = None
        self._tool_status = "completed" if not is_error else "error"
        
        if self._live:
            self._live.update(self._build_display())
        
        if is_error:
            self.console.print(f"  [red]![/red] {tool_name.lower()} failed", style=THEME_DIM)
            if output:
                # Show first 100 chars of error
                error_preview = str(output)[:100].replace("\n", " ")
                self.console.print(f"    {error_preview}", style=THEME_DIM)
    
    def step_finish(self, cost: float, tokens: Dict[str, Any]) -> None:
        """Display step completion with usage stats."""
        input_tokens = tokens.get("input", 0)
        output_tokens = tokens.get("output", 0)
        cache = tokens.get("cache", {})
        cache_read = cache.get("read", 0)
        cache_write = cache.get("write", 0)
        
        self.console.print(f"  [dim]step: {input_tokens:,}in/{output_tokens:,}out ${cost:.4f}[/dim]")
    
    def session_status(self, status_type: str) -> None:
        """Update session status."""
        self._session_status = status_type
        if self._live:
            self._live.update(self._build_display())
    
    def thinking(self, text: str) -> None:
        """Display thinking text (for compatibility with ClaudeUI)."""
        # For streaming, we use update_text instead
        # This is a fallback for non-streaming scenarios
        if not self._live and self.verbose and len(text) > 20:
            display_text = text[:100].replace("\n", " ").strip()
            if len(text) > 100:
                display_text += "..."
            self.console.print(f"  .. {display_text}", style=THEME_DIM)
    
    def success(self, script_path: str) -> None:
        """Display success message."""
        self.console.print()
        self.console.print(f" [dim]decoding complete[/dim]")
        self.console.print(f" [white]{script_path}[/white]")
        self.console.print()
    
    def error(self, message: str) -> None:
        """Display error message."""
        self.console.print()
        self.console.print(f" [dim]![/dim] [red]error:[/red] {message}")
    
    def permission_requested(self, perm_type: str, title: str) -> None:
        """Display when a permission is requested."""
        self.console.print(f"  [yellow]?[/yellow] [dim]permission:[/dim] {title}", style=THEME_DIM)
    
    def permission_approved(self, perm_type: str) -> None:
        """Display when a permission is auto-approved."""
        self.console.print(f"  [green]✓[/green] [dim]auto-approved {perm_type}[/dim]")
    
    def todo_updated(self, todos: list) -> None:
        """Display todo list updates."""
        if not todos:
            return
        
        # Count by status
        pending = sum(1 for t in todos if t.get("status") == "pending")
        completed = sum(1 for t in todos if t.get("status") == "completed")
        in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
        
        parts = []
        if in_progress:
            parts.append(f"{in_progress} active")
        if pending:
            parts.append(f"{pending} pending")
        if completed:
            parts.append(f"{completed} done")
        
        status_str = ", ".join(parts) if parts else f"{len(todos)} items"
        self.console.print(f"  [dim]tasks:[/dim] {status_str}")
    
    def file_edited(self, file_path: str) -> None:
        """Display when a file is edited."""
        short_path = self._truncate_path(file_path, 40)
        self.console.print(f"  [dim]✎[/dim] {short_path}", style=THEME_DIM)
    
    def session_busy(self) -> None:
        """Display busy indicator."""
        # This is handled by the live display spinner
        pass
    
    def session_idle(self) -> None:
        """Display idle state."""
        # Usually means we're done
        pass
    
    def session_diff(self, diffs: list) -> None:
        """Display file changes summary."""
        if not diffs:
            return
        
        total_add = sum(d.get("additions", 0) for d in diffs)
        total_del = sum(d.get("deletions", 0) for d in diffs)
        
        files_summary = f"{len(diffs)} file{'s' if len(diffs) > 1 else ''}"
        changes = []
        if total_add:
            changes.append(f"+{total_add}")
        if total_del:
            changes.append(f"-{total_del}")
        
        change_str = " ".join(changes) if changes else ""
        self.console.print(f"  [dim]diff:[/dim] {files_summary} {change_str}")
    
    def session_compacted(self) -> None:
        """Display context compaction notification."""
        self.console.print(f"  [dim]context compacted[/dim]")
    
    def session_retry(self, attempt: int, message: str) -> None:
        """Display retry status."""
        reason = message if message else "retrying..."
        self.console.print(f"  [yellow]⟳[/yellow] [dim]attempt {attempt}:[/dim] {reason}")
    
    def _summarize_input(self, tool_name: str, tool_input: dict) -> str:
        """Create a brief summary of tool input."""
        tool_lower = tool_name.lower()
        
        if tool_lower in ("read", "file_read"):
            path = tool_input.get("path", tool_input.get("file_path", ""))
            return f"[dim]{self._truncate_path(path)}[/dim]"
        elif tool_lower in ("write", "file_write", "edit"):
            path = tool_input.get("path", tool_input.get("file_path", ""))
            return f"[dim]→ {self._truncate_path(path)}[/dim]"
        elif tool_lower in ("bash", "shell"):
            cmd = str(tool_input.get("command", ""))[:60]
            return f"[dim]$ {cmd}{'...' if len(cmd) >= 60 else ''}[/dim]"
        elif tool_lower in ("glob", "find"):
            pattern = tool_input.get("pattern", tool_input.get("query", ""))
            return f"[dim]'{pattern}'[/dim]"
        elif tool_lower in ("webfetch", "web_fetch"):
            url = str(tool_input.get("url", ""))[:50]
            return f"[dim]{url}{'...' if len(url) >= 50 else ''}[/dim]"
        elif tool_lower == "todowrite":
            todos = tool_input.get("todos", [])
            return f"[dim]{len(todos)} items[/dim]"
        
        return ""
    
    def _truncate_path(self, path: str, max_len: int = 50) -> str:
        """Truncate a path for display."""
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len - 3):]
