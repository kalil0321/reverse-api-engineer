"""Helpers for agent-browser provider: bootstrap + prompt context.

Prefer a globally installed ``agent-browser`` on ``PATH``. If missing, run
``npm install -g <pin>`` (from config / ``RAE_AGENT_BROWSER_PACKAGE``) so the daemon
pairs consistently with Chromium; notify the operator when Reverse API Engineer performs
that install. Fall back to ``npx -y <pin>`` only when npm/global install cannot run.
Models invoke the CLI from shell tooling (for example Bash on Claude SDK runs).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
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

_SHELL_INVOKER: str | None = None


@dataclass(frozen=True)
class AgentBrowserSetup:
    """Outcome of resolving the CLI before an agent-browser session."""

    error: str | None = None
    notices: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.error is None


def reset_agent_browser_setup_cache() -> None:
    """Clear cached shell invocation (for tests only)."""

    global _SHELL_INVOKER
    _SHELL_INVOKER = None


def print_agent_browser_setup_notices(console, setup: AgentBrowserSetup) -> None:
    """Emit install/fallback chatter before streaming."""

    for note in setup.notices:
        console.print(f"\n[yellow]agent-browser[/yellow]: {note}")


def _config_manager_snapshot() -> dict[str, Any]:
    """Load config defaults merged with ~/.reverse-api/config.json."""

    try:
        from .config import ConfigManager

        cm = ConfigManager(get_config_path())
        return cm.config.copy()
    except Exception:
        return {}


def agent_browser_npx_package() -> str:
    """Pinned npm specifier passed to ``npm install -g`` / ``npx -y`` (``RAE_AGENT_BROWSER_PACKAGE``)."""

    env = os.environ.get("RAE_AGENT_BROWSER_PACKAGE", "").strip()
    if env:
        return env
    cfg = _config_manager_snapshot()
    return str(cfg.get("agent_browser_npx_package") or "agent-browser@0")


def agent_browser_extra_notes() -> str:
    """Optional user guidance from ``agent_browser_notes``."""

    txt = (_config_manager_snapshot().get("agent_browser_notes") or "").strip()
    if txt:
        return txt
    return os.environ.get("RAE_AGENT_BROWSER_NOTES", "").strip()


def _probe_help_argv(argv_without_help: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            [*argv_without_help, "--help"],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"timed out running `{shlex.join(argv_without_help)} --help`."
    except OSError as e:
        return f"failed subprocess `{shlex.join(argv_without_help)}`: {e}"

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 0:
        return None
    blob = stderr or stdout or "(no output)"
    blob = blob[:1600]
    return (
        f"`{shlex.join(argv_without_help)} --help` failed with exit "
        f"{proc.returncode}. Output (truncated): {blob}"
    )


def agent_browser_shell_invoker() -> str:
    """Shell command prefix embedded in prompts (requires prior successful ``ensure_*`` unless testing)."""

    global _SHELL_INVOKER
    if _SHELL_INVOKER is not None:
        return _SHELL_INVOKER
    pkg = agent_browser_npx_package()
    return shlex.join(["npx", "-y", pkg])


def _finalize_npx_invoker(notices: list[str]) -> AgentBrowserSetup:
    global _SHELL_INVOKER

    if shutil.which("npx") is None:
        return AgentBrowserSetup(
            error=(
                "npx not found on PATH. Install agent-browser globally "
                "`npm install -g agent-browser`, or fix PATH so npm's global bin is visible."
            ),
            notices=tuple(notices),
        )

    pkg = agent_browser_npx_package()
    err = _probe_help_argv(["npx", "-y", pkg])
    if err:
        hint = "`RAE_AGENT_BROWSER_PACKAGE` or config `agent_browser_npx_package` can pin/coerce versions."
        return AgentBrowserSetup(
            error=f"{err} Adjust {hint}",
            notices=tuple(notices),
        )

    inv = shlex.join(["npx", "-y", pkg])
    _SHELL_INVOKER = inv
    return AgentBrowserSetup(notices=tuple(notices))


def ensure_agent_browser_runtime() -> AgentBrowserSetup:
    """Resolve ``agent-browser`` on PATH or install globally, else fall back to ``npx -y``.

    Successful runs stash the shell snippet for ``agent_browser_prompt_fields``.
    """

    global _SHELL_INVOKER
    notices: list[str] = []
    _SHELL_INVOKER = None

    if shutil.which("agent-browser"):
        err = _probe_help_argv(["agent-browser"])
        if err:
            return AgentBrowserSetup(error=err, notices=tuple(notices))
        _SHELL_INVOKER = "agent-browser"
        return AgentBrowserSetup(notices=tuple(notices))

    if shutil.which("node") is None:
        return AgentBrowserSetup(error="node not found in PATH (needed to install/run agent-browser).")

    npm = shutil.which("npm")
    pkg = agent_browser_npx_package()
    if npm is None:
        notices.append("npm was not found on PATH; falling back to `npx -y …` instead of global install.")
        return _finalize_npx_invoker(notices)

    try:
        proc = subprocess.run(
            [npm, "install", "-g", pkg],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        notices.append("`npm install -g …` timed out; falling back to `npx -y …` for this session.")
        return _finalize_npx_invoker(notices)
    except OSError as e:
        notices.append(f"Could not spawn npm globally ({e}); falling back to `npx -y …`.")
        return _finalize_npx_invoker(notices)

    if proc.returncode != 0:
        blob = (proc.stderr or proc.stdout or "").strip()
        notices.append(
            "`npm install -g …` returned a non-zero status (showing truncated output "
            f"below); falling back to `npx -y …`. Output: {(blob[:800] + '…') if len(blob) > 800 else blob or '(empty)'}"
        )
        return _finalize_npx_invoker(notices)

    notices.append(
        f'Installed upstream agent-browser with `npm install -g {pkg}`. '
        'If Chromium is missing, run `agent-browser install` once (add `--with-deps` on trimmed Linux VMs). '
        'Reuse this global install across runs for consistent browser pairing.'
    )

    if not shutil.which("agent-browser"):
        return AgentBrowserSetup(
            error=(
                "Installed via npm but `agent-browser` is still not on PATH. "
                "Append `npm bin -g` to PATH or reinstall with a toolchain that exposes the global shim."
            ),
            notices=tuple(notices),
        )

    err = _probe_help_argv(["agent-browser"])
    if err:
        return AgentBrowserSetup(error=err, notices=tuple(notices))

    _SHELL_INVOKER = "agent-browser"
    return AgentBrowserSetup(notices=tuple(notices))


def allowed_tools_agent_browser_agent_mode() -> list[str]:
    """Tool allow-list for Claude SDK runs when browsing is delegated to agent-browser."""

    return sorted(_AGENT_BROWSER_TOOLS)


def agent_browser_prompt_fields(*, run_id: str, headless: bool) -> dict[str, str]:
    """Variables for ``prompts/auto/user_agent_browser.md``."""

    shell = agent_browser_shell_invoker()
    session = f"rae-{run_id}"
    headed = (
        ""
        if headless
        else "Use the global `--headed` flag on subcommands that show a window when you need "
        "a visible browser (local debugging only).\n\n"
    )
    notes = agent_browser_extra_notes()
    notes_block = ""
    if notes:
        notes_block = f"\n## Extra operator notes (from config or RAE_AGENT_BROWSER_NOTES)\n\n{notes}\n"
    return {
        "agent_browser_shell": shell,
        "agent_browser_npx_package": agent_browser_npx_package(),
        "agent_browser_session": session,
        "agent_browser_headed_hint": headed,
        "agent_browser_notes_block": notes_block,
    }
