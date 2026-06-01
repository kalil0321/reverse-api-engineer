from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import websockets

from rae_agent.debug_log import get_log
from rae_agent.protocol import AgentEvent, ChatRequest, ProtocolError
from rae_agent.session import run_chat

logger = logging.getLogger("rae_agent")


async def handle_connection(websocket, base_dir: Path) -> None:
    # Chat work runs in detached tasks so the read loop can still pick
    # up a `cancel` envelope while a turn is streaming — otherwise the
    # cancel would sit in the WS buffer until the turn finishes.
    active_tasks: dict[str, asyncio.Task] = {}
    try:
        async for raw in websocket:
            await _dispatch(websocket, raw, base_dir, active_tasks)
    except websockets.ConnectionClosed:
        pass
    finally:
        for task in list(active_tasks.values()):
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks.values(), return_exceptions=True)


async def _dispatch(
    websocket,
    raw: str | bytes,
    base_dir: Path,
    active_tasks: dict[str, asyncio.Task],
) -> None:
    log = get_log()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.note("invalid_json", error=str(exc))
        await websocket.send(json.dumps(AgentEvent.error(None, f"invalid JSON: {exc}").to_dict()))
        return

    msg_type = payload.get("type")
    chat_id = str(payload.get("id") or "") or None
    log.ws_in(msg_type or "?", chat_id)

    if msg_type == "cancel":
        task = active_tasks.get(chat_id or "")
        if task is not None and not task.done():
            log.note("cancel_dispatched", chat_id=chat_id, taskRepr=repr(task))
            task.cancel()
        else:
            log.note("cancel_no_task", chat_id=chat_id, activeIds=list(active_tasks.keys()))
        return

    try:
        request = ChatRequest.from_payload(payload)
    except ProtocolError as exc:
        log.note("protocol_error", error=str(exc))
        await websocket.send(json.dumps(AgentEvent.error(None, str(exc)).to_dict()))
        return

    previous = active_tasks.get(request.id)
    if previous is not None and not previous.done():
        log.note("evicting_previous_task", chat_id=request.id)
        previous.cancel()

    log.note("task_spawned", chat_id=request.id, model=request.model, numFlows=len(request.flows))
    task = asyncio.create_task(_stream(websocket, request, base_dir))
    active_tasks[request.id] = task
    task.add_done_callback(lambda _t: active_tasks.pop(request.id, None))


async def _stream(websocket, request: ChatRequest, base_dir: Path) -> None:
    log = get_log()
    try:
        async for event in run_chat(request, base_dir):
            log.event_out(event.type, request.id)
            await websocket.send(json.dumps(event.to_dict()))
    except asyncio.CancelledError:
        log.turn_finished(request.id, "cancelled")
        try:
            await websocket.send(json.dumps(AgentEvent.cancelled(request.id).to_dict()))
        except websockets.ConnectionClosed:
            pass
        raise
    except ValueError as exc:
        log.turn_finished(request.id, f"value_error: {exc}")
        try:
            await websocket.send(json.dumps(AgentEvent.error(request.id, str(exc)).to_dict()))
        except websockets.ConnectionClosed:
            pass
    except Exception as exc:
        log.turn_finished(request.id, f"exception: {type(exc).__name__}: {exc}")
        logger.exception("agent run failed")
        try:
            await websocket.send(json.dumps(AgentEvent.error(request.id, str(exc)).to_dict()))
        except websockets.ConnectionClosed:
            pass
    else:
        log.turn_finished(request.id, "complete")


async def serve(host: str, port: int, base_dir: Path) -> None:
    async def handler(websocket):
        await handle_connection(websocket, base_dir)

    async with websockets.serve(handler, host, port, max_size=64 * 1024 * 1024) as server:
        sockets = list(server.sockets or [])
        bound_port = sockets[0].getsockname()[1] if sockets else port
        print(f"RAE_AGENT_LISTENING:{bound_port}", flush=True)
        await asyncio.Future()


def resolve_base_dir() -> Path:
    raw = os.environ.get("RAE_AGENT_WORKDIR")
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "rae-agent-sessions"


def main() -> None:
    logging.basicConfig(level=os.environ.get("RAE_AGENT_LOG", "INFO"))

    host = os.environ.get("RAE_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("RAE_AGENT_PORT", "0"))
    base_dir = resolve_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(serve(host, port, base_dir))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
