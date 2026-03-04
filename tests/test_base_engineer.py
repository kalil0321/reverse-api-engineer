"""Tests for base_engineer.py - BaseEngineer abstract class."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reverse_api.base_engineer import BaseEngineer


class ConcreteEngineer(BaseEngineer):
    """Concrete implementation for testing."""

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        return {"test": True}


class TestBaseEngineerInit:
    """Test BaseEngineer initialization."""

    def test_basic_init(self, tmp_path):
        """Basic initialization sets all attributes."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    model="claude-sonnet-4-5",
                    output_dir=str(tmp_path),
                )
                assert engineer.run_id == "test123"
                assert engineer.har_path == har_path
                assert engineer.prompt == "test prompt"
                assert engineer.model == "claude-sonnet-4-5"
                assert engineer.output_mode == "client"
                assert engineer.is_fresh is False
                assert engineer.output_language == "python"

    def test_docs_mode(self, tmp_path):
        """Docs mode uses docs directory."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs") as mock_docs:
            with patch("reverse_api.base_engineer.MessageStore"):
                engineer = ConcreteEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_mode="docs",
                    output_dir=str(tmp_path),
                )
                mock_docs.assert_called_once()
                assert engineer.output_mode == "docs"


class TestBaseEngineerHelpers:
    """Test helper methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_get_output_extension_python(self, tmp_path):
        """Python extension."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_output_extension() == ".py"

    def test_get_output_extension_javascript(self, tmp_path):
        """JavaScript extension."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_output_extension() == ".js"

    def test_get_output_extension_typescript(self, tmp_path):
        """TypeScript extension."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_output_extension() == ".ts"

    def test_get_output_extension_unknown(self, tmp_path):
        """Unknown language defaults to .py."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_output_extension() == ".py"

    def test_get_client_filename_python(self, tmp_path):
        """Client filename for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_client_filename() == "api_client.py"

    def test_get_client_filename_docs(self, tmp_path):
        """Client filename for docs mode."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        assert eng._get_client_filename() == "openapi.json"

    def test_get_run_command_python(self, tmp_path):
        """Run command for Python."""
        eng = self._make_engineer(tmp_path, output_language="python")
        assert eng._get_run_command() == "python api_client.py"

    def test_get_run_command_javascript(self, tmp_path):
        """Run command for JavaScript."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        assert eng._get_run_command() == "node api_client.js"

    def test_get_run_command_typescript(self, tmp_path):
        """Run command for TypeScript."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        assert eng._get_run_command() == "npx tsx api_client.ts"

    def test_get_run_command_unknown(self, tmp_path):
        """Unknown language defaults to Python command."""
        eng = self._make_engineer(tmp_path, output_language="rust")
        assert eng._get_run_command() == "python api_client.py"


