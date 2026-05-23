"""Tests for bundled agent-browser MCP wiring."""

from __future__ import annotations

from pathlib import Path

from reverse_api.agent_browser_bundle import agent_browser_command_list, agent_browser_stdio_mcp_config


def test_stdio_mcp_config_headless_writes_har_argv(tmp_path: Path):
    har = tmp_path / "recording.har"
    name, cfg = agent_browser_stdio_mcp_config(har_path=har, run_id="run_xyz", headless=True)
    assert name == "agent-browser"
    assert cfg["command"] == "node"
    assert "--har-out" in cfg["args"]
    har_i = cfg["args"].index("--har-out")
    assert cfg["args"][har_i + 1] == str(har)
    sess_i = cfg["args"].index("--session")
    assert cfg["args"][sess_i + 1] == "run_xyz"
    assert "--headed" not in cfg["args"]


def test_stdio_mcp_config_headed_requests_window(tmp_path: Path):
    har = tmp_path / "recording.har"
    _name, cfg = agent_browser_stdio_mcp_config(har_path=har, run_id="abc", headless=False)
    assert "--headed" in cfg["args"]


def test_command_list_matches_stdio_shape(tmp_path: Path):
    har = tmp_path / "recording.har"
    flat = agent_browser_command_list(har_path=har, run_id="r1", headless=True)
    assert flat[0] == "node"
    _name, cfg = agent_browser_stdio_mcp_config(har_path=har, run_id="r1", headless=True)
    assert flat == [cfg["command"], *cfg["args"]]

