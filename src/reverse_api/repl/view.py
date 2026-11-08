"""What the session looks like: the header, the ledger of steps, the client card and the bar under it."""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from prompt_toolkit.formatted_text import FormattedText
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .. import __version__
from ..theme import MODE_COLORS
from ..utils import predates_effort, recorded_cost
from .logo import LOGO_COLS, logo_rows
from .style import (
    AMBER,
    CHIP_INK,
    CHIP_LAVENDER,
    CHIP_YELLOW,
    CODE_THEME,
    DIM,
    GAUGE_EMPTY,
    HAIRLINE,
    INK,
    INK_SOFT,
    MINT,
    PASTEL_OTHER,
    PASTEL_READ,
    PASTEL_RUN,
    PASTEL_WRITE,
    PINK,
    RECEIPT_HL,
    height,
    rich_style,
    width,
)
from .transcript import Raw, Transcript

EFFORTS = ["low", "medium", "high", "xhigh", "max"]
VERB_COL = 9
INDENT = 6 + VERB_COL
CODE_PREVIEW = 8
OUTPUT_PREVIEW = 3
NOTE_LINES = 3
MENU_ROWS = 10
TOP_PADDING = 1
FLAP = "abcdefghijklmnopqrstuvwxyz"
KIND_TINT = {"read": PASTEL_READ, "write": PASTEL_WRITE, "run": PASTEL_RUN, "other": PASTEL_OTHER}
KIND_VERB = {"read": "reading the site", "write": "writing the client", "run": "testing the client", "other": "thinking"}
LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".psm1": "powershell",
    ".ps1": "powershell",
    ".md": "markdown",
    ".json": "json",
    ".sh": "bash",
}
LANGUAGE_NAMES = {"csharp": "c#", "javascript": "javascript", "typescript": "typescript", "powershell": "powershell"}


def model_label(model: str | None) -> str:
    """Short lowercase name for a model id: claude-sonnet-5-5 reads as sonnet 5.5."""
    if not model:
        return "default model"
    m = re.match(r"claude-(sonnet|opus|haiku)-(\d+)-(\d+)", model)
    return f"{m.group(1)} {m.group(2)}.{m.group(3)}" if m else model


def default_effort(model: str | None) -> str:
    return "medium" if model in ("claude-opus-5-5", "claude-haiku-5-5") else "high"


def language_for(path: str | Path) -> str:
    return LANGUAGES.get(Path(str(path)).suffix.lower(), "text")


def first_definition(source: str) -> int:
    """1-based line of the first function or class, where code says the most."""
    pattern = (
        r"\s*(async\s+def|def|class|function|func|export\s+(default\s+)?(async\s+)?function|export\s+class"
        r"|public\s+(static\s+)?(class|async|function))\b"
    )
    for n, line in enumerate(source.splitlines(), 1):
        if re.match(pattern, line):
            return n
    skip = ("import ", "from ", "require(", "using ", "#include", "package ", "//", "#", "<?php")
    lines = source.splitlines()
    i = 0
    if lines and lines[0].lstrip().startswith(('"""', "'''")):
        quote = lines[0].lstrip()[:3]
        i = 1 if lines[0].count(quote) >= 2 else next((n + 1 for n in range(1, len(lines)) if quote in lines[n]), 0)
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith(skip)):
        i += 1
    return i + 1 if i < len(lines) else 1


class AgentMarkdown(Markdown):
    """Markdown without HTML, so placeholders like /lst/<make>/<model> stay visible."""

    def __init__(self, markup: str, **kwargs: Any) -> None:
        super().__init__(markup, **kwargs)
        self.parsed = MarkdownIt().enable("strikethrough").enable("table").disable(["html_inline", "html_block"]).parse(markup)


# Flag emoji are pairs of regional indicators; terminals draw them wider than they are counted,
# which leaves stray characters behind on redraw. Variation selectors, joiners and skin tones
# cause the same drift, so text gets their plain form.
_DRIFT = re.compile("[\U0001f1e6-\U0001f1ff]{2}\\s?|[\ufe0f\u200d\U0001f3fb-\U0001f3ff]")


def terminal_safe(text: str) -> str:
    return _DRIFT.sub("", text)


ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def readable(line: str) -> str:
    """A line of tool output, or a word for it when it is bytes rather than text, such as a compressed body.
    Terminal colors are text: a test runner's green PASS is not binary."""
    text = ANSI.sub("", line)
    odd = sum(1 for ch in text if ch == "\ufffd" or (ord(ch) < 32 and ch != "\t"))
    return "(binary data)" if text and odd * 10 > len(text) else line


