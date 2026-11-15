"""report_client_verified as a stdio MCP server, for an SDK that takes MCP servers but no in-process tools.

The engine sees the call in the agent's own events; this server only answers it.
Run with ``python -m reverse_api.verification_mcp``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

SERVER = "verification"
TOOL = "report_client_verified"
DESCRIPTION = (
    "Call this exactly once, after you have actually run the generated "
    "client live against the target and personally confirmed it works. "
    "Do not call this speculatively, before a real run, or more than "
    "once per session."
)
RECORDED = "Recorded — thanks for confirming."
ALREADY_RECORDED = "Already recorded earlier in this session — no need to call this again."


def server_config() -> dict[str, Any]:
    """The MCP server entry an SDK launches: this module, on the Python running rae."""
    return {"command": sys.executable, "args": ["-I", "-m", __name__]}


def serve(stdin: TextIO, stdout: TextIO) -> None:
    """Answers MCP requests, one JSON-RPC message per line, until stdin closes."""
    reported = False

    def send(message: dict[str, Any]) -> None:
        stdout.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        stdout.flush()

    for line in stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict) or msg.get("id") is None:
            continue  # notifications need no answer
        method, params = msg.get("method"), msg.get("params") or {}
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER, "version": "1"},
            }
        elif method == "tools/list":
            schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
            result = {"tools": [{"name": TOOL, "description": DESCRIPTION, "inputSchema": schema}]}
        elif method == "tools/call" and params.get("name") == TOOL:
            result = {"content": [{"type": "text", "text": ALREADY_RECORDED if reported else RECORDED}]}
            reported = True
        elif method == "ping":
            result = {}
        else:
            send({"id": msg["id"], "error": {"code": -32601, "message": f"unknown method {method}"}})
            continue
        send({"id": msg["id"], "result": result})


if __name__ == "__main__":
    serve(sys.stdin, sys.stdout)
