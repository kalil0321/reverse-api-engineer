"""NDJSON event streaming for scripted CLI invocations (--json-stream)."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def make_json_stream_sink(write_line: Callable[[str], None]) -> Callable[[dict[str, Any]], None]:
    """Build a sink that writes one JSON object per line."""

    import json

    def sink(event: dict[str, Any]) -> None:
        write_line(json.dumps(event, default=str))

    return sink


class StreamingUIWrapper:
    """Delegate to an inner UI and emit json-stream events for key lifecycle hooks."""

    def __init__(self, inner: Any, sink: Callable[[dict[str, Any]], None]) -> None:
        self._inner = inner
        self._sink = sink

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def header(self, run_id: str, prompt: str, model: str | None = None, sdk: str | None = None, mode: str | None = None) -> None:
        self._sink(
            {
                "event": "header",
                "run_id": run_id,
                "prompt": prompt,
                "model": model,
                "sdk": sdk,
                "mode": mode,
            }
        )
        self._inner.header(run_id, prompt, model=model, sdk=sdk, mode=mode)

    def start_analysis(self) -> None:
        self._sink({"event": "progress", "message": "analysis_started"})
        self._inner.start_analysis()

    def tool_start(
        self, tool_name: str, tool_input: dict | Any = None, call_id: str | None = None
    ) -> None:
        event: dict[str, Any] = {"event": "tool_start", "name": tool_name}
        if call_id:
            event["call_id"] = call_id
        # Emit the real structured input (json.dumps serializes it); a stringified
        # repr would not be parseable as JSON by downstream consumers.
        if tool_input is not None:
            event["input"] = tool_input
        self._sink(event)
        # Inner UIs render only; not all accept call_id, so don't forward it.
        self._inner.tool_start(tool_name, tool_input)

    def tool_result(
        self,
        tool_name: str,
        is_error: bool = False,
        output: str | None = None,
        call_id: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": "tool_end",
            "name": tool_name,
            "is_error": is_error,
            "output_preview": (output[:200] if output else None),
        }
        if call_id:
            event["call_id"] = call_id
        self._sink(event)
        self._inner.tool_result(tool_name, is_error, output)

    def thinking(self, text: str, max_length: int = 500) -> None:
        preview = text[:500] if text else ""
        if preview.strip():
            self._sink({"event": "thinking", "text": preview})
        if hasattr(self._inner, "thinking"):
            sig = inspect.signature(self._inner.thinking)
            if "max_length" in sig.parameters:
                self._inner.thinking(text, max_length=max_length)
            else:
                self._inner.thinking(text)
        else:
            self._inner.thinking(text)

    def thinking_block(self, text: str, max_chars: int = 8000) -> None:
        preview = text[:800] if text else ""
        if preview.strip():
            self._sink({"event": "thinking_block", "text": preview})
        self._inner.thinking_block(text, max_chars=max_chars)

    def success(self, script_path: str, local_path: str | None = None) -> None:
        self._sink({"event": "success", "script_path": script_path, "local_path": local_path})
        self._inner.success(script_path, local_path)

    def error(self, message: str) -> None:
        self._sink({"event": "error", "message": message})
        self._inner.error(message)


def attach_json_stream_to_engineer(
    engineer: Any,
    sink: Callable[[dict[str, Any]], None],
    **run_started_extra: Any,
) -> None:
    """Enable NDJSON UI events on an engineer instance."""
    engineer._json_event_sink = sink
    engineer.ui = StreamingUIWrapper(engineer.ui, sink)
    started: dict[str, Any] = {
        "event": "run_started",
        "run_id": engineer.run_id,
        "sdk": getattr(engineer, "sdk", None),
    }
    for key, value in run_started_extra.items():
        if value is not None:
            started[key] = value
    sink(started)
