"""Tests for native_host.py - Native messaging host."""

import io
import json
import platform
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.native_host import (
    HOST_NAME,
    NativeHostHandler,
    get_host_script_path,
    get_native_host_manifest_dir,
    read_message,
    run_host,
    send_message,
    uninstall_native_host,
)


class TestHostName:
    """Test HOST_NAME constant."""

    def test_host_name(self):
        """HOST_NAME is set correctly."""
        assert HOST_NAME == "com.reverse_api.engineer"


class TestGetNativeHostManifestDir:
    """Test get_native_host_manifest_dir function."""

    def test_linux(self):
        """Linux manifest directory."""
        with patch("reverse_api.native_host.platform.system", return_value="Linux"):
            path = get_native_host_manifest_dir()
            assert ".config/google-chrome/NativeMessagingHosts" in str(path)

    def test_darwin(self):
        """macOS manifest directory."""
        with patch("reverse_api.native_host.platform.system", return_value="Darwin"):
            path = get_native_host_manifest_dir()
            assert "Library/Application Support/Google/Chrome/NativeMessagingHosts" in str(path)

    def test_windows(self):
        """Windows manifest directory."""
        with patch("reverse_api.native_host.platform.system", return_value="Windows"):
            path = get_native_host_manifest_dir()
            assert "NativeMessagingHosts" in str(path)

    def test_unsupported(self):
        """Unsupported platform raises RuntimeError."""
        with patch("reverse_api.native_host.platform.system", return_value="FreeBSD"):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                get_native_host_manifest_dir()


class TestGetHostScriptPath:
    """Test get_host_script_path function."""

    def test_path_in_app_dir(self):
        """Host script is in app directory."""
        path = get_host_script_path()
        assert path.name == "native-host.py"
        assert ".reverse-api" in str(path)


