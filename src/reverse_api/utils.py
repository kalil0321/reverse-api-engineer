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
        # Check if event loop is already running (e.g., called from async context)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in async context, use fallback to avoid nested asyncio.run
            return _slugify(prompt)

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
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        TextBlock,
    )

    # Suppress claude_agent_sdk logs
    logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
    logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(logging.WARNING)

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


async def _generate_folder_name_opencode_async(prompt: str, session_id: str = None) -> str:
    """Async helper to generate folder name using OpenCode API with event streaming.

    Args:
        prompt: The task prompt to generate a folder name for
        session_id: Optional existing session ID to reuse. If None, creates a new session.
    """
    import json

    import httpx

    from .config import ConfigManager

    BASE_URL = "http://127.0.0.1:4096"

    # Get config for provider and model
    config_manager = ConfigManager(get_config_path())
    opencode_provider = config_manager.get("opencode_provider", "anthropic")
    opencode_model = config_manager.get("opencode_model", "claude-opus-4-5")

    folder_prompt = (
        f"Generate a short folder name (1-3 words, lowercase, underscores) for this task: {prompt}\n\n"
        f"Respond with ONLY the folder name, nothing else. Example: apple_jobs_api"
    )

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        try:
            await client.get("/global/health")
        except Exception as e:
            raise Exception("OpenCode server not responding") from e

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
            except TimeoutError:
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


def parse_engineer_prompt(input_text: str, session_manager=None) -> dict:
    """Parse engineer mode input for tags.

    Args:
        input_text: The raw input text to parse
        session_manager: Optional SessionManager to resolve latest run_id when needed

    Returns:
        dict: {
            "run_id": str | None,
            "fresh": bool,
            "docs": bool,
            "prompt": str,
            "is_tag_command": bool,
            "error": str | None  # Error message if validation failed
        }
    """
    if not input_text:
        return {
            "run_id": None,
            "fresh": False,
            "docs": False,
            "prompt": "",
            "is_tag_command": False,
            "error": None,
        }

    # Check for standalone @docs first (no prompt parameter)
    if input_text.strip() == "@docs":
        # Resolve latest run if session_manager provided
        run_id = None
        error = None
        if session_manager:
            latest_runs = session_manager.get_history(limit=1)
            if not latest_runs:
                error = "no runs found in history"
            else:
                run_id = latest_runs[0]["run_id"]

        return {
            "run_id": run_id,
            "fresh": False,
            "docs": True,
            "prompt": "",
            "is_tag_command": True,
            "error": error,
        }

    # Enhanced regex for @id <run_id> [--fresh] [@docs] <prompt>
    # Group 1: run_id
    # Group 2: fresh flag (optional)
    # Group 3: docs flag (optional)
    # Group 4: prompt (optional)
    pattern = r"@id\s+([a-zA-Z0-9-_]+)(?:\s+(--fresh))?(?:\s+(@docs))?(?:\s+(.*))?"
    match = re.match(pattern, input_text.strip())

    if match:
        run_id = match.group(1)
        fresh = bool(match.group(2))
        docs = bool(match.group(3))
        remaining_prompt = match.group(4) or ""
        return {
            "run_id": run_id,
            "fresh": fresh,
            "docs": docs,
            "prompt": remaining_prompt,
            "is_tag_command": True,
            "error": None,
        }

    # Implicit mode - resolve latest run if session_manager provided
    run_id = None
    error = None
    if session_manager:
        latest_runs = session_manager.get_history(limit=1)
        if not latest_runs:
            error = "no runs found in history"
        else:
            run_id = latest_runs[0]["run_id"]

    return {
        "run_id": run_id,
        "fresh": False,
        "docs": False,
        "prompt": input_text.strip(),
        "is_tag_command": False,
        "error": error,
    }


def parse_record_only_tag(prompt: str) -> tuple[str, bool]:
    """Parse @record-only tag from prompt.

    When present, skips reverse engineering and only records HAR.

    Args:
        prompt: The user prompt that may contain @record-only tag

    Returns:
        tuple: (cleaned_prompt, is_record_only)
    """
    if not prompt:
        return "", False

    # Match @record-only anywhere in the prompt (case-insensitive)
    pattern = r"@record-only\s*"
    if re.search(pattern, prompt, re.IGNORECASE):
        cleaned = re.sub(pattern, "", prompt, flags=re.IGNORECASE).strip()
        return cleaned, True
    return prompt, False


