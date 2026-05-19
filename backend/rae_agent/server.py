from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import websockets

from rae_agent.protocol import AgentEvent, ChatRequest, ProtocolError
from rae_agent.session import run_chat

logger = logging.getLogger("rae_agent")


async def handle_connection(websocket, base_dir: Path) -> None:
    try:
        async for raw in websocket:
            await _process(websocket, raw, base_dir)
    except websockets.ConnectionClosed:
        return


async def _process(websocket, raw: str | bytes, base_dir: Path) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        await websocket.send(json.dumps(AgentEvent.error(None, f"invalid JSON: {exc}").to_dict()))
        return

    try:
        request = ChatRequest.from_payload(payload)
    except ProtocolError as exc:
        await websocket.send(json.dumps(AgentEvent.error(None, str(exc)).to_dict()))
        return

    try:
        async for event in run_chat(request, base_dir):
            await websocket.send(json.dumps(event.to_dict()))
    except Exception as exc:
        logger.exception("agent run failed")
        await websocket.send(json.dumps(AgentEvent.error(request.id, str(exc)).to_dict()))


async def serve(host: str, port: int, base_dir: Path) -> None:
    async def handler(websocket):
        await handle_connection(websocket, base_dir)

    async with websockets.serve(handler, host, port, max_size=64 * 1024 * 1024) as server:
        sockets = list(server.sockets or [])
        bound_port = sockets[0].getsockname()[1] if sockets else port
        print(f"RAE_AGENT_LISTENING:{bound_port}", flush=True)
        await asyncio.Future()


def main() -> None:
    logging.basicConfig(level=os.environ.get("RAE_AGENT_LOG", "INFO"))

    host = os.environ.get("RAE_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("RAE_AGENT_PORT", "0"))
    base_dir = Path(
        os.environ.get("RAE_AGENT_WORKDIR", tempfile.gettempdir())
    ) / "rae-agent-sessions"
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(serve(host, port, base_dir))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
