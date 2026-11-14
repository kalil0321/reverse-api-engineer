"""Tests for copying the session's selected text to the clipboard."""

from __future__ import annotations

import base64
import subprocess
from unittest.mock import MagicMock

import pytest

from reverse_api.repl import clipboard


@pytest.fixture
def local(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """A local macOS session with pbcopy; returns the mocked subprocess.run."""
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = MagicMock()
    monkeypatch.setattr(clipboard.subprocess, "run", run)
    return run


def osc52(text: str) -> str:
    return f"\x1b]52;c;{base64.b64encode(text.encode()).decode()}\x07"


def test_macos_copies_with_pbcopy_in_utf_8(local):
    written: list[str] = []
    clipboard.copy("GET /api/jobs · 200 ✓", written.append)
    (command,), kwargs = local.call_args
    assert command == ["pbcopy"] and kwargs["input"] == "GET /api/jobs · 200 ✓".encode()
    assert kwargs["env"]["LC_CTYPE"] == "UTF-8" and written == []
    # xclip keeps any output pipe open from the background, so a captured one would wait out the timeout.
    assert kwargs["stdout"] is subprocess.DEVNULL and kwargs["stderr"] is subprocess.DEVNULL


def test_over_ssh_the_terminal_copies_on_the_users_machine(local, monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 52100 10.0.0.1 22")
    written: list[str] = []
    clipboard.copy("token", written.append)
    local.assert_not_called()
    assert written == [osc52("token")]


def test_a_failing_copy_command_falls_back_to_the_terminal(local):
    local.side_effect = subprocess.CalledProcessError(1, ["pbcopy"])
    written: list[str] = []
    clipboard.copy("token", written.append)
    assert written == [osc52("token")]


@pytest.mark.parametrize(
    "platform,wayland,found,command",
    [
        ("linux", "wayland-0", {"wl-copy", "xclip"}, ["wl-copy"]),
        ("linux", None, {"wl-copy", "xclip"}, ["xclip", "-selection", "clipboard"]),
        ("linux", None, {"xsel"}, ["xsel", "--clipboard", "--input"]),
        ("linux", None, set(), None),
        ("win32", None, {"clip"}, None),
    ],
)
def test_each_platform_finds_its_copy_command(monkeypatch, platform, wayland, found, command):
    monkeypatch.setattr(clipboard.sys, "platform", platform)
    if wayland:
        monkeypatch.setenv("WAYLAND_DISPLAY", wayland)
    else:
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}" if name in found else None)
    assert clipboard.copy_command() == command
