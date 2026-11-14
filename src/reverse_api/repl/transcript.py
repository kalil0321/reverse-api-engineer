"""The conversation as prompt_toolkit lines: rich renderables rendered at the current width, plus captured output."""

from __future__ import annotations

import io
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from rich.console import Console, RenderableType

from .style import THEME, pt_style, width

Line = list[tuple[Any, ...]]
# (line, character) in the conversation's lines. A window hands its control the index of the character
# under the pointer, the whole of a wide one, rather than a screen column.
Point = tuple[int, int]
LINE_END = 1 << 30  # past the last character of any line


@dataclass
class Selection:
    """Text dragged over in the conversation, from where the drag began to where the pointer is."""

    anchor: Point
    head: Point
    dragging: bool = True

    @property
    def span(self) -> tuple[Point, Point]:
        return min(self.anchor, self.head), max(self.anchor, self.head)

    def chars(self, line: int) -> tuple[int, int | None] | None:
        """The characters selected on a line, both included (None: to its end), or None when it is outside."""
        (l0, c0), (l1, c1) = self.span
        if not l0 <= line <= l1:
            return None
        return (c0 if line == l0 else 0), (c1 if line == l1 else None)


def text_of(line: Line) -> str:
    return "".join(text for _style, text, *_ in line)


def selected_text(lines: list[Line], selection: Selection) -> str:
    """The selected text, one row per line, without the padding a terminal would also leave out.

    Blank rows at its end are dropped: pasted into a shell, a final newline would run the command.
    """
    (l0, _), (l1, _) = selection.span
    rows = []
    for i in range(l0, min(l1, len(lines) - 1) + 1):
        lo, hi = selection.chars(i) or (0, None)
        rows.append(text_of(lines[i])[lo : None if hi is None else hi + 1].rstrip())
    return "\n".join(rows).rstrip("\n")


def highlight(line: Line, lo: int, hi: int | None) -> Line:
    """The line with its characters ``lo`` to ``hi`` drawn reversed; link handlers are kept."""
    out: Line = []
    i = 0
    for style, text, *handler in line:
        for ch in text:
            picked = i >= lo and (hi is None or i <= hi)
            out.append((f"{style} reverse" if picked else style, ch, *handler))
            i += 1
    return out


class Raw:
    """Lines captured from plain prints, kept as they were written."""

    def __init__(self, lines: list[Line], text: str) -> None:
        self.lines = lines
        self.text = text


class Transcript:
    """Everything shown in the conversation, re-rendered when the terminal width changes.

    Engines add items from their own thread while the app reads lines, hence the lock.
    """

    def __init__(self, on_link: Callable[[str], None]) -> None:
        self.items: list[RenderableType | Raw] = []
        self.full: list[RenderableType | Raw] = []  # what ctrl+o shows: the same items, unfolded
        self.on_link = on_link
        self._lock = threading.RLock()
        self._width = 0
        self._lines: list[Line] = []
        self._live: RenderableType | None = None  # a message still being revealed

    def add(self, inline: RenderableType | Raw, full: RenderableType | Raw | None = None) -> int:
        """Append an item; returns how many lines it added at the current width."""
        with self._lock:
            self.items.append(inline)
            self.full.append(inline if full is None else full)
            if self._width == width():
                new = self._render(inline)
                self._lines.extend(new)
                return len(new)
            return 0

    def last(self) -> RenderableType | Raw | None:
        with self._lock:
            return self.items[-1] if self.items else None

    def clear(self) -> None:
        with self._lock:
            self.items.clear()
            self.full.clear()
            self._lines.clear()

    def set_live(self, renderable: RenderableType | None) -> None:
        with self._lock:
            self._live = renderable

    def lines(self) -> list[Line]:
        with self._lock:
            if self._width != width():
                self._width = width()
                self._lines = [line for item in self.items for line in self._render(item)]
            return self._lines + (self._render(self._live) if self._live is not None else [])

    def _render(self, item: RenderableType | Raw) -> list[Line]:
        if isinstance(item, Raw):
            return item.lines
        console = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor", width=width(), theme=THEME, highlight=False)
        if isinstance(item, str):
            item = console.render_str(item, highlight=False)
        out: list[Line] = []
        for segments in console.render_lines(item, console.options, pad=False):
            frags: Line = []
            for seg in segments:
                if seg.control:
                    continue
                target = seg.style.link if seg.style else None
                if target:
                    frags.append((pt_style(seg.style) + " underline", seg.text, self._opener(target)))
                else:
                    frags.append((pt_style(seg.style), seg.text))
            out.append(frags)
        return out

    def _opener(self, target: str) -> Callable[[MouseEvent], object]:
        def handler(event: MouseEvent) -> object:
            if event.event_type == MouseEventType.MOUSE_UP:
                self.on_link(target)
                return None
            return NotImplemented

        return handler


