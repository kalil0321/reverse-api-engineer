"""What the engines talk to while the full-screen session is open: their UI calls become ledger entries.

Engines run in a worker thread; everything here only appends to the transcript or waits on
thread-safe queues, and asks the app to redraw.
"""

from __future__ import annotations

import asyncio
import json
import queue
import re
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import IO, Any, cast
from urllib.parse import urlparse

from rich.console import Console

from ..utils import predates_effort
from .style import THEME, width
from .transcript import Raw, TranscriptWriter
from .view import KIND_VERB, VERB_COL, LedgerView, default_effort, language_for

# Tools that are plumbing for the agent, not steps worth showing. A todo list shows as the plan instead.
HIDDEN_TOOLS = {"ToolSearch", "AskUserQuestion", "TodoWrite", "report_intent"}
QUIET_RESULTS = {"Write", "Edit", "MultiEdit", "TodoWrite", "TaskCreate", "TaskUpdate", "report_client_verified"}
LOOK_TOOLS = {"take_snapshot", "browser_snapshot", "take_screenshot", "browser_take_screenshot"}
# Other SDKs' names for Claude Code's tools: OpenCode's, Copilot's and Cursor's.
ALIASES = {
    "bash": "Bash",
    "shell": "Bash",
    "read": "Read",
    "view": "Read",
    "write": "Write",
    "create": "Write",
    "edit": "Edit",
    "glob": "Glob",
    "grep": "Grep",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
    "todowrite": "TodoWrite",
    "updateTodos": "TodoWrite",
    "Agent": "Task",
    "task": "Task",
    "question": "AskUserQuestion",
}
# OpenCode prefixes an MCP server's tools with the server's name, which rae makes per session: playwright-ses_4f2a…_.
OPENCODE_MCP = re.compile(r"^(?:playwright|chrome-devtools)-(?:ses_[A-Za-z0-9]+_)?")
# The arguments that best say what a tool we have no wording for works on, most telling first.
TARGET_KEYS = ("url", "file_path", "filePath", "path", "query", "text", "pattern", "command", "description", "name", "id")


def usage_tokens(usage: dict[str, Any]) -> int:
    """Every token a run's usage counts: Claude's names, then Copilot's and Cursor's for their cache."""
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cache_read_tokens", "cache_write_tokens")
    return sum(int(usage.get(key, 0) or 0) for key in keys)


def short_name(tool_name: str) -> str:
    """mcp__chrome-devtools__navigate_page reads as navigate_page, and each SDK's name for a tool as Claude Code's."""
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) == 3:
            tool_name = parts[2]
    tool_name = OPENCODE_MCP.sub("", tool_name)
    return ALIASES.get(tool_name, tool_name)


