"""Tests for utils.py - Utility functions."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reverse_api.utils import (
    _slugify,
    check_for_updates,
    generate_folder_name,
    generate_run_id,
    get_actions_path,
    get_app_dir,
    get_base_output_dir,
    get_collected_dir,
    get_config_path,
    get_docs_dir,
    get_har_dir,
    get_history_path,
    get_messages_path,
    get_project_root,
    get_timestamp,
    parse_codegen_tag,
    parse_engineer_prompt,
    parse_record_only_tag,
)


class TestSlugify:
    """Test _slugify function."""

    def test_basic_text(self):
        """Converts basic text to slug."""
        assert _slugify("Hello World") == "hello_world"

    def test_removes_special_chars(self):
        """Removes special characters."""
        assert _slugify("Hello! World?") == "hello_world"

    def test_limits_to_three_words(self):
        """Takes first 3 words only."""
        result = _slugify("one two three four five")
        assert result == "one_two_three"

    def test_truncates_to_50_chars(self):
        """Truncates to 50 characters."""
        long_text = "a" * 100
        result = _slugify(long_text)
        assert len(result) <= 50

    def test_lowercase(self):
        """Converts to lowercase."""
        assert _slugify("HELLO WORLD") == "hello_world"

    def test_empty_string(self):
        """Handles empty string."""
        assert _slugify("") == ""

    def test_numbers(self):
        """Keeps numbers."""
        assert _slugify("test 123 api") == "test_123_api"

    def test_only_special_chars(self):
        """Handles string with only special chars."""
        result = _slugify("!@#$%")
        assert result == ""


class TestParseEngineerPrompt:
    """Test parse_engineer_prompt function."""

    def test_empty_input(self):
        """Empty input returns defaults."""
        result = parse_engineer_prompt("")
        assert result["run_id"] is None
        assert result["fresh"] is False
        assert result["docs"] is False
        assert result["prompt"] == ""
        assert result["is_tag_command"] is False
        assert result["error"] is None

    def test_none_input(self):
        """None input returns defaults."""
        result = parse_engineer_prompt(None)
        assert result["prompt"] == ""

    def test_standalone_docs_with_history(self):
        """@docs resolves latest run from session manager."""
        mock_sm = MagicMock()
        mock_sm.get_history.return_value = [{"run_id": "latest123"}]
        result = parse_engineer_prompt("@docs", session_manager=mock_sm)
        assert result["run_id"] == "latest123"
        assert result["docs"] is True
        assert result["is_tag_command"] is True

    def test_standalone_docs_no_history(self):
        """@docs with empty history returns error."""
        mock_sm = MagicMock()
        mock_sm.get_history.return_value = []
        result = parse_engineer_prompt("@docs", session_manager=mock_sm)
        assert result["error"] == "no runs found in history"

    def test_standalone_docs_no_session_manager(self):
        """@docs without session_manager returns None run_id."""
        result = parse_engineer_prompt("@docs")
        assert result["run_id"] is None
        assert result["docs"] is True

    def test_id_tag_basic(self):
        """@id <run_id> parses correctly."""
        result = parse_engineer_prompt("@id abc123 improve the auth")
        assert result["run_id"] == "abc123"
        assert result["prompt"] == "improve the auth"
        assert result["is_tag_command"] is True

    def test_id_tag_with_fresh(self):
        """@id with --fresh flag."""
        result = parse_engineer_prompt("@id abc123 --fresh start over")
        assert result["run_id"] == "abc123"
        assert result["fresh"] is True
        assert result["prompt"] == "start over"

    def test_id_tag_with_docs(self):
        """@id with @docs flag."""
        result = parse_engineer_prompt("@id abc123 @docs generate openapi")
        assert result["run_id"] == "abc123"
        assert result["docs"] is True
        assert result["prompt"] == "generate openapi"

    def test_id_tag_with_fresh_and_docs(self):
        """@id with both --fresh and @docs."""
        result = parse_engineer_prompt("@id abc123 --fresh @docs regenerate")
        assert result["run_id"] == "abc123"
        assert result["fresh"] is True
        assert result["docs"] is True
        assert result["prompt"] == "regenerate"

    def test_id_tag_no_prompt(self):
        """@id with no trailing prompt."""
        result = parse_engineer_prompt("@id abc123")
        assert result["run_id"] == "abc123"
        assert result["prompt"] == ""

    def test_plain_text_with_session_manager(self):
        """Plain text resolves latest run via session manager."""
        mock_sm = MagicMock()
        mock_sm.get_history.return_value = [{"run_id": "latest456"}]
        result = parse_engineer_prompt("fix the auth handler", session_manager=mock_sm)
        assert result["run_id"] == "latest456"
        assert result["prompt"] == "fix the auth handler"
        assert result["is_tag_command"] is False

    def test_plain_text_no_session_manager(self):
        """Plain text without session manager returns None run_id."""
        result = parse_engineer_prompt("fix the auth handler")
        assert result["run_id"] is None
        assert result["prompt"] == "fix the auth handler"

    def test_plain_text_empty_history(self):
        """Plain text with empty history returns error."""
        mock_sm = MagicMock()
        mock_sm.get_history.return_value = []
        result = parse_engineer_prompt("fix something", session_manager=mock_sm)
        assert result["error"] == "no runs found in history"


class TestParseRecordOnlyTag:
    """Test parse_record_only_tag function."""

    def test_empty_string(self):
        """Empty string returns empty prompt and False."""
        prompt, is_record = parse_record_only_tag("")
        assert prompt == ""
        assert is_record is False

    def test_no_tag(self):
        """No tag returns original prompt."""
        prompt, is_record = parse_record_only_tag("capture the api")
        assert prompt == "capture the api"
        assert is_record is False

    def test_with_tag(self):
        """@record-only tag is detected and removed."""
        prompt, is_record = parse_record_only_tag("@record-only capture traffic")
        assert prompt == "capture traffic"
        assert is_record is True

    def test_tag_case_insensitive(self):
        """Tag is case insensitive."""
        prompt, is_record = parse_record_only_tag("@RECORD-ONLY capture")
        assert is_record is True
        assert prompt == "capture"

    def test_tag_at_end(self):
        """Tag at end of prompt."""
        prompt, is_record = parse_record_only_tag("capture traffic @record-only")
        assert is_record is True
        assert prompt == "capture traffic"

    def test_none_input(self):
        """None input returns empty and False."""
        prompt, is_record = parse_record_only_tag(None)
        assert prompt == ""
        assert is_record is False


class TestParseCodegenTag:
    """Test parse_codegen_tag function."""

    def test_empty_string(self):
        """Empty string returns empty prompt and False."""
        prompt, is_codegen = parse_codegen_tag("")
        assert prompt == ""
        assert is_codegen is False

    def test_no_tag(self):
        """No tag returns original prompt."""
        prompt, is_codegen = parse_codegen_tag("automate this")
        assert prompt == "automate this"
        assert is_codegen is False

    def test_with_tag(self):
        """@codegen tag is detected and removed."""
        prompt, is_codegen = parse_codegen_tag("@codegen login flow")
        assert prompt == "login flow"
        assert is_codegen is True

    def test_tag_case_insensitive(self):
        """Tag is case insensitive."""
        prompt, is_codegen = parse_codegen_tag("@CODEGEN login")
        assert is_codegen is True

    def test_none_input(self):
        """None input returns empty and False."""
        prompt, is_codegen = parse_codegen_tag(None)
        assert prompt == ""
        assert is_codegen is False


class TestGenerateRunId:
    """Test generate_run_id function."""

    def test_returns_string(self):
        """Returns a string."""
        run_id = generate_run_id()
        assert isinstance(run_id, str)

    def test_length(self):
        """Run ID is 12 characters."""
        run_id = generate_run_id()
        assert len(run_id) == 12

    def test_hex_characters(self):
        """Run ID contains only hex characters."""
        run_id = generate_run_id()
        assert re.match(r"^[0-9a-f]+$", run_id)

    def test_unique(self):
        """Two run IDs are different."""
        id1 = generate_run_id()
        id2 = generate_run_id()
        assert id1 != id2


class TestPathHelpers:
    """Test path helper functions."""

    def test_get_project_root(self):
        """get_project_root returns a valid directory."""
        root = get_project_root()
        assert isinstance(root, Path)

    def test_get_app_dir(self):
        """get_app_dir returns ~/.reverse-api."""
        app_dir = get_app_dir()
        assert app_dir == Path.home() / ".reverse-api"

    def test_get_config_path(self):
        """get_config_path returns config.json in app dir."""
        config_path = get_config_path()
        assert config_path == Path.home() / ".reverse-api" / "config.json"

    def test_get_history_path(self):
        """get_history_path returns history.json in app dir."""
        history_path = get_history_path()
        assert history_path == Path.home() / ".reverse-api" / "history.json"

    def test_get_base_output_dir_default(self):
        """get_base_output_dir returns runs/ in app dir by default."""
        base = get_base_output_dir()
        assert base == Path.home() / ".reverse-api" / "runs"

    def test_get_base_output_dir_custom(self):
        """get_base_output_dir returns custom dir when specified."""
        base = get_base_output_dir("/custom/output")
        assert base == Path("/custom/output")

    def test_get_timestamp(self):
        """get_timestamp returns ISO format."""
        ts = get_timestamp()
        assert "T" in ts  # ISO format contains T separator

    def test_get_messages_path(self, tmp_path):
        """get_messages_path returns correct path."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            path = get_messages_path("run123")
            assert path == tmp_path / "messages" / "run123.jsonl"


