"""Rich Terminal UI for Claude SDK interactions."""

import json
from typing import Any

from rich.console import Console
from rich.padding import Padding
from rich.text import Text

from .theme import (
    APP_TAGLINE,
    BANNER_INNER_WIDTH,
    BRAND_MARK,
    BRAND_WORDMARK,
    MODE_COLORS,
    THEME_DIM,
    THEME_ERROR,
    THEME_PRIMARY,
    THEME_SECONDARY,
    THEME_SUCCESS,
)

ERROR_CTA = "If an unexpected error occurred, please create an issue at https://github.com/kalil0321/reverse-api-engineer/issues/new"


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
    "mcp": "◇",
    "browser_navigate": "br",
    "browser_click": "br",
    "browser_type": "br",
    "browser_snapshot": "br",
    "browser_tabs": "br",
    "browser_lock": "br",
    "browser_unlock": "br",
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

    def header(self, run_id: str, prompt: str, model: str | None = None, sdk: str | None = None, mode: str | None = None) -> None:
        """Display the session header."""
        print_session_header(self.console, run_id, prompt, model=model, sdk=sdk, mode=mode)

    def start_analysis(self) -> None:
        """Display analysis start message."""
        self.console.print(" [dim]decoding starting...[/dim]")
        self.console.print()

    def tool_start(self, tool_name: str, tool_input: dict | Any) -> None:
        """Display when a tool starts execution."""
        self._tool_count += 1
        self._tools_used.append(tool_name)

        args = self._coerce_tool_input(tool_input)
        icon = self._tool_icon_for(tool_name)
        header = self._tool_header_label(tool_name)
        input_summary = self._summarize_input(tool_name, args)

        self.console.print(f"  [dim]>[/dim] {icon} [white]{header}[/white]")
        if input_summary:
            self.console.print(f"      {input_summary}")

    def tool_result(self, tool_name: str, is_error: bool = False, output: str | None = None) -> None:
        """Display when a tool completes."""
        tl = tool_name.lower()
        if is_error:
            self.console.print(f"  [dim]![/dim] [red]{self._tool_header_label(tool_name)} failed[/red]")
            if output and self.verbose:
                err = str(output).strip().replace("\n", " ")
                if len(err) > 200:
                    err = err[:197] + "..."
                self.console.print(f"      [dim]{err}[/dim]")
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
        elif output and self.verbose and (tl.startswith("mcp") or "web" in tl or "fetch" in tl):
            preview = str(output).strip()
            if len(preview) > 400:
                preview = preview[:397] + "..."
            if "\n" in preview:
                lines = preview.split("\n")[:12]
                self.console.print("  [dim]│[/dim] [dim]result[/dim]")
                for line in lines:
                    self.console.print(f"  [dim]│[/dim] [dim]{line[:140]}{'…' if len(line) > 140 else ''}[/dim]")
            elif preview:
                self.console.print(f"  [dim]│[/dim] [dim]{preview}[/dim]")

    def todo_updated(self, todos: list) -> None:
        """Show agent todo list (Cursor / Claude todo-style tools)."""
        if not self.verbose or not todos:
            return

        icons = {
            "pending": "○",
            "in_progress": "›",
            "completed": "✓",
            "cancelled": "✗",
        }
        pending = sum(1 for t in todos if str(t.get("status", "")).lower() == "pending")
        done = sum(1 for t in todos if str(t.get("status", "")).lower() == "completed")
        active = [t for t in todos if str(t.get("status", "")).lower() == "in_progress"]

        summary_parts: list[str] = []
        if active:
            summary_parts.append(f"{len(active)} active")
        if pending:
            summary_parts.append(f"{pending} pending")
        if done:
            summary_parts.append(f"{done} done")
        summary = ", ".join(summary_parts) if summary_parts else f"{len(todos)} items"

        self.console.print(f"  [dim]todos[/dim] [white]{summary}[/white]")
        for t in todos[:14]:
            st = str(t.get("status", "pending")).lower()
            ic = icons.get(st, "·")
            line = (t.get("activeForm") or t.get("content") or "").strip() or "(empty)"
            if len(line) > 76:
                line = line[:73] + "..."
            self.console.print(f"      [dim]{ic}[/dim]  {line}")
        if len(todos) > 14:
            self.console.print(f"      [dim]… {len(todos) - 14} more[/dim]")
        self.console.print()

    def thinking(self, text: str, max_length: int = 500) -> None:
        """Display Claude's thinking/response text."""
        if not self.verbose:
            return

        if len(text) < 5:
            return

        display_text = text.replace("\n", " ").strip()
        if len(display_text) > max_length:
            display_text = display_text[:max_length] + "..."
        self.console.print(f"  [dim].. {display_text}[/dim]")

    def thinking_block(self, text: str, max_chars: int = 8000) -> None:
        """Print one cohesive model reasoning / reply block (not token-by-token).

        Used by the Cursor SDK path where the bridge streams fine-grained deltas;
        the engineer buffers those and flushes them here as a single visual unit.
        """
        if not self.verbose:
            return
        raw = (text or "").strip()
        if len(raw) < 2:
            return
        if len(raw) > max_chars:
            raw = raw[:max_chars] + "\n…"
        self.console.print()
        self.console.print(Padding(Text(raw, style="dim"), (0, 0, 0, 2)))
        self.console.print()

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

    def _coerce_tool_input(self, tool_input: Any) -> dict:
        if isinstance(tool_input, dict):
            return tool_input
        if isinstance(tool_input, str) and tool_input.strip():
            s = tool_input.strip()
            if s.startswith("{"):
                try:
                    parsed = json.loads(s)
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    return {}
        return {}

    def _tool_icon_for(self, tool_name: str) -> str:
        if tool_name in TOOL_ICONS and tool_name != "default":
            return TOOL_ICONS[tool_name]
        tl = tool_name.lower()
        if tl.startswith("mcp"):
            return TOOL_ICONS.get("mcp", "◇")
        return TOOL_ICONS["default"]

    def _tool_header_label(self, tool_name: str) -> str:
        if not tool_name:
            return "tool"
        tl = tool_name.lower()
        if tl.startswith("mcp_"):
            rest = tool_name[4:].replace("__", " · ")
            rest = rest.replace("_", " ")
            if len(rest) > 56:
                return rest[:53].strip() + "…"
            return rest
        if len(tool_name) > 48:
            return tool_name[:45] + "…"
        return tool_name

    def _summarize_input(self, tool_name: str, tool_input: dict) -> str:
        """Create a brief summary of tool input."""
        tl = tool_name.lower()
        if tl in ("todowrite", "todo_write", "write_todos", "update_todos"):
            todos = tool_input.get("todos")
            if isinstance(todos, list):
                return f"[dim]{len(todos)} item(s)[/dim]"
            return "[dim]todos[/dim]"
        if tl == "call_mcp_tool":
            mn = tool_input.get("name") or tool_input.get("server") or tool_input.get("tool")
            if isinstance(mn, str) and mn:
                return f"[dim]{mn[:70]}{'…' if len(mn) > 70 else ''}[/dim]"
            return ""
        if tl.startswith("mcp"):
            keys = ("url", "path", "file_path", "command", "query", "pattern", "browserTab", "tabId", "text")
            for k in keys:
                v = tool_input.get(k)
                if isinstance(v, str) and v.strip():
                    vv = v.replace("\n", " ").strip()
                    cap = 72 if k in ("url", "path", "file_path") else 60
                    return f"[dim]{k}[/dim] [dim]{vv[:cap]}{'…' if len(vv) > cap else ''}[/dim]"
            args = tool_input.get("arguments")
            if isinstance(args, str) and args.strip().startswith("{"):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict):
                for k in keys:
                    v = args.get(k)
                    if isinstance(v, str) and v.strip():
                        vv = v.replace("\n", " ").strip()
                        return f"[dim]{k}[/dim] [dim]{vv[:70]}{'…' if len(vv) > 70 else ''}[/dim]"
            blob = json.dumps(tool_input, default=str)
            if len(blob) > 90:
                return f"[dim]{blob[:87]}…[/dim]"
            return f"[dim]{blob}[/dim]"
        if tool_name == "Read" or tl == "read":
            path = tool_input.get("file_path") or tool_input.get("path", "")
            return f"[dim]{self._truncate_path(path)}[/dim]"
        elif tool_name == "Write" or tl == "write":
            path = tool_input.get("file_path") or tool_input.get("path", "")
            return f"[dim]→ {self._truncate_path(path)}[/dim]"
        elif tool_name == "Edit" or tl == "edit":
            path = tool_input.get("file_path") or tool_input.get("path", "")
            return f"[dim]{self._truncate_path(path)}[/dim]"
        elif tool_name == "Bash" or tl in ("bash", "shell"):
            cmd = str(tool_input.get("command", ""))
            cmd = cmd.replace("\n", " ").strip()
            return f"[dim]$ {cmd[:60]}{'...' if len(cmd) > 60 else ''}[/dim]"
        elif tool_name in ("Grep", "Glob") or tl in ("grep", "glob"):
            pattern = tool_input.get("pattern", tool_input.get("query", ""))
            return f"[dim]'{pattern}'[/dim]"
        elif tool_name == "WebSearch" or tl == "websearch":
            query = tool_input.get("query", "")
            return f"[dim]'{query[:50]}{'...' if len(query) > 50 else ''}'[/dim]"
        elif tool_name == "WebFetch" or tl == "webfetch":
            url = tool_input.get("url", "")
            return f"[dim]{url[:60]}{'...' if len(url) > 60 else ''}[/dim]"
        elif tool_name == "browser_navigate":
            url = tool_input.get("url", "")
            return f"[dim]{url[:50]}{'...' if len(url) > 50 else ''}[/dim]"
        elif tool_name == "browser_click":
            ref = tool_input.get("elementRef", "")
            return f"[dim]ref={ref[:40]}{'...' if len(ref) > 40 else ''}[/dim]"
        elif tool_name == "browser_type":
            text = tool_input.get("text", "")[:30]
            return f"[dim]'{text}{'...' if len(text) >= 30 else ''}'[/dim]"
        elif tool_name == "browser_snapshot":
            return "[dim]page structure[/dim]"
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
        {"name": "Sonnet 4.6 [Balanced]", "value": "claude-sonnet-4-6"},
        {"name": "Opus 4.6 [Power]", "value": "claude-opus-4-6"},
        {"name": "Haiku 4.5 [Speed]", "value": "claude-haiku-4-5"},
    ]