class TestReadMessage:
    """Test read_message function."""

    def test_read_valid_message(self):
        """Reads a properly formatted message."""
        msg = {"type": "status"}
        encoded = json.dumps(msg).encode("utf-8")
        data = struct.pack("<I", len(encoded)) + encoded

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(data)
            result = read_message()
            assert result == msg

    def test_read_empty_stdin(self):
        """Returns None on empty stdin."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"")
            result = read_message()
            assert result is None

    def test_read_incomplete_length(self):
        """Returns None on incomplete length bytes."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(b"\x01\x00")
            result = read_message()
            assert result is None

    def test_read_incomplete_message(self):
        """Returns None when message data is shorter than declared length."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.buffer = io.BytesIO(struct.pack("<I", 100) + b"short")
            result = read_message()
            assert result is None


class TestSendMessage:
    """Test send_message function."""

    def test_send_message(self):
        """Sends properly formatted message."""
        msg = {"type": "status", "connected": True}
        output = io.BytesIO()

        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = output
            send_message(msg)

        output.seek(0)
        length = struct.unpack("<I", output.read(4))[0]
        data = json.loads(output.read(length).decode("utf-8"))
        assert data == msg


class TestNativeHostHandler:
    """Test NativeHostHandler class."""

    def _make_handler(self):
        with patch("reverse_api.native_host.ConfigManager") as mock_cm:
            mock_cm.return_value.config_path = Path("/test/config.json")
            handler = NativeHostHandler()
            return handler

    def test_handle_status(self):
        """Status handler returns version info."""
        handler = self._make_handler()
        result = handler.handle_status({"type": "status", "_callbackId": "cb1"})
        assert result["type"] == "status"
        assert result["connected"] is True
        assert "version" in result
        assert result["_callbackId"] == "cb1"

    def test_handle_save_har_missing_data(self):
        """Save HAR fails without required data."""
        handler = self._make_handler()
        result = handler.handle_save_har({"type": "saveHar"})
        assert result["type"] == "error"
        assert "Missing" in result["message"]

    def test_handle_save_har_success(self, tmp_path):
        """Save HAR saves data successfully."""
        handler = self._make_handler()
        har_data = {"log": {"entries": []}}

        with patch("reverse_api.native_host.get_har_dir", return_value=tmp_path):
            result = handler.handle_save_har({
                "type": "saveHar",
                "run_id": "test123",
                "har": har_data,
                "_callbackId": "cb1",
            })
            assert result["type"] == "complete"
            assert "path" in result
            assert handler.current_run_id == "test123"

    def test_handle_save_har_exception(self, tmp_path):
        """Save HAR handles exceptions."""
        handler = self._make_handler()
        with patch("reverse_api.native_host.get_har_dir", side_effect=ValueError("bad id")):
            result = handler.handle_save_har({
                "type": "saveHar",
                "run_id": "../bad",
                "har": {"log": {}},
                "_callbackId": "cb1",
            })
            assert result["type"] == "error"

    def test_handle_generate_no_run_id(self):
        """Generate fails without run_id."""
        handler = self._make_handler()
        handler.current_run_id = None
        result = handler.handle_generate({"type": "generate"})
        assert result["type"] == "error"
        assert "No run_id" in result["message"]

    def test_handle_generate_with_current_run_id(self):
        """Generate uses current_run_id when message has none."""
        handler = self._make_handler()
        handler.current_run_id = "current_id"

        with patch.object(handler, "_run_async", side_effect=Exception("mock")):
            result = handler.handle_generate({"type": "generate"})
            assert result["type"] == "error"
            assert result["retryable"] is True

    def test_handle_generate_with_message_run_id(self):
        """Generate uses run_id from message."""
        handler = self._make_handler()

        with patch.object(handler, "_run_async", side_effect=Exception("mock")):
            result = handler.handle_generate({"type": "generate", "run_id": "from_msg"})
            assert result["type"] == "error"

    def test_handle_chat_no_message(self):
        """Chat fails without message."""
        handler = self._make_handler()
        result = handler.handle_chat({"type": "chat"})
        assert result["type"] == "error"
        assert "No message" in result["message"]

    def test_handle_chat_no_run_id(self):
        """Chat fails without run_id."""
        handler = self._make_handler()
        handler.current_run_id = None
        result = handler.handle_chat({"type": "chat", "message": "test"})
        assert result["type"] == "error"
        assert "No active session" in result["message"]

    def test_handle_chat_uses_message_run_id(self):
        """Chat uses run_id from message."""
        handler = self._make_handler()
        handler.current_run_id = "old_id"

        with patch.object(handler, "_run_async", side_effect=Exception("mock")):
            result = handler.handle_chat({
                "type": "chat",
                "message": "test",
                "run_id": "from_message",
            })
            assert result["type"] == "error"

    def test_handle_chat_exception(self):
        """Chat handles exceptions."""
        handler = self._make_handler()
        handler.current_run_id = "test_id"

        with patch.object(handler, "_run_async", side_effect=Exception("chat failed")):
            result = handler.handle_chat({
                "type": "chat",
                "message": "test",
            })
            assert result["type"] == "error"
            assert "chat failed" in result["message"]

    def test_handle_unknown_type(self):
        """Unknown message type returns error."""
        handler = self._make_handler()
        result = handler.handle_message({"type": "unknown"})
        assert result["type"] == "error"
        assert "Unknown" in result["message"]

    def test_handle_message_routes(self):
        """handle_message routes to correct handler."""
        handler = self._make_handler()
        result = handler.handle_message({"type": "status"})
        assert result["type"] == "status"

    def test_handle_message_routes_save_har(self):
        """handle_message routes saveHar correctly."""
        handler = self._make_handler()
        result = handler.handle_message({"type": "saveHar"})
        assert result["type"] == "error"  # Missing data

    def test_summarize_tool_input_read(self):
        """Summarize Read tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Read", {"file_path": "/test.py"})
        assert result["file_path"] == "/test.py"

    def test_summarize_tool_input_write(self):
        """Summarize Write tool input."""
        handler = self._make_handler()
        content = "x" * 200
        result = handler._summarize_tool_input("Write", {"file_path": "/test.py", "content": content})
        assert result["file_path"] == "/test.py"
        assert result["content_length"] == 200
        assert result["content_preview"].endswith("...")

    def test_summarize_tool_input_write_short(self):
        """Summarize Write tool with short content."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Write", {"file_path": "/t.py", "content": "short"})
        assert result["content_preview"] == "short"

    def test_summarize_tool_input_bash(self):
        """Summarize Bash tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Bash", {"command": "python test.py"})
        assert result["command"] == "python test.py"

    def test_summarize_tool_input_glob(self):
        """Summarize Glob tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Glob", {"pattern": "*.py"})
        assert result["pattern"] == "*.py"

    def test_summarize_tool_input_grep(self):
        """Summarize Grep tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Grep", {"pattern": "def test_", "path": "/src"})
        assert result["pattern"] == "def test_"
        assert result["path"] == "/src"

    def test_summarize_tool_input_edit(self):
        """Summarize Edit tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Edit", {"file_path": "/test.py", "old_string": "x" * 100})
        assert result["file_path"] == "/test.py"
        assert result["old_string"].endswith("...")

    def test_summarize_tool_input_edit_short(self):
        """Summarize Edit tool with short old_string."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("Edit", {"file_path": "/t.py", "old_string": "short"})
        assert result["old_string"] == "short"

    def test_summarize_tool_input_generic(self):
        """Summarize generic tool input."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("CustomTool", {"key": "value", "long": "x" * 200})
        assert result["key"] == "value"
        assert result["long"].endswith("...")

    def test_summarize_tool_input_generic_non_string(self):
        """Summarize generic tool with non-string value."""
        handler = self._make_handler()
        result = handler._summarize_tool_input("CustomTool", {"count": 42})
        assert result["count"] == 42


class TestUninstallNativeHost:
    """Test uninstall_native_host function."""

    def test_uninstall_nothing_installed(self, tmp_path):
        """Uninstall when nothing is installed."""
        with patch("reverse_api.native_host.get_native_host_manifest_dir", return_value=tmp_path):
            with patch("reverse_api.native_host.get_host_script_path", return_value=tmp_path / "script.py"):
                success, msg = uninstall_native_host()
                assert success is True
                assert "not installed" in msg

    def test_uninstall_removes_manifest(self, tmp_path):
        """Uninstall removes manifest file."""
        manifest = tmp_path / f"{HOST_NAME}.json"
        manifest.write_text("{}")

        with patch("reverse_api.native_host.get_native_host_manifest_dir", return_value=tmp_path):
            with patch("reverse_api.native_host.get_host_script_path", return_value=tmp_path / "nonexistent.py"):
                success, msg = uninstall_native_host()
                assert success is True
                assert "Removed manifest" in msg
                assert not manifest.exists()

    def test_uninstall_removes_host_script(self, tmp_path):
        """Uninstall removes host script."""
        script = tmp_path / "native-host.py"
        script.write_text("#!/usr/bin/env python3")

        with patch("reverse_api.native_host.get_native_host_manifest_dir", return_value=tmp_path):
            with patch("reverse_api.native_host.get_host_script_path", return_value=script):
                success, msg = uninstall_native_host()
                assert success is True
                assert "Removed host script" in msg
                assert not script.exists()

    def test_uninstall_exception(self, tmp_path):
        """Uninstall handles exceptions."""
        with patch("reverse_api.native_host.get_native_host_manifest_dir", side_effect=Exception("fail")):
            success, msg = uninstall_native_host()
            assert success is False
            assert "Failed to uninstall" in msg


class TestCheckPythonVersion:
    """Test _check_python_version helper."""

    def test_current_python(self):
        """Current Python meets version requirement."""
        import sys
        from reverse_api.native_host import _check_python_version

        result = _check_python_version(sys.executable, min_version=(3, 10))
        assert result is True

    def test_invalid_path(self):
        """Invalid path returns False."""
        from reverse_api.native_host import _check_python_version

        result = _check_python_version("/nonexistent/python", min_version=(3, 10))
        assert result is False


class TestFindPythonInterpreter:
    """Test _find_python_interpreter function."""

    def test_finds_current_interpreter(self):
        """Finds the current Python interpreter."""
        import sys
        from reverse_api.native_host import _find_python_interpreter

        result = _find_python_interpreter()
        assert result == sys.executable

    def test_no_suitable_python(self):
        """Raises when no suitable Python found."""
        from reverse_api.native_host import _find_python_interpreter

        with patch("reverse_api.native_host._check_python_version", return_value=False):
            with patch("reverse_api.native_host.shutil.which", return_value=None):
                with pytest.raises(RuntimeError, match="Could not find"):
                    _find_python_interpreter()

    def test_finds_via_shutil_which(self):
        """Falls back to shutil.which."""
        import sys
        from reverse_api.native_host import _find_python_interpreter

        def mock_check(path, min_version):
            if path == sys.executable:
                return False
            if path == "/found/python3":
                return True
            return False

        with patch("reverse_api.native_host._check_python_version", side_effect=mock_check):
            with patch("reverse_api.native_host.shutil.which", return_value="/found/python3"):
                result = _find_python_interpreter()
                assert result == "/found/python3"


class TestInstallNativeHost:
    """Test install_native_host function."""

    def test_install_without_extension_id(self, tmp_path):
        """Install fails without extension_id."""
        from reverse_api.native_host import install_native_host

        success, msg = install_native_host(extension_id=None)
        assert success is False
        assert "Extension ID is required" in msg

    def test_install_with_extension_id(self, tmp_path):
        """Install succeeds with extension_id."""
        import sys
        from reverse_api.native_host import install_native_host

        with patch("reverse_api.native_host.get_native_host_manifest_dir", return_value=tmp_path / "manifests"):
            with patch("reverse_api.native_host.get_host_script_path", return_value=tmp_path / "host.py"):
                with patch("reverse_api.native_host._find_python_interpreter", return_value=sys.executable):
                    success, msg = install_native_host(extension_id="abcdef1234567890abcdef1234567890")
                    assert success is True
                    assert "installed successfully" in msg

    def test_install_exception(self, tmp_path):
        """Install handles exceptions."""
        from reverse_api.native_host import install_native_host

        with patch("reverse_api.native_host._find_python_interpreter", side_effect=RuntimeError("no python")):
            success, msg = install_native_host(extension_id="test")
            assert success is False
            assert "Failed to install" in msg


class TestNativeHostHandlerRunAsyncMethod:
    """Test _run_async method."""

    def test_run_async_creates_loop(self):
        """_run_async creates event loop on first call."""
        with patch("reverse_api.native_host.ConfigManager") as mock_cm:
            mock_cm.return_value.config_path = Path("/test/config.json")
            handler = NativeHostHandler()
            assert handler._loop is None

            async def simple_coro():
                return 42

            result = handler._run_async(simple_coro())
            assert result == 42
            assert handler._loop is not None

    def test_run_async_reuses_loop(self):
        """_run_async reuses existing event loop."""
        with patch("reverse_api.native_host.ConfigManager") as mock_cm:
            mock_cm.return_value.config_path = Path("/test/config.json")
            handler = NativeHostHandler()

            async def coro1():
                return 1

            async def coro2():
                return 2

            handler._run_async(coro1())
            loop = handler._loop
            handler._run_async(coro2())
            assert handler._loop is loop


class TestRunHost:
    """Test run_host function."""

    def test_run_host_processes_messages(self):
        """run_host processes messages until None."""
        messages = [
            {"type": "status"},
            None,
        ]
        msg_iter = iter(messages)

        with patch("reverse_api.native_host.read_message", side_effect=lambda: next(msg_iter)):
            with patch("reverse_api.native_host.send_message") as mock_send:
                with patch("reverse_api.native_host.NativeHostHandler") as mock_handler_cls:
                    mock_handler = MagicMock()
                    mock_handler.handle_message.return_value = {"type": "status", "connected": True}
                    mock_handler_cls.return_value = mock_handler

                    run_host()

                    mock_handler.handle_message.assert_called_once_with({"type": "status"})
                    mock_send.assert_called_once()

    def test_run_host_handles_exception(self):
        """run_host sends error on exception."""
        call_count = [0]

        def mock_read():
            call_count[0] += 1
            if call_count[0] == 1:
                return {"type": "status"}
            return None

        with patch("reverse_api.native_host.read_message", side_effect=mock_read):
            with patch("reverse_api.native_host.send_message") as mock_send:
                with patch("reverse_api.native_host.NativeHostHandler") as mock_handler_cls:
                    mock_handler = MagicMock()
                    mock_handler.handle_message.side_effect = Exception("handler error")
                    mock_handler_cls.return_value = mock_handler

                    run_host()

                    error_call = mock_send.call_args_list[0]
                    assert error_call[0][0]["type"] == "error"
                    assert "handler error" in error_call[0][0]["message"]


class TestNativeHostGenerateAsync:
    """Test _generate_async method."""

    def _make_handler(self):
        with patch("reverse_api.native_host.ConfigManager") as mock_cm:
            mock_cm.return_value.config_path = Path("/test/config.json")
            mock_cm.return_value.get.return_value = "claude-sonnet-4-5"
            return NativeHostHandler()

    @pytest.mark.asyncio
    async def test_generate_har_not_found(self, tmp_path):
        """Generate returns error when HAR file missing."""
        handler = self._make_handler()

        with patch("reverse_api.native_host.get_har_dir", return_value=tmp_path / "har"):
            result = await handler._generate_async("run123", "claude-sonnet-4-5", {"_callbackId": "cb1"})
            assert result["type"] == "error"
            assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_generate_exception(self, tmp_path):
        """Generate handles exception during analysis."""
        handler = self._make_handler()

        har_dir = tmp_path / "har"
        har_dir.mkdir(parents=True)
        (har_dir / "recording.har").write_text('{"log": {}}')

        mock_engineer = MagicMock()

        async def mock_analyze():
            raise Exception("analysis failed")

        mock_engineer.analyze_and_generate = mock_analyze

        # Patch at source modules since _generate_async uses lazy imports
        with patch("reverse_api.utils.get_har_dir", return_value=har_dir):
            with patch("reverse_api.utils.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.native_host.send_message"):
                    with patch("reverse_api.engineer.ClaudeEngineer", return_value=mock_engineer):
                        result = await handler._generate_async(
                            "run123", "claude-sonnet-4-5", {"_callbackId": "cb1"}
                        )
                        assert result["type"] == "error"
                        assert result["retryable"] is True

    @pytest.mark.asyncio
    async def test_generate_success(self, tmp_path):
        """Generate succeeds with HAR file."""
        handler = self._make_handler()

        har_dir = tmp_path / "har"
        har_dir.mkdir(parents=True)
        (har_dir / "recording.har").write_text('{"log": {"entries": []}}')

        mock_engineer = MagicMock()

        async def mock_analyze():
            return {"script_path": str(tmp_path / "scripts" / "api_client.py")}

        mock_engineer.analyze_and_generate = mock_analyze

        # Patch at source modules since _generate_async uses lazy imports
        with patch("reverse_api.utils.get_har_dir", return_value=har_dir):
            with patch("reverse_api.utils.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.native_host.send_message"):
                    with patch("reverse_api.engineer.ClaudeEngineer", return_value=mock_engineer):
                        with patch("reverse_api.session.SessionManager"):
                            result = await handler._generate_async(
                                "run123", "claude-sonnet-4-5", {"_callbackId": "cb1"}
                            )
                            assert result["type"] == "complete"


class TestNativeHostChatAsync:
    """Test _chat_async_streaming method."""

    def _make_handler(self):
        with patch("reverse_api.native_host.ConfigManager") as mock_cm:
            mock_cm.return_value.config_path = Path("/test/config.json")
            mock_cm.return_value.get.return_value = "claude-sonnet-4-5"
            handler = NativeHostHandler()
            handler.config = mock_cm.return_value
            return handler

    @pytest.mark.asyncio
    async def test_chat_har_not_found(self, tmp_path):
        """Chat returns error when HAR file missing."""
        handler = self._make_handler()

        with patch("reverse_api.native_host.get_har_dir", return_value=tmp_path / "har"):
            result = await handler._chat_async_streaming(
                "test message", "run123", {"_callbackId": "cb1"}
            )
            assert result["type"] == "error"
            assert "capture traffic" in result["message"].lower() or "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_chat_exception(self, tmp_path):
        """Chat handles SDK exception."""
        handler = self._make_handler()

        har_dir = tmp_path / "har"
        har_dir.mkdir(parents=True)
        (har_dir / "recording.har").write_text('{"log": {}}')

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)

        # Patch at source modules since _chat_async_streaming uses lazy imports
        with patch("reverse_api.utils.get_har_dir", return_value=har_dir):
            with patch("reverse_api.utils.get_scripts_dir", return_value=scripts_dir):
                with patch("reverse_api.native_host.send_message"):
                    # Patch ClaudeSDKClient at its source (claude_agent_sdk)
                    mock_sdk = MagicMock()
                    mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)
                    with patch("claude_agent_sdk.ClaudeSDKClient", mock_sdk):
                        result = await handler._chat_async_streaming(
                            "test message", "run123", {"_callbackId": "cb1"}
                        )
                        assert result["type"] == "error"
