"""Utility functions for run ID generation and path management."""

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path


def generate_folder_name(prompt: str, sdk: str = None, session_id: str = None) -> str:
    """Generate a clean folder name from a prompt.

    Uses Claude Agent SDK (for Claude SDK) or OpenCode API (for OpenCode SDK)
    to generate a short, descriptive name. Falls back to simple slugification if API call fails.

    Args:
        prompt: The task prompt to generate a folder name for
        sdk: The SDK to use ("opencode" or "claude"). If None, checks config.
        session_id: Optional OpenCode session ID to reuse. Only used when sdk="opencode".
    """
    # Get SDK from config if not provided
    if sdk is None:
        try:
            from .config import ConfigManager

            config_manager = ConfigManager(get_config_path())
            sdk = config_manager.get("sdk", "claude")
        except Exception:
            sdk = "claude"

    try:
        if sdk == "opencode":
            return asyncio.run(_generate_folder_name_opencode_async(prompt, session_id))
        else:
            return asyncio.run(_generate_folder_name_async(prompt))
    except Exception:
        pass

    # Fallback: simple slugify
    return _slugify(prompt)


async def _generate_folder_name_async(prompt: str) -> str:
    """Async helper to generate folder name using Claude Agent SDK."""
    import logging
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
    )

    # Suppress claude_agent_sdk logs
    logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
    logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(
        logging.WARNING
    )

    options = ClaudeAgentOptions(
        allowed_tools=[],  # No tools needed for simple text generation
        permission_mode="dontAsk",
        model="claude-haiku-4-5",
    )

    folder_name = ""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            f"Generate a short folder name (1-3 words, lowercase, underscores) for this task: {prompt}\n\n"
            f"Respond with ONLY the folder name, nothing else. Example: apple_jobs_api"
        )

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        folder_name = block.text.strip().lower()
                        break

    # Clean up the name to be filesystem-safe
    name = re.sub(r"[^a-z0-9_]", "_", folder_name)
    name = re.sub(r"_+", "_", name)  # Collapse multiple underscores
    name = name.strip("_")[:50]  # Limit length

    return name if name else _slugify(prompt)


async def _generate_folder_name_opencode_async(
    prompt: str, session_id: str = None
) -> str:
    """Async helper to generate folder name using OpenCode API with event streaming.

    Args:
        prompt: The task prompt to generate a folder name for
        session_id: Optional existing session ID to reuse. If None, creates a new session.
    """
    import httpx
    import json
    from .config import ConfigManager

    BASE_URL = "http://127.0.0.1:4096"

    # Get config for provider and model
    config_manager = ConfigManager(get_config_path())
    opencode_provider = config_manager.get("opencode_provider", "anthropic")
    opencode_model = config_manager.get("opencode_model", "claude-sonnet-4-5")

    folder_prompt = (
        f"Generate a short folder name (1-3 words, lowercase, underscores) for this task: {prompt}\n\n"
        f"Respond with ONLY the folder name, nothing else. Example: apple_jobs_api"
    )

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        try:
            await client.get("/global/health")
        except Exception:
            raise Exception("OpenCode server not responding")

        session_created = False
        if session_id is None:
            session_r = await client.post("/session", json={})
            session_r.raise_for_status()
            session_id = session_r.json()["id"]
            session_created = True

        try:
            event_complete = asyncio.Event()

            async def stream_events():
                """Stream events and wait for session.idle."""
                try:
                    async with client.stream("GET", "/event", timeout=None) as response:
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue

                            try:
                                data = json.loads(line[6:].strip())
                                event_type = data.get("type")
                                properties = data.get("properties", {})

                                if event_type == "session.idle":
                                    if properties.get("sessionID") == session_id:
                                        event_complete.set()
                                        return
                                elif event_type == "session.status":
                                    if properties.get("sessionID") == session_id:
                                        status = properties.get("status", {})
                                        if status.get("type") == "idle":
                                            event_complete.set()
                                            return
                            except (json.JSONDecodeError, KeyError):
                                continue
                except Exception:
                    # If streaming fails, set event to allow fallback
                    event_complete.set()

            event_task = asyncio.create_task(stream_events())

            await asyncio.sleep(0.1)

            await client.post(
                f"/session/{session_id}/message",
                json={
                    "model": {
                        "providerID": opencode_provider,
                        "modelID": opencode_model,
                    },
                    "parts": [{"type": "text", "text": folder_prompt}],
                },
            )

            try:
                await asyncio.wait_for(event_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass  # Fall through to fetch messages anyway

            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass

            messages_r = await client.get(f"/session/{session_id}/message")
            if messages_r.status_code == 200:
                messages = messages_r.json()
                for msg in reversed(messages):
                    info = msg.get("info", {})
                    if info.get("role") == "assistant":
                        parts = msg.get("parts", [])
                        for part in parts:
                            if part.get("type") == "text":
                                folder_name = part.get("text", "").strip().lower()
                                if folder_name:
                                    name = re.sub(r"[^a-z0-9_]", "_", folder_name)
                                    name = re.sub(r"_+", "_", name)
                                    name = name.strip("_")[:50]
                                    return name if name else _slugify(prompt)
        finally:
            # Only clean up session if we created it
            if session_created:
                try:
                    await client.delete(f"/session/{session_id}")
                except Exception:
                    pass

    return _slugify(prompt)


def _slugify(text: str) -> str:
    """Simple slugify fallback - converts text to a filesystem-safe name."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    words = text.split("_")[:3]  # Take first 3 words
    return "_".join(words)[:50]


def generate_run_id() -> str:
    """Generate a unique run ID using a short UUID format."""
    return uuid.uuid4().hex[:12]


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_app_dir() -> Path:
    """Get the central application data directory."""
    app_dir = Path.home() / ".reverse-api"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    """Get the path to the config file."""
    return get_app_dir() / "config.json"


def get_history_path() -> Path:
    """Get the path to the history file."""
    return get_app_dir() / "history.json"


def get_base_output_dir(output_dir: str | None = None) -> Path:
    """Get the base directory for outputs (HARs and scripts)."""
    if output_dir:
        return Path(output_dir)
    return get_app_dir() / "runs"


def get_har_dir(run_id: str, output_dir: str | None = None) -> Path:
    """Get the HAR directory for a specific run."""
    base_dir = get_base_output_dir(output_dir)
    har_dir = base_dir / "har" / run_id
    har_dir.mkdir(parents=True, exist_ok=True)
    return har_dir


def get_scripts_dir(run_id: str, output_dir: str | None = None) -> Path:
    """Get the scripts directory for a specific run."""
    base_dir = get_base_output_dir(output_dir)
    scripts_dir = base_dir / "scripts" / run_id
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def get_messages_path(run_id: str, output_dir: str | None = None) -> Path:
    """Get the messages file path for a specific run."""
    base_dir = get_base_output_dir(output_dir)
    messages_dir = base_dir / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    return messages_dir / f"{run_id}.jsonl"


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()
