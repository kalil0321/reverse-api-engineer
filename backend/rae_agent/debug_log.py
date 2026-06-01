from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class DebugLog:
    """Append-only JSONL of every WS in/out + task lifecycle event,
    with monotonic timestamps and per-turn elapsed timing. Lives at
    `~/.reverse-api/logs/agent-<uuid>.jsonl` per sidecar run."""

    def __init__(self, log_dir: Path | None = None) -> None:
        if log_dir is None:
            log_dir = Path.home() / ".reverse-api" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"agent-{uuid.uuid4().hex[:8]}.jsonl"
        self._sidecar_start = time.monotonic()
        self._turn_starts: dict[str, float] = {}
        try:
            self.path.write_text("")
        except OSError:
            pass

    def _append(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, default=str)
        try:
            with self.path.open("a") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def _now(self, chat_id: str | None = None) -> dict[str, float]:
        sidecar_ms = (time.monotonic() - self._sidecar_start) * 1000
        out: dict[str, float] = {"tSidecarMs": round(sidecar_ms, 2)}
        if chat_id and chat_id in self._turn_starts:
            out["tTurnMs"] = round((time.monotonic() - self._turn_starts[chat_id]) * 1000, 2)
        return out

    def turn_started(self, chat_id: str, model: str, num_flows: int) -> None:
        self._turn_starts[chat_id] = time.monotonic()
        self._append({
            "ts": time.time(),
            "kind": "turn_started",
            "chatId": chat_id,
            "model": model,
            "numFlows": num_flows,
            **self._now(chat_id),
        })

    def turn_finished(self, chat_id: str, outcome: str) -> None:
        self._append({
            "ts": time.time(),
            "kind": "turn_finished",
            "chatId": chat_id,
            "outcome": outcome,
            **self._now(chat_id),
        })
        self._turn_starts.pop(chat_id, None)

    def ws_in(self, msg_type: str, chat_id: str | None) -> None:
        self._append({
            "ts": time.time(),
            "kind": "ws_in",
            "msgType": msg_type,
            "chatId": chat_id,
            **self._now(chat_id),
        })

    def event_out(self, event_type: str, chat_id: str | None, extra: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "ts": time.time(),
            "kind": "event_out",
            "eventType": event_type,
            "chatId": chat_id,
            **self._now(chat_id),
        }
        if extra:
            payload.update(extra)
        self._append(payload)

    def note(self, message: str, chat_id: str | None = None, **fields: Any) -> None:
        self._append({
            "ts": time.time(),
            "kind": "note",
            "message": message,
            "chatId": chat_id,
            **self._now(chat_id),
            **fields,
        })


_singleton: DebugLog | None = None


def get_log() -> DebugLog:
    global _singleton
    if _singleton is None:
        _singleton = DebugLog()
    return _singleton
