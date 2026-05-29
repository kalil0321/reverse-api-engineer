"""Tests for reverse_api/agent_browser helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reverse_api import agent_browser


@pytest.fixture(autouse=True)
def clear_setup_cache():
    agent_browser.reset_agent_browser_setup_cache()
    yield
    agent_browser.reset_agent_browser_setup_cache()


def test_allowed_tools_contains_bash():
    tools = agent_browser.allowed_tools_agent_browser_agent_mode()
    assert "Bash" in tools


def test_ensure_missing_node():
    with patch.object(agent_browser.shutil, "which", return_value=None):
        st = agent_browser.ensure_agent_browser_runtime()
    assert not st.ok
    assert st.error and "node" in st.error.lower()


def test_global_binary_short_circuits_npm():
    help_ok = MagicMock(returncode=0, stderr="", stdout="ok")

    def which_side(name: str):
        return "/fake/agent-browser" if name == "agent-browser" else None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=help_ok) as run:
            st = agent_browser.ensure_agent_browser_runtime()
    assert st.ok
    assert st.notices == ()
    assert agent_browser.agent_browser_shell_invoker() == "agent-browser"
    run.assert_called_once()
    argv = run.call_args[0][0]
    assert argv == ["agent-browser", "--help"]


def test_global_help_failure():
    proc = MagicMock(returncode=1, stderr="broken", stdout="")

    def which_side(name: str):
        return "/broken/ab" if name == "agent-browser" else None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=proc):
            st = agent_browser.ensure_agent_browser_runtime()
    assert not st.ok
    assert st.error and "failed" in st.error.lower()


def test_npm_global_install_then_help():
    help_ok = MagicMock(returncode=0, stderr="", stdout="usage")
    state = {"have_ab": False}

    def which_fn(cmd: str) -> str | None:
        if cmd == "agent-browser":
            return "/usr/bin/agent-browser" if state["have_ab"] else None
        if cmd == "node":
            return "/usr/bin/node"
        if cmd == "npm":
            return "/usr/bin/npm"
        return None

    def npm_then_help(argv, **_kwargs):
        if argv and str(argv[0]).endswith("npm") and len(argv) >= 2 and argv[1] == "install":
            state["have_ab"] = True
            return MagicMock(returncode=0, stderr="", stdout="")
        return help_ok

    with patch.object(agent_browser.shutil, "which", side_effect=which_fn):
        with patch.object(agent_browser.subprocess, "run", side_effect=npm_then_help) as run:
            with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="agent-browser@test"):
                st = agent_browser.ensure_agent_browser_runtime()
    assert st.ok
    assert any("Installed upstream agent-browser" in n for n in st.notices)
    assert agent_browser.agent_browser_shell_invoker() == "agent-browser"

    first_cmd = run.call_args_list[0][0][0]
    assert first_cmd[:4] == ["/usr/bin/npm", "install", "-g", "agent-browser@test"]


def test_npm_missing_falls_back_npx():
    help_ok = MagicMock(returncode=0, stderr="", stdout="usage")

    def which_side(cmd: str) -> str | None:
        if cmd == "agent-browser":
            return None
        if cmd == "node":
            return "/bin/node"
        if cmd == "npm":
            return None
        if cmd == "npx":
            return "/bin/npx"
        return None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=help_ok):
            with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="agent-browser@x"):
                st = agent_browser.ensure_agent_browser_runtime()
    assert st.ok
    assert any("npm was not found" in n.lower() for n in st.notices)
    assert agent_browser.agent_browser_shell_invoker() == "npx -y agent-browser@x"


def test_npx_package_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_AGENT_BROWSER_PACKAGE", "agent-browser@fixture")
    assert agent_browser.agent_browser_npx_package() == "agent-browser@fixture"


def test_prompt_fields_includes_shell_and_notes():
    with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="pkg@x"):
        with patch("reverse_api.agent_browser.agent_browser_extra_notes", return_value="cloud hint"):
            with patch("reverse_api.agent_browser.agent_browser_shell_invoker", return_value="agent-browser"):
                fields = agent_browser.agent_browser_prompt_fields(run_id="run1", headless=True)
    assert fields["agent_browser_session"] == "rae-run1"
    assert fields["agent_browser_npx_package"] == "pkg@x"
    assert fields["agent_browser_shell"] == "agent-browser"
    assert "cloud hint" in fields["agent_browser_notes_block"]


def test_extra_notes_env_overrides_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_AGENT_BROWSER_NOTES", "from env")
    with patch("reverse_api.agent_browser._config_manager_snapshot", return_value={"agent_browser_notes": "from config"}):
        assert agent_browser.agent_browser_extra_notes() == "from env"


def test_global_install_missing_path_falls_back_npx():
    help_ok = MagicMock(returncode=0, stderr="", stdout="usage")

    def which_side(cmd: str) -> str | None:
        if cmd == "agent-browser":
            return None
        if cmd == "node":
            return "/bin/node"
        if cmd == "npm":
            return "/bin/npm"
        if cmd == "npx":
            return "/bin/npx"
        return None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", side_effect=[MagicMock(returncode=0), help_ok]) as run:
            with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value="agent-browser@pin"):
                st = agent_browser.ensure_agent_browser_runtime()
    assert st.ok
    assert agent_browser.agent_browser_shell_invoker() == "npx -y agent-browser@pin"
    assert any("not on PATH" in n for n in st.notices)
    assert run.call_args_list[0][0][0][1] == "install"


def test_check_only_skips_npm_install():
    help_ok = MagicMock(returncode=0, stderr="", stdout="usage")

    def which_side(cmd: str) -> str | None:
        if cmd == "agent-browser":
            return None
        if cmd == "npm":
            return "/bin/npm"
        if cmd == "npx":
            return "/bin/npx"
        return None

    with patch.object(agent_browser.shutil, "which", side_effect=which_side):
        with patch.object(agent_browser.subprocess, "run", return_value=help_ok) as run:
            st = agent_browser.check_agent_browser_runtime()
    assert st.ok
    assert any("npm install -g" in n for n in st.notices)
    run.assert_not_called()
    assert agent_browser.agent_browser_shell_invoker().startswith("npx")

