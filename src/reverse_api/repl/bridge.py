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

# Tools that are plumbing for the agent, not steps worth showing.
HIDDEN_TOOLS = {"ToolSearch", "AskUserQuestion", "report_intent"}
QUIET_RESULTS = {"Write", "Edit", "MultiEdit", "report_client_verified"}
# The agent's task list shows as the plan, not as steps. These tools write all of it at once...
PLAN_TOOLS = {"TodoWrite", "update_plan"}
# ...and these, Claude Code's, one task at a time, by the id TaskCreate's result gives.
TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
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
    "todo_write": "TodoWrite",
    "write_todos": "TodoWrite",
    "update_todos": "TodoWrite",
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
    """The browser tools of Chrome DevTools MCP and Playwright MCP, as steps; None for any other tool."""
    url = args.get("url") if isinstance(args.get("url"), str) else None
    if name in ("navigate_page", "browser_navigate", "new_page"):
        return "navigate", first_line(url or args.get("type") or "page"), "read", url, None
    if name == "browser_navigate_back":
        return "navigate", "back", "read", None, None
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
    if name in ("evaluate_script", "browser_evaluate", "browser_run_code", "browser_run_code_unsafe"):
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
    if name in HIDDEN_TOOLS or name in PLAN_TOOLS or name in TASK_TOOLS:
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
        self.on_stop: Callable[[], None] | None = None  # how esc stops a stretch that has no asyncio task
        self.reset_plan()

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
        if self.on_stop is not None:
            # A stretch that is not an engine's task, such as manual capture's browser, stops its own way.
            stop, self.on_stop = self.on_stop, None
            stop()
            return True
        if self.loop and self.task and not self.task.done():
            # Cancelling again would cut the SDK's cleanup short and leave its CLI process behind.
            if not self.stopping:
                self.stopping = True
                self.loop.call_soon_threadsafe(self.task.cancel)
            return True
        return False

    def reset_plan(self) -> None:
        self.plan: dict[str, dict[str, Any]] = {}  # the agent's tasks by id, in the order it made them
        # TaskCreate and TaskUpdate calls waiting for their result: (call id, tool, the new task's key or the task as it was)
        self.plan_calls: list[tuple[str | None, str, Any]] = []
        self.plan_made = 0  # TaskCreate calls so far, so each waiting task gets its own key
        self.plan_changed = False
        self.plan_shown: list[dict[str, Any]] | None = None

    def plan_call(self, name: str, call_id: str | None) -> Any:
        """The waiting call a result answers: the one with its id when the SDK gives ids, else the oldest of that tool."""
        same = [i for i, (cid, tool, _) in enumerate(self.plan_calls) if tool == name]
        exact = [i for i in same if call_id is not None and self.plan_calls[i][0] == call_id]
        if not (exact or same):
            return None
        return self.plan_calls.pop((exact or same)[0])[2]

    def plan_tool(self, name: str, args: dict[str, Any], call_id: str | None = None) -> bool:
        """Takes a todo, plan or task tool's call into the plan; False for any other tool."""
        if name in PLAN_TOOLS:
            items = args.get("todos") if isinstance(args.get("todos"), list) else args.get("plan")
            if isinstance(items, list):
                self.set_plan(items)
            return True
        if name == "TaskCreate":
            key, self.plan_made = f"new-{self.plan_made}", self.plan_made + 1
            subject = args.get("subject") or args.get("description") or "task"
            self.plan[key] = {"subject": subject, "activeForm": args.get("activeForm"), "status": "pending"}
            self.plan_calls.append((call_id, name, key))
            self.plan_changed = True
        elif name == "TaskUpdate":
            task_id = str(args.get("taskId"))
            before = self.plan.get(task_id)
            self.plan_calls.append((call_id, name, (task_id, dict(before) if before is not None else None)))
            if task_id in self.plan and args.get("status") == "deleted":
                self.plan.pop(task_id)
                self.plan_changed = True
            elif task_id in self.plan:
                self.plan[task_id].update({k: args[k] for k in ("status", "subject", "activeForm") if args.get(k)})
                self.plan_changed = True
        return name in TASK_TOOLS

    def plan_result(self, name: str, output: str, failed: bool = False, call_id: str | None = None) -> None:
        """TaskCreate's result names the task's id; TaskList's lists every task, so a resumed run catches up."""
        call = self.plan_call(name, call_id) if name in ("TaskCreate", "TaskUpdate") else None
        if name == "TaskCreate" and call is not None:
            key, found = call, re.search(r"#(\w+)", output)
            if failed:
                self.plan.pop(key, None)  # the task was never made
                self.plan_changed = True
            elif found and key in self.plan:
                self.plan = {(found.group(1) if k == key else k): v for k, v in self.plan.items()}
        elif name == "TaskUpdate" and call is not None:
            task_id, before = call
            if failed and before is not None:
                self.plan[task_id] = before  # back in its place, or at the end if the call had deleted it
                self.plan_changed = True
        elif name == "TaskList" and not failed:
            rows = re.findall(r"^#(\w+) \[([\w-]+)\] (.+)$", output, re.MULTILINE)
            if rows:
                known = self.plan
                self.plan = {i: {**known.get(i, {}), "subject": subject, "status": status} for i, status, subject in rows}
                self.plan_changed = True

    def set_plan(self, items: list[Any]) -> None:
        self.plan = {str(i): dict(item) for i, item in enumerate(items) if isinstance(item, dict)}
        self.plan_calls, self.plan_changed = [], True

    def flush_plan(self) -> None:
        """Shows the plan once a batch of changes is done, and only when it differs from the one shown."""
        if not self.plan_changed:
            return
        self.plan_changed = False
        items = [dict(task) for task in self.plan.values()]
        if items and items != self.plan_shown:
            self.plan_shown = items
            self.view.plan(items)
            self.invalidate()

    def docs_ready(self, path: Path) -> None:
        """A documentation run's result, which gets no client card."""
        self.flush_card()
        self.view.docs_ready(path)
        self.invalidate()

    def copied(self, folder: Path) -> None:
        """A finished run's copy in the working directory, where the user looks for it."""
        self.flush_card()
        self.view.copied(folder)
        self.invalidate()

    def flush_card(self) -> None:
        self.flush_plan()
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
        self.b.reset_plan()
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
        name = short_name(tool_name)
        args = tool_input if isinstance(tool_input, dict) else {}
        if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
            try:
                parsed = json.loads(tool_input)
                args = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                args = {}
        if self.b.plan_tool(name, args, call_id):
            self._changed()
            return  # its change shows with the next step, message or card, so a batch of them makes one plan
        self.b.flush_card()
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
        if name in PLAN_TOOLS or name in TASK_TOOLS:
            self.b.plan_result(name, str(output or ""), failed=is_error, call_id=call_id)
            return
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
        # Cursor and OpenCode also report their todo tool's list on their own; the plan shows once per change.
        if todos:
            self.b.set_plan(todos)
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
        self.b.flush_plan()
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