def _banner_plain_row(console: Console, text: str, *, style: str = THEME_DIM) -> None:
    """Print a plain-text row inside the terminal-style banner frame."""
    visible = text[:BANNER_INNER_WIDTH]
    pad = " " * (BANNER_INNER_WIDTH - len(visible))
    console.print(
        f"  [{THEME_DIM}]│[/{THEME_DIM}] [{style}]{visible}[/{style}]{pad} [{THEME_DIM}]│[/{THEME_DIM}]"
    )


def print_brand_line(console: Console, *, version: str | None = None, version_color: str | None = None) -> None:
    """Print the * rae wordmark (optional version suffix)."""
    line = f" [{THEME_PRIMARY}]{BRAND_MARK}[/{THEME_PRIMARY}] [{THEME_SECONDARY}]{BRAND_WORDMARK}[/{THEME_SECONDARY}]"
    if version is not None:
        color = version_color or THEME_PRIMARY
        line += f" [{color}]v{version}[/{color}]"
    console.print(line)


def print_session_header(
    console: Console,
    run_id: str,
    prompt: str,
    model: str | None = None,
    sdk: str | None = None,
    mode: str | None = None,
    *,
    mode_label: str = "task",
) -> None:
    """Session header matching the site terminal-window pattern."""
    from . import __version__

    mode_color = MODE_COLORS.get(mode or "", THEME_PRIMARY)

    console.print()
    print_brand_line(console, version=__version__, version_color=mode_color)
    console.print(f" [{THEME_DIM}]━[/{THEME_DIM}] [{THEME_SECONDARY}]{run_id}[/{THEME_SECONDARY}]")
    if sdk:
        console.print(
            f" [{THEME_DIM}]sdk[/{THEME_DIM}]    [{THEME_SECONDARY}]{sdk}[/{THEME_SECONDARY}]"
            f" [{THEME_DIM}]|[/{THEME_DIM}] [{THEME_DIM}]model[/{THEME_DIM}]"
            f" [{THEME_SECONDARY}]{model or '---'}[/{THEME_SECONDARY}]"
        )
    else:
        console.print(
            f" [{THEME_DIM}]model[/{THEME_DIM}]  [{THEME_SECONDARY}]{model or '---'}[/{THEME_SECONDARY}]"
        )
    console.print(f" [{mode_color}]{mode_label}[/{mode_color}]   [{THEME_SECONDARY}]{prompt}[/{THEME_SECONDARY}]")
    console.print()