def first_line(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


TRAFFIC_TOOLS = {"traffic_overview", "search_flows", "get_flow", "endpoint_clusters", "auth_trace", "wait_for_flows", "replay_flow"}


def describe_traffic(name: str, args: dict[str, Any]) -> tuple[str, str, str, str | None, str | None]:
    """rae desktop's traffic tools (desktop/tools/traffic.py), as steps."""
    if name == "traffic_overview":
        return "overview", "captured traffic", "read", None, None
    if name == "search_flows":
        found = " ".join(str(args[k]) for k in ("text", "method", "host", "path", "status", "mime") if args.get(k))
        return "search", first_line(found or "all requests"), "read", None, None
    if name == "get_flow":
        return "request", first_line(f"{args.get('id', '?')} {args.get('json_path') or args.get('part') or ''}".strip()), "read", None, None
    if name == "endpoint_clusters":
        return "endpoints", first_line(args.get("host") or "all hosts"), "read", None, None
    if name == "auth_trace":
        return "auth", first_line(args.get("header") or args.get("value") or "credentials"), "read", None, None
    if name == "replay_flow":
        changed = ", ".join(k for k in ("method", "url", "headers", "body") if args.get(k)) or "as captured"
        return "replay", first_line(f"{args.get('id', '?')} · {changed}"), "run", None, None
    return "wait", first_line(args.get("host") or args.get("path_contains") or f"requests after {args.get('after_seq', '?')}"), "read", None, None


def describe_other(name: str, args: dict[str, Any]) -> tuple[str, str, str, str | None, str | None]:
    """A tool rae has no wording for: its name as the verb, cut to the column, and its most telling argument."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.removeprefix("browser_")).replace("_", " ").lower().split() or ["tool"]
    verb, rest = (" ".join(words), []) if len(" ".join(words)) <= VERB_COL else (words[0][:VERB_COL], words[1:])
    values = [args[k] for k in TARGET_KEYS if isinstance(args.get(k), (str, int, float)) and not isinstance(args.get(k), bool)]
    values = values or [v for v in args.values() if isinstance(v, (str, int, float)) and not isinstance(v, bool)]
    target = " · ".join(part for part in (" ".join(rest), first_line(values[0]) if values else "") if part)
    return verb, first_line(target), "other", None, None


def patched_files(args: dict[str, Any]) -> list[str]:
    patch = str(args.get("patchText") or args.get("patch") or args.get("input") or "")
    return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$", patch, re.M)


def describe_browser(name: str, args: dict[str, Any]) -> tuple[str, str, str, str | None, str | None] | None:
    """The browser tools of Chrome DevTools MCP, Playwright MCP and rae desktop, as steps; None for any other tool."""
    url = args.get("url") if isinstance(args.get("url"), str) else None
    if name in ("navigate_page", "browser_navigate", "new_page"):
        return "navigate", first_line(url or args.get("type") or "page"), "read", url, None
    if name == "browser_navigate_back":
        return "navigate", "back", "read", None, None
    if name == "browser_scroll":
        return "scroll", str(args.get("direction") or "down"), "read", None, None
    if name in ("list_network_requests", "browser_network_requests"):
        types = args.get("resourceTypes")
        return "network", ", ".join(types) if isinstance(types, list) and types else "all requests", "read", None, None
    if name == "get_network_request":
        return "request", f"#{args.get('reqid', '?')}", "read", None, None
    if name in LOOK_TOOLS:
        return "look", "screenshot" if "screenshot" in name else "page structure", "read", None, None
    if name in ("click", "browser_click", "hover", "browser_hover"):
        return "click", first_line(args.get("element") or args.get("uid") or args.get("ref") or "element"), "read", None, None
    if name in ("fill", "fill_form", "browser_type", "type_text", "press_key", "browser_press_key"):
        return "type", first_line(args.get("value") or args.get("text") or args.get("key") or "text"), "read", None, None
    if name in ("evaluate_script", "browser_evaluate", "browser_run_code"):
        return "script", first_line(args.get("function") or args.get("script") or args.get("code") or "page script"), "read", None, None
    if name in ("wait_for", "browser_wait_for"):
        return "wait", first_line(args.get("text") or args.get("time") or "page"), "read", None, None
    if name in ("list_pages", "select_page", "close_page", "browser_tabs", "browser_close"):
        return "tabs", name.replace("_", " "), "read", None, None
    if name == "browser_install":
        return "install", "browser", "other", None, None
    return None


def describe(name: str, args: dict[str, Any]) -> tuple[str, str, str, str | None, str | None] | None:
    """(verb, target, kind, url, path) for a tool call, or None when the call is not worth a step."""
    if name in HIDDEN_TOOLS:
        return None
    if name == "mcp" and isinstance(args.get("toolName"), str):
        # Cursor calls every MCP tool through this one, with the real tool and its arguments inside.
        inner = args.get("args")
        return describe(short_name(args["toolName"]), inner if isinstance(inner, dict) else {})
    if (browser := describe_browser(name, args)) is not None:
        return browser
    url = args.get("url") if isinstance(args.get("url"), str) else None
    path = args.get("file_path") or args.get("filePath") or args.get("path")
    path = path if isinstance(path, str) else None
    if name in TRAFFIC_TOOLS:
        return describe_traffic(name, args)
    if name == "report_client_verified":
        return "verified", first_line(args.get("summary") or "the client ran on the live site"), "other", None, None
    if name == "Write":
        return "write", Path(path).name if path else "file", "write", None, path
    if name in ("Edit", "MultiEdit"):
        return "edit", Path(path).name if path else "file", "write", None, path
    if name == "apply_patch":
        files = patched_files(args)
        more = f" +{len(files) - 1}" if len(files) > 1 else ""
        return "edit", f"{Path(files[0]).name}{more}" if files else "files", "write", None, files[0] if files else None
    if name == "Read":
        return "read", Path(path).name if path else "file", "read", None, path
    if name == "Bash":
        return "run", first_line(args.get("command") or args.get("description") or "command"), "run", None, None
    if name in ("Glob", "Grep"):
        return "search", first_line(args.get("pattern") or args.get("globPattern") or args.get("query") or ""), "read", None, None
    if name == "readLints":
        paths = args.get("paths")
        names = [Path(str(p)).name for p in paths] if isinstance(paths, list) else []
        return "lint", ", ".join(names) or "workspace", "read", None, None
    if name == "Task":
        return "subagent", first_line(args.get("description") or args.get("prompt") or "task"), "other", None, None
    if name == "WebFetch":
        return "fetch", first_line(url or ""), "read", url, None
    if name == "WebSearch":
        return "search", first_line(args.get("query") or ""), "read", None, None
    if name in ("TaskCreate", "TaskUpdate"):
        return "plan", first_line(args.get("subject") or args.get("description") or args.get("status") or "task"), "other", None, None
    return describe_other(name, args)


class Bridge:
    """One per session: routes engine calls to the view and carries follow-ups, questions and cancellation."""

    def __init__(self, view: LedgerView, invalidate: Callable[[], None], ask_user: Callable[[dict[str, Any]], Future]) -> None:
        self.view = view
        self.st = view.st
        self.invalidate = invalidate
        self.ask_user = ask_user
        self.follow_ups: queue.Queue[str | None] = queue.Queue()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.pending_card: Path | None = None
        self.cost_base = 0.0
        self.verified = False  # the agent called report_client_verified in this run
        self.workspace: tuple[Path, Path | None] | None = None  # the run's folder and its synced copy
        self.stopping = False  # the run is already on its way out: stopped once, or ended while it waited
        self.failed = False  # the engine already said why the run failed

    def ui(self) -> LedgerUI:
        return LedgerUI(self)

    def bind_task(self) -> None:
        """Remember the engine's task so esc can cancel it from the app's thread."""
        self.stopping = False
        try:
            self.loop, self.task = asyncio.get_running_loop(), asyncio.current_task()
        except RuntimeError:
            self.loop, self.task = None, None

    def cancel(self) -> bool:
        if self.loop and self.task and not self.task.done():
            # Cancelling again would cut the SDK's cleanup short and leave its CLI process behind.
            if not self.stopping:
                self.stopping = True
                self.loop.call_soon_threadsafe(self.task.cancel)
            return True
        return False

    def flush_card(self) -> None:
        path, self.pending_card = self.pending_card, None
        if path is None:
            return
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            return  # no file, no card: the run reported a path it never wrote
        self.view.card(path, source.count("\n") + 1 if source else 0, language_for(path))
        self.invalidate()

    async def follow_up(self) -> str | None:
        """The next message for this run: a queued one, or whatever the user types; None ends the run."""
        st = self.st
        self.flush_card()
        if st.queue:
            text: str | None = st.queue.pop(0)
            self.view.user(text or "")
        else:
            st.running, st.waiting = False, True
            self.invalidate()
            text = await asyncio.get_running_loop().run_in_executor(None, self.follow_ups.get)
            st.waiting = False
            if text is None:
                st.running, st.verb, st.kind = True, "wrapping up", "other"  # until the app's finish() runs
                self.invalidate()
                return None
        self.failed = False  # an error shown in an earlier turn says nothing of how this one ends
        st.running, st.verb, st.kind = True, "thinking", "other"
        self.invalidate()
        return text

    async def ask(self, questions: list[Any]) -> dict[str, str]:
        """Questions from the agent, answered through the input bar."""
        answers: dict[str, str] = {}
        for q in questions:
            get = q.get if isinstance(q, dict) else lambda key, default=None, q=q: getattr(q, key, default)
            text = str(get("question", "") or "")
            if not text:
                continue
            options = []
            for opt in get("options", []) or []:
                label = opt.get("label", "") if isinstance(opt, dict) else getattr(opt, "label", "")
                desc = opt.get("description", "") if isinstance(opt, dict) else getattr(opt, "description", "")
                if label:
                    options.append((str(label), str(desc or "")))
            self.view.question(text)
            self.invalidate()
            spec = {"question": text, "options": options, "multi": bool(get("multiSelect", False))}
            answer = await asyncio.wrap_future(self.ask_user(spec))
            answers[text] = answer or ""
            self.view.answer(answer or "skipped")
            self.invalidate()
        return answers


class LedgerUI:
    """Drop-in for ClaudeUI while the session is open."""

    shows_tool_results = True  # engines read tool results from user messages only for this UI

    def __init__(self, bridge: Bridge, verbose: bool = True) -> None:
        self.b = bridge
        self.view = bridge.view
        self.st = bridge.st
        self.verbose = verbose
        self._plan: list | None = None
        # Engines also print directly; that output joins the conversation as plain lines.
        writer = TranscriptWriter(self._printed)
        self.console = Console(file=cast(IO[str], writer), force_terminal=True, color_system="truecolor", width=width(), theme=THEME, highlight=False)

    def _printed(self, raw: Raw) -> None:
        self.view.out(raw)
        self.b.invalidate()

    def _changed(self) -> None:
        self.b.invalidate()

    def header(self, run_id: str, prompt: str, model: str | None = None, sdk: str | None = None, mode: str | None = None) -> None:
        self.b.bind_task()
        st = self.st
        st.run_id, st.step, st.tokens = run_id, 0, 0
        st.running, st.waiting, st.verb, st.kind = True, False, "starting", "other"
        self.b.cost_base = st.cost
        self.b.verified, self.b.workspace = False, None
        # The run's own model and SDK; the selection in st.model stays for the next run.
        st.run_model, st.run_sdk = model or st.model, sdk or st.sdk
        claude = st.run_sdk == "claude" and not predates_effort(st.run_model)
        st.run_effort = (st.effort or default_effort(st.run_model)) if claude else None
        self.view.run_line(run_id, mode)
        self._changed()

    def start_analysis(self) -> None:
        pass

    def tool_start(self, tool_name: str, tool_input: dict | Any, call_id: str | None = None) -> None:
        _ = call_id
        self.b.flush_card()
        name = short_name(tool_name)
        args = tool_input if isinstance(tool_input, dict) else {}
        if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
            try:
                parsed = json.loads(tool_input)
                args = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                args = {}
        if name == "TodoWrite" and isinstance(args.get("todos"), list):
            self.todo_updated(args["todos"])
        found = describe(name, args)
        if found is None:
            return
        verb, target, kind, url, path = found
        st = self.st
        st.kind = kind
        st.verb = "reading traffic" if verb in ("network", "request") else KIND_VERB.get(kind, "thinking")
        if url:
            st.host = urlparse(url).netloc or st.host
        self.view.step(verb, target, kind, path=Path(path) if path else None, url=url)
        content = args.get("content") if isinstance(args.get("content"), str) else args.get("file_text")
        if name == "Write" and isinstance(content, str) and path:
            st.client_name = Path(path).name
            self.view.code(content, language_for(path))
        elif name in ("Edit", "MultiEdit") and path:
            edits: list[Any] = args["edits"] if isinstance(args.get("edits"), list) else [args]
            for edit in edits[:3]:
                old = edit.get("old_string", edit.get("oldString")) if isinstance(edit, dict) else None
                new = edit.get("new_string", edit.get("newString")) if isinstance(edit, dict) else None
                if isinstance(old, str) and isinstance(new, str):
                    self.view.diff(old, new, language_for(path))
        self._changed()

    def tool_result(self, tool_name: str, is_error: bool = False, output: str | None = None, call_id: str | None = None) -> None:
        _ = call_id
        name = short_name(tool_name)
        if name in HIDDEN_TOOLS:
            return
        if name == "report_client_verified" and not is_error:
            if not self.b.verified and self.b.workspace:
                self.view.workspace(*self.b.workspace)
            self.b.verified = True  # the card promises a client that ran, so only a confirmed report counts
        text = str(output or "").strip()
        lines = text.splitlines()
        if is_error:
            self.view.receipt(lines or ["failed"], error=True)
        elif name in QUIET_RESULTS:
            return
        elif name in LOOK_TOOLS:
            self.view.receipt([f"{len(lines)} lines captured"] if lines else ["captured"])
        elif name == "Read":
            self.view.receipt([f"{len(lines)} lines"])
        else:
            self.view.receipt(lines)
        self._changed()

    def todo_updated(self, todos: list) -> None:
        # Cursor also reports its todo tool's list on its own: one plan per change.
        if todos and todos != self._plan:
            self._plan = todos
            self.view.plan(todos)
            self._changed()

    def stream_thinking(self, delta: str) -> None:
        """A delta of the model's reasoning summary, shown live in the margin."""
        if delta:
            self.b.flush_card()
            self.view.stream(delta, kind="note")
            self.st.verb, self.st.kind = "thinking", "other"
            self._changed()

    def thinking_note(self, text: str) -> None:
        """The complete reasoning summary for a turn; settles the live note."""
        if text and text.strip():
            self.view.stream_done(text.strip(), kind="note")
            self._changed()

    def stream_text(self, delta: str) -> None:
        """A text delta from the SDK, shown as it arrives."""
        if delta:
            self.b.flush_card()
            self.view.stream(delta)
            self._changed()

    def thinking(self, text: str, max_length: int = 500) -> None:
        _ = max_length
        if text and text.strip():
            self.b.flush_card()
            self.view.stream_done(text.strip())
            self._changed()

    def thinking_block(self, text: str, max_chars: int = 8000) -> None:
        self.thinking(text[:max_chars])

    def progress(self, message: str) -> None:
        self.view.notice(message)
        self._changed()

    def workspace(self, folder: Path, copy: Path | None) -> None:
        self.b.workspace = (folder.resolve(), copy.resolve() if copy else None)

    def success(self, script_path: str, local_path: str | None = None) -> None:
        _ = local_path
        path = Path(script_path)
        if path.exists():
            self.st.last_client = path  # /open works for any client, verified or not
        # The card promises a working client, so it waits for the agent to have verified one.
        self.b.pending_card = path if self.b.verified else None
        self._changed()

    def usage(self, usage: dict[str, Any]) -> None:
        st = self.st
        st.tokens = usage_tokens(usage)
        cost = usage.get("estimated_cost_usd")
        if isinstance(cost, (int, float)):
            st.cost = self.b.cost_base + float(cost)
        self.b.flush_card()

    def error(self, message: str) -> None:
        self.b.failed = True
        self.view.error(message)
        self._changed()

    def sync_started(self, dest_dir: str) -> None:
        _ = dest_dir

    def sync_flash(self, message: str) -> None:
        _ = message

    def sync_error(self, message: str) -> None:
        self.view.notice(f"sync error: {message}")
        self._changed()


class CursorLedgerUI(LedgerUI):
    """Cursor streams token-sized text; its engine buffers it and flushes whole blocks."""

    def __init__(self, bridge: Bridge, engineer: Any, verbose: bool = True) -> None:
        super().__init__(bridge, verbose=verbose)
        self._eng = engineer

    def thinking(self, text: str, max_length: int = 500) -> None:
        _ = max_length
        if text:
            self._eng._cursor_feed_thinking(text)
            self.stream_text(text)

    def thinking_block(self, text: str, max_chars: int = 8000) -> None:
        LedgerUI.thinking(self, text[:max_chars])


_bridge: Bridge | None = None


def adaptive_thinking(model: str | None) -> bool:
    """Adaptive thinking exists from the 4.6 models on, and not on Haiku 4.5; unknown names get none."""
    m = re.match(r"claude-(opus|sonnet|haiku|fable)-(\d+)-(\d{1,2})(?!\d)", model or "")
    if m is None:
        return False
    return (int(m.group(2)), int(m.group(3))) >= (4, 6) and not (m.group(1) == "haiku" and m.group(2) == "4")


def stream_options(model: str | None = None) -> dict[str, Any]:
    """ClaudeAgentOptions kwargs for the session: streamed text, and reasoning summaries to show while the agent thinks."""
    if _bridge is None:
        return {}
    options: dict[str, Any] = {"include_partial_messages": True}
    if adaptive_thinking(model):
        options["thinking"] = {"type": "adaptive", "display": "summarized"}
    return options


def active() -> Bridge | None:
    """The open session's bridge, or None when rae runs in the classic interface or headless."""
    return _bridge


def activate(bridge: Bridge | None) -> None:
    global _bridge
    _bridge = bridge