class TestGetHarDir:
    """Test get_har_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("abc123")
            assert har_dir == tmp_path / "har" / "abc123"
            assert har_dir.exists()

    def test_run_id_with_hyphens(self, tmp_path):
        """Hyphens are allowed in run_id."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("crx-abc-123")
            assert har_dir.exists()

    def test_run_id_with_underscores(self, tmp_path):
        """Underscores are allowed in run_id."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            har_dir = get_har_dir("run_123_test")
            assert har_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_har_dir("")

    def test_special_chars_raise(self):
        """Special characters in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("../../../etc")

    def test_dots_raise(self):
        """Dots in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("run.123")

    def test_spaces_raise(self):
        """Spaces in run_id raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_har_dir("run 123")

    def test_too_long_run_id(self):
        """Run ID > 64 chars raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_har_dir("a" * 65)

    def test_custom_output_dir(self, tmp_path):
        """Custom output_dir is used."""
        har_dir = get_har_dir("run123", output_dir=str(tmp_path))
        assert har_dir == tmp_path / "har" / "run123"


class TestGetScriptsDir:
    """Test get_scripts_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        from reverse_api.utils import get_scripts_dir

        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            scripts_dir = get_scripts_dir("abc123")
            assert scripts_dir == tmp_path / "scripts" / "abc123"
            assert scripts_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="cannot be empty"):
            get_scripts_dir("")

    def test_special_chars_raise(self):
        """Special characters raise ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="Invalid run_id"):
            get_scripts_dir("../hack")

    def test_too_long_raises(self):
        """Too long run_id raises ValueError."""
        from reverse_api.utils import get_scripts_dir

        with pytest.raises(ValueError, match="too long"):
            get_scripts_dir("x" * 65)


class TestGetDocsDir:
    """Test get_docs_dir with validation."""

    def test_valid_run_id(self, tmp_path):
        """Valid run_id creates correct directory."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            docs_dir = get_docs_dir("abc123")
            assert docs_dir == tmp_path / "docs" / "abc123"
            assert docs_dir.exists()

    def test_empty_run_id_raises(self):
        """Empty run_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            get_docs_dir("")

    def test_special_chars_raise(self):
        """Special characters raise ValueError."""
        with pytest.raises(ValueError, match="Invalid run_id"):
            get_docs_dir("../hack")

    def test_too_long_raises(self):
        """Too long run_id raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            get_docs_dir("x" * 65)


