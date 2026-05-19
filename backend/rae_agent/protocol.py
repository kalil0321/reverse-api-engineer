from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TargetLanguage(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GO = "go"


class ProtocolError(Exception):
    pass


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
                request_headers=[(k, v) for k, v in payload.get("requestHeaders", [])],
                request_body=payload.get("requestBody"),
                response_status=payload.get("responseStatus"),
                response_headers=[(k, v) for k, v in payload.get("responseHeaders", [])],
                response_body=payload.get("responseBody"),
                started_at=float(payload.get("startedAt", 0.0)),
                finished_at=payload.get("finishedAt"),
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
        return cls(
            id=str(payload.get("id", "")),
            user_message=str(payload.get("message", "")),
            target=target,
            flows=flows,
            history=history,
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
    def error(cls, chat_id: str | None, message: str) -> "AgentEvent":
        payload: dict[str, Any] = {"message": message}
        if chat_id is not None:
            payload["id"] = chat_id
        return cls(type="error", payload=payload)
