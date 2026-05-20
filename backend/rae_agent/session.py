from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

# `StreamEvent` is defined in claude_agent_sdk.types but not re-exported from
# the package's public namespace (at least up to 0.1.48). Import it directly
# from the submodule, and degrade gracefully to an unmatchable sentinel class
# if the SDK ever drops it — we just lose streaming, not the whole sidecar.
try:
    from claude_agent_sdk.types import StreamEvent
except ImportError:  # pragma: no cover - SDK shape changed
    class StreamEvent:  # type: ignore[no-redef]
        """Stub used only for isinstance checks when the SDK doesn't expose
        StreamEvent. Nothing will match it, so streaming silently degrades."""
        pass

from rae_agent.prompts import SYSTEM_PROMPT, build_user_prompt
from rae_agent.protocol import AgentEvent, ChatRequest, sanitize_session_id


@dataclass
class SessionDirs:
    root: Path
    flows_dir: Path
    output_dir: Path

    @classmethod
    def make(cls, chat_id: str, base: Path) -> "SessionDirs":
        base_resolved = base.resolve()
        root = (base_resolved / chat_id).resolve()
        if base_resolved not in root.parents and root != base_resolved:
            raise ValueError(f"session id escapes base directory: {chat_id!r}")
        flows_dir = root / "flows"
        output_dir = root / "out"
        for directory in (root, flows_dir, output_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return cls(root=root, flows_dir=flows_dir, output_dir=output_dir)


def _serialize_flow(flow) -> dict[str, Any]:
    return {
        "id": flow.id,
        "scheme": flow.scheme,
        "method": flow.method,
        "url": flow.url,
        "request_headers": flow.request_headers,
        "request_body": flow.request_body,
        "response_status": flow.response_status,
        "response_headers": flow.response_headers,
        "response_body": flow.response_body,
        "started_at": flow.started_at,
        "finished_at": flow.finished_at,
    }


async def run_chat(request: ChatRequest, base_dir: Path) -> AsyncIterator[AgentEvent]:
    fallback_id = uuid.uuid4().hex
    chat_id = sanitize_session_id(request.id, fallback_id)
    dirs = SessionDirs.make(chat_id, base_dir)
    flows_path = dirs.flows_dir / "flows.json"
    flows_payload = [_serialize_flow(flow) for flow in request.flows]
    flows_path.write_text(json.dumps(flows_payload, indent=2))

    prompt = build_user_prompt(request, str(flows_path))

    options = ClaudeAgentOptions(
        model=os.environ.get("RAE_AGENT_MODEL", "claude-opus-4-7"),
        system_prompt=SYSTEM_PROMPT,
        cwd=str(dirs.output_dir),
        allowed_tools=["Read", "Write", "Edit"],
        # `acceptEdits` still prompts for Read on paths outside the cwd —
        # including the session's own flows.json, which lives in the
        # sibling flows/ directory. Use `bypassPermissions` (same setting
        # the reverse_api collector + auto_engineer use) so the agent can
        # operate end-to-end without a permission dialog. The sidecar is
        # already isolated to per-chat session directories, so there's no
        # broader-than-intended access enabled here.
        permission_mode="bypassPermissions",
        include_partial_messages=True,
    )

    pending_writes: dict[str, str] = {}

    try:
        async for sdk_message in query(prompt=prompt, options=options):
            async for event in _translate(chat_id, sdk_message, pending_writes):
                yield event
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        yield AgentEvent.error(chat_id, f"{type(exc).__name__}: {exc}")
        return

    files = sorted(
        str(path.relative_to(dirs.output_dir))
        for path in dirs.output_dir.rglob("*")
        if path.is_file()
    )
    yield AgentEvent.complete(chat_id, str(dirs.output_dir), files)


async def _translate(
    chat_id: str,
    message: Any,
    pending_writes: dict[str, str],
) -> AsyncIterator[AgentEvent]:
    # With include_partial_messages=True the SDK emits a StreamEvent for each
    # raw Anthropic API stream chunk. We forward `text_delta` chunks as
    # assistant_text_chunk events so the macOS UI can render the response
    # incrementally instead of waiting for the final AssistantMessage.
    if isinstance(message, StreamEvent):
        raw = message.event or {}
        if raw.get("type") == "content_block_delta":
            delta = raw.get("delta") or {}
            if delta.get("type") == "text_delta":
                text = delta.get("text") or ""
                if text:
                    yield AgentEvent.assistant_text_chunk(chat_id, text)
        return

    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                # Text already streamed via StreamEvent chunks above — skip
                # to avoid emitting the same body twice.
                continue
            elif isinstance(block, ToolUseBlock):
                tool_input = dict(block.input or {})
                yield AgentEvent.tool_use(chat_id, block.name, tool_input)
                if block.name == "Write":
                    path = tool_input.get("file_path") or tool_input.get("path")
                    if isinstance(path, str):
                        pending_writes[block.id] = path
    elif isinstance(message, UserMessage):
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                output = block.content if isinstance(block.content, str) else json.dumps(block.content)
                is_error = bool(block.is_error)
                yield AgentEvent.tool_result(
                    chat_id,
                    name="",
                    output=output[:4000],
                    is_error=is_error,
                )
                pending_path = pending_writes.pop(block.tool_use_id, None)
                if pending_path is not None and not is_error:
                    yield AgentEvent.file_written(chat_id, pending_path)
    elif isinstance(message, ResultMessage):
        return