class TestGetActionsPath:
    """Test get_actions_path."""

    def test_returns_actions_json(self, tmp_path):
        """Returns actions.json inside har dir."""
        with patch("reverse_api.utils.get_base_output_dir", return_value=tmp_path):
            path = get_actions_path("run123")
            assert path.name == "actions.json"
            assert "har" in str(path)


class TestGetCollectedDir:
    """Test get_collected_dir."""

    def test_creates_collected_dir(self, tmp_path):
        """Creates collected directory."""
        with patch("reverse_api.utils.Path.cwd", return_value=tmp_path):
            from reverse_api.utils import get_collected_dir

            path = get_collected_dir("test_collection")
            assert path.exists()
            assert path.name == "test_collection"


class TestCheckForUpdates:
    """Test check_for_updates function."""

    def test_no_update_needed(self):
        """Returns None when versions match."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "0.0.0.dev"}}
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            with patch("reverse_api.utils.__version__", "0.0.0.dev"):
                assert check_for_updates() is None

    def test_update_available(self):
        """Returns update message when newer version exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "99.0.0"}}
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            result = check_for_updates()
            assert result is not None
            assert "99.0.0" in result

    def test_network_error_returns_none(self):
        """Returns None on network error."""
        with patch("reverse_api.utils.httpx.get", side_effect=Exception("network error")):
            assert check_for_updates() is None

    def test_non_200_returns_none(self):
        """Returns None on non-200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch("reverse_api.utils.httpx.get", return_value=mock_response):
            assert check_for_updates() is None


class TestGenerateFolderName:
    """Test generate_folder_name function."""

    def test_falls_back_to_slugify_in_async_context(self):
        """Falls back to _slugify when in async context."""
        import asyncio

        async def _inner():
            return generate_folder_name("test api capture")

        result = asyncio.run(_inner())
        # Should use _slugify fallback since we're in async context
        assert isinstance(result, str)
        assert len(result) > 0

    def test_falls_back_on_exception(self):
        """Falls back to _slugify on exception."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                result = generate_folder_name("test api", sdk="claude")
                assert isinstance(result, str)
                assert len(result) > 0

    def test_sdk_opencode_falls_back(self):
        """OpenCode SDK falls back to slugify when API unavailable."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("no server")):
                result = generate_folder_name("apple jobs api", sdk="opencode")
                assert isinstance(result, str)

    def test_sdk_default_from_config(self):
        """SDK defaults from config when not provided."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                result = generate_folder_name("test prompt")
                assert isinstance(result, str)

    def test_config_exception_defaults_to_claude(self):
        """Config exception defaults SDK to claude."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", side_effect=Exception("fail")):
                with patch("reverse_api.utils.get_config_path", side_effect=Exception("no config")):
                    result = generate_folder_name("test prompt")
                    assert isinstance(result, str)

    def test_opencode_calls_opencode_async(self):
        """OpenCode SDK calls _generate_folder_name_opencode_async."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="opencode_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="opencode")
                assert result == "opencode_result"

    def test_claude_calls_claude_async(self):
        """Claude SDK calls _generate_folder_name_async."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="claude_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="claude")
                assert result == "claude_result"

    def test_with_session_id(self):
        """OpenCode with session_id passes it through."""
        with patch("reverse_api.utils.asyncio.get_running_loop", side_effect=RuntimeError):
            with patch("reverse_api.utils.asyncio.run", return_value="test_result") as mock_run:
                result = generate_folder_name("test prompt", sdk="opencode", session_id="sess123")
                assert result == "test_result"
