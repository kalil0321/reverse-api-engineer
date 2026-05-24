"""Helpers for agent-browser provider: bootstrap + prompt context.

This mode avoids a custom MCP shim. Agents drive Vercel's ``agent-browser`` CLI directly
via their shell tooling (e.g. Bash), after we verify ``npx`` can fetch the CLI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from .utils import get_config_path

_AGENT_BROWSER_TOOLS = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash",
        "WebFetch",
        "WebSearch",
        "AskUserQuestion",
    },
)


def _config_manager_snapshot() -> dict[str, Any]:
    """Load config defaults merged with ~/.reverse-api/config.json."""
    try:
        from .config import ConfigManager

        cm = ConfigManager(get_config_path())
        return cm.config.copy()
    except Exception:
        return {}


def agent_browser_npx_package() -> str:
    """Pinned npm specifier passed to ``npx -y <pkg>`` (override with ``RAE_AGENT_BROWSER_PACKAGE``)."""

    env = os.environ.get("RAE_AGENT_BROWSER_PACKAGE", "").strip()
    if env:
        return env
    cfg = _config_manager_snapshot()
    return str(cfg.get("agent_browser_npx_package") or "agent-browser@0")


def agent_browser_extra_notes() -> str:
    """Optional user guidance (cloud browsers, corp proxy, …) from ``agent_browser_notes``."""

    txt = (_config_manager_snapshot().get("agent_browser_notes") or "").strip()
    if txt:
        return txt
    return os.environ.get("RAE_AGENT_BROWSER_NOTES", "").strip()


def ensure_agent_browser_runtime() -> str | None:
    """Return None if agent-browser CLI is fetchable via npx; otherwise a short error."""

    if shutil.which("node") is None:
        return "node not found in PATH (needed to run agent-browser via npx)."
    if shutil.which("npx") is None:
        return "npx not found in PATH (needed to bootstrap agent-browser)."
    pkg = agent_browser_npx_package()
    try:
        proc = subprocess.run(
            ["npx", "-y", pkg, "--help"],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"timed out prefetching `{pkg}` with npx (network?)."
    except OSError as e:
        return f"failed to run npx: {e}"

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    if proc.returncode == 0:
        return None

    err_blob = stderr or stdout or "(no output)"
    err_blob = err_blob[:1600]
    hint = "`RAE_AGENT_BROWSER_PACKAGE` env or config `agent_browser_npx_package` can pin/coerce versions."
    return (
        f"npx prefetch of `{pkg}` failed (exit {proc.returncode}). Output: {err_blob} "
        f"Try `npm i -g agent-browser && agent-browser install`, or adjust {hint}"
    )


def allowed_tools_agent_browser_agent_mode() -> list[str]:
    """Tool allow-list for Claude auto engineer when MCP browser is omitted."""

    return sorted(_AGENT_BROWSER_TOOLS)


def agent_browser_prompt_fields(*, run_id: str, headless: bool) -> dict[str, str]:
    """Variables for ``prompts/auto/user_agent_browser.md``."""

    pkg = agent_browser_npx_package()
    session = f"rae-{run_id}"
    headed = "" if headless else "Use the global `--headed` flag on subcommands that show a window when you need a visible browser (local debugging only).\n\n"
    notes = agent_browser_extra_notes()
    notes_block = ""
    if notes:
        notes_block = f"\n## Extra operator notes (from config or RAE_AGENT_BROWSER_NOTES)\n\n{notes}\n"
    return {
        "agent_browser_npx_package": pkg,
        "agent_browser_session": session,
        "agent_browser_headed_hint": headed,
        "agent_browser_notes_block": notes_block,
    }
