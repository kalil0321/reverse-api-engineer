"""Tests for engineer.py - run_reverse_engineering dispatch."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.engineer import APIReverseEngineer, ClaudeEngineer, run_reverse_engineering


class TestClaudeEngineerAlias:
    """Test backward compatibility alias."""

    def test_alias(self):
        """APIReverseEngineer is alias for ClaudeEngineer."""
        assert APIReverseEngineer is ClaudeEngineer


class TestRunReverseEngineering:
    """Test run_reverse_engineering dispatch function."""

    def test_dispatches_to_claude(self, tmp_path):
        """Claude SDK is used by default."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value={"test": True}):
                result = run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    sdk="claude",
                )
                mock_cls.assert_called_once()

    def test_dispatches_to_opencode(self, tmp_path):
        """OpenCode SDK is used when specified."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.opencode_engineer.OpenCodeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value={"test": True}):
                result = run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    sdk="opencode",
                    opencode_provider="anthropic",
                    opencode_model="claude-opus-4-5",
                )
                mock_cls.assert_called_once()

    def test_starts_sync(self, tmp_path):
        """Sync is started before analysis."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value=None):
                run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                )
                mock_instance.start_sync.assert_called_once()

    def test_stops_sync_on_error(self, tmp_path):
        """Sync is stopped even on error."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", side_effect=Exception("fail")):
                with pytest.raises(Exception):
                    run_reverse_engineering(
                        run_id="test123",
                        har_path=har_path,
                        prompt="test prompt",
                    )
                mock_instance.stop_sync.assert_called_once()

    def test_passes_all_params_to_claude(self, tmp_path):
        """All parameters are forwarded to ClaudeEngineer."""
        har_path = tmp_path / "test.har"
        har_path.touch()

        with patch("reverse_api.engineer.ClaudeEngineer") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.start_sync = MagicMock()
            mock_instance.stop_sync = MagicMock()

            with patch("reverse_api.engineer.asyncio.run", return_value=None):
                run_reverse_engineering(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test",
                    model="claude-opus-4-5",
                    additional_instructions="extra",
                    output_dir="/custom",
                    verbose=False,
                    enable_sync=True,
                    is_fresh=True,
                    output_language="typescript",
                    output_mode="docs",
                )
                kwargs = mock_cls.call_args[1]
                assert kwargs["run_id"] == "test123"
                assert kwargs["model"] == "claude-opus-4-5"
                assert kwargs["output_language"] == "typescript"
                assert kwargs["output_mode"] == "docs"
                assert kwargs["is_fresh"] is True


class TestClaudeEngineerHandleAskUserQuestion:
    """Test _handle_ask_user_question method."""

    def _make_engineer(self, tmp_path):
        har_path = tmp_path / "test.har"
        har_path.touch()
        with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
            with patch("reverse_api.base_engineer.MessageStore"):
                return ClaudeEngineer(
                    run_id="test123",
                    har_path=har_path,
                    prompt="test prompt",
                    output_dir=str(tmp_path),
                )

    @pytest.mark.asyncio
    async def test_non_ask_user_tool_allows(self, tmp_path):
        """Non-AskUserQuestion tools return allow behavior."""
        eng = self._make_engineer(tmp_path)
        result = await eng._handle_ask_user_question("Write", {"file_path": "/test.py"})
        assert result["behavior"] == "allow"
        assert result["updatedInput"] == {"file_path": "/test.py"}

    @pytest.mark.asyncio
    async def test_single_select_question(self, tmp_path):
        """Single select question with options."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value="Option A - Description A")

        with patch("reverse_api.engineer.questionary.select", return_value=mock_select):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Which option?",
                    "header": "Choice",
                    "multiSelect": False,
                    "options": [
                        {"label": "Option A", "description": "Description A"},
                        {"label": "Option B", "description": "Description B"},
                    ],
                }],
            })
            assert result["behavior"] == "allow"
            assert result["updatedInput"]["answers"]["Which option?"] == "Option A"

    @pytest.mark.asyncio
    async def test_multi_select_question(self, tmp_path):
        """Multi select question with options."""
        eng = self._make_engineer(tmp_path)

        mock_checkbox = MagicMock()
        mock_checkbox.ask_async = AsyncMock(return_value=["Option A - Desc", "Option B"])

        with patch("reverse_api.engineer.questionary.checkbox", return_value=mock_checkbox):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Which features?",
                    "header": "Features",
                    "multiSelect": True,
                    "options": [
                        {"label": "Option A", "description": "Desc"},
                        {"label": "Option B"},
                    ],
                }],
            })
            assert result["behavior"] == "allow"
            assert "Option A" in result["updatedInput"]["answers"]["Which features?"]

    @pytest.mark.asyncio
    async def test_empty_question_skipped(self, tmp_path):
        """Empty question text is skipped."""
        eng = self._make_engineer(tmp_path)
        result = await eng._handle_ask_user_question("AskUserQuestion", {
            "questions": [{"question": "", "header": "", "multiSelect": False, "options": []}],
        })
        assert result["behavior"] == "allow"
        assert result["updatedInput"]["answers"] == {}

    @pytest.mark.asyncio
    async def test_select_cancelled(self, tmp_path):
        """Cancelled selection returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.engineer.questionary.select", return_value=mock_select):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Which option?",
                    "header": "",
                    "multiSelect": False,
                    "options": [{"label": "A"}],
                }],
            })
            assert result["updatedInput"]["answers"]["Which option?"] == ""

    @pytest.mark.asyncio
    async def test_checkbox_cancelled(self, tmp_path):
        """Cancelled checkbox returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_checkbox = MagicMock()
        mock_checkbox.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.engineer.questionary.checkbox", return_value=mock_checkbox):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Which features?",
                    "header": "",
                    "multiSelect": True,
                    "options": [{"label": "A"}],
                }],
            })
            assert result["updatedInput"]["answers"]["Which features?"] == ""

    @pytest.mark.asyncio
    async def test_text_fallback_single_select(self, tmp_path):
        """Text input fallback when no options for single select."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="custom answer")

        with patch("reverse_api.engineer.questionary.text", return_value=mock_text):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Enter value?",
                    "header": "",
                    "multiSelect": False,
                    "options": [],
                }],
            })
            assert result["updatedInput"]["answers"]["Enter value?"] == "custom answer"

    @pytest.mark.asyncio
    async def test_text_fallback_multi_select(self, tmp_path):
        """Text input fallback when no options for multi select."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value="custom answer")

        with patch("reverse_api.engineer.questionary.text", return_value=mock_text):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Enter value?",
                    "header": "",
                    "multiSelect": True,
                    "options": [],
                }],
            })
            assert result["updatedInput"]["answers"]["Enter value?"] == "custom answer"

    @pytest.mark.asyncio
    async def test_text_fallback_cancelled(self, tmp_path):
        """Cancelled text input returns empty answer."""
        eng = self._make_engineer(tmp_path)

        mock_text = MagicMock()
        mock_text.ask_async = AsyncMock(return_value=None)

        with patch("reverse_api.engineer.questionary.text", return_value=mock_text):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Enter value?",
                    "header": "",
                    "multiSelect": False,
                    "options": [],
                }],
            })
            assert result["updatedInput"]["answers"]["Enter value?"] == ""

    @pytest.mark.asyncio
    async def test_question_with_header(self, tmp_path):
        """Question with header displays it."""
        eng = self._make_engineer(tmp_path)

        mock_select = MagicMock()
        mock_select.ask_async = AsyncMock(return_value="A")

        with patch("reverse_api.engineer.questionary.select", return_value=mock_select):
            result = await eng._handle_ask_user_question("AskUserQuestion", {
                "questions": [{
                    "question": "Pick?",
                    "header": "Section Header",
                    "multiSelect": False,
                    "options": [{"label": "A"}],
                }],
            })
            assert result["behavior"] == "allow"


