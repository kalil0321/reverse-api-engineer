"""Tests for reverse_api/agent_browser helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reverse_api import agent_browser


def test_allowed_tools_contains_bash():
    tools = agent_browser.allowed_tools_agent_browser_agent_mode()
    assert "Bash" in tools


def test_ensure_agent_browser_missing_node():
    with patch.object(agent_browser.shutil, "which", return_value=None):
        err = agent_browser.ensure_agent_browser_runtime()
    assert err is not None
    assert "node" in err.lower()


def test_ensure_agent_browser_missing_npx():
    def which_side(cmd: str) -> str | None:
        return "/fake/node" if cmd == "node" else None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        err = agent_browser.ensure_agent_browser_runtime()
    assert err is not None
    assert "npx" in err.lower()


def test_ensure_prefetch_ok():
    def which_side(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd in ("node", "npx") else None

    proc = MagicMock(returncode=0, stderr="", stdout="usage")

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=proc):
            with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="agent-browser@test"):
                err = agent_browser.ensure_agent_browser_runtime()
    assert err is None


def test_ensure_prefetch_nonzero():
    def which_side(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd in ("node", "npx") else None

    proc = MagicMock(returncode=127, stderr="ENOTFOUND", stdout="")

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=proc):
            with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="agent-browser@test"):
                err = agent_browser.ensure_agent_browser_runtime()
    assert err is not None
    assert "prefetch" in err.lower()


def test_npx_package_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_AGENT_BROWSER_PACKAGE", "agent-browser@fixture")
    assert agent_browser.agent_browser_npx_package() == "agent-browser@fixture"


def test_prompt_fields_includes_notes_block():
    with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="pkg@x"):
        with patch("reverse_api.agent_browser.agent_browser_extra_notes", return_value="cloud hint"):
            fields = agent_browser.agent_browser_prompt_fields(run_id="run1", headless=True)
    assert fields["agent_browser_session"] == "rae-run1"
    assert fields["agent_browser_npx_package"] == "pkg@x"
    assert "cloud hint" in fields["agent_browser_notes_block"]
