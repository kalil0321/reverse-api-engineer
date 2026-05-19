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

from rae_agent.prompts import SYSTEM_PROMPT, build_user_prompt
from rae_agent.protocol import AgentEvent, ChatRequest


@dataclass
class SessionDirs:
    root: Path
    flows_dir: Path
    output_dir: Path

    @classmethod
    def make(cls, chat_id: str, base: Path) -> "SessionDirs":
        root = base / chat_id
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
    chat_id = request.id or str(uuid.uuid4())
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
        permission_mode="acceptEdits",
    )

    try:
        async for sdk_message in query(prompt=prompt, options=options):
            async for event in _translate(chat_id, sdk_message):
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


async def _translate(chat_id: str, message: Any) -> AsyncIterator[AgentEvent]:
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                if block.text:
                    yield AgentEvent.assistant_text(chat_id, block.text)
            elif isinstance(block, ToolUseBlock):
                yield AgentEvent.tool_use(chat_id, block.name, dict(block.input or {}))
                if block.name == "Write" and isinstance(block.input, dict):
                    path = block.input.get("file_path") or block.input.get("path")
                    if isinstance(path, str):
                        yield AgentEvent.file_written(chat_id, path)
    elif isinstance(message, UserMessage):
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                output = block.content if isinstance(block.content, str) else json.dumps(block.content)
                yield AgentEvent.tool_result(
                    chat_id,
                    name="",
                    output=output[:4000],
                    is_error=bool(block.is_error),
                )
    elif isinstance(message, ResultMessage):
        return
