"""OpenCode SDK implementation for API reverse engineering.

Uses direct httpx calls with correct API format based on OpenCode
TypeScript SDK documentation.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .base_engineer import BaseEngineer
from .opencode_ui import OpenCodeUI

# Enable debug mode with OPENCODE_DEBUG=1
DEBUG = os.environ.get("OPENCODE_DEBUG", "0") == "1"


def debug_log(msg: str):
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] [DEBUG] {msg}")


class OpenCodeEngineer(BaseEngineer):
    """Uses OpenCode AI to analyze HAR files and generate Python API scripts."""

    BASE_URL = "http://127.0.0.1:4096"

    # Map short model names to full Anthropic model IDs
    MODEL_MAP = {
        "sonnet": "claude-sonnet-4-5",
        "opus": "claude-opus-4-5",
        "haiku": "claude-haiku-4-5",
    }

    def __init__(self, *args, **kwargs):
        # Pop OpenCode-specific kwargs before passing to parent class
        self.opencode_provider = kwargs.pop("opencode_provider", "anthropic")
        self.opencode_model = kwargs.pop("opencode_model", "claude-sonnet-4-5")

        super().__init__(*args, **kwargs)

        # Override UI with OpenCode-specific version
        self.opencode_ui = OpenCodeUI(verbose=kwargs.get("verbose", True))
        self.ui = self.opencode_ui  # Ensure base class uses our specialized UI
        self._last_error: str | None = None
        self._session_id: str | None = None
        self._last_event_time = 0.0

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with OpenCode."""
        self.opencode_ui.header(self.run_id, self.prompt, self.opencode_model, self.sdk)
        self.opencode_ui.start_analysis()

        # Save the prompt to messages
        self.message_store.save_prompt(self._build_analysis_prompt())

        try:
            async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=600.0) as client:
                # Health check
                try:
                    health_r = await client.get("/global/health")
                    health_r.raise_for_status()
                    health = health_r.json()
                    self.opencode_ui.health_check(health)
                except Exception as e:
                    debug_log(f"Health check failed: {e}")
                    self.opencode_ui.error(f"OpenCode server not responding. Is it running on {self.BASE_URL}?")
                    return None

                # Create a new session
                r = await client.post("/session", json={})
                r.raise_for_status()
                session_data = r.json()
                self._session_id = session_data["id"]

                self.opencode_ui.session_created(self._session_id)

                # Start event stream BEFORE sending message
                event_task = asyncio.create_task(self._stream_events(client))

                # Give event stream a moment to connect
                await asyncio.sleep(0.1)

                # Send prompt with correct format
                # POST /session/:id/message with model object
                # Resolve short model name to full model ID if needed
                model_id = self.MODEL_MAP.get(self.opencode_model, self.opencode_model)

                prompt_body = {
                    "model": {
                        "providerID": self.opencode_provider,
                        "modelID": model_id,
                    },
                    "parts": [{"type": "text", "text": self._build_analysis_prompt()}],
                }

                prompt_r = await client.post(f"/session/{self._session_id}/message", json=prompt_body)
                prompt_r.raise_for_status()

                # Wait for events to complete
                try:
                    await asyncio.wait_for(event_task, timeout=600.0)
                except TimeoutError:
                    self._last_error = "Session timed out (10 min)"
                    self.opencode_ui.error(self._last_error)

                # Stop streaming UI
                self.opencode_ui.stop_streaming()

                # Check for errors
                if self._last_error:
                    self.opencode_ui.error(self._last_error)
                    self.message_store.save_error(self._last_error)
                    return None

            # Success
            script_path = str(self.scripts_dir / self._get_client_filename())

            # Fetch actual provider and model used from session messages
            try:
                async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0) as client:
                    messages_r = await client.get(f"/session/{self._session_id}/message")
                    if messages_r.status_code == 200:
                        messages = messages_r.json()
                        # Find first assistant message with provider/model info
                        for msg in messages:
                            info = msg.get("info", {})
                            if info.get("role") == "assistant":
                                provider_id = info.get("providerID")
                                model_id = info.get("modelID")
                                if provider_id and model_id:
                                    self.opencode_ui.model_info(provider_id, model_id)
                                    break
            except Exception as e:
                debug_log(f"Failed to fetch session messages: {e}")

            # Show session summary before success message
            self.opencode_ui.session_summary(self.usage_metadata)
            local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
            self.opencode_ui.success(script_path, local_path)

            result_data: dict[str, Any] = {
                "script_path": script_path,
                "usage": self.usage_metadata,
                "session_id": self._session_id,
            }
            self.message_store.save_result(result_data)
            return result_data

        except httpx.ConnectError:
            self.opencode_ui.error("Connection error")
            self.opencode_ui.console.print("\n[dim]Make sure OpenCode is running: opencode[/dim]")
            self.message_store.save_error("Connection error")
            return None

        except Exception as e:
            error_msg = str(e) if str(e) else "Unknown error"
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return None

    async def _stream_events(self, client: httpx.AsyncClient):
        """Stream events from OpenCode and update UI."""
        seen_parts: set = set()  # Track part IDs to avoid duplicates
        import time

        self._last_event_time = time.time()

        debug_log("Starting event stream...")

        # Start the live display
        self.opencode_ui.start_streaming()

        try:
            debug_log("Connecting to GET /event")
            async with client.stream("GET", "/event", timeout=None) as response:
                debug_log(f"Event stream connected, status={response.status_code}")
                async for line in response.aiter_lines():
                    if not line:
                        continue

                    # SSE format: "data: {...}"
                    if not line.startswith("data: "):
                        if line.startswith("data:"):
                            line_data = line[5:].strip()
                        else:
                            debug_log(f"Skipping non-data line: {line[:50]}")
                            continue
                    else:
                        line_data = line[6:].strip()

                    if not line_data:
                        continue

                    self._last_event_time = time.time()

                    try:
                        data = json.loads(line_data)
                    except json.JSONDecodeError as e:
                        error_str = str(e)
                        # Check if this is a buffer size error
                        if "buffer size" in error_str.lower() or "1048576" in error_str or "exceeded maximum buffer" in error_str.lower():
                            debug_log(f"Buffer size error detected: {e}")
                            self._last_error = (
                                "Screenshot too large (exceeds 1MB limit). Try element-specific screenshots instead of full-page screenshots."
                            )
                            self.opencode_ui.error(self._last_error)
                            self.opencode_ui.console.print(
                                "[dim]Tip: Use browser_snapshot() for page structure or take smaller, element-specific screenshots.[/dim]"
                            )
                            # Don't continue - this is a fatal error for the session
                            return
                        debug_log(f"JSON decode error: {e}, data: {line_data[:100]}")
                        continue

                    event_type = data.get("type")
                    properties = data.get("properties", {})

                    debug_log(f"Event: {event_type}")

                    # Handle different event types
                    if event_type == "message.part.updated":
                        await self._handle_part_update(properties, seen_parts)

                    elif event_type == "session.idle":
                        event_sid = properties.get("sessionID")
                        debug_log(f"session.idle: sessionID={event_sid}, our session={self._session_id}")
                        if event_sid == self._session_id:
                            debug_log("Our session is idle, returning!")
                            self.opencode_ui.session_status("idle")
                            return  # Done!

                    elif event_type == "session.status":
                        event_sid = properties.get("sessionID")
                        status = properties.get("status", {})
                        status_type = status.get("type", "idle")
                        debug_log(f"session.status: sessionID={event_sid}, status={status_type}")
                        if event_sid == self._session_id:
                            if status_type == "retry":
                                attempt = status.get("attempt", 1)
                                message = status.get("message", "")
                                self.opencode_ui.session_retry(attempt, message)
                            else:
                                self.opencode_ui.session_status(status_type)

                            if status_type == "idle":
                                debug_log("Our session status is idle, returning!")
                                return  # Done!

                    elif event_type == "permission.updated":
                        # Auto-approve permissions so the agent can proceed
                        permission_id = properties.get("id")
                        perm_session = properties.get("sessionID")
                        perm_type = properties.get("type", "")
                        perm_title = properties.get("title", "")

                        debug_log(f"permission.updated: id={permission_id}, type={perm_type}, title={perm_title}")

                        if perm_session == self._session_id and permission_id:
                            # Show permission request in UI
                            self.opencode_ui.permission_requested(perm_type, perm_title)

                            # Auto-approve the permission
                            # OpenCode expects: "once" | "always" | "reject"
                            debug_log(f"Auto-approving permission {permission_id}")
                            try:
                                perm_response = await client.post(
                                    f"/session/{self._session_id}/permissions/{permission_id}",
                                    json={"response": "always"},  # "once", "always", or "reject"
                                )
                                debug_log(f"Permission response: {perm_response.status_code}")
                                if perm_response.status_code == 200:
                                    self.opencode_ui.permission_approved(perm_type)
                            except Exception as pe:
                                debug_log(f"Permission approval failed: {pe}")

                    elif event_type == "todo.updated":
                        todos = properties.get("todos", [])
                        event_sid = properties.get("sessionID")
                        if event_sid == self._session_id and todos:
                            debug_log(f"todo.updated: {len(todos)} todos")
                            self.opencode_ui.todo_updated(todos)

                    elif event_type == "file.edited":
                        file_path = properties.get("file", "")
                        if file_path:
                            debug_log(f"file.edited: {file_path}")
                            self.opencode_ui.file_edited(file_path)

                    elif event_type == "session.diff":
                        event_sid = properties.get("sessionID")
                        diffs = properties.get("diff", [])
                        if event_sid == self._session_id and diffs:
                            debug_log(f"session.diff: {len(diffs)} files changed")
                            self.opencode_ui.session_diff(diffs)

                    elif event_type == "session.compacted":
                        event_sid = properties.get("sessionID")
                        if event_sid == self._session_id:
                            debug_log("session.compacted")
                            self.opencode_ui.session_compacted()

                    elif event_type == "session.error":
                        event_sid = properties.get("sessionID")
                        if event_sid and event_sid != self._session_id:
                            debug_log(f"session.error for other session {event_sid}, ignoring")
                            continue

                        error_obj = properties.get("error", {})
                        debug_log(f"session.error: {error_obj}")

                        # Parse error with type-specific handling
                        if isinstance(error_obj, dict):
                            error_name = error_obj.get("name", "UnknownError")
                            error_data = error_obj.get("data", {})

                            if error_name == "ProviderAuthError":
                                provider = error_data.get("providerID", "unknown")
                                msg = error_data.get("message", "Authentication failed")
                                self._last_error = f"Auth error ({provider}): {msg}"
                            elif error_name == "APIError":
                                msg = error_data.get("message", "API error")
                                status = error_data.get("statusCode", "")
                                self._last_error = f"API error{' (' + str(status) + ')' if status else ''}: {msg}"
                            elif error_name == "MessageAbortedError":
                                self._last_error = "Aborted"
                            else:
                                msg = error_data.get("message", "") if isinstance(error_data, dict) else str(error_data)
                                self._last_error = f"{error_name}: {msg}" if msg else error_name
                        else:
                            self._last_error = str(error_obj)

                        self.opencode_ui.error(self._last_error)
                        return

        except httpx.ReadError as e:
            self._last_error = f"Stream disconnected: {e}"
        except Exception as e:
            self._last_error = str(e) if str(e) else "Stream error"

    async def _handle_part_update(self, properties: dict, seen_parts: set):
        """Handle message.part.updated events."""
        part = properties.get("part", {})
        delta = properties.get("delta")  # Incremental text update

        part_id = part.get("id", "")
        part_type = part.get("type")
        part_session = part.get("sessionID")

        # Only process parts for our session
        if part_session != self._session_id:
            return

        if part_type == "text":
            text = part.get("text", "")
            debug_log(f"Handling text part: id={part_id}, delta={'yes' if delta else 'no'}, len={len(text)}")
            # Use delta for incremental updates if available
            self.opencode_ui.update_text(text, delta)

            # Save to message store (only significant updates)
            if len(text) > 50 and part_id not in seen_parts:
                seen_parts.add(part_id)
                self.message_store.save_thinking(text)

        elif part_type == "tool":
            tool_name = part.get("tool", "tool")
            state = part.get("state", {})
            status = state.get("status")

            debug_log(f"Handling tool part: id={part_id}, tool={tool_name}, status={status}")

            if status == "running" and part_id not in seen_parts:
                seen_parts.add(part_id)
                tool_input = state.get("input", {})
                self.opencode_ui.tool_start(tool_name, tool_input)
                self.message_store.save_tool_start(tool_name, tool_input)

            elif status == "completed":
                output = state.get("output", "")
                self.opencode_ui.tool_result(tool_name, False, output)
                self.message_store.save_tool_result(tool_name, False, output)

            elif status == "error":
                error = state.get("error", "Tool error")
                self.opencode_ui.tool_result(tool_name, True, error)
                self.message_store.save_tool_result(tool_name, True, error)

        elif part_type == "step-finish":
            debug_log("Handling step-finish part")
            # Extract usage stats
            api_cost = part.get("cost", 0)
            tokens = part.get("tokens", {})

            input_tokens = tokens.get("input", 0)
            output_tokens = tokens.get("output", 0)
            reasoning_tokens = tokens.get("reasoning", 0)
            cache = tokens.get("cache", {})
            cache_read = cache.get("read", 0)
            cache_write = cache.get("write", 0)

            if api_cost == 0 and (input_tokens > 0 or output_tokens > 0):
                from .pricing import calculate_cost

                calculated_cost = calculate_cost(
                    model_id=self.opencode_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_tokens=cache_write,
                    cache_read_tokens=cache_read,
                    reasoning_tokens=reasoning_tokens,
                )
                cost = calculated_cost
                debug_log(f"API cost was 0, calculated locally: ${cost:.4f}")
            else:
                cost = api_cost

            self.usage_metadata["input_tokens"] = self.usage_metadata.get("input_tokens", 0) + input_tokens
            self.usage_metadata["output_tokens"] = self.usage_metadata.get("output_tokens", 0) + output_tokens
            self.usage_metadata["reasoning_tokens"] = self.usage_metadata.get("reasoning_tokens", 0) + reasoning_tokens
            self.usage_metadata["cache_read_tokens"] = self.usage_metadata.get("cache_read_tokens", 0) + cache_read
            self.usage_metadata["cache_creation_tokens"] = self.usage_metadata.get("cache_creation_tokens", 0) + cache_write
            self.usage_metadata["cost"] = self.usage_metadata.get("cost", 0) + cost


def run_opencode_engineering(
    run_id: str,
    har_path: Path,
    prompt: str,
    model: str | None = None,
    additional_instructions: str | None = None,
    output_dir: str | None = None,
    verbose: bool = True,
    opencode_provider: str | None = None,
    opencode_model: str | None = None,
) -> dict[str, Any] | None:
    """Synchronous wrapper for OpenCode reverse engineering."""
    engineer = OpenCodeEngineer(
        run_id=run_id,
        har_path=har_path,
        prompt=prompt,
        model=model,
        additional_instructions=additional_instructions,
        output_dir=output_dir,
        verbose=verbose,
        opencode_provider=opencode_provider,
        opencode_model=opencode_model,
    )
    return asyncio.run(engineer.analyze_and_generate())
