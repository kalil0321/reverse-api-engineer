"""Resolve Windows launchers without interpreting arguments as batch syntax."""

from __future__ import annotations

import locale
import re
import shutil
import sys
from pathlib import Path


def decode_process_output(output: bytes | str | None) -> str:
    """Preserve UTF-8 tool output, with a fallback for legacy native tools."""
    if output is None:
        return ""
    if isinstance(output, bytes):
        try:
            output = output.decode("utf-8")
        except UnicodeDecodeError:
            output = output.decode(locale.getencoding(), errors="replace")
    return output.replace("\r\n", "\n").replace("\r", "\n")


def resolve_windows_command(argv: list[str]) -> list[str]:
    """Prefer native npm/npx entrypoints, and reject unsafe batch fallbacks.

    CreateProcess does not search PATHEXT, while .cmd files can invoke cmd.exe
    even with shell=False. list2cmdline does not escape batch metacharacters.
    """
    if sys.platform == "win32":
        return _resolve_batch_command(argv)
    return argv


def _resolve_batch_command(argv: list[str]) -> list[str]:
    executable = shutil.which(argv[0]) or argv[0]
    if Path(executable).suffix.lower() not in {".cmd", ".bat"}:
        return [executable, *argv[1:]]

    name = Path(executable).stem.lower()
    node = shutil.which("node")
    if name in {"npm", "npx"} and node and Path(node).suffix.lower() == ".exe":
        # Standard Node installs and npm's global Windows shims place npm here.
        for root in (Path(executable).parent, Path(node).parent):
            entrypoint = root / "node_modules" / "npm" / "bin" / f"{name}-cli.js"
            if entrypoint.is_file():
                return [node, str(entrypoint), *argv[1:]]

    # Maven and nonstandard shims have no universal native entrypoint. Never
    # silently interpret their paths/arguments as commands or variable expansion.
    if any(re.search(r'[&|<>^()%!"\r\n]', arg) for arg in [executable, *argv[1:]]):
        raise ValueError(
            "Cannot safely pass shell metacharacters to a Windows batch launcher. "
            "For npm/npx, use a Node.js installation with its native npm entrypoints; "
            "otherwise use a native executable or paths/arguments without batch metacharacters."
        )
    return [executable, *argv[1:]]
