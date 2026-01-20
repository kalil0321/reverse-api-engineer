"""
Native Messaging Host for Chrome Extension

This module implements the native messaging protocol for communication
between the Chrome extension and the reverse-api-engineer CLI.

Native messaging uses stdin/stdout with length-prefixed JSON messages:
- First 4 bytes: message length (little-endian uint32)
- Remaining bytes: JSON message
"""

import asyncio
import json
import os
import platform
import shutil
import struct
import sys
from pathlib import Path
from typing import Any

from .config import ConfigManager
from .utils import (
    generate_run_id,
    get_har_dir,
    get_scripts_dir,
    get_app_dir,
)

HOST_NAME = "com.reverse_api.engineer"


def get_native_host_manifest_dir() -> Path:
    """Get the directory for native messaging host manifests."""
    system = platform.system()

    if system == "Darwin":  # macOS
        return Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
    elif system == "Linux":
        return Path.home() / ".config/google-chrome/NativeMessagingHosts"
    elif system == "Windows":
        # Windows uses registry, but manifest still needs to exist
        return Path.home() / "AppData/Local/Google/Chrome/User Data/NativeMessagingHosts"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def get_host_script_path() -> Path:
    """Get the path to the native host script."""
    return get_app_dir() / "native-host.py"


def _find_python_interpreter() -> str:
    """
    Find a suitable Python 3.10+ interpreter.

    Chrome launches native hosts with a minimal environment, so we need
    an absolute path to a Python interpreter that supports modern syntax
    (like `str | None` union types which require Python 3.10+).

    Returns:
        Absolute path to a Python 3.10+ interpreter

    Raises:
        RuntimeError: If no suitable Python interpreter is found
    """
    import subprocess

    # First, try the current interpreter (the one running this code)
    current_python = sys.executable
    if current_python and _check_python_version(current_python, min_version=(3, 10)):
        return current_python

    # Common Python interpreter names to search for, in order of preference
    python_names = ["python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"]

    # Common paths where Python might be installed
    system = platform.system()
    if system == "Darwin":  # macOS
        search_paths = [
            "/opt/homebrew/bin",  # Apple Silicon Homebrew
            "/usr/local/bin",  # Intel Homebrew
            "/usr/bin",
        ]
    elif system == "Linux":
        search_paths = [
            "/usr/bin",
            "/usr/local/bin",
            str(Path.home() / ".local/bin"),
        ]
    elif system == "Windows":
        search_paths = [
            str(Path.home() / "AppData/Local/Programs/Python"),
            "C:/Python313",
            "C:/Python312",
            "C:/Python311",
            "C:/Python310",
            str(Path.home() / "AppData/Local/Microsoft/WindowsApps"),
        ]
    else:
        search_paths = []

    # Search for a suitable Python interpreter
    for search_path in search_paths:
        for python_name in python_names:
            if system == "Windows":
                # On Windows, also check in version subdirectories
                candidates = [
                    Path(search_path) / python_name / "python.exe",
                    Path(search_path) / f"{python_name}.exe",
                ]
            else:
                candidates = [Path(search_path) / python_name]

            for candidate in candidates:
                if candidate.exists() and _check_python_version(str(candidate), min_version=(3, 10)):
                    return str(candidate)

    # Try using shutil.which as a fallback
    for python_name in python_names:
        python_path = shutil.which(python_name)
        if python_path and _check_python_version(python_path, min_version=(3, 10)):
            return python_path

    raise RuntimeError("Could not find a Python 3.10+ interpreter. Please install Python 3.10 or later and ensure it's in your PATH.")


