"""The interactive CLI: a full-screen session with the conversation above an input bar fixed to the bottom.

Agent and engineer runs on the Claude, Copilot and Cursor SDKs stream into the conversation
through the bridge. Screens not ported yet (manual, collector, OpenCode runs, /settings) leave
full screen, run in the plain terminal on the main thread, then hand back.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
import threading
import time
import warnings
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import IO, Any, cast
from urllib.parse import urlparse
from urllib.request import url2pathname

import click
from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.processors import AfterInput, ConditionalProcessor
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.output import create_output
from prompt_toolkit.styles import Style
from rich.console import Console, RenderableType
from rich.text import Text

from ..messages import MessageStore
from .bridge import Bridge, activate, describe, first_line, short_name
from .style import DIM, INK, SKY, THEME, height, width
from .transcript import Raw, Transcript, TranscriptControl, TranscriptWriter
from .view import EFFORTS, LedgerView, Picker, SessionState, model_label, run_summary, strip_markdown

MODES = {
    "agent": "the agent browses the site and writes the client",
    "manual": "you browse, rae records the traffic",
    "engineer": "re-engineer a past run",
    "collector": "collect data into json and csv",
}
EFFORT_NOTES = {
    "low": "fastest, fewer tool calls",
    "medium": "lighter reasoning, the default on Opus 5.5 and Haiku 5.5",
    "high": "deep reasoning, the default for most models",
    "xhigh": "deeper reasoning on hard captures",
    "max": "most thorough, slowest and priciest",
}
COMMANDS = {
    "/new": "start a new capture",
    "/model": "choose the model",
    "/effort": "how hard the agent thinks",
    "/mode": "choose the mode",
    "/settings": "all settings",
    "/history": "past runs, to look at or re-engineer",
    "/resume": "continue a past run's conversation",
    "/messages": "what the agent did in a past run",
    "/output": "everything from this session, unfolded",
    "/open": "open the latest client",
    "/clear": "clear the conversation and start over",
    "/help": "keys and commands",
    "/exit": "quit rae",
}
ALIASES = {"/quit": "/exit", "/commands": "/help"}
HISTORY_RUNS = 20
# Commands that open a picker are echoed once a choice shows something, not when the picker opens.
PICKER_COMMANDS = {"/model", "/effort", "/mode", "/history", "/messages", "/resume"}
URL_IN_PROMPT = re.compile(r"https?://([^/\s]+)|\b((?:[\w-]+\.)+(?:com|io|co|ch|de|fr|uk|org|net|dev|ai|app|so|sh|eu|jobs))\b")


def file_path(target: str) -> str:
    """A file:// link as a local path: url2pathname turns /C:/x into C:\\x on Windows, and a host makes a UNC path."""
    parsed = urlparse(target)
    path = url2pathname(parsed.path)
    if parsed.netloc and parsed.netloc != "localhost":
        sep = "\\" if sys.platform == "win32" else "/"
        path = f"{sep}{sep}{parsed.netloc}{path}"
    return path


def open_target(target: str) -> None:
    """Open a clicked link: files with the system's default app, URLs in the browser."""
    path = file_path(target) if target.startswith("file://") else target
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603


def host_in(prompt: str) -> str:
    m = URL_IN_PROMPT.search(prompt)
    return (m.group(1) or m.group(2) or "") if m else ""


def run_log(run_id: str) -> list[tuple[str, str, str, str]]:
    """A past run's saved messages as (clock, verb, text, kind) rows, for /messages and /resume."""
    entries: list[tuple[str, str, str, str]] = []
    for msg in MessageStore(run_id).load():
        kind, content, clock = msg.get("type"), msg.get("content"), str(msg.get("timestamp", ""))[11:19]
        if kind == "prompt":
            # The first prompt of a run is the engine's full brief; the user's words are its mission.
            mission = re.search(r"<mission>(.*?)</mission>", str(content), re.DOTALL)
            entries.append((clock, "prompt", first_line(mission.group(1) if mission else content, 200), "user"))
        elif kind == "tool_start" and isinstance(content, dict):
            found = describe(short_name(str(content.get("name", ""))), content.get("input") or {})
            if found:
                entries.append((clock, found[0], found[1], found[2]))
        elif kind == "tool_result" and isinstance(content, dict) and content.get("is_error"):
            entries.append((clock, "failed", first_line(content.get("output") or "the tool returned an error", 200), "error"))
        elif kind == "thinking":
            entries.append((clock, "says", first_line(strip_markdown(str(content)), 200), "say"))
        elif kind == "error":
            entries.append((clock, "error", first_line(content, 200), "error"))
        elif kind == "result":
            script = content.get("script_path") if isinstance(content, dict) else None
            entries.append((clock, "done", Path(script).name if script else "finished", "done"))
    return entries