class OpenCodeLedgerUI(LedgerUI):
    """Drop-in for OpenCodeUI while the session is open. OpenCode sends each text part whole again as it grows,
    with no end: a part is complete when another one starts, or a step, the result or an error comes."""

    def __init__(self, bridge: Bridge, verbose: bool = True) -> None:
        super().__init__(bridge, verbose=verbose)
        self._text = ""
        self._part: str | None = None

    def _settle(self) -> None:
        if self._text:
            self.view.stream_done(self._text)
            self._text = ""
            self._changed()
        self._part = None

    def update_text(self, text: str, delta: str | None = None, part_id: str | None = None) -> None:
        _ = delta  # the whole part is in text
        # Another part, by its id when OpenCode gives one; text that does not continue the part shown is one too.
        if self._text and ((part_id is not None and part_id != self._part) or not text.startswith(self._text)):
            self._settle()
        new, self._text, self._part = text[len(self._text) :], text, part_id
        if new:
            self.stream_text(new)

    def start_streaming(self) -> None:
        pass

    def stop_streaming(self) -> None:
        self._settle()

    def tool_start(self, tool_name: str, tool_input: dict | Any = None, call_id: str | None = None) -> None:
        self._settle()
        super().tool_start(tool_name, tool_input or {}, call_id=call_id)

    def success(self, script_path: str, local_path: str | None = None) -> None:
        self._settle()
        super().success(script_path, local_path)
        path = Path(script_path)
        if not self.b.verified and path.exists():
            # OpenCode has no tool to report a verified client, so no card: say where the client is instead.
            self.view.workspace(path.parent, Path(local_path).parent if local_path else None)

    def error(self, message: str, *, unexpected: bool | None = None) -> None:
        _ = unexpected
        self._settle()
        super().error(message)

    def session_summary(self, usage_metadata: dict[str, Any]) -> None:
        self.usage(usage_metadata)

    def server_started(self, package: str, base_url: str) -> None:
        self.progress(f"opencode started: {package} at {base_url}")

    def compatibility_warning(self, message: str) -> None:
        self.progress(f"opencode: {message}")

    def ollama_ready(self, model: str, started: bool = False) -> None:
        self.progress(f"ollama {'started' if started else 'connected'}, using {model}")

    def session_retry(self, attempt: int, message: str) -> None:
        self.progress(f"opencode retries (attempt {attempt}): {message}")

    def session_compacted(self) -> None:
        self.progress("opencode compacted the conversation to fit the model's context")

    # What the session already shows another way, or does not need: steps, the plan and the card.
    def health_check(self, health: dict[str, Any]) -> None:
        pass

    def session_created(self, session_id: str) -> None:
        pass

    def model_info(self, provider: str, model: str) -> None:
        pass

    def session_status(self, status_type: str) -> None:
        pass

    def step_finish(self, cost: float, tokens: dict[str, Any]) -> None:
        pass

    def permission_requested(self, perm_type: str, title: str) -> None:
        pass

    def permission_approved(self, perm_type: str) -> None:
        pass

    def file_edited(self, file_path: str) -> None:
        pass

    def session_diff(self, diffs: list) -> None:
        pass

    def session_busy(self) -> None:
        pass

    def session_idle(self) -> None:
        pass


class CollectorLedgerUI(LedgerUI):
    """Drop-in for CollectorUI while the session is open."""

    def header(self, run_id: str, prompt: str, model: str | None = None, sdk: str | None = None, mode: str | None = None, **kwargs: Any) -> None:
        _ = kwargs
        super().header(run_id, prompt, model=model, sdk=sdk or "claude", mode=mode or "collector")

    def start_collecting(self) -> None:
        pass

    def item_saved(self, preview: str) -> None:
        self.b.flush_card()
        self.view.step("saved", first_line(preview), "write")
        self._changed()

    def collection_complete(self, total_items: int, output_path: str) -> None:
        self.b.flush_card()
        self.view.collected(total_items, Path(output_path))
        self._changed()

    def usage_summary(self, usage: dict[str, Any]) -> None:
        self.usage(usage)


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