class TestClaudeEngineerAnalyzeAndGenerate:
    """Test analyze_and_generate method."""

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
            with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                mock_ms_instance = MagicMock()
                mock_ms.return_value = mock_ms_instance
                eng = ClaudeEngineer(**defaults)
                eng.scripts_dir = tmp_path / "scripts"
                eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                return eng

    def _make_result_message(self, is_error=False, result_text="Success"):
        """Create a mock that passes isinstance(x, ResultMessage)."""
        from claude_agent_sdk import ResultMessage
        mock = MagicMock(spec=ResultMessage)
        mock.is_error = is_error
        mock.result = result_text
        return mock

    def _make_assistant_message(self, content=None):
        """Create a mock that passes isinstance(x, AssistantMessage)."""
        from claude_agent_sdk import AssistantMessage
        mock = MagicMock(spec=AssistantMessage)
        mock.content = content or []
        mock.usage = None
        return mock

    def _make_tool_use_block(self, name="Read", tool_input=None):
        from claude_agent_sdk import ToolUseBlock
        mock = MagicMock(spec=ToolUseBlock)
        mock.name = name
        mock.input = tool_input or {}
        return mock

    def _make_tool_result_block(self, is_error=False, content="output"):
        from claude_agent_sdk import ToolResultBlock
        mock = MagicMock(spec=ToolResultBlock)
        mock.is_error = is_error
        mock.content = content
        return mock

    def _make_text_block(self, text="Thinking..."):
        from claude_agent_sdk import TextBlock
        mock = MagicMock(spec=TextBlock)
        mock.text = text
        return mock

    @pytest.mark.asyncio
    async def test_successful_generation(self, tmp_path):
        """Successful analysis returns result dict."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None
            assert "script_path" in result

    @pytest.mark.asyncio
    async def test_result_error(self, tmp_path):
        """Error result returns None."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=True, result_text="Analysis failed")

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_error_none_message(self, tmp_path):
        """Error result with None message uses 'Unknown error'."""
        eng = self._make_engineer(tmp_path)

        mock_result = self._make_result_message(is_error=True, result_text=None)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_assistant_message_with_tools(self, tmp_path):
        """AssistantMessage with tool blocks processes correctly."""
        eng = self._make_engineer(tmp_path)

        mock_tool_use = self._make_tool_use_block("Read", {"file_path": "/test.py"})
        mock_tool_result = self._make_tool_result_block(is_error=False, content="file content")
        mock_text = self._make_text_block("Analyzing the file...")

        mock_assistant = self._make_assistant_message(
            content=[mock_tool_use, mock_tool_result, mock_text]
        )
        mock_assistant.usage = {"input_tokens": 100, "output_tokens": 50}

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None

    @pytest.mark.asyncio
    async def test_exception_handling(self, tmp_path):
        """Exception during SDK use returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_with_usage_metadata(self, tmp_path):
        """Result with usage metadata calculates cost."""
        eng = self._make_engineer(tmp_path)
        eng.usage_metadata = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
        }

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None
            assert "usage" in result
            assert "estimated_cost_usd" in result["usage"]

    @pytest.mark.asyncio
    async def test_result_with_local_scripts_dir(self, tmp_path):
        """Result includes local path when local_scripts_dir is set."""
        eng = self._make_engineer(tmp_path)
        eng.local_scripts_dir = tmp_path / "local_scripts"

        mock_result = self._make_result_message(is_error=False)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await eng.analyze_and_generate()
            assert result is not None
