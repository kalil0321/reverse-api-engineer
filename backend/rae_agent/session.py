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
_STREAMING_ENABLED = True
try:
    from claude_agent_sdk.types import StreamEvent
except ImportError:  # pragma: no cover - SDK shape changed
    _STREAMING_ENABLED = False

    class StreamEvent:  # type: ignore[no-redef]
        """Stub used only for isinstance checks when the SDK doesn't expose
        StreamEvent. Nothing will match it, so streaming silently degrades —
        but we then fall back to emitting whole TextBlocks from
        AssistantMessage so the user still sees the assistant's reply."""
        pass

from rae_agent.debug_log import get_log
from rae_agent.prompts import SYSTEM_PROMPT_APPEND, build_user_prompt
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
        output_dir = root / "scripts"
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

    selected_model = request.model or os.environ.get("RAE_AGENT_MODEL") or "claude-sonnet-4-6"
    get_log().turn_started(chat_id, selected_model, len(request.flows))

    def _build_options(resume_id: str | None) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=selected_model,
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": SYSTEM_PROMPT_APPEND,
            },
            cwd=str(dirs.output_dir),
            allowed_tools=[
                "Read", "Write", "Edit",
                "Grep", "Glob", "Bash",
                "WebFetch", "WebSearch",
            ],
            permission_mode="bypassPermissions",
            include_partial_messages=True,
            resume=resume_id,
        )

    pending_writes: dict[str, str] = {}
    captured_session_id: str | None = None

    async def _stream(opts: ClaudeAgentOptions):
        nonlocal captured_session_id
        async for sdk_message in query(prompt=prompt, options=opts):
            if captured_session_id is None:
                sid = getattr(sdk_message, "session_id", None)
                if isinstance(sid, str) and sid:
                    captured_session_id = sid
                    yield AgentEvent.session_started(chat_id, sid)
            async for event in _translate(chat_id, sdk_message, pending_writes):
                yield event

    options = _build_options(request.claude_session_id)
    try:
        async for event in _stream(options):
            yield event
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # `resume=` points at a Claude CLI session file that doesn't
        # exist anymore (e.g. user cleared `~/.claude/projects/...`).
        # Retry once without resume to recover the turn.
        message = f"{type(exc).__name__}: {exc}"
        is_stale = (
            request.claude_session_id is not None
            and "No conversation found" in str(exc)
        )
        if not is_stale:
            yield AgentEvent.error(chat_id, message)
            return
        pending_writes.clear()
        captured_session_id = None
        try:
            async for event in _stream(_build_options(None)):
                yield event
        except asyncio.CancelledError:
            raise
        except Exception as retry_exc:
            yield AgentEvent.error(
                chat_id,
                f"{type(retry_exc).__name__}: {retry_exc}"
            )
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
    # `include_partial_messages=True` makes the SDK forward raw API
    # stream deltas; we relay text deltas so the UI can render
    # incrementally rather than waiting for the final AssistantMessage.
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
                # When real streaming is on, the text already arrived via
                # StreamEvent chunks — skip to avoid duplicating the body.
                # When the SDK doesn't expose StreamEvent we fall back to
                # emitting the whole TextBlock so the user actually sees
                # the assistant's reply.
                if _STREAMING_ENABLED:
                    continue
                if block.text:
                    yield AgentEvent.assistant_text(chat_id, block.text)
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
        # The SDK computes cost + token usage for the turn and hands it
        # back as a ResultMessage. Forward both so the macOS settings
        # sheet can display "N input + M output tokens · $X.XX" per
        # session without us having to maintain our own pricing table.
        usage_dict = message.usage or {}
        model_used: str | None = None
        if isinstance(message.model_usage, dict) and message.model_usage:
            # `model_usage` keys are model ids — the first one is the
            # model that actually ran. Useful when the agent switched
            # mid-turn (rare in our setup but the SDK supports it).
            model_used = next(iter(message.model_usage.keys()), None)
        yield AgentEvent.usage(
            chat_id=chat_id,
            model=model_used,
            input_tokens=int(usage_dict.get("input_tokens") or 0),
            output_tokens=int(usage_dict.get("output_tokens") or 0),
            cache_creation_input_tokens=int(usage_dict.get("cache_creation_input_tokens") or 0),
            cache_read_input_tokens=int(usage_dict.get("cache_read_input_tokens") or 0),
            total_cost_usd=message.total_cost_usd,
            duration_ms=int(message.duration_ms or 0),
            num_turns=int(message.num_turns or 0),
        )
        return