def raw_lines(text: str, plain_style: str = "", indent: str = "") -> Raw:
    """Plain or ANSI-colored text as transcript lines; uncolored text takes ``plain_style``."""
    frags = to_formatted_text(ANSI(text))
    lines: list[Line] = [[("", indent)] if indent else []]
    for style, chunk, *_ in frags:
        parts = chunk.split("\n")
        for i, part in enumerate(parts):
            if i:
                lines.append([("", indent)] if indent else [])
            if part:
                lines[-1].append((style or plain_style, part))
    return Raw(lines, text)


class TranscriptWriter(io.TextIOBase):
    """A file that turns whatever is written to it into transcript lines.

    Installed as sys.stdout and sys.stderr while the full-screen app runs, so stray prints
    land in the conversation instead of corrupting the screen. It reports no terminal, which
    keeps rich from animating spinners into it.
    """

    def __init__(self, sink: Callable[[Raw], None], plain_style: str = "", indent: str = "") -> None:
        super().__init__()
        self._sink = sink
        self._plain_style, self._indent = plain_style, indent
        self._buf = ""
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        # No descriptor: a subprocess handed the real one would draw over the full-screen app.
        raise io.UnsupportedOperation("the session's output is not a file descriptor")

    def write(self, s: str) -> int:
        with self._lock:
            self._buf += s
            if "\n" in self._buf:
                done, self._buf = self._buf.rsplit("\n", 1)
                self._sink(raw_lines(done, self._plain_style, self._indent))
        return len(s)

    def flush(self) -> None:
        with self._lock:
            if self._buf:
                done, self._buf = self._buf, ""
                self._sink(raw_lines(done, self._plain_style, self._indent))


class TranscriptControl(FormattedTextControl):
    """The wheel scrolls the conversation, a drag selects text, and a click goes to the link under the pointer."""

    def __init__(
        self,
        get_text: Callable[[], FormattedText],
        on_scroll: Callable[[int], None],
        on_drag: Callable[[MouseEvent], bool] = lambda _event: False,
    ) -> None:
        super().__init__(get_text, focusable=False, show_cursor=False)
        self.on_scroll = on_scroll
        self.on_drag = on_drag  # True when the event was part of a selection

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.on_scroll(3)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.on_scroll(-3)
            return None
        if self.on_drag(mouse_event):
            return None
        return super().mouse_handler(mouse_event)


# The rest of the screen is under the conversation: a drag that reaches it goes on, and ends where it is let go.


class TextBelow(FormattedTextControl):
    def __init__(self, get_text: Callable[[], Any], on_drag: Callable[[MouseEvent], bool]) -> None:
        super().__init__(get_text)
        self.on_drag = on_drag

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        return None if self.on_drag(mouse_event) else super().mouse_handler(mouse_event)


class InputBelow(BufferControl):
    def __init__(self, on_drag: Callable[[MouseEvent], bool], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.on_drag = on_drag

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        return None if self.on_drag(mouse_event) else super().mouse_handler(mouse_event)