def parse_codegen_tag(prompt: str) -> tuple[str, bool]:
    """Parse @codegen tag from prompt.

    When present, records actions and generates Playwright script instead of API client.

    Returns:
        tuple: (cleaned_prompt, is_codegen)
    """
    if not prompt:
        return "", False

    pattern = r"@codegen\s*"
    if re.search(pattern, prompt, re.IGNORECASE):
        cleaned = re.sub(pattern, "", prompt, flags=re.IGNORECASE).strip()
        return cleaned, True
    return prompt, False


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
    """Get the HAR directory for a specific run.

    Args:
        run_id: Run identifier (must be alphanumeric with hyphens/underscores only)
        output_dir: Optional custom output directory

    Returns:
        Path to the HAR directory

    Raises:
        ValueError: If run_id contains invalid characters or attempts path traversal
    """
    # Validate run_id to prevent path traversal attacks
    if not run_id:
        raise ValueError("run_id cannot be empty")

    # Allow alphanumeric characters, hyphens, and underscores
    # Chrome extension IDs start with crx- followed by UUID-style format
    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        raise ValueError(
            f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed"
        )

    # Limit length to prevent extremely long paths
    if len(run_id) > 64:
        raise ValueError(f"run_id too long: {len(run_id)} characters (max 64)")

    base_dir = get_base_output_dir(output_dir)
    har_dir = base_dir / "har" / run_id

    # Verify the resolved path is within the base directory (defense in depth)
    try:
        har_dir_resolved = har_dir.resolve()
        base_dir_resolved = base_dir.resolve()
        if not har_dir_resolved.is_relative_to(base_dir_resolved):
            raise ValueError(f"Path traversal detected: {run_id}")
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path for run_id {run_id}: {e}") from e

    har_dir.mkdir(parents=True, exist_ok=True)
    return har_dir


def get_actions_path(run_id: str, output_dir: str | None = None) -> Path:
    """Get the actions JSON file path for a specific run."""
    har_dir = get_har_dir(run_id, output_dir)
    return har_dir / "actions.json"


def get_scripts_dir(run_id: str, output_dir: str | None = None) -> Path:
    """Get the scripts directory for a specific run.

    Args:
        run_id: Run identifier (must be alphanumeric with hyphens/underscores only)
        output_dir: Optional custom output directory

    Returns:
        Path to the scripts directory

    Raises:
        ValueError: If run_id contains invalid characters or attempts path traversal
    """
    # Validate run_id to prevent path traversal attacks
    if not run_id:
        raise ValueError("run_id cannot be empty")

    # Allow alphanumeric characters, hyphens, and underscores
    # Chrome extension IDs start with crx- followed by UUID-style format
    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        raise ValueError(
            f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed"
        )

    # Limit length to prevent extremely long paths
    if len(run_id) > 64:
        raise ValueError(f"run_id too long: {len(run_id)} characters (max 64)")

    base_dir = get_base_output_dir(output_dir)
    scripts_dir = base_dir / "scripts" / run_id

    # Verify the resolved path is within the base directory (defense in depth)
    try:
        scripts_dir_resolved = scripts_dir.resolve()
        base_dir_resolved = base_dir.resolve()
        if not scripts_dir_resolved.is_relative_to(base_dir_resolved):
            raise ValueError(f"Path traversal detected: {run_id}")
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path for run_id {run_id}: {e}") from e

    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def get_docs_dir(run_id: str, output_dir: str | None = None) -> Path:
    """Get the docs directory for a specific run.

    Args:
        run_id: Run identifier (must be alphanumeric with hyphens/underscores only)
        output_dir: Optional custom output directory

    Returns:
        Path to the docs directory

    Raises:
        ValueError: If run_id contains invalid characters or attempts path traversal
    """
    # Validate run_id to prevent path traversal attacks
    if not run_id:
        raise ValueError("run_id cannot be empty")

    # Allow alphanumeric characters, hyphens, and underscores
    # Chrome extension IDs start with crx- followed by UUID-style format
    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        raise ValueError(
            f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed"
        )

    # Limit length to prevent extremely long paths
    if len(run_id) > 64:
        raise ValueError(f"run_id too long: {len(run_id)} characters (max 64)")

    base_dir = get_base_output_dir(output_dir)
    docs_dir = base_dir / "docs" / run_id

    # Verify the resolved path is within the base directory (defense in depth)
    try:
        docs_dir_resolved = docs_dir.resolve()
        base_dir_resolved = base_dir.resolve()
        if not docs_dir_resolved.is_relative_to(base_dir_resolved):
            raise ValueError(f"Path traversal detected: {run_id}")
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid path for run_id {run_id}: {e}") from e

    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir


def get_messages_path(run_id: str, output_dir: str | None = None) -> Path:
    """Get the messages file path for a specific run."""
    base_dir = get_base_output_dir(output_dir)
    messages_dir = base_dir / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    return messages_dir / f"{run_id}.jsonl"


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def get_collected_dir(folder_name: str) -> Path:
    """Get ./collected/{folder_name}/ directory for collector mode output.

    Args:
        folder_name: Name of the collection folder

    Returns:
        Path to the collection output directory
    """
    path = Path.cwd() / "collected" / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path
