"""Tests for session.py - SessionManager."""

import json

import pytest

from reverse_api.session import SessionManager


class TestSessionManagerInit:
    """Test SessionManager initialization."""

    def test_empty_history_when_no_file(self, history_path):
        """SessionManager starts with empty history when no file exists."""
        sm = SessionManager(history_path)
        assert sm.history == []

    def test_loads_existing_history(self, history_path):
        """SessionManager loads history from existing file."""
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps([{"run_id": "abc123", "prompt": "test"}]))
        sm = SessionManager(history_path)
        assert len(sm.history) == 1
        assert sm.history[0]["run_id"] == "abc123"

    def test_corrupted_json_falls_back_to_empty(self, history_path):
        """SessionManager uses empty history when file has invalid JSON."""
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text("not valid json")
        sm = SessionManager(history_path)
        assert sm.history == []


class TestSessionManagerAddRun:
    """Test adding runs to history."""

    def test_add_run_basic(self, history_path):
        """Add a basic run to history."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test prompt")
        assert len(sm.history) == 1
        assert sm.history[0]["run_id"] == "run1"
        assert sm.history[0]["prompt"] == "test prompt"
        assert sm.history[0]["mode"] == "manual"

    def test_add_run_with_kwargs(self, history_path):
        """Add a run with additional metadata."""
        sm = SessionManager(history_path)
        sm.add_run(
            "run1",
            "test prompt",
            url="https://example.com",
            model="claude-sonnet-4-5",
            mode="agent",
            sdk="claude",
            output_mode="docs",
            usage={"input_tokens": 100},
            paths={"har": "/path/to/har"},
        )
        run = sm.history[0]
        assert run["url"] == "https://example.com"
        assert run["model"] == "claude-sonnet-4-5"
        assert run["mode"] == "agent"
        assert run["sdk"] == "claude"
        assert run["output_mode"] == "docs"
        assert run["usage"]["input_tokens"] == 100
        assert run["paths"]["har"] == "/path/to/har"

    def test_add_run_most_recent_first(self, history_path):
        """Most recent run is first in history."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "first")
        sm.add_run("run2", "second")
        assert sm.history[0]["run_id"] == "run2"
        assert sm.history[1]["run_id"] == "run1"

    def test_add_run_deduplicates(self, history_path):
        """Adding a run with same ID replaces the old one."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "original")
        sm.add_run("run1", "updated")
        assert len(sm.history) == 1
        assert sm.history[0]["prompt"] == "updated"

    def test_add_run_persists_to_disk(self, history_path):
        """Adding a run saves to disk."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        with open(history_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["run_id"] == "run1"


class TestSessionManagerUpdateRun:
    """Test updating existing runs."""

    def test_update_usage(self, history_path):
        """Update usage data for an existing run."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test", usage={"input_tokens": 100})
        sm.update_run("run1", usage={"output_tokens": 50})
        run = sm.get_run("run1")
        assert run["usage"]["input_tokens"] == 100
        assert run["usage"]["output_tokens"] == 50

    def test_update_paths(self, history_path):
        """Update paths data for an existing run."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test", paths={"har": "/old"})
        sm.update_run("run1", paths={"scripts": "/new"})
        run = sm.get_run("run1")
        assert run["paths"]["har"] == "/old"
        assert run["paths"]["scripts"] == "/new"

    def test_update_other_fields(self, history_path):
        """Update arbitrary fields for an existing run."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        sm.update_run("run1", model="claude-opus-4-5", status="complete")
        run = sm.get_run("run1")
        assert run["model"] == "claude-opus-4-5"
        assert run["status"] == "complete"

    def test_update_nonexistent_run(self, history_path):
        """Updating a nonexistent run does nothing."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        sm.update_run("nonexistent", model="new")
        # Should not crash, run1 should be unchanged
        assert sm.get_run("run1")["model"] is None


class TestSessionManagerGetRun:
    """Test retrieving runs."""

    def test_get_existing_run(self, history_path):
        """Get run by ID."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        run = sm.get_run("run1")
        assert run is not None
        assert run["run_id"] == "run1"

    def test_get_nonexistent_run(self, history_path):
        """Get returns None for nonexistent run."""
        sm = SessionManager(history_path)
        assert sm.get_run("nonexistent") is None


class TestSessionManagerGetHistory:
    """Test getting history list."""

    def test_get_history_default_limit(self, history_path):
        """Get history with default limit."""
        sm = SessionManager(history_path)
        for i in range(15):
            sm.add_run(f"run{i}", f"prompt {i}")
        history = sm.get_history()
        assert len(history) == 10  # Default limit

    def test_get_history_custom_limit(self, history_path):
        """Get history with custom limit."""
        sm = SessionManager(history_path)
        for i in range(5):
            sm.add_run(f"run{i}", f"prompt {i}")
        history = sm.get_history(limit=3)
        assert len(history) == 3

    def test_get_history_less_than_limit(self, history_path):
        """Get history when fewer entries than limit."""
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        history = sm.get_history(limit=10)
        assert len(history) == 1


class TestSessionManagerSave:
    """Test save functionality."""

    def test_save_creates_parent_dirs(self, tmp_path):
        """Save creates parent directories."""
        history_path = tmp_path / "nested" / "dir" / "history.json"
        sm = SessionManager(history_path)
        sm.add_run("run1", "test")
        assert history_path.exists()
