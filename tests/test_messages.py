"""Tests for messages.py - MessageStore."""

import json
from unittest.mock import patch

import pytest

from reverse_api.messages import MessageStore


class TestMessageStoreInit:
    """Test MessageStore initialization."""

    def test_creates_messages_dir(self, tmp_path):
        """MessageStore creates parent directories."""
        with patch("reverse_api.messages.get_messages_path", return_value=tmp_path / "messages" / "test.jsonl"):
            store = MessageStore("test123")
            assert store.messages_path.parent.exists()

    def test_run_id_stored(self, tmp_path):
        """MessageStore stores the run_id."""
        with patch("reverse_api.messages.get_messages_path", return_value=tmp_path / "messages" / "test.jsonl"):
            store = MessageStore("test123")
            assert store.run_id == "test123"


class TestMessageStoreAppend:
    """Test appending messages."""

    def test_append_creates_file(self, tmp_path):
        """Append creates the JSONL file."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            store.append("test", "content")
            assert msg_path.exists()

    def test_append_writes_jsonl(self, tmp_path):
        """Append writes valid JSONL."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            store.append("test", "content")
            lines = msg_path.read_text().strip().split("\n")
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["type"] == "test"
            assert data["content"] == "content"
            assert "timestamp" in data

    def test_append_multiple_messages(self, tmp_path):
        """Multiple appends create multiple lines."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            store.append("type1", "content1")
            store.append("type2", "content2")
            lines = msg_path.read_text().strip().split("\n")
            assert len(lines) == 2

    def test_append_with_kwargs(self, tmp_path):
        """Append includes extra kwargs."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            store.append("test", "content", extra_field="value")
            data = json.loads(msg_path.read_text().strip())
            assert data["extra_field"] == "value"


class TestMessageStoreSaveHelpers:
    """Test convenience save methods."""

    def _make_store(self, tmp_path):
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
        return store, msg_path

    def test_save_prompt(self, tmp_path):
        """save_prompt writes prompt type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_prompt("analyze this HAR")
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "prompt"
        assert data["content"] == "analyze this HAR"

    def test_save_tool_start(self, tmp_path):
        """save_tool_start writes tool_start type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_tool_start("Read", {"file_path": "/test"})
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "tool_start"
        assert data["content"]["name"] == "Read"
        assert data["content"]["input"]["file_path"] == "/test"

    def test_save_tool_result(self, tmp_path):
        """save_tool_result writes tool_result type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_tool_result("Read", is_error=False, output="file content")
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "tool_result"
        assert data["content"]["name"] == "Read"
        assert data["content"]["is_error"] is False
        assert data["content"]["output"] == "file content"

    def test_save_tool_result_error(self, tmp_path):
        """save_tool_result handles error flag."""
        store, msg_path = self._make_store(tmp_path)
        store.save_tool_result("Bash", is_error=True, output="command failed")
        data = json.loads(msg_path.read_text().strip())
        assert data["content"]["is_error"] is True

    def test_save_thinking(self, tmp_path):
        """save_thinking writes thinking type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_thinking("I should analyze the headers first")
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "thinking"
        assert "analyze" in data["content"]

    def test_save_error(self, tmp_path):
        """save_error writes error type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_error("Connection refused")
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "error"
        assert data["content"] == "Connection refused"

    def test_save_result(self, tmp_path):
        """save_result writes result type."""
        store, msg_path = self._make_store(tmp_path)
        store.save_result({"script_path": "/output/api_client.py"})
        data = json.loads(msg_path.read_text().strip())
        assert data["type"] == "result"
        assert data["content"]["script_path"] == "/output/api_client.py"


class TestMessageStoreLoad:
    """Test loading messages."""

    def test_load_empty_file(self, tmp_path):
        """Load returns empty list when no file."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            assert store.load() == []

    def test_load_messages(self, tmp_path):
        """Load returns all messages."""
        msg_path = tmp_path / "test.jsonl"
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            store.save_prompt("test")
            store.save_thinking("thinking...")
            messages = store.load()
            assert len(messages) == 2
            assert messages[0]["type"] == "prompt"
            assert messages[1]["type"] == "thinking"

    def test_load_skips_invalid_json_lines(self, tmp_path):
        """Load skips lines with invalid JSON."""
        msg_path = tmp_path / "test.jsonl"
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(msg_path, "w") as f:
            f.write('{"type": "valid", "content": "ok", "timestamp": "now"}\n')
            f.write("not valid json\n")
            f.write('{"type": "valid2", "content": "ok2", "timestamp": "now"}\n')
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            messages = store.load()
            assert len(messages) == 2

    def test_load_skips_empty_lines(self, tmp_path):
        """Load skips empty lines."""
        msg_path = tmp_path / "test.jsonl"
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(msg_path, "w") as f:
            f.write('{"type": "valid", "content": "ok", "timestamp": "now"}\n')
            f.write("\n")
            f.write("   \n")
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            store = MessageStore("test123")
            messages = store.load()
            assert len(messages) == 1


class TestMessageStoreExists:
    """Test exists class method."""

    def test_exists_true(self, tmp_path):
        """exists returns True when file exists."""
        msg_path = tmp_path / "messages" / "test.jsonl"
        msg_path.parent.mkdir(parents=True, exist_ok=True)
        msg_path.touch()
        with patch("reverse_api.messages.get_messages_path", return_value=msg_path):
            with patch("reverse_api.utils.get_messages_path", return_value=msg_path):
                assert MessageStore.exists("test") is True

    def test_exists_false(self, tmp_path):
        """exists returns False when file doesn't exist."""
        msg_path = tmp_path / "messages" / "nonexistent.jsonl"
        with patch("reverse_api.utils.get_messages_path", return_value=msg_path):
            assert MessageStore.exists("nonexistent") is False
