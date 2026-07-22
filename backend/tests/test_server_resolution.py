from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from rae_agent.server import resolve_base_dir


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv("RAE_AGENT_WORKDIR", raising=False)
    yield


def test_resolve_base_dir_uses_env_when_set(monkeypatch):
    monkeypatch.setenv("RAE_AGENT_WORKDIR", "/custom/path")
    assert resolve_base_dir() == Path("/custom/path")


def test_resolve_base_dir_does_not_append_when_env_set(monkeypatch):
    monkeypatch.setenv("RAE_AGENT_WORKDIR", "/foo/bar")
    result = resolve_base_dir()
    assert str(result) == "/foo/bar"
    assert "rae-agent-sessions" not in str(result)


def test_resolve_base_dir_falls_back_to_tmpdir():
    result = resolve_base_dir()
    assert result.name == "rae-agent-sessions"
    assert str(result).startswith(tempfile.gettempdir())
