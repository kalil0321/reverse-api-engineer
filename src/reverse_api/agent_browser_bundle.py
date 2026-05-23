"""Bundled stdio MCP server for Vercel agent-browser (used by agent-provider ``agent-browser``)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

_AGENT_BROWSER_HOME = Path(__file__).resolve().parent / "agent_browser_mcp"
_SERVER_JS = _AGENT_BROWSER_HOME / "server.mjs"
_MCP_MARKER = _AGENT_BROWSER_HOME / "node_modules" / "@modelcontextprotocol"


def bundled_agent_browser_mcp_server_js() -> Path:
    return _SERVER_JS


def agent_browser_bundle_error() -> str | None:
    """Return a user-facing setup message if bundled MCP deps are missing."""

    if not _SERVER_JS.is_file():
        return f"Bundled agent-browser MCP is missing {_SERVER_JS.name} (broken install)."
    if not _MCP_MARKER.is_dir():
        return (
            "agent-browser mode requires MCP bundle dependencies: "
            f"npm install --prefix {_AGENT_BROWSER_HOME}"
        )
    if not shutil.which("node"):
        return "node executable not found in PATH (required for agent-browser MCP)."
    if not shutil.which("npx"):
        return "npx not found in PATH (downloads agent-browser on demand via MCP tools)."
    return None


def agent_browser_stdio_mcp_config(*, har_path: Path, run_id: str, headless: bool) -> tuple[str, dict[str, Any]]:
    """Return (server_name, mcp_servers entry) compatible with ClaudeAgentOptions.mcp_servers."""

    cmd = bundled_agent_browser_mcp_server_js()
    args = [
        str(cmd),
        "--har-out",
        str(har_path),
        "--session",
        run_id,
    ]
    if not headless:
        args.append("--headed")
    return "agent-browser", {
        "type": "stdio",
        "command": "node",
        "args": args,
    }


def agent_browser_command_list(*, har_path: Path, run_id: str, headless: bool) -> list[str]:
    """Flat CLI command list used by OpenCode (``config.command`` expects argv)."""

    _name, cfg = agent_browser_stdio_mcp_config(har_path=har_path, run_id=run_id, headless=headless)
    argv: list[str] = [cfg["command"], *(cfg["args"] or [])]
    return argv
