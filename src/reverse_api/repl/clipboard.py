"""The system clipboard, for text selected in the full-screen session."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from collections.abc import Callable

LINUX_COMMANDS = (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])


def copy_command() -> list[str] | None:
    """The platform's copy command, when this machine has one."""
    if sys.platform == "darwin":
        candidates: tuple[list[str], ...] = (["pbcopy"],)
    elif sys.platform.startswith("linux"):
        candidates = ((["wl-copy"],) if os.environ.get("WAYLAND_DISPLAY") else ()) + LINUX_COMMANDS
    else:
        candidates = ()
    return next((cmd for cmd in candidates if shutil.which(cmd[0])), None)


def copy(text: str, write_raw: Callable[[str], None]) -> None:
    """Puts text on the clipboard with the platform's command, else asks the terminal to with OSC 52.

    Over SSH the platform's clipboard is the remote machine's, so the terminal, on the user's own, does it.
    """
    remote = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))
    command = None if remote else copy_command()
    if command is not None:
        # pbcopy reads its input in the locale's encoding.
        env = {**os.environ, "LC_CTYPE": "UTF-8"} if command[0] == "pbcopy" else None
        try:
            # xclip stays in the background to serve the clipboard, holding open any output pipe it was given.
            out = subprocess.DEVNULL
            subprocess.run(command, input=text.encode(), env=env, check=True, stdout=out, stderr=out, timeout=2)
            return
        except (OSError, subprocess.SubprocessError):
            pass
    write_raw(f"\x1b]52;c;{base64.b64encode(text.encode()).decode()}\x07")