def _check_python_version(python_path: str, min_version: tuple[int, int]) -> bool:
    """Check if a Python interpreter meets the minimum version requirement."""
    import subprocess

    try:
        result = subprocess.run(
            [python_path, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version_str = result.stdout.strip()
            major, minor = map(int, version_str.split(".")[:2])
            return (major, minor) >= min_version
    except Exception:
        pass
    return False


def install_native_host(extension_id: str | None = None) -> tuple[bool, str]:
    """
    Install the native messaging host.

    Args:
        extension_id: Chrome extension ID. Required for the host to work.
                     Get this from chrome://extensions/ after loading the extension.

    Returns:
        Tuple of (success, message)
    """
    try:
        # Find a suitable Python interpreter
        python_path = _find_python_interpreter()

        # Create manifest directory
        manifest_dir = get_native_host_manifest_dir()
        manifest_dir.mkdir(parents=True, exist_ok=True)

        # Create the host script in app directory
        host_script = get_host_script_path()
        host_script.parent.mkdir(parents=True, exist_ok=True)

        # Write the host script with absolute path to Python interpreter
        # This is critical because Chrome launches the script with a minimal
        # environment where /usr/bin/env python3 may resolve to an older Python
        # Find site-packages path
        import reverse_api

        site_packages = str(Path(reverse_api.__file__).parent.parent)

        # Use repr() to properly escape Windows backslashes in paths
        host_script_content = f'''#!{python_path}
"""Native messaging host entry point."""
import sys
sys.path.insert(0, {repr(site_packages)})
from reverse_api.native_host import run_host
run_host()
'''
        host_script.write_text(host_script_content)
        host_script.chmod(0o755)

        # Build manifest
        manifest = {
            "name": HOST_NAME,
            "description": "Reverse API Engineer Native Messaging Host",
            "path": str(host_script),
            "type": "stdio",
        }

        # Add allowed origins - Chrome does NOT support wildcards
        # Extension ID is required for the native host to work
        if extension_id:
            manifest["allowed_origins"] = [f"chrome-extension://{extension_id}/"]
        else:
            return False, (
                "Extension ID is required for native messaging to work.\n"
                "To find your extension ID:\n"
                "  1. Go to chrome://extensions/\n"
                "  2. Find 'Reverse API Engineer'\n"
                "  3. Copy the ID (32-character string)\n"
                "  4. Run: reverse-api-engineer install-host --extension-id YOUR_ID_HERE"
            )

        # Write manifest
        manifest_path = manifest_dir / f"{HOST_NAME}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # On Windows, also need to add registry entry
        if platform.system() == "Windows":
            _install_windows_registry(manifest_path)

        return True, f"Native host installed successfully.\nManifest: {manifest_path}\nHost script: {host_script}\nPython interpreter: {python_path}"

    except Exception as e:
        return False, f"Failed to install native host: {e}"


def _install_windows_registry(manifest_path: Path) -> None:
    """Install Windows registry entry for native messaging."""
    import winreg

    key_path = f"SOFTWARE\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}"

    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
        winreg.CloseKey(key)
    except Exception as e:
        raise RuntimeError(f"Failed to create registry entry: {e}")


def uninstall_native_host() -> tuple[bool, str]:
    """
    Uninstall the native messaging host.

    Returns:
        Tuple of (success, message)
    """
    try:
        messages = []

        # Remove manifest
        manifest_dir = get_native_host_manifest_dir()
        manifest_path = manifest_dir / f"{HOST_NAME}.json"
        if manifest_path.exists():
            manifest_path.unlink()
            messages.append(f"Removed manifest: {manifest_path}")

        # Remove host script
        host_script = get_host_script_path()
        if host_script.exists():
            host_script.unlink()
            messages.append(f"Removed host script: {host_script}")

        # On Windows, remove registry entry
        if platform.system() == "Windows":
            try:
                import winreg

                key_path = f"SOFTWARE\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}"
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
                messages.append("Removed Windows registry entry")
            except FileNotFoundError:
                pass

        if messages:
            return True, "Native host uninstalled:\n" + "\n".join(messages)
        else:
            return True, "Native host was not installed"

    except Exception as e:
        return False, f"Failed to uninstall native host: {e}"


def read_message() -> dict[str, Any] | None:
    """
    Read a message from stdin using native messaging protocol.

    Returns:
        Parsed JSON message or None if stdin is closed or incomplete read
    """
    # Read message length (4 bytes, little-endian)
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None

    message_length = struct.unpack("<I", raw_length)[0]

    # Read message content
    message_bytes = sys.stdin.buffer.read(message_length)
    if len(message_bytes) < message_length:
        return None

    return json.loads(message_bytes.decode("utf-8"))


def send_message(message: dict[str, Any]) -> None:
    """
    Send a message to stdout using native messaging protocol.

    Args:
        message: Dictionary to send as JSON
    """
    encoded = json.dumps(message).encode("utf-8")
    # Write length prefix (4 bytes, little-endian)
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


class NativeHostHandler:
    """Handles messages from the Chrome extension."""

    def __init__(self):
        from .utils import get_config_path

        self.config = ConfigManager(get_config_path())
        self.current_run_id: str | None = None
        self.engineer = None
        self._loop = None

    def handle_status(self, message: dict) -> dict:
        """Handle status check request."""
        from . import __version__

        return {
            "type": "status",
            "connected": True,
            "version": __version__,
            "config_path": str(self.config.config_path),
            "_callbackId": message.get("_callbackId"),
        }

    def handle_save_har(self, message: dict) -> dict:
        """Save HAR data to disk."""
        run_id = message.get("run_id")
        har_data = message.get("har")

        if not run_id or not har_data:
            return {
                "type": "error",
                "message": "Missing run_id or har data",
                "_callbackId": message.get("_callbackId"),
            }

        try:
            har_dir = get_har_dir(run_id)
            har_dir.mkdir(parents=True, exist_ok=True)

            har_path = har_dir / "recording.har"
            # Save without indentation to improve I/O performance and slightly reduce size.
            # Note: If HAR data embeds response bodies, the overall file can still be very large;
            # this function only controls JSON formatting, not how bodies are stored.
            har_path.write_text(json.dumps(har_data, separators=(',', ':')))

            self.current_run_id = run_id

            return {
                "type": "complete",
                "path": str(har_path),
                "_callbackId": message.get("_callbackId"),
            }
        except Exception as e:
            return {
                "type": "error",
                "message": str(e),
                "_callbackId": message.get("_callbackId"),
            }

    def handle_generate(self, message: dict) -> dict:
        """Generate API client from HAR."""
        run_id = message.get("run_id") or self.current_run_id
        model = message.get("model") or self.config.get("claude_code_model")

        if not run_id:
            return {
                "type": "error",
                "message": "No run_id provided and no current session",
                "_callbackId": message.get("_callbackId"),
            }

        # Run the async generation
        try:
            result = self._run_async(self._generate_async(run_id, model, message))
            return result
        except Exception as e:
            return {
                "type": "error",
                "message": str(e),
                "retryable": True,
                "_callbackId": message.get("_callbackId"),
            }

    async def _generate_async(self, run_id: str, model: str, message: dict) -> dict:
        """Async API client generation."""
        # TODO: Add support for OpenCode SDK based on config.get("sdk")
        # Currently only Claude Agent SDK is supported for native host
        from .engineer import ClaudeEngineer
        from .session import SessionManager
        from .utils import get_har_dir, get_scripts_dir

        # Check HAR exists
        har_dir = get_har_dir(run_id)
        har_path = har_dir / "recording.har"

        if not har_path.exists():
            return {
                "type": "error",
                "message": f"HAR file not found: {har_path}",
                "_callbackId": message.get("_callbackId"),
            }

        # Send progress update
        send_message(
            {
                "type": "progress",
                "message": "Analyzing HAR file...",
                "percent": 10,
            }
        )

        # Create engineer
        self.engineer = ClaudeEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt="Generate a Python API client from this HAR capture",
            model=model,
            output_mode="client",
            output_language="python",
            output_dir=str(get_scripts_dir(run_id)),
            verbose=False,  # Don't show TUI output when running as host
        )

        # Progress callback
        def on_progress(percent: int, msg: str):
            send_message(
                {
                    "type": "progress",
                    "message": msg,
                    "percent": percent,
                }
            )

        send_message(
            {
                "type": "progress",
                "message": "Generating API client with Claude...",
                "percent": 30,
            }
        )

        # Run generation
        try:
            result = await self.engineer.analyze_and_generate()

            send_message(
                {
                    "type": "progress",
                    "message": "Generation complete",
                    "percent": 100,
                }
            )

            # Update session
            session = SessionManager()
            session.add_run(
                run_id=run_id,
                prompt="Chrome extension capture",
                url="",
                model=model,
                mode="extension",
                sdk="claude",
                output_mode="client",
            )

            return {
                "type": "complete",
                "script_path": str(get_scripts_dir(run_id)),
                "run_id": run_id,
                "_callbackId": message.get("_callbackId"),
            }

        except Exception as e:
            return {
                "type": "error",
                "message": str(e),
                "retryable": True,
                "_callbackId": message.get("_callbackId"),
            }

    def handle_chat(self, message: dict) -> dict:
        """Handle chat message - streams agent events back to extension."""
        user_message = message.get("message")
        run_id = message.get("run_id") or self.current_run_id

        if not user_message:
            return {
                "type": "error",
                "message": "No message provided",
                "_callbackId": message.get("_callbackId"),
            }

        if not run_id:
            return {
                "type": "error",
                "message": "No active session. Please capture traffic first.",
                "_callbackId": message.get("_callbackId"),
            }

        try:
            result = self._run_async(self._chat_async_streaming(user_message, run_id, message))
            return result
        except Exception as e:
            return {
                "type": "error",
                "message": str(e),
                "_callbackId": message.get("_callbackId"),
            }

    async def _chat_async_streaming(self, user_message: str, run_id: str, message: dict) -> dict:
        """Async chat with streaming of agent events."""
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            ThinkingBlock,
        )
        from .utils import get_har_dir, get_scripts_dir

        har_dir = get_har_dir(run_id)
        har_path = har_dir / "recording.har"

        if not har_path.exists():
            return {
                "type": "error",
                "message": f"No HAR file found. Please capture traffic first.",
                "_callbackId": message.get("_callbackId"),
            }

        model = message.get("model") or self.config.get("claude_code_model") or "claude-sonnet-4-5"
        scripts_dir = get_scripts_dir(run_id)
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # Build the prompt with HAR context
        har_content = har_path.read_text()

        # System prompt for API client generation
        system_context = f"""You are an expert at reverse engineering APIs from HTTP traffic.

The user has captured browser traffic (HAR format) and wants to create a Python API client.

HAR file location: {har_path}
Output directory: {scripts_dir}

When analyzing, focus on:
1. Authentication patterns (cookies, tokens, headers)
2. API endpoints and their purposes
3. Request/response formats
4. Rate limiting or pagination patterns

Generate clean, production-ready Python code with:
- Type hints
- Error handling
- Session management
- Docstrings

The HAR content is available at the path above. Use the Read tool to analyze it.
"""

        options = ClaudeAgentOptions(
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "Glob",
                "Grep",
            ],
            permission_mode="acceptEdits",
            cwd=str(scripts_dir.parent.parent),
            model=model,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                # Send the user message with context
                full_prompt = f"{system_context}\n\nUser request: {user_message}"
                await client.query(full_prompt)

                final_text = ""
                last_tool_name = None

                async for msg in client.receive_response():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                final_text += block.text
                                # Stream text block
                                send_message(
                                    {
                                        "type": "agent_event",
                                        "event_type": "text",
                                        "content": block.text,
                                    }
                                )
                            elif isinstance(block, ThinkingBlock):
                                send_message(
                                    {
                                        "type": "agent_event",
                                        "event_type": "thinking",
                                        "content": block.thinking[:500] + "..." if len(block.thinking) > 500 else block.thinking,
                                    }
                                )
                            elif isinstance(block, ToolUseBlock):
                                last_tool_name = block.name
                                # Stream tool use
                                send_message(
                                    {
                                        "type": "agent_event",
                                        "event_type": "tool_use",
                                        "tool_name": block.name,
                                        "tool_input": self._summarize_tool_input(block.name, block.input),
                                    }
                                )
                            elif isinstance(block, ToolResultBlock):
                                # Stream tool result
                                is_error = block.is_error if block.is_error else False
                                output = ""
                                if hasattr(block, "content"):
                                    output = str(block.content)[:500] if block.content else ""

                                send_message(
                                    {
                                        "type": "agent_event",
                                        "event_type": "tool_result",
                                        "tool_name": last_tool_name or "Tool",
                                        "is_error": is_error,
                                        "output": output + "..." if len(output) >= 500 else output,
                                    }
                                )

                    elif isinstance(msg, ResultMessage):
                        # Final result
                        send_message(
                            {
                                "type": "agent_event",
                                "event_type": "done",
                                "is_error": msg.is_error,
                                "cost": getattr(msg, "total_cost_usd", None),
                                "duration_ms": getattr(msg, "duration_ms", None),
                            }
                        )

                self.current_run_id = run_id

                return {
                    "type": "chat_response",
                    "message": final_text or "Task completed.",
                    "content": final_text or "I've processed your request.",
                    "_callbackId": message.get("_callbackId"),
                }

        except Exception as e:
            send_message(
                {
                    "type": "agent_event",
                    "event_type": "error",
                    "message": str(e),
                }
            )
            return {
                "type": "error",
                "message": str(e),
                "_callbackId": message.get("_callbackId"),
            }

    def _summarize_tool_input(self, tool_name: str, input_data: dict) -> dict:
        """Summarize tool input for display (avoid sending huge payloads)."""
        summary = {}

        if tool_name == "Read":
            summary["file_path"] = input_data.get("file_path", "")
        elif tool_name == "Write":
            summary["file_path"] = input_data.get("file_path", "")
            content = input_data.get("content", "")
            summary["content_length"] = len(content)
            summary["content_preview"] = content[:100] + "..." if len(content) > 100 else content
        elif tool_name == "Bash":
            summary["command"] = input_data.get("command", "")[:200]
        elif tool_name == "Glob":
            summary["pattern"] = input_data.get("pattern", "")
        elif tool_name == "Grep":
            summary["pattern"] = input_data.get("pattern", "")
            summary["path"] = input_data.get("path", "")
        elif tool_name == "Edit":
            summary["file_path"] = input_data.get("file_path", "")
            summary["old_string"] = (
                (input_data.get("old_string", "")[:50] + "...") if len(input_data.get("old_string", "")) > 50 else input_data.get("old_string", "")
            )
        else:
            # Generic summary
            for key, value in input_data.items():
                if isinstance(value, str) and len(value) > 100:
                    summary[key] = value[:100] + "..."
                else:
                    summary[key] = value

        return summary

    def _run_async(self, coro):
        """Run async coroutine in event loop."""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop.run_until_complete(coro)

    def handle_message(self, message: dict) -> dict:
        """Route message to appropriate handler."""
        msg_type = message.get("type")

        handlers = {
            "status": self.handle_status,
            "saveHar": self.handle_save_har,
            "generate": self.handle_generate,
            "chat": self.handle_chat,
        }

        handler = handlers.get(msg_type)
        if handler:
            return handler(message)
        else:
            return {
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
                "_callbackId": message.get("_callbackId"),
            }


def run_host():
    """Main entry point for the native messaging host."""
    handler = NativeHostHandler()

    while True:
        try:
            message = read_message()
            if message is None:
                break

            response = handler.handle_message(message)
            send_message(response)

        except Exception as e:
            # Send error response
            send_message(
                {
                    "type": "error",
                    "message": str(e),
                }
            )


if __name__ == "__main__":
    run_host()