def strip_markdown(text: str) -> str:
    """Thinking summaries come as light Markdown; a margin note shows them as plain text."""
    text = re.sub(r"\*\*(\S(?:.*?\S)?)\*\*", r"\1", text)  # only ** bold: __ is too often part of a name
    return re.sub(r"(`|^#+\s+|^\s*[-*]\s+(?=\S))", "", text, flags=re.MULTILINE)


def first_words(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def escape_partial(text: str) -> str:
    """Half-streamed Markdown, kept from opening a code block that has not closed yet."""
    return text + "\n```" if text.count("```") % 2 else text


def run_summary(run: dict[str, Any]) -> str:
    """One line for a past run in a picker: when, what was asked, what it cost."""
    when = str(run.get("timestamp", ""))[5:16].replace("T", " ")
    prompt = " ".join(str(run.get("prompt") or "").split())
    prompt = prompt if len(prompt) <= 44 else prompt[:43] + "…"
    cost = recorded_cost(run.get("usage")) or 0
    return f"{when}  {prompt:<44}  " + (money(cost) if cost else "")


def link(text: str, target: Path | str) -> str:
    """Clickable text; a relative path has no file URI, so it stays plain."""
    if isinstance(target, Path):
        if not target.is_absolute():
            return escape(text)
        target = target.as_uri()
    return f"[link={target.replace('[', '%5B').replace(']', '%5D')}]{escape(text)}[/link]"


class Deferred:
    """A renderable built when it is first rendered, then kept."""

    def __init__(self, build: Callable[[], RenderableType]) -> None:
        self._build: Callable[[], RenderableType] | None = build
        self._built: RenderableType | None = None

    def __rich_console__(self, console: Any, options: Any) -> Any:
        if self._build is not None:
            self._built, self._build = self._build(), None
        yield self._built


@dataclass
class Picker:
    title: str
    items: list[tuple[str, str, str]]  # value, label, description
    current: str | None
    on_pick: Callable[[str | None], None]
    index: int = 0
    question: bool = False  # an agent question, which ends with its run
    multi: bool = False  # several options can be chosen, with space, before enter sends them
    chosen: list[str] = field(default_factory=list)
    typed: bool = False  # enter sends what was typed in the bar, when anything was
    search: bool = False  # what is typed in the bar narrows the items
    hint: str = ""  # shown in the empty bar: what typing does here


@dataclass
class SessionState:
    mode: str = "agent"
    sdk: str = "claude"
    model: str | None = None
    effort: str | None = None  # None: the model's default
    run_id: str | None = None
    running: bool = False  # the agent is working
    waiting: bool = False  # a run is open and waits for a follow-up
    verb: str = "thinking"
    kind: str = "other"
    started: float = 0.0
    tokens: int = 0
    cost: float = 0.0
    step: int = 0
    host: str = ""
    client_name: str = ""
    last_client: Path | None = None
    queue: list[str] = field(default_factory=list)
    scroll: int = 0  # lines scrolled up from the latest output
    folded: bool = False  # some output was cut short, so ctrl+o has more to show
    palette_index: int = 0
    picker: Picker | None = None
    question: Any = None  # a free-text question waiting for the next Enter
    # The open run's own model, SDK and effort. They can differ from the selection above, which is
    # what the next run starts with: a resumed run keeps its SDK, and /model mid-run waits for the next one.
    run_model: str | None = None
    run_sdk: str | None = None
    run_effort: str | None = None
    collector_model: str | None = None  # collector mode runs on its own model setting

    @property
    def accent(self) -> str:
        return MODE_COLORS.get(self.mode, PINK)

    @property
    def model_label(self) -> str:
        return model_label(self.model)

    @property
    def effort_label(self) -> str:
        return self.effort or default_effort(self.next_model)

    @property
    def has_effort(self) -> bool:
        """Effort is a Claude setting; collector mode goes by its own model."""
        return self.sdk == "claude" and not predates_effort(self.next_model)

    @property
    def no_effort_reason(self) -> str:
        if self.sdk == "claude":
            return f"{model_label(self.next_model)} has no effort setting · /model picks one that does"
        return f"effort is a claude setting · this session runs {self.sdk} {self.model_label}"

    @property
    def next_model(self) -> str | None:
        """What a new run in the current mode starts with."""
        return self.collector_model if self.mode == "collector" and self.collector_model else self.model

    @property
    def live_model_label(self) -> str:
        """The model the next message goes to: the open run's, else the selection for this mode."""
        return model_label(self.run_model or self.next_model)

    @property
    def run_open(self) -> bool:
        return self.running or self.waiting

    def elapsed(self) -> str:
        secs = int(time.time() - self.started) if self.started else 0
        return f"{secs // 60}m{secs % 60:02d}s" if secs >= 60 else f"{secs}s"


PLAN_STATUSES = {
    "pending": "pending",
    "todo": "pending",
    "notstarted": "pending",
    "inprogress": "in_progress",
    "active": "in_progress",
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def hanging(mark: Text, body: Text, margin: int) -> Table:
    """A mark right-aligned in a margin of this width, and text that wraps under itself instead of the left edge."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=margin, justify="right")
    grid.add_column(overflow="fold")  # a path or URL breaks across lines rather than losing its end
    grid.add_row(mark, body)
    return grid


def k(n: float) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(int(n))


def money(cost: float) -> str:
    return "<$0.01" if 0 < cost < 0.005 else f"${cost:.2f}"


class LedgerView:
    """A numbered ledger of tool steps with └ receipts, agent messages as Markdown, a boarding-pass card."""

    def __init__(self, st: SessionState, transcript: Transcript) -> None:
        self.st = st
        self.t = transcript
        self._verb: str | None = None
        self._verb_at = 0.0
        # A message being revealed, and what arrived after it: engines write from their thread,
        # the app reveals on its frames, so both go through this lock.
        self._lock = threading.RLock()
        self._live: dict[str, Any] | None = None
        self._pending: list[tuple[RenderableType | Raw, RenderableType | Raw | None]] = []

    # writing to the transcript

    def out(self, inline: RenderableType | Raw, full: RenderableType | Raw | None = None) -> None:
        with self._lock:
            if self._live is not None:
                self._pending.append((inline, full))  # shown once the message above has finished
                return
            self._emit(inline, full)

    def _emit(self, inline: RenderableType | Raw, full: RenderableType | Raw | None = None) -> None:
        added = self.t.add(inline, full)
        if self.st.scroll:
            self.st.scroll += added  # keep the reader's place while output arrives

    def gap(self) -> None:
        with self._lock:
            last = self._pending[-1][0] if self._pending else self.t.last()
            if (self._pending or self.t.items) and last != "":
                self.out("")

    # streaming messages

    def _message_grid(self, text: str) -> Table:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=2, justify="right")
        grid.add_column(max_width=min(96, width() - 4))
        grid.add_row(f"[{self.st.accent}]¶[/]", AgentMarkdown(terminal_safe(text), code_theme=CODE_THEME))
        return grid

    def _note_grid(self, text: str, live: bool = False, full: bool = False) -> Table:
        """The model's reasoning in the margin: dim italic, the end shown while it streams, the start once done."""
        lines = [line for line in strip_markdown(terminal_safe(text)).splitlines() if line.strip()] or [""]
        shown = lines if full else lines[-NOTE_LINES:] if live else lines[:NOTE_LINES]
        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=5, justify="right")
        grid.add_column(max_width=min(92, width() - 8))
        body = Text("\n".join(shown), style=f"italic {DIM}")
        if len(shown) < len(lines) and not live:
            self.st.folded = True
            body.append(f"\n+{len(lines) - len(shown)} lines · ctrl+o full output", style=DIM)
        grid.add_row(Text("┊", style=HAIRLINE), body)
        return grid

    def stream(self, delta: str, kind: str = "message") -> None:
        """A piece of the agent's text, or of its reasoning (kind "note"), as it is generated."""
        with self._lock:
            if self._live is not None and (self._live["closing"] or self._live["kind"] != kind):
                self._finalize()
            if self._live is None:
                self.gap()
                self._live = {"target": "", "shown": 0, "closing": False, "kind": kind}
            self._live["target"] += delta

    def stream_done(self, final: str | None = None, kind: str = "message") -> None:
        """The text is complete; ``final`` replaces what streamed, or starts a reveal when nothing did."""
        with self._lock:
            # A live text that is already complete belongs to an earlier message, still being revealed.
            if self._live is not None and (self._live["kind"] != kind or self._live["closing"]):
                self._finalize()
            if self._live is None:
                if not final or not final.strip():
                    return
                self.gap()
                self._live = {"target": "", "shown": 0, "closing": False, "kind": kind}
            if final and final.strip():
                self._live["target"] = final
            self._live["closing"] = True

    def tick(self) -> None:
        """Reveal a little more of the live message; called on every frame of the app."""
        with self._lock:
            live = self._live
            if live is None:
                return
            target, shown = live["target"], live["shown"]
            backlog = len(target) - shown
            if backlog > 0:
                # Steady at first, faster when text piles up, and stopping on word ends.
                nxt = min(len(target), shown + max(3, math.ceil(backlog * 0.18)))
                space = target.find(" ", nxt)
                live["shown"] = space if 0 <= space - nxt <= 6 else nxt
            if live["closing"] and live["shown"] >= len(target):
                self._finalize()
                return
            partial = target[: live["shown"]]
            if live["kind"] == "note":
                self.t.set_live(self._note_grid(partial, live=True))
            else:
                self.t.set_live(Group(self._message_grid(escape_partial(partial) + " ▍")))

    def flush_live(self) -> None:
        """Settle the live message at once, with everything that waited behind it."""
        with self._lock:
            if self._live is not None:
                self._finalize()

    def _finalize(self) -> None:
        live, self._live = self._live, None
        self.t.set_live(None)
        text = (live or {}).get("target", "").strip()
        if text:
            note = (live or {}).get("kind") == "note"
            self._emit(*((self._note_grid(text), self._note_grid(text, full=True)) if note else (self._message_grid(text),)))
            self._emit("")
        pending, self._pending = self._pending, []
        for inline, full in pending:
            self._emit(inline, full)

    # header

    def header_rows(self, theta: float) -> list[list[tuple[str, str]]]:
        st = self.st
        text = [
            [],
            [],
            [
                (f"fg:{PINK} bold", " * "),
                (f"fg:{INK} bold", "rae"),
                (f"fg:{DIM}", f"  v{__version__}"),
                (f"fg:{INK_SOFT}", "   turn websites into "),
                (f"fg:{PINK} italic", "APIs"),
            ],
            [(f"fg:{DIM}", f"   {st.sdk} · {st.model_label}" + (f" · effort {st.effort_label}" if st.has_effort else ""))],
            [],
            [(f"fg:{DIM}", "   describe the API you want · / for commands")],
        ]
        widest = max(sum(len(t) for _, t in row) for row in text)
        logo = logo_rows(theta) if width() >= widest + LOGO_COLS + 10 and height() >= 24 else []
        rows: list[list[tuple[str, str]]] = [[] for _ in range(TOP_PADDING)]
        for r in range(max(len(text), len(logo))):
            row = list(text[r]) if r < len(text) else []
            if r < len(logo):
                row += [("", " " * (width() - LOGO_COLS - 5 - sum(len(t) for _, t in row)))] + logo[r]
            rows.append(row)
        rows.append([])
        return rows

    def header_text(self) -> list[Text]:
        """The header frozen, for printing the session into the terminal at exit."""
        out = []
        for row in self.header_rows(theta=0.0):
            line = Text()
            for style, chunk in row:
                line.append(chunk, style=rich_style(style))
            out.append(line)
        return out

    # the ledger

    def user(self, text: str) -> None:
        self.gap()
        self.out(hanging(Text("›", style=f"bold {self.st.accent}"), Text(terminal_safe(text), style=INK), 2))
        self.out("")

    def command(self, cmd: str, arg: str = "") -> None:
        """A slash command, kept in the conversation so it reads why something appeared."""
        self.gap()
        self.out(f" [{DIM}]›[/] [{self.st.accent}]{escape(cmd)}[/]" + (f" [{INK_SOFT}]{escape(arg)}[/]" if arg else ""))

    def run_line(self, run_id: str, mode: str | None) -> None:
        self.out(f"   [{DIM}]run {escape(run_id)} · {escape(mode or self.st.mode)}[/]")
        self.out("")

    def note(self, text: str) -> None:
        """Real reasoning, when a model shares it: set in the margin."""
        self.out(f"      [{HAIRLINE}]┊[/] [italic {DIM}]“{escape(text)}”[/]")

    def step(self, verb: str, target: str, kind: str = "other", path: Path | None = None, url: str | None = None) -> None:
        st = self.st
        st.step += 1
        tint = KIND_TINT.get(kind, PASTEL_OTHER)
        # One line per step: a target that wrapped would start again at the left edge, under the numbers.
        room = max(10, width() - INDENT - 2)
        target = target if len(target) <= room else target[: room - 1] + "…"
        shown = link(target, path) if path else link(target, url) if url else escape(target)
        self.out(f" [{tint}]*[/] [{DIM}]{st.step:02d}[/]  [bold {tint}]{escape(verb):<{VERB_COL}}[/] [{INK_SOFT}]{shown}[/]")

    def receipt(self, lines: list[str], error: bool = False) -> None:
        room = max(20, width() - INDENT - 4)

        def block(rows: list[str], more: int, cut: bool) -> Group:
            texts = []
            for i, line in enumerate(rows):
                line = terminal_safe(readable(line))
                body = Text(line if not cut or len(line) <= room else line[: room - 1] + "…", style=PINK if error else DIM)
                RECEIPT_HL.highlight(body)
                texts.append(Text.assemble(" " * INDENT, ("└ " if i == 0 else "  ", HAIRLINE), body))
            if more:
                texts.append(Text.assemble(" " * (INDENT + 2), (f"+{more} lines · ctrl+o full output", DIM)))
            return Group(*texts)

        # Browser tools answer in markdown; their heading marks are noise in a receipt.
        lines = [re.sub(r"^#+\s+", "", line.rstrip()) for line in lines if line.strip()] or ["done"]
        more = max(0, len(lines) - OUTPUT_PREVIEW)
        self.st.folded = self.st.folded or more > 0
        # The full copy is only styled if ctrl+o asks for it: tool output can run to thousands of lines.
        self.out(block(lines[:OUTPUT_PREVIEW], more, cut=True), Deferred(lambda: block(lines, 0, cut=False)))

    def workspace(self, folder: Path, copy: Path | None) -> None:
        """Where a verified client's files are, absolute so a click opens them; a long path wraps under itself."""
        rows = [("in", folder), ("copy", copy)] if copy else [("in", folder)]
        for label, path in rows:
            mark = Text.from_markup(f"[{HAIRLINE}]└[/] [{DIM}]{label}[/]")
            self.out(Padding(hanging(mark, Text.from_markup(f"[{INK_SOFT}]{link(str(path), path)}[/]"), len(label) + 2), (0, 0, 0, INDENT)))

    def collected(self, total: int, folder: Path) -> None:
        """A collector run's result: how many items, and the folder with its JSON, CSV and README."""
        items = f"{total} item{'s' if total != 1 else ''}"
        body = Text.from_markup(f"[bold {INK}]{items}[/] [italic {PINK}]collected[/] [{INK_SOFT}]{link(str(folder), folder)}[/]")
        self.out(Padding(hanging(Text("*", style=self.st.accent), body, 1), (0, 0, 0, 1)))

    def docs_ready(self, path: Path) -> None:
        body = Text.from_markup(f"[bold {INK}]{link(path.name, path)}[/] [italic {PINK}]documentation ready[/]")
        self.out(Padding(hanging(Text("*", style=self.st.accent), body, 1), (0, 0, 0, 1)))

    def copied(self, folder: Path) -> None:
        mark = Text("copied to", style=DIM)
        self.out(Padding(hanging(mark, Text.from_markup(f"[{INK_SOFT}]{link(str(folder), folder)}[/]"), len("copied to")), (0, 0, 0, 3)))

    def code(self, source: str, language: str) -> None:
        """Written code, previewed from its first definition; ctrl+o shows all of it."""
        total = source.count("\n") + 1
        first = first_definition(source)
        self.st.folded = self.st.folded or total > CODE_PREVIEW
        preview = Syntax(
            source, language, theme=CODE_THEME, line_numbers=True, line_range=(first, first + CODE_PREVIEW - 1), background_color="default"
        )
        full = Syntax(source, language, theme=CODE_THEME, line_numbers=True, background_color="default")
        parts: list[RenderableType] = [Padding(preview, (0, 0, 0, INDENT))]
        if total > CODE_PREVIEW:
            parts.append(Text.assemble(" " * (INDENT + 2), (f"+{total - CODE_PREVIEW} lines · ctrl+o full output", DIM)))
        self.out(Group(*parts), Padding(full, (0, 0, 0, INDENT)))

    def diff(self, removed: str, added: str, language: str) -> None:
        def code_line(line: str) -> Text:
            text = Syntax(line, language, theme=CODE_THEME, background_color="default").highlight(line)
            text.rstrip()
            return text

        old, new = removed.splitlines(), added.splitlines()
        rows = [Text.assemble(" " * INDENT, ("- ", f"bold {PINK}"), code_line(line)) for line in old]
        rows += [Text.assemble(" " * INDENT, ("+ ", f"bold {MINT}"), code_line(line)) for line in new]
        shown = [row.copy() for row in rows[: OUTPUT_PREVIEW * 2]]
        for row in shown:
            row.no_wrap, row.overflow = True, "ellipsis"  # a wrapped line would start again at the left edge; ctrl+o keeps it whole
        if len(rows) > len(shown):
            self.st.folded = True
            shown.append(Text.assemble(" " * (INDENT + 2), (f"+{len(rows) - len(shown)} lines · ctrl+o full output", DIM)))
        self.out(Group(*shown), Group(*rows))

    def message(self, text: str) -> None:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=2, justify="right")
        grid.add_column(max_width=min(96, width() - 4))
        grid.add_row(f"[{self.st.accent}]¶[/]", AgentMarkdown(text, code_theme=CODE_THEME))
        self.gap()
        self.out(grid)
        self.out("")

    def plan(self, todos: list[dict[str, Any]]) -> None:
        """The agent's task list, in any SDK's shape: Claude's content and activeForm, Claude's task subject,
        a plan's step, statuses such as Cursor's inProgress."""
        marks = {"completed": "✓", "in_progress": "›", "pending": "○", "cancelled": "✗"}
        rows = []
        for t in todos[:12]:
            raw = re.sub(r"[\s_-]", "", str(t.get("status") or "pending")).lower()
            status = PLAN_STATUSES.get(raw, "pending")
            text = (t.get("activeForm") if status == "in_progress" else None) or next(
                (t[k] for k in ("content", "subject", "step", "description", "title", "text") if t.get(k)), ""
            )
            color = MINT if status == "completed" else INK if status == "in_progress" else DIM
            rows.append(Text.assemble(" " * INDENT, (f"{marks.get(status, '·')} ", color), (terminal_safe(str(text))[:90], color)))
        self.out(Group(*rows))

    def card(self, path: Path, lines_written: int, language: str) -> None:
        """The run's receipt as a boarding pass: the client on the left, a perforated stub with the run's model."""
        st = self.st
        lang = LANGUAGE_NAMES.get(language, language)
        main = [
            (f"[{st.accent}]*[/] [bold {INK}]{link(path.name, path)}[/] [italic {PINK}]ready[/]", f"* {path.name} ready"),
            (f"  [{INK_SOFT}]{lang} · {lines_written} lines[/]", f"  {lang} · {lines_written} lines"),
            (f"  [{DIM}]{k(st.tokens)} tokens · {money(st.cost)}[/]", f"  {k(st.tokens)} tokens · {money(st.cost)}"),
        ]
        model, effort, sdk = st.live_model_label, st.run_effort, st.run_sdk or st.sdk
        stub = [
            (f"[{INK_SOFT}]{escape(model)}[/]", model),
            (f"[{DIM}]effort {effort}[/]", f"effort {effort}") if effort else (f"[{DIM}]{sdk}[/]", sdk),
            (f"[{DIM}]{st.elapsed()}[/]", st.elapsed()),
        ]
        main_w = max(len(plain) for _, plain in main) + 4
        stub_w = max(len(plain) for _, plain in stub) + 4
        legend = " client "
        top = f"╭─[{DIM}]{legend}[/][{HAIRLINE}]{'─' * (main_w - len(legend) - 1)}┬{'─' * stub_w}╮"
        lines = [f" [{HAIRLINE}]{top}[/]"]
        for (m, mp), (t, tp) in zip(main, stub, strict=True):
            lines.append(f" [{HAIRLINE}]│[/]  {m}{' ' * (main_w - 2 - len(mp))}[{HAIRLINE}]┊[/]  {t}{' ' * (stub_w - 2 - len(tp))}[{HAIRLINE}]│[/]")
        lines += [f" [{HAIRLINE}]╰{'─' * main_w}┴{'─' * stub_w}╯[/]"]
        self.gap()
        self.out("\n".join(lines))
        self.out("")
        st.last_client = path

    def run_details(self, run: dict[str, Any]) -> None:
        """A past run picked in /history: when and how it ran, what it cost, where its client is."""
        usage = run.get("usage") or {}
        cost = recorded_cost(usage) or 0
        tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
        when = str(run.get("timestamp", ""))[:16].replace("T", " ")
        facts = " · ".join(x for x in (when, model_label(run.get("model")) if run.get("model") else "", run.get("mode") or "") if x)
        spend = " · ".join(x for x in (money(cost) if cost else "", f"{k(tokens)} tokens" if tokens else "") if x)
        script = (run.get("paths") or {}).get("script_path")
        lines = [f" [{self.st.accent}]*[/] [bold {INK}]{escape(str(run.get('run_id', '')))}[/]  [{DIM}]{escape(facts)}[/]"]
        lines.append(f"   [{HAIRLINE}]└[/] [{INK_SOFT}]{escape(first_words(str(run.get('prompt') or ''), 200))}[/]")
        if spend or script:
            client = link(Path(script).name, Path(script)) if script and Path(script).exists() else "no client"
            lines.append(f"     [{DIM}]{escape(spend) + ' · ' if spend else ''}[/][{INK_SOFT}]{client}[/]")
        self.out("\n".join(lines))

    def event(self, key: str, old: str, new: str, note: str = "") -> None:
        """A settings change, set apart from the conversation: ◇ model  sonnet 5.5 → opus 5.5."""
        tail = f"  [{DIM}]· {escape(note)}[/]" if note else ""
        self.out(f"   [{AMBER}]◇[/] [{INK_SOFT}]{escape(key)}[/]  [{DIM}]{escape(old)} →[/] [bold {INK}]{escape(new)}[/]{tail}")

    def help(self, modes: dict[str, str], commands: dict[str, str], keys: tuple[tuple[str, str], ...]) -> None:
        """/help: what rae does, then its modes, commands and keys, their names in one column."""
        accent = self.st.accent
        about = (
            "rae turns a website into an API client. Describe the API you want: the agent opens the site, "
            "reads the requests it makes, writes a client and runs it against the live site before it is done."
        )
        self.out(Padding(Text(about, style=INK_SOFT), (0, 0, 0, 3)))
        sections = [
            ("modes", "shift+tab switches", [(m, d, f"bold {accent}" if m == self.st.mode else INK) for m, d in modes.items()]),
            ("commands", "type / for the list", [(c, d, accent) for c, d in commands.items()]),
            ("keys", "", [(key, d, INK) for key, d in keys]),
        ]
        name_w = max(len(name) for _, _, rows in sections for name, _, _ in rows)
        for title, note, rows in sections:
            self.out("")
            self.out(f"   [bold {INK}]{title}[/]" + (f"  [{DIM}]· {note}[/]" if note else ""))
            grid = Table.grid(padding=(0, 2))
            grid.add_column(width=name_w)
            grid.add_column()
            for name, desc, style in rows:
                current = f"  [{accent}]●[/]" if title == "modes" and name == self.st.mode else ""
                grid.add_row(Text(name, style=style), Text.from_markup(f"[{DIM}]{escape(desc)}[/]{current}"))
            self.out(Padding(grid, (0, 0, 0, 5)))
        self.out("")
        self.out(f"   [{DIM}]docs[/]  [{INK_SOFT}]{link('reverseapi.dev/docs', 'https://reverseapi.dev/docs')}[/]")
        self.out("")

    def notice(self, text: str) -> None:
        self.out(Padding(Text(text, style=DIM), (0, 0, 0, 3)))

    def error(self, text: str) -> None:
        self.gap()
        self.out(hanging(Text("!", style=f"bold {PINK}"), Text(text, style=PINK), 4))
        self.out("")

    def question(self, text: str) -> None:
        self.gap()
        self.out(f" [bold {AMBER}]?[/] [{INK}]{escape(text)}[/]")

    def answer(self, text: str) -> None:
        self.out(f"      [{HAIRLINE}]┊[/] [{INK_SOFT}]{escape(text)}[/]")
        self.out("")

    def interrupted(self) -> None:
        self.out(f"      [{HAIRLINE}]┊[/] [{PINK}]interrupted[/] [{DIM}]· the partial capture is kept[/]")
        self.out("")

    # the bar

    def flap(self, verb: str) -> str:
        """The verb, flipping in letter by letter like a split-flap board when the step changes."""
        if verb != self._verb:
            self._verb, self._verb_at = verb, time.time()
        settled = int((time.time() - self._verb_at) / 0.035)
        tick = int(time.time() * 30)
        return "".join(ch if i < settled or ch == " " else FLAP[(tick + i * 7) % len(FLAP)] for i, ch in enumerate(verb))

    def spinner(self) -> list[tuple[str, str]]:
        """A tape from the site to the client with packets running along it: a website turning into an API."""
        st = self.st
        tint = KIND_TINT.get(st.kind, PASTEL_OTHER)
        source, sink, clock = st.host or "the site", st.client_name or "your API", st.elapsed()
        head = [("", "\n"), (f"fg:{INK} italic", f" {self.flap(st.verb)}"), ("", " " * max(2, 22 - len(st.verb)))]
        track = max(8, width() - sum(len(t) for _, t in head) - len(source) - len(sink) - len(clock) - 6)
        offset = int(time.time() * 9)
        tape = [(f"fg:{tint} bold", "▪") if (i - offset) % 7 == 0 else (f"fg:{HAIRLINE}", "┄") for i in range(track)]
        out = head + [(f"fg:{INK_SOFT}", source), ("", " ")] + tape + [("", " "), (f"fg:{INK_SOFT}", sink), (f"fg:{DIM}", f"   {clock}")]
        for q in st.queue:
            out += [("", "\n"), (f"fg:{DIM}", "   queued › "), (f"fg:{INK_SOFT}", q)]
        return out + [("", "\n")]  # a blank row between the tape and the input

    def seam(self) -> list[tuple[str, str]]:
        """The line above the input, a fieldset legend: the mode on the left, the model on the right."""
        st = self.st
        left = [(f"fg:{HAIRLINE}", " ┄┄ "), (f"fg:{st.accent} italic", st.mode), ("", " ")]
        right = [("", " "), (f"fg:{INK_SOFT}", st.live_model_label), (f"fg:{HAIRLINE}", " ┄┄")]
        used = sum(len(t) for _, t in left) + sum(len(t) for _, t in right)
        return left + [(f"fg:{HAIRLINE}", "┄" * max(1, width() - used - 1))] + right

    def seam_under(self) -> list[tuple[str, str]]:
        return [(f"fg:{HAIRLINE}", " " + "┄" * (width() - 2))]

    def marker(self) -> list[tuple[str, str]]:
        return [(f"fg:{AMBER if self.st.question else self.st.accent} bold", " › ")]

    @staticmethod
    def pill(color: str, body: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """A pastel chip with rounded half-block ends, like a small post-it."""
        return [(f"fg:{color}", "▐")] + [(f"{style} bg:{color}", text) for style, text in body] + [(f"fg:{color}", "▌")]

    def status(self) -> FormattedText:
        st = self.st
        level = EFFORTS.index(st.effort_label) if st.effort_label in EFFORTS else 2
        gauge = [
            (f"fg:{CHIP_INK}", " "),
            (f"fg:{PINK} bold", "▰" * (level + 1)),
            (f"fg:{GAUGE_EMPTY}", "▱" * (len(EFFORTS) - level - 1)),
            (f"fg:{CHIP_INK}", f" {st.effort_label} "),
        ]
        left: list[tuple[str, str]] = [("", "   ")]
        if st.has_effort:
            left += self.pill(CHIP_LAVENDER, gauge) + [(f"fg:{DIM}", " ⌃e  ")]
        if st.cost:
            left += self.pill(CHIP_YELLOW, [(f"fg:{CHIP_INK} bold", f" {money(st.cost)} ")]) + [("", "  ")]
        if st.scroll:
            hint = [(f"fg:{AMBER}", "end ↓ back to the latest ")]
        elif st.question is not None:
            hint = [(f"fg:{AMBER}", "type your answer · esc skips ")]
        elif st.running:
            hint = [(f"fg:{DIM}", "esc stops · enter queues ")]
        elif st.waiting:
            hint = [(f"fg:{DIM}", "type a follow-up · /new starts over" + (" · ⌃o expand " if st.folded else " "))]
        else:
            hint = [(f"fg:{DIM}", "/ commands" + (" · ⌃o expand " if st.folded else " "))]
        used = sum(len(t) for _, t in left) + sum(len(t) for _, t in hint)
        run = f"· run {st.run_id} " if st.run_id else ""
        if run and used + 1 + len(run) <= width():  # left out rather than cut off
            hint, used = hint + [(f"fg:{DIM}", run)], used + len(run)
        return FormattedText(left + [("", " " * max(1, width() - used))] + hint)

    def menu(
        self, rows: list[tuple[str, str, bool, bool]], title: str | None = None, limit: int = MENU_ROWS, empty: str = "no matching command"
    ) -> FormattedText:
        """A list under the input: (label, description, selected, current)."""
        st = self.st
        out: list[tuple[str, str]] = []
        if title:
            out += [(f"fg:{DIM} italic", f"   {title}")]
        label_w = max((len(r[0]) for r in rows), default=0) + 3
        selected_at = next((i for i, r in enumerate(rows) if r[2]), 0)
        start = max(0, min(selected_at - limit // 2, len(rows) - limit))
        hidden = max(0, len(rows) - limit)
        rows = rows[start : start + limit]
        for label, desc, selected, current in rows:
            if out:
                out += [("", "\n")]
            if selected:
                out += [(f"fg:{st.accent} bold", " › "), (f"fg:{INK} bold", f"{label:<{label_w}}"), (f"fg:{INK_SOFT}", desc)]
            else:
                out += [("", "   "), (f"fg:{INK_SOFT}", f"{label:<{label_w}}"), (f"fg:{DIM}", desc)]
            out += [(f"fg:{st.accent}", "  ●" if current else "")]
        if not rows:
            out += [(f"fg:{DIM}", f"   {empty}")]
        if hidden:
            out += [("", "\n"), (f"fg:{DIM}", f"   {hidden} more · ↑↓")]
        return FormattedText(out)