class InputLexer(Lexer):
    """Highlights /commands and URLs while typing."""

    def __init__(self, st: SessionState) -> None:
        self.st = st

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        def get_line(n: int) -> StyleAndTextTuples:
            line = document.lines[n]
            frags: StyleAndTextTuples = []
            pos = 0
            for m in re.finditer(r"(^/\w*)|(https?://\S+)|(\b[\w.-]+\.(?:com|ch|io|dev|org|net|ai|co)\S*)", line):
                frags.append(("", line[pos : m.start()]))
                frags.append((f"fg:{self.st.accent} bold" if m.group(1) else f"fg:{SKY} underline", m.group(0)))
                pos = m.end()
            frags.append(("", line[pos:]))
            return frags

        return get_line


class Session:
    def __init__(self) -> None:
        from .. import cli

        self.cli = cli
        sdk = cli.config_manager.get("sdk", "claude")
        self.st = SessionState(
            sdk=sdk,
            model=cli.default_model_for_configured_sdk(sdk),
            effort=cli.config_manager.get("claude_effort"),
            collector_model=cli.config_manager.get("collector_model"),
        )
        self.transcript = Transcript(on_link=open_target)
        self.view = LedgerView(self.st, self.transcript)
        self.buf = Buffer(multiline=False, history=InMemoryHistory())
        self.bridge = Bridge(self.view, self.invalidate, self.ask_user)
        self.app: Application | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.real_out, self.real_err = sys.stdout, sys.stderr
        self.classic_job: Callable[[], None] | None = None
        self.first: tuple[str, Callable[[], Any]] | None = None  # a run a subcommand handed over
        # Per mode, how a subcommand's options (--headless, --output-dir...) start each prompt: runner(prompt, model).
        self.runners: dict[str, Callable[[str, str | None], Any]] = {}
        self.worker: threading.Thread | None = None
        self.update_checked = False
        self.buf.on_text_changed += self._reset_palette
        # Stray prints read as notices: dim and indented like the rest of the ledger.
        self.capture = TranscriptWriter(self._captured, plain_style=f"fg:{DIM}", indent="   ")

    # plumbing

    def invalidate(self) -> None:
        if self.app is not None:
            self.app.invalidate()

    def _reset_palette(self, _buf: Buffer) -> None:
        self.st.palette_index = 0  # typing narrows the menu, so the first match is the one enter runs

    def _captured(self, raw: Raw) -> None:
        self.view.out(raw)
        self.invalidate()

    def call_soon(self, fn: Callable[[], None]) -> None:
        if self.loop is not None:
            try:
                self.loop.call_soon_threadsafe(fn)
            except RuntimeError:
                pass  # between two stretches of full screen the loop is closed; nothing to redraw

    def ask_user(self, spec: dict[str, Any]) -> Future:
        """Show an agent question in the bar; the future resolves with the answer, or an empty string if skipped."""
        fut: Future = Future()

        def show() -> None:
            if fut.done():
                return  # the run was stopped before the question reached the bar
            options = spec.get("options") or []
            if options:
                items = [(label, label, desc) for label, desc in options] + [("", "something else", "type your own answer")]

                def picked(value: str | None) -> None:
                    if value == "":
                        if not fut.done():
                            self.st.question = fut
                    elif not fut.done():
                        fut.set_result(value or "")

                multi = bool(spec.get("multi"))
                title = str(spec.get("question", "")) + (" · space picks several, enter sends" if multi else "")
                self.st.picker = Picker(title, items, None, picked, question=True, multi=multi)
            else:
                self.st.question = fut
            self.invalidate()

        self.call_soon(show)
        return fut

    # commands

    def palette_active(self) -> bool:
        """The command menu shows while a command is typed, but not over a picker, nor while the agent
        awaits a typed answer, which can start with / (a path)."""
        st, text = self.st, self.buf.text
        return st.picker is None and st.question is None and text.startswith("/") and " " not in text

    def palette_items(self) -> list[tuple[str, str]]:
        typed = self.buf.text.strip().lower()
        aliased = {target for alias, target in ALIASES.items() if alias.startswith(typed)}
        items = [(c, d) for c, d in COMMANDS.items() if c.startswith(typed) or c in aliased]
        return sorted(items, key=lambda item: item[0] != ALIASES.get(typed, typed))

    def choose(self) -> None:
        """Enter on an open picker: its highlighted item, or for an agent's question, whatever was typed meanwhile."""
        p, self.st.picker = self.st.picker, None
        if p is None:
            return
        if p.question and self.buf.text.strip():
            answer = self.buf.text.strip()
            self.buf.reset()
            p.on_pick(answer)
        elif p.multi and p.chosen:
            p.on_pick(", ".join(value for value, _, _ in p.items if value in p.chosen))
        else:
            p.on_pick(p.items[p.index][0])

    def toggle(self) -> None:
        """Space on a several-answers question: adds or removes the highlighted option."""
        p = self.st.picker
        if p is None or not p.multi:
            return
        value = p.items[p.index][0]
        if value:
            p.chosen.remove(value) if value in p.chosen else p.chosen.append(value)

    def open_picker(self, title: str, items: list[tuple[str, str, str]], current: str | None, on_pick: Callable[[str | None], None]) -> None:
        index = next((i for i, (v, _, _) in enumerate(items) if v == current), 0)
        self.st.picker = Picker(title, items, current, on_pick, index)

    def set_model(self, value: str | None) -> None:
        st = self.st
        if not value or value == st.next_model:
            return
        old = model_label(st.next_model)
        if st.mode == "collector":
            st.collector_model = value
            self.cli.config_manager.set("collector_model", value)
        else:
            st.model = value
            self.cli.config_manager.set("claude_code_model", value)
        self.view.event("collector model" if st.mode == "collector" else "model", old, model_label(value), "from the next run" if st.run_open else "")

    def set_effort(self, value: str | None) -> None:
        if not value or value == self.st.effort_label:
            return
        old = self.st.effort_label
        self.st.effort = value
        self.cli.config_manager.set("claude_effort", value)
        self.view.event("effort", old, value, "from the next run" if self.st.run_open else "")

    def set_mode(self, value: str | None) -> None:
        if value and value != self.st.mode:
            old, self.st.mode = self.st.mode, value
            self.view.event("mode", old, value)

    def cycle_effort(self) -> None:
        if not self.st.has_effort:
            return
        level = EFFORTS.index(self.st.effort_label) if self.st.effort_label in EFFORTS else 2
        value = EFFORTS[(level + 1) % len(EFFORTS)]
        self.st.effort = value
        self.cli.config_manager.set("claude_effort", value)

    def run_command(self, text: str) -> None:
        cmd, _, arg = text.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        cmd = ALIASES.get(cmd, cmd)
        st, view = self.st, self.view
        if cmd not in PICKER_COMMANDS | {"/exit", "/clear"}:
            view.command(cmd, arg)
        if cmd == "/exit":
            self.quit()
        elif cmd == "/new":
            if st.waiting:
                self.end_run()
            elif st.running:
                view.notice("a run is in progress · esc stops it")
            else:
                view.notice("ready · describe the API you want")
        elif cmd == "/help":
            view.notice("enter sends · esc stops a run · shift+tab mode · ctrl+e effort · ctrl+o full output · ctrl+d quits")
            view.notice("pageup/pagedown or the mouse wheel scroll · end jumps to the latest · click a file or URL to open it")
        elif cmd == "/model":
            if st.sdk != "claude":
                view.command(cmd)
                view.notice(f"the {st.sdk} model is set in /settings")
            else:
                from ..tui import get_model_choices

                choices = [(c["value"], model_label(c["value"]), c["name"].split("[")[-1].rstrip("]").lower()) for c in get_model_choices()]
                current = st.next_model
                if current and current not in [value for value, _, _ in choices]:
                    choices.insert(0, (current, model_label(current), "current"))  # e.g. the Sonnet 4.6 default
                title = "choose the collector's model" if st.mode == "collector" else "choose a model"
                self.open_picker(title, choices, current, self.set_model)
        elif cmd == "/effort" and not st.has_effort:
            view.command(cmd)
            view.notice(st.no_effort_reason)
        elif cmd == "/effort":
            self.open_picker("how hard the agent thinks", [(e, e, EFFORT_NOTES[e]) for e in EFFORTS], st.effort_label, self.set_effort)
        elif cmd == "/mode":
            self.open_picker("choose a mode", [(m, m, d) for m, d in MODES.items()], st.mode, self.set_mode)
        elif cmd == "/output":
            self.show_output()
        elif cmd == "/open":
            if st.last_client:
                open_target(str(st.last_client))
            else:
                view.notice("no client yet")
        elif cmd == "/clear":
            if st.running:
                view.notice("a run is in progress · esc stops it")
            else:
                if st.waiting:
                    self.end_run()
                view.flush_live()
                self.transcript.clear()
                st.scroll, st.folded, st.cost, st.tokens, st.step = 0, False, 0.0, 0, 0
                st.last_client, st.client_name, st.host, st.run_id = None, "", "", None
                self.bridge.cost_base = 0.0
        elif cmd == "/settings":
            self.classic(lambda: self.cli.handle_settings(), then=self.reload_settings, pause=False)
        elif cmd == "/history":
            self.pick_run(cmd, "past runs", self.show_run)
        elif cmd == "/resume":
            if arg:
                self.resume(arg)
            else:
                self.pick_run(cmd, "resume a run", self.resume, keep=self.cli.resumable, empty="no run can be resumed yet · runs from now on can")
        elif cmd == "/messages":
            if arg:
                self.show_messages(arg)
            else:
                self.pick_run(cmd, "whose messages", self.show_messages)
        else:
            view.notice(f"unknown command {cmd} · / lists them")
        self.invalidate()

    def reload_settings(self) -> None:
        cfg = self.cli.config_manager
        cfg.load()
        self.st.sdk = cfg.get("sdk", "claude")
        self.st.model = self.cli.default_model_for_configured_sdk(self.st.sdk)
        self.st.effort = cfg.get("claude_effort")
        self.st.collector_model = cfg.get("collector_model")

    # past runs

    def pick_run(
        self,
        cmd: str,
        title: str,
        then: Callable[[str], None],
        keep: Callable[[dict[str, Any]], bool] | None = None,
        empty: str = "no runs yet",
    ) -> None:
        runs = self.cli.session_manager.get_history(limit=len(self.cli.session_manager.history))
        runs = [r for r in runs if keep is None or keep(r)][:HISTORY_RUNS]
        if not runs:
            self.view.command(cmd)
            self.view.notice(empty)
            return
        items = [(r["run_id"], r["run_id"], run_summary(r)) for r in runs]
        self.open_picker(title, items, None, lambda value: then(value) if value else None)

    def show_run(self, run_id: str) -> None:
        run = self.cli.session_manager.get_run(run_id)
        self.view.command("/history", run_id)
        if run is None:
            self.view.notice(f"no run {run_id}")
            return
        self.view.run_details(run)
        actions = [("resume", "resume", "continue its conversation")] if self.cli.resumable(run) else []
        actions += [
            ("engineer", "re-engineer", "write its client again from the capture"),
            ("messages", "messages", "what the agent did, step by step"),
            ("", "back", ""),
        ]

        def act(value: str | None) -> None:
            if value == "resume":
                self.resume(run_id)
            elif value == "engineer":
                self.reengineer(run_id)
            elif value == "messages":
                self.show_messages(run_id)

        self.open_picker(f"run {run_id}", actions, None, act)
        self.invalidate()

    def show_messages(self, run_id: str) -> None:
        self.view.command("/messages", run_id)
        entries = run_log(run_id)
        if not entries:
            self.view.notice(f"no messages for run {run_id}")
        else:
            self.view.message_log(entries)
        self.invalidate()

    def resume(self, run_id: str) -> None:
        """Reopen a past run's SDK session; the next message in the bar continues its conversation."""
        st = self.st
        run = self.cli.session_manager.get_run(run_id)
        self.view.command("/resume", run_id)
        if st.running or st.waiting:
            self.view.notice("a run is open · /new ends it first")
        elif run is None or not self.cli.resumable(run):
            self.view.notice(f"run {run_id} has no saved session to resume" if run else f"no run {run_id}")
        elif run["sdk_session"].get("sdk") == "opencode":
            # OpenCode runs still use the classic screen, which asks for the next message there.
            self.view.run_details(run)
            self.show_past(run_id)
            self.classic(lambda: self.cli.resume_run(run_id))
        else:
            self.view.run_details(run)
            self.show_past(run_id)
            self.view.gap()
            st.host, st.client_name = host_in(str(run.get("prompt") or "")), ""
            st.started, st.running, st.verb, st.kind = time.time(), True, "reopening", "other"
            self.work(lambda: self.cli.resume_run(run_id))
        self.invalidate()

    def show_past(self, run_id: str) -> None:
        """What the run did so far, so a resumed conversation picks up in view."""
        entries = run_log(run_id)
        if entries:
            self.view.gap()
            self.view.message_log(entries, latest=True)

    def reengineer(self, run_id: str) -> None:
        if self.st.running or self.st.waiting:
            self.view.notice("a run is open · /new ends it first")
            return
        self.view.command("re-engineer", run_id)
        self.start(run_id, mode="engineer", echo=False)

    # runs

    def submit(self, text: str) -> None:
        st = self.st
        if isinstance(st.question, Future):
            fut, st.question = st.question, None
            if not fut.done():
                fut.set_result(text)
            return
        if not text:
            return
        if text.startswith("/"):
            self.run_command(text)
            return
        st.scroll = 0
        if st.running:
            st.queue.append(text)
        elif st.waiting:
            self.view.user(text)
            self.bridge.follow_ups.put(text)
        else:
            self.start(text)
        self.invalidate()

    def start(self, prompt: str, mode: str | None = None, echo: bool = True) -> None:
        cli = self.cli
        mode = mode or self.st.mode
        model = (self.st.collector_model if mode == "collector" else self.st.model) if self.st.sdk == "claude" else None
        run: Callable[[], Any]
        runner = self.runners.get(mode)
        if runner is not None:
            run = lambda: runner(prompt, model)  # noqa: E731
        elif mode == "manual":
            run = lambda: cli.run_manual_capture(prompt=prompt, url=None, reverse_engineer=True, model=model)  # noqa: E731
        elif mode == "collector":
            run = lambda: cli.run_collector(prompt=prompt, model=model)  # noqa: E731
        elif mode == "engineer":
            run = lambda: cli.engineer_from_prompt(prompt, model)  # noqa: E731
        else:
            run = lambda: cli.run_agent_capture(prompt=prompt, model=model)  # noqa: E731
        self.launch(prompt, run, mode, echo)

    def launch(self, prompt: str, run: Callable[[], Any], mode: str | None = None, echo: bool = True) -> None:
        """Start a run in the session, or in the plain terminal for the screens not ported yet."""
        st = self.st
        mode = mode or st.mode
        st.host, st.client_name = host_in(prompt), ""
        if echo:
            self.view.user(prompt)
        if mode in ("manual", "collector") or st.sdk == "opencode":
            self.classic(run)
        else:
            st.started, st.running, st.verb, st.kind = time.time(), True, "starting", "other"
            self.work(run)

    def start_first(self) -> None:
        """Once the app is up: the run a subcommand handed over, and the check for a newer rae."""
        if self.first is not None:
            (prompt, run), self.first = self.first, None
            self.launch(prompt, run)
        if not self.update_checked:
            self.update_checked = True

            def check() -> None:
                from ..utils import check_for_updates

                message = check_for_updates()
                if message:
                    self.view.notice(message)
                    self.invalidate()

            threading.Thread(target=check, name="rae-update-check", daemon=True).start()

    def work(self, fn: Callable[[], Any]) -> None:
        """Run an engine in a worker thread; its UI calls stream into the conversation through the bridge."""

        def target() -> None:
            result: Any = None
            try:
                result = fn()
            except (asyncio.CancelledError, KeyboardInterrupt):
                result = {"error": "interrupted"}
            except BaseException as exc:  # noqa: BLE001  # the engine thread must never take the app down
                self.view.error(str(exc) or type(exc).__name__)
            finally:
                self.finish(result)

        self.worker = threading.Thread(target=target, name="rae-run", daemon=True)
        self.worker.start()

    def end_run(self) -> None:
        """End a run that waits for a follow-up. It stays busy until its worker has wrapped up,
        so a prompt sent meanwhile is queued for after it instead of racing its cleanup."""
        st = self.st
        st.waiting, st.running, st.verb, st.kind = False, True, "wrapping up", "other"
        self.bridge.follow_ups.put(None)

    def finish(self, result: Any) -> None:
        st = self.st
        # A stream cut short never closes its live message; settle it so nothing stays hidden behind it.
        self.view.flush_live()
        self.bridge.flush_card()
        if st.picker is not None and st.picker.question:
            st.picker = None
        st.question = None
        if isinstance(result, dict) and result.get("error") and not result.get("error_reported"):
            if result["error"] in ("interrupted", "Agent analysis cancelled."):
                self.view.interrupted()
            else:
                self.view.error(str(result["error"]))
        self.bridge.task = None
        while not self.bridge.follow_ups.empty():
            self.bridge.follow_ups.get_nowait()
        st.run_model = st.run_sdk = st.run_effort = None
        # Take the queued prompt before going idle: a prompt typed in between would otherwise start
        # its own run alongside it.
        nxt = st.queue.pop(0) if st.queue else None
        st.waiting = False
        if nxt is None:
            st.running = False
        else:

            def start_next() -> None:
                st.running = False  # on the app's thread, so nothing can slip in before the queued prompt
                self.start(nxt)

            self.call_soon(start_next)
        self.invalidate()

    def classic(self, fn: Callable[[], Any], then: Callable[[], None] | None = None, pause: bool = True) -> None:
        """Leave full screen and run fn in the plain terminal on the main thread, then come back.

        The classic screens prompt with questionary, which runs its own event loop, and manual
        capture installs signal handlers; both need the main thread with no loop running.
        ``pause`` keeps what fn printed on screen until the user is done reading it.
        """
        if self.st.running:
            self.view.notice("a run is in progress · esc stops it")
            return

        def job() -> None:
            try:
                fn()
                if pause:
                    self.cli.console.print("\n [dim]enter returns to the session[/dim]", end="")
                    input()
            except (KeyboardInterrupt, EOFError, click.Abort):
                pass
            except Exception as exc:  # noqa: BLE001  # a failing classic screen must not end the session
                self.view.error(str(exc) or type(exc).__name__)
            if then:
                then()

        self.classic_job = job
        if self.app is not None:
            self.app.exit()

    def stop(self) -> None:
        st = self.st
        if st.running:
            st.queue.clear()
            if not self.bridge.cancel():
                self.view.notice("this run cannot be stopped from here")
        elif st.waiting:
            self.end_run()

    def show_output(self) -> None:
        items = list(self.transcript.full)

        def page() -> None:
            buf = io.StringIO()
            console = Console(file=buf, force_terminal=True, color_system="truecolor", width=width(), highlight=False, theme=THEME)
            for item in items:
                console.print(Text.from_ansi(item.text) if isinstance(item, Raw) else item)
            sys.stdout = self.real_out
            try:
                click.echo_via_pager(buf.getvalue())  # click turns on less -R itself unless LESS says otherwise
            finally:
                sys.stdout = cast(IO[str], self.capture)

        asyncio.ensure_future(run_in_terminal(page))

    def take_classic_job(self) -> Callable[[], None] | None:
        job, self.classic_job = self.classic_job, None
        return job

    def wait_for_run(self, timeout: float = 60) -> None:
        """After quitting: let a stopped run close its SDK session, sync its files and save its history."""
        worker = self.worker
        if worker is not None and worker.is_alive():
            print(" stopping the run…", file=self.real_err, flush=True)
            worker.join(timeout)

    def quit(self) -> None:
        self.classic_job = None
        self.st.queue.clear()  # nothing new starts on the way out
        if self.st.running:
            self.bridge.cancel()
        if self.st.waiting:
            self.bridge.follow_ups.put(None)
        if self.app is not None:
            self.app.exit()

    # layout

    def transcript_view(self, window: Window) -> FormattedText:
        """The header (animated while visible) and the conversation, sliced to the window."""
        st = self.st
        self.view.tick()
        lines = self.view.header_rows(theta=time.time() * 0.35) + self.transcript.lines()
        rows = window.render_info.window_height if window.render_info else height() - 5
        st.scroll = max(0, min(st.scroll, len(lines) - rows))
        end = len(lines) - st.scroll
        out: list[Any] = []
        for i, line in enumerate(lines[max(0, end - rows) : end]):
            out += ([("", "\n")] if i else []) + line
        return FormattedText(out)

    def build(self) -> Application:
        st, view, buf = self.st, self.view, self.buf
        palette_open = Condition(self.palette_active)
        picker_open = Condition(lambda: st.picker is not None)

        def palette_view() -> FormattedText:
            items = self.palette_items()
            st.palette_index = min(st.palette_index, max(0, len(items) - 1))
            return view.menu([(c, d, i == st.palette_index, False) for i, (c, d) in enumerate(items)], limit=len(COMMANDS))

        def picker_view() -> FormattedText:
            p = st.picker
            if p is None:
                return FormattedText([])
            rows = [
                ((("◉ " if value in p.chosen else "○ ") if p.multi and value else "") + label, desc, i == p.index, value == p.current)
                for i, (value, label, desc) in enumerate(p.items)
            ]
            return view.menu(rows, title=p.title)

        transcript_window: Window = Window(wrap_lines=False)
        transcript_window.content = TranscriptControl(lambda: self.transcript_view(transcript_window), self.scroll)
        kb = self.bindings(palette_open, picker_open)

        def text_window(fn: Callable[[], Any]) -> Window:
            return Window(FormattedTextControl(fn), dont_extend_height=True)

        placeholder = ConditionalProcessor(
            AfterInput("describe the API you want, e.g. all open jobs on jobs.ashbyhq.com/openai", style=f"fg:{DIM} italic"),
            filter=Condition(lambda: not buf.text and not st.waiting and st.question is None),
        )
        follow_hint = ConditionalProcessor(
            AfterInput("a follow-up for this run, or /new", style=f"fg:{DIM} italic"),
            filter=Condition(lambda: not buf.text and st.waiting and st.question is None),
        )
        layout = Layout(
            HSplit(
                [
                    transcript_window,
                    ConditionalContainer(text_window(lambda: FormattedText(view.spinner())), filter=Condition(lambda: st.running)),
                    text_window(lambda: FormattedText(view.seam())),
                    VSplit(
                        [
                            Window(FormattedTextControl(lambda: FormattedText(view.marker())), dont_extend_width=True, dont_extend_height=True),
                            Window(
                                BufferControl(buffer=buf, lexer=InputLexer(st), input_processors=[placeholder, follow_hint]),
                                dont_extend_height=True,
                                wrap_lines=True,
                            ),
                        ]
                    ),
                    text_window(lambda: FormattedText(view.seam_under())),
                    ConditionalContainer(text_window(palette_view), filter=palette_open),
                    ConditionalContainer(text_window(picker_view), filter=picker_open),
                    ConditionalContainer(text_window(view.status), filter=~palette_open & ~picker_open),
                ]
            ),
            focused_element=buf,
        )
        return Application(
            layout=layout,
            key_bindings=merge_key_bindings([load_key_bindings(), kb]),
            style=Style.from_dict({"": INK}),
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.05,
            output=create_output(stdout=sys.__stdout__),
        )

    def scroll(self, delta: int) -> None:
        self.st.scroll = max(0, self.st.scroll + delta)

    def bindings(self, palette_open: Condition, picker_open: Condition) -> KeyBindings:  # noqa: C901  # one small handler per key
        st, buf = self.st, self.buf
        kb = KeyBindings()

        @kb.add("enter", filter=palette_open)
        def _(event: KeyPressEvent) -> None:
            items = self.palette_items()
            cmd = items[st.palette_index][0] if items else buf.text.strip()
            buf.reset()
            self.run_command(cmd)

        @kb.add("tab", filter=palette_open)
        def _(event: KeyPressEvent) -> None:
            items = self.palette_items()
            if items:
                buf.text = items[st.palette_index][0] + " "
                buf.cursor_position = len(buf.text)

        @kb.add("up", filter=palette_open)
        def _(event: KeyPressEvent) -> None:
            st.palette_index = max(0, st.palette_index - 1)

        @kb.add("down", filter=palette_open)
        def _(event: KeyPressEvent) -> None:
            st.palette_index = min(len(self.palette_items()) - 1, st.palette_index + 1)

        @kb.add("space", filter=picker_open & Condition(lambda: bool(st.picker and st.picker.multi) and not buf.text))
        def _(event: KeyPressEvent) -> None:
            self.toggle()

        @kb.add("up", filter=picker_open)
        def _(event: KeyPressEvent) -> None:
            if st.picker:
                st.picker.index = max(0, st.picker.index - 1)

        @kb.add("down", filter=picker_open)
        def _(event: KeyPressEvent) -> None:
            if st.picker:
                st.picker.index = min(len(st.picker.items) - 1, st.picker.index + 1)

        @kb.add("enter", filter=picker_open)
        def _(event: KeyPressEvent) -> None:
            self.choose()

        @kb.add("enter", filter=~palette_open & ~picker_open)
        def _(event: KeyPressEvent) -> None:
            text = buf.text.strip()
            if text:
                buf.append_to_history()
            buf.reset()
            self.submit(text)

        @kb.add("pageup")
        def _(event: KeyPressEvent) -> None:
            self.scroll(max(1, height() // 2))

        @kb.add("pagedown")
        def _(event: KeyPressEvent) -> None:
            self.scroll(-max(1, height() // 2))

        @kb.add("end", filter=Condition(lambda: not buf.text))
        def _(event: KeyPressEvent) -> None:
            st.scroll = 0

        @kb.add("s-tab")
        def _(event: KeyPressEvent) -> None:
            modes = list(MODES)
            st.mode = modes[(modes.index(st.mode) + 1) % len(modes)]

        @kb.add("c-e")
        def _(event: KeyPressEvent) -> None:
            self.cycle_effort()

        @kb.add("c-o")
        def _(event: KeyPressEvent) -> None:
            self.show_output()

        @kb.add("escape", eager=True)
        def _(event: KeyPressEvent) -> None:
            if st.picker is not None:
                p, st.picker = st.picker, None
                p.on_pick(None)
            elif isinstance(st.question, Future):
                fut, st.question = st.question, None
                if not fut.done():
                    fut.set_result("")
            elif buf.text.startswith("/"):
                buf.reset()
            else:
                self.stop()

        @kb.add("c-c")
        def _(event: KeyPressEvent) -> None:
            if st.running or st.waiting:
                self.stop()
            elif buf.text:
                buf.reset()
            else:
                self.quit()

        @kb.add("c-d")
        def _(event: KeyPressEvent) -> None:
            self.quit()

        return kb

    # lifecycle

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.app = self.build()
        activate(self.bridge)
        sys.stdout = sys.stderr = cast(IO[str], self.capture)
        # The SDK warns once that bypassPermissions shadows can_use_tool; it is not for the user.
        warnings.filterwarnings("ignore", message=".*can_use_tool.*")
        try:
            await self.app.run_async(pre_run=self.start_first)
        finally:
            sys.stdout, sys.stderr = self.real_out, self.real_err
            activate(None)

    def print_transcript(self) -> None:
        """Leave the session in the terminal's history, like a normal command's output."""
        self.view.flush_live()
        console = Console(force_terminal=sys.stdout.isatty(), highlight=False, theme=THEME)
        for line in self.view.header_text():
            console.print(line)
        for item in self.transcript.items:
            renderable: RenderableType = Text.from_ansi(item.text) if isinstance(item, Raw) else item
            console.print(renderable)


def run_session(
    mode: str = "agent",
    model: str | None = None,
    first: tuple[str, Callable[[], Any]] | None = None,
    runner: Callable[[str, str | None], Any] | None = None,
) -> None:
    """Entry point for the interactive CLI: full screen, with stretches in the plain terminal for classic screens.

    A subcommand hands over its options: ``first`` is its prompt and run, with every option bound, and
    ``runner(prompt, model)`` starts the prompts typed later in ``mode`` with the options that still apply.
    """
    session = Session()
    session.st.mode = mode
    if model and mode == "collector":
        session.st.collector_model = model
    elif model:
        session.st.model = model
    session.first = first
    if runner is not None:
        session.runners[mode] = runner
    try:
        while True:
            asyncio.run(session.run())
            job = session.take_classic_job()
            if job is None:
                break
            job()
    except KeyboardInterrupt:
        pass
    session.wait_for_run()
    session.print_transcript()
