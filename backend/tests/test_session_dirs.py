from __future__ import annotations

from pathlib import Path

import pytest

from rae_agent.session import SessionDirs


def test_make_creates_directories(tmp_path: Path):
    dirs = SessionDirs.make("abc-123", tmp_path)
    assert dirs.root.exists()
    assert dirs.flows_dir.exists()
    assert dirs.output_dir.exists()
    assert dirs.root == (tmp_path / "abc-123").resolve()


def test_make_is_idempotent(tmp_path: Path):
    SessionDirs.make("chat1", tmp_path)
    dirs = SessionDirs.make("chat1", tmp_path)
    assert dirs.root.exists()


def test_make_rejects_path_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        SessionDirs.make("../escape", tmp_path)


def test_make_rejects_absolute_path(tmp_path: Path):
    with pytest.raises(ValueError):
        SessionDirs.make("/tmp/elsewhere", tmp_path)


def test_make_keeps_session_inside_base(tmp_path: Path):
    dirs = SessionDirs.make("nested-deep", tmp_path)
    assert tmp_path.resolve() in dirs.root.parents