def display_banner(console: Console, sdk: str | None = None, model: str | None = None):
    """Display startup banner (terminal-window chrome + * rae branding)."""
    w = BANNER_INNER_WIDTH
    rule = "─" * w

    console.print()
    console.print(f"  [{THEME_DIM}]╭{rule}╮[/{THEME_DIM}]")
    console.print(
        f"  [{THEME_DIM}]│[/{THEME_DIM}] [{THEME_DIM}]○ ○ ○[/{THEME_DIM}]"
        f"  [{THEME_SECONDARY}]reverse-api-engineer[/{THEME_SECONDARY}]"
        f"  [{THEME_DIM}]│[/{THEME_DIM}]"
    )
    console.print(f"  [{THEME_DIM}]├{rule}┤[/{THEME_DIM}]")
    brand_pad = " " * (BANNER_INNER_WIDTH - len(BRAND_MARK) - 1 - len(BRAND_WORDMARK))
    console.print(
        f"  [{THEME_DIM}]│[/{THEME_DIM}] "
        f"[{THEME_PRIMARY}]{BRAND_MARK}[/{THEME_PRIMARY}] "
        f"[{THEME_SECONDARY}]{BRAND_WORDMARK}[/{THEME_SECONDARY}]"
        f"{brand_pad} [{THEME_DIM}]│[/{THEME_DIM}]"
    )
    _banner_plain_row(console, APP_TAGLINE)
    if sdk and model:
        sdk_line = f"sdk {sdk} · model {model}"
        _banner_plain_row(console, sdk_line, style=THEME_SECONDARY)
    console.print(f"  [{THEME_DIM}]╰{rule}╯[/{THEME_DIM}]")
    console.print()


def display_footer(console: Console):
    """Display minimalist footer."""
    from datetime import datetime

    from . import __version__

    time_str = datetime.now().strftime("%H:%M")

    console.print(
        f"\n [{THEME_DIM}][{THEME_PRIMARY}]*[/{THEME_PRIMARY}]"
        f" v{__version__} {time_str} via cli[/{THEME_DIM}]"
    )
    console.print()
