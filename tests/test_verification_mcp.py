"""Tests for the stdio MCP server that gives Codex the report_client_verified tool."""

from __future__ import annotations

import io
import json
import subprocess
from typing import Any

from reverse_api import verification_mcp
from reverse_api.verification_mcp import ALREADY_RECORDED, DESCRIPTION, RECORDED, TOOL, serve, server_config


def ask(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(msg_id: int) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": {"name": TOOL, "arguments": {"summary": "200 OK"}}}


def test_it_introduces_itself_in_the_clients_protocol_version():
    [reply] = ask({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
    assert reply["id"] == 1 and reply["result"]["protocolVersion"] == "2025-11-25"
    assert reply["result"]["capabilities"] == {"tools": {}}


def test_it_lists_the_one_tool_claude_also_has():
    [reply] = ask({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    [tool] = reply["result"]["tools"]
    assert tool["name"] == TOOL and tool["description"] == DESCRIPTION
    assert tool["inputSchema"]["required"] == ["summary"]


def test_a_second_report_is_acknowledged_without_counting_again():
    replies = ask(call(1), call(2))
    assert [r["result"]["content"][0]["text"] for r in replies] == [RECORDED, ALREADY_RECORDED]


def test_notifications_get_no_reply_and_unknown_requests_an_error():
    replies = ask(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 7, "method": "resources/list"},
        {"jsonrpc": "2.0", "id": 8, "method": "ping"},
    )
    assert replies[0]["id"] == 7 and replies[0]["error"]["code"] == -32601
    assert replies[1] == {"jsonrpc": "2.0", "id": 8, "result": {}}


def test_codex_can_start_it_from_its_config():
    config = server_config()
    assert config["args"][-1] == verification_mcp.__name__
    lines = "".join(json.dumps(m) + "\n" for m in ({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, call(2)))
    done = subprocess.run([config["command"], *config["args"]], input=lines, capture_output=True, text=True, timeout=30)
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert replies[0]["result"]["tools"][0]["name"] == TOOL
    assert replies[1]["result"]["content"][0]["text"] == RECORDED
