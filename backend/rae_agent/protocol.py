from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from reverse_api.utils import OUTPUT_LANGUAGE_EXTENSIONS

# Derive the accepted output languages from reverse-api's single source of
# truth so the agent panel never drifts behind the CLI (it used to accept only
# python/typescript/go while the CLI had grown to nine). Building the enum from
# the registry keeps the `.value` interface the rest of the sidecar relies on.
TargetLanguage = Enum(
    "TargetLanguage",
    {lang.upper(): lang for lang in OUTPUT_LANGUAGE_EXTENSIONS},
    type=str,
)


class ProtocolError(Exception):
    pass


_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]+$")


def sanitize_session_id(raw: str, fallback: str) -> str:
    if not raw:
        return fallback
    candidate = raw.strip()
    if not candidate or candidate in {".", ".."}:
        return fallback
    if "/" in candidate or "\\" in candidate or "\x00" in candidate:
        return fallback
    if not _SAFE_ID_PATTERN.fullmatch(candidate):
        return fallback
    return candidate[:128]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"expected float, got {value!r}") from exc


@dataclass
class FlowSummary:
    id: str
    scheme: str
    method: str
    url: str
    request_headers: list[tuple[str, str]]
    request_body: str | None
    response_status: int | None
    response_headers: list[tuple[str, str]]
    response_body: str | None
    started_at: float
    finished_at: float | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FlowSummary":
        try:
            return cls(
                id=str(payload["id"]),
                scheme=str(payload["scheme"]),
                method=str(payload["method"]),
                url=str(payload["url"]),
                request_headers=[(str(k), str(v)) for k, v in payload.get("requestHeaders", [])],
                request_body=payload.get("requestBody"),
                response_status=payload.get("responseStatus"),
                response_headers=[(str(k), str(v)) for k, v in payload.get("responseHeaders", [])],
                response_body=payload.get("responseBody"),
                started_at=float(payload.get("startedAt", 0.0)),
                finished_at=_optional_float(payload.get("finishedAt")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"invalid flow payload: {exc}") from exc


@dataclass
class ChatRequest:
    id: str
    user_message: str
    target: TargetLanguage
    flows: list[FlowSummary] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    claude_session_id: str | None = None
    model: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChatRequest":
        if payload.get("type") != "chat":
            raise ProtocolError("expected type=chat")
        try:
            target_value = str(payload.get("target", "python")).lower()
            target = TargetLanguage(target_value)
        except ValueError as exc:
            raise ProtocolError(f"unsupported target language: {payload.get('target')!r}") from exc
        flows = [FlowSummary.from_payload(f) for f in payload.get("flows", [])]
        history = [
            {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
            for item in payload.get("history", [])
        ]
        raw_sid = payload.get("claudeSessionId") or payload.get("claude_session_id")
        claude_session_id = str(raw_sid) if isinstance(raw_sid, str) and raw_sid else None
        raw_model = payload.get("model")
        model = str(raw_model).strip() if isinstance(raw_model, str) and raw_model.strip() else None
        return cls(
            id=str(payload.get("id", "")),
            user_message=str(payload.get("message", "")),
            target=target,
            flows=flows,
            history=history,
            claude_session_id=claude_session_id,
            model=model,
        )


@dataclass
class AgentEvent:
    type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.payload}

    @classmethod
    def assistant_text(cls, chat_id: str, text: str) -> "AgentEvent":
        return cls(type="assistant_text", payload={"id": chat_id, "text": text})

    @classmethod
    def session_started(cls, chat_id: str, claude_session_id: str) -> "AgentEvent":
        return cls(
            type="session_started",
            payload={"id": chat_id, "claudeSessionId": claude_session_id},
        )

    @classmethod
    def assistant_text_chunk(cls, chat_id: str, text: str) -> "AgentEvent":
        return cls(type="assistant_text_chunk", payload={"id": chat_id, "text": text})

    @classmethod
    def tool_use(cls, chat_id: str, name: str, tool_input: dict[str, Any]) -> "AgentEvent":
        return cls(type="tool_use", payload={"id": chat_id, "name": name, "input": tool_input})

    @classmethod
    def tool_result(cls, chat_id: str, name: str, output: str, is_error: bool) -> "AgentEvent":
        return cls(
            type="tool_result",
            payload={"id": chat_id, "name": name, "output": output, "is_error": is_error},
        )

    @classmethod
    def file_written(cls, chat_id: str, path: str) -> "AgentEvent":
        return cls(type="file_written", payload={"id": chat_id, "path": path})

    @classmethod
    def complete(cls, chat_id: str, workdir: str, files: list[str]) -> "AgentEvent":
        return cls(
            type="complete",
            payload={"id": chat_id, "workdir": workdir, "files": files},
        )

    @classmethod
    def usage(
        cls,
        chat_id: str,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int,
        cache_read_input_tokens: int,
        total_cost_usd: float | None,
        duration_ms: int,
        num_turns: int,
    ) -> "AgentEvent":
        return cls(
            type="usage",
            payload={
                "id": chat_id,
                "model": model,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "cacheCreationInputTokens": cache_creation_input_tokens,
                "cacheReadInputTokens": cache_read_input_tokens,
                "totalCostUsd": total_cost_usd,
                "durationMs": duration_ms,
                "numTurns": num_turns,
            },
        )

    @classmethod
    def error(cls, chat_id: str | None, message: str) -> "AgentEvent":
        payload: dict[str, Any] = {"message": message}
        if chat_id is not None:
            payload["id"] = chat_id
        return cls(type="error", payload=payload)

    @classmethod
    def cancelled(cls, chat_id: str) -> "AgentEvent":
        return cls(type="cancelled", payload={"id": chat_id})
