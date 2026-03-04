"""Tests for auto_engineer.py - Auto mode engineers."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from reverse_api.auto_engineer import ClaudeAutoEngineer, OpenCodeAutoEngineer


class TestClaudeAutoEngineerInit:
    """Test ClaudeAutoEngineer initialization."""

    def test_init(self, tmp_path):
        """Initializes with HAR path and MCP run_id."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    eng = ClaudeAutoEngineer(
                        run_id="test123",
                        prompt="browse and capture",
                        model="claude-sonnet-4-5",
                        output_dir=str(tmp_path),
                    )
                    assert eng.mcp_run_id == "test123"
                    assert eng.har_path == tmp_path / "har" / "recording.har"


class TestClaudeAutoEngineerPrompt:
    """Test auto prompt building."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-5",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ClaudeAutoEngineer(**defaults)

    def test_python_prompt(self, tmp_path):
        """Python prompt includes correct language references."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_auto_prompt()
        assert "Python" in prompt
        assert "requests" in prompt
        assert "api_client.py" in prompt

    def test_javascript_prompt(self, tmp_path):
        """JavaScript prompt includes JS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        prompt = eng._build_auto_prompt()
        assert "JavaScript" in prompt
        assert "fetch" in prompt
        assert "api_client.js" in prompt
        assert "package.json" in prompt

    def test_typescript_prompt(self, tmp_path):
        """TypeScript prompt includes TS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        prompt = eng._build_auto_prompt()
        assert "TypeScript" in prompt
        assert "interfaces" in prompt
        assert "api_client.ts" in prompt

    def test_prompt_includes_mcp_tools(self, tmp_path):
        """Prompt includes MCP browser tool references."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_auto_prompt()
        assert "browser_navigate" in prompt
        assert "browser_click" in prompt
        assert "browser_close" in prompt
        assert "browser_network_requests" in prompt

    def test_prompt_includes_har_path(self, tmp_path):
        """Prompt includes HAR file path."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_auto_prompt()
        assert "recording.har" in prompt

    def test_prompt_includes_screenshot_guidelines(self, tmp_path):
        """Prompt includes screenshot guidelines."""
        eng = self._make_engineer(tmp_path)
        prompt = eng._build_auto_prompt()
        assert "Screenshot" in prompt
        assert "1MB" in prompt


class TestClaudeAutoEngineerAnalyze:
    """Test ClaudeAutoEngineer analyze_and_generate."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-5",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value = MagicMock()
                    eng = ClaudeAutoEngineer(**defaults)
                    eng.scripts_dir = tmp_path / "scripts"
                    eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                    return eng

    @pytest.mark.asyncio
    async def test_exception_generic(self, tmp_path):
        """Generic exception returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_buffer_size(self, tmp_path):
        """Buffer size exception shows specific message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("exceeded maximum buffer size 1048576")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_mcp_server(self, tmp_path):
        """MCP server exception shows npm install hint."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("MCP server failed to start")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_other(self, tmp_path):
        """Other exception shows generic message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("some other error")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_message_error(self, tmp_path):
        """ResultMessage with error returns None."""
        eng = self._make_engineer(tmp_path)

        from claude_agent_sdk import ResultMessage
        mock_result = MagicMock(spec=ResultMessage)
        mock_result.is_error = True
        mock_result.result = "Error occurred"

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_message_success(self, tmp_path):
        """ResultMessage with success returns result dict."""
        eng = self._make_engineer(tmp_path)

        from claude_agent_sdk import ResultMessage
        mock_result = MagicMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.result = "Success"

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None
            assert "script_path" in result

    @pytest.mark.asyncio
    async def test_result_with_usage(self, tmp_path):
        """Result with usage metadata calculates cost."""
        eng = self._make_engineer(tmp_path)
        eng.usage_metadata = {
            "input_tokens": 5000,
            "output_tokens": 2000,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
        }

        from claude_agent_sdk import ResultMessage
        mock_result = MagicMock(spec=ResultMessage)
        mock_result.is_error = False

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            if result is not None:
                assert "usage" in result


class TestOpenCodeAutoEngineerInit:
    """Test OpenCodeAutoEngineer initialization."""

    def test_init(self, tmp_path):
        """Initializes with MCP run_id."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-5",
                        )
                        assert eng.mcp_run_id == "test123"
                        assert eng.mcp_name is None

    def test_build_auto_prompt_reuses_claude_prompt(self, tmp_path):
        """OpenCode auto prompt reuses ClaudeAutoEngineer prompt."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-5",
                        )
                        prompt = eng._build_auto_prompt()
                        assert "browser_navigate" in prompt
                        assert "Python" in prompt


class TestOpenCodeAutoEngineerAnalyze:
    """Test OpenCodeAutoEngineer analyze_and_generate."""

    def _make_engineer(self, tmp_path):
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value = MagicMock()
                    with patch("reverse_api.opencode_engineer.OpenCodeUI") as mock_ui:
                        mock_ui.return_value = MagicMock()
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-5",
                        )
                        eng.scripts_dir = tmp_path / "scripts"
                        eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                        return eng

    @pytest.mark.asyncio
    async def test_health_check_401(self, tmp_path):
        """401 on health check returns None."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_connect_error(self, tmp_path):
        """ConnectError returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_general_exception(self, tmp_path):
        """General exception returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("unexpected")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_buffer_size_exception(self, tmp_path):
        """Buffer size exception shows specific message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("exceeded maximum buffer size 1048576")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_401(self, tmp_path):
        """HTTP error with non-401 status."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(side_effect=error)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None