class TestBaseEngineerBuildPrompt:
    """Test _build_analysis_prompt method."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value.messages_path = tmp_path / "messages" / "test.jsonl"
                    return ConcreteEngineer(**defaults)

    def test_python_prompt(self, tmp_path):
        """Python prompt includes Python-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="python")
        prompt = eng._build_analysis_prompt()
        assert "Python script" in prompt
        assert "requests" in prompt

    def test_javascript_prompt(self, tmp_path):
        """JavaScript prompt includes JS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        prompt = eng._build_analysis_prompt()
        assert "JavaScript module" in prompt
        assert "fetch" in prompt

    def test_typescript_prompt(self, tmp_path):
        """TypeScript prompt includes TS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        prompt = eng._build_analysis_prompt()
        assert "TypeScript module" in prompt
        assert "interfaces" in prompt

    def test_docs_prompt(self, tmp_path):
        """Docs mode prompt includes OpenAPI instructions."""
        eng = self._make_engineer(tmp_path, output_mode="docs")
        prompt = eng._build_analysis_prompt()
        assert "OpenAPI" in prompt

    def test_prompt_includes_har_path(self, tmp_path):
        """Prompt includes HAR file path."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_analysis_prompt()
        assert str(eng.har_path) in prompt

    def test_prompt_includes_user_prompt(self, tmp_path):
        """Prompt includes user's original prompt."""
        eng = self._make_engineer(tmp_path, prompt="capture spotify api")
        prompt = eng._build_analysis_prompt()
        assert "capture spotify api" in prompt

    def test_prompt_includes_additional_instructions(self, tmp_path):
        """Additional instructions are appended."""
        eng = self._make_engineer(tmp_path, additional_instructions="Focus on auth")
        prompt = eng._build_analysis_prompt()
        assert "Focus on auth" in prompt

    def test_prompt_includes_tag_context(self, tmp_path):
        """Prompt includes tag-based workflow context."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_analysis_prompt()
        assert "Tag-Based Workflows" in prompt
        assert eng.run_id in prompt


class TestBaseEngineerSync:
    """Test sync-related methods."""

    def _make_engineer(self, tmp_path, **kwargs):
        har_path = tmp_path / "test.har"
        har_path.touch()
        defaults = {
            "run_id": "test123",
            "har_path": har_path,
            "prompt": "test prompt",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=tmp_path / "docs"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ConcreteEngineer(**defaults)

    def test_start_sync_disabled(self, tmp_path):
        """Start sync does nothing when disabled."""
        eng = self._make_engineer(tmp_path, enable_sync=False)
        eng.start_sync()
        assert eng.sync_watcher is None

    def test_stop_sync_no_watcher(self, tmp_path):
        """Stop sync is safe with no watcher."""
        eng = self._make_engineer(tmp_path)
        eng.stop_sync()  # Should not raise

    def test_stop_sync_with_error(self, tmp_path):
        """Stop sync handles errors gracefully."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.stop.side_effect = Exception("stop failed")
        eng.sync_watcher = mock_watcher
        eng.stop_sync()  # Should not raise
        assert eng.sync_watcher is None

    def test_get_sync_status_no_watcher(self, tmp_path):
        """Sync status returns None with no watcher."""
        eng = self._make_engineer(tmp_path)
        assert eng.get_sync_status() is None

    def test_get_sync_status_with_watcher(self, tmp_path):
        """Sync status returns watcher status."""
        eng = self._make_engineer(tmp_path)
        mock_watcher = MagicMock()
        mock_watcher.get_status.return_value = {"active": True}
        eng.sync_watcher = mock_watcher
        status = eng.get_sync_status()
        assert status == {"active": True}

    def test_start_sync_enabled(self, tmp_path):
        """Start sync creates watcher when enabled."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)

        eng = self._make_engineer(tmp_path, enable_sync=True)
        eng.scripts_dir = scripts_dir

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_project"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_project"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher

                    eng.start_sync()

                    assert eng.sync_watcher is mock_watcher
                    assert eng.local_scripts_dir == tmp_path / "local" / "test_project"
                    mock_watcher.start.assert_called_once()

    def test_start_sync_docs_mode(self, tmp_path):
        """Start sync uses docs directory in docs mode."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)

        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.get_docs_dir", return_value=docs_dir):
                with patch("reverse_api.base_engineer.MessageStore"):
                    har_path = tmp_path / "test.har"
                    har_path.touch()
                    eng = ConcreteEngineer(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                        output_dir=str(tmp_path),
                        enable_sync=True,
                        output_mode="docs",
                    )

        with patch("reverse_api.base_engineer.generate_folder_name", return_value="test_docs"):
            with patch("reverse_api.base_engineer.get_available_directory", return_value=tmp_path / "local" / "test_docs"):
                with patch("reverse_api.base_engineer.FileSyncWatcher") as mock_watcher_cls:
                    mock_watcher = MagicMock()
                    mock_watcher_cls.return_value = mock_watcher
                    eng.start_sync()
                    assert eng.sync_watcher is not None
