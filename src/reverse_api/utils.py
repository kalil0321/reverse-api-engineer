"""Utility functions for run ID generation and path management."""

import asyncio
import platform
import re
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from . import __version__


def check_for_updates() -> str | None:
    """Check PyPI for newer version.

    Returns:
        Update message if newer version available, None otherwise.
    """
    try:
        response = httpx.get(
            "https://pypi.org/pypi/reverse-api-engineer/json",
            timeout=2.0,
        )
        if response.status_code == 200:
            latest = response.json()["info"]["version"]
            if latest != __version__:
                return f"update available: {__version__} → {latest}  (pip install -U reverse-api-engineer | uv tool upgrade reverse-api-engineer)"
    except Exception:
        pass
    return None


def generate_folder_name(prompt: str, sdk: str = None, session_id: str = None) -> str:
    """Generate a clean folder name from a prompt.

    Uses Claude Agent SDK (for Claude SDK) or OpenCode API (for OpenCode SDK)
    to generate a short, descriptive name. Falls back to simple slugification if API call fails.

    Args:
        prompt: The task prompt to generate a folder name for
        sdk: The SDK to use ("opencode", "claude", or "cursor"). If None, checks config.
        session_id: Optional OpenCode session ID to reuse. Only used when sdk="opencode".
    """
    from rich.console import Console
    from rich.status import Status

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

        console = Console()
        with Status(" [dim]generating folder name...[/dim]", console=console, spinner="dots", spinner_style="dim"):
            if sdk == "opencode":
                return asyncio.run(_generate_folder_name_opencode_async(prompt, session_id))
            if sdk == "cursor":
                return _slugify(prompt)
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

    from .prompts import FOLDER_NAME_PROMPT

    async with ClaudeSDKClient(options=options) as client:
        await client.query(FOLDER_NAME_PROMPT.format(prompt=prompt))

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
    opencode_model = config_manager.get("opencode_model", "claude-opus-4-6")

    from .prompts import FOLDER_NAME_PROMPT

    folder_prompt = FOLDER_NAME_PROMPT.format(prompt=prompt)

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
        raise ValueError(f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed")

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
        raise ValueError(f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed")

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
        raise ValueError(f"Invalid run_id: {run_id}. Only alphanumeric characters, hyphens, and underscores are allowed")

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


def get_downloads_dir() -> Path:
    """Get the user's Downloads folder path (cross-platform).

    Returns:
        Path to the Downloads directory
    """
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        # Windows: Use USERPROFILE environment variable
        import os

        user_profile = os.environ.get("USERPROFILE", str(home))
        downloads = Path(user_profile) / "Downloads"
    elif system == "Darwin":  # macOS
        downloads = home / "Downloads"
    else:  # Linux and others
        downloads = home / "Downloads"

    # Fallback to home/Downloads if the standard location doesn't exist
    if not downloads.exists():
        downloads = home / "Downloads"

    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def sanitize_domain(domain: str) -> str:
    """Clean domain name for use in folder names.

    Args:
        domain: Raw domain (e.g., "api.github.com", "www.example.com")

    Returns:
        Clean domain string (e.g., "api_github_com", "example_com")
    """
    # Remove www. prefix
    domain = re.sub(r"^www\.", "", domain)
    # Remove common TLDs for cleaner names
    domain = re.sub(r"\.(com|org|net|io|co|app|dev)$", "", domain)
    # Replace dots and other invalid chars with underscores
    domain = re.sub(r"[^a-zA-Z0-9]", "_", domain)
    # Collapse multiple underscores
    domain = re.sub(r"_+", "_", domain)
    # Strip leading/trailing underscores
    domain = domain.strip("_")
    return domain.lower()[:50]  # Limit length


def get_visible_save_path(domain: str, base_dir: Path | str, suffix: int = 0) -> Path:
    """Generate a visible save path with unique naming.

    Creates folder names like: rae_github_com_2025-02-02
    If folder exists and has content, appends _1, _2, etc.

    Args:
        domain: Domain name (will be sanitized)
        base_dir: Base directory (e.g., Downloads or custom path)
        suffix: Current suffix number for recursion (start with 0)

    Returns:
        Path object ready for use (directory created)
    """
    if isinstance(base_dir, str):
        base_dir = Path(base_dir)

    # Sanitize domain
    clean_domain = sanitize_domain(domain)
    if not clean_domain:
        clean_domain = "unknown"

    # Get current date
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Build folder name
    suffix_str = f"_{suffix}" if suffix > 0 else ""
    folder_name = f"rae_{clean_domain}_{date_str}{suffix_str}"

    # Build full path
    path = base_dir / folder_name

    # Check if exists and has content (non-empty)
    if path.exists() and any(path.iterdir()):
        # Recursively try next suffix
        return get_visible_save_path(domain, base_dir, suffix + 1)

    # Create directory
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_run(identifier: str, session_manager) -> dict:
    """Resolve a run by exact ID or fuzzy prompt/folder name match.

    Args:
        identifier: Run ID (12-char hex) or search term to fuzzy match
        session_manager: SessionManager instance to search history

    Returns:
        The matching run dict

    Raises:
        click.ClickException: If no match or ambiguous match without TTY
    """
    import click
    import questionary

    # 1. Try exact run_id match
    run = session_manager.get_run(identifier)
    if run:
        return run

    # 2. Fuzzy match against prompt and folder names
    identifier_lower = identifier.lower()
    matches = []
    for run in session_manager.history:
        prompt = (run.get("prompt") or "").lower()
        run_id = run.get("run_id", "")
        # Also check the script folder name from paths
        script_path = run.get("paths", {}).get("script_path", "")
        folder_name = Path(script_path).parent.name if script_path else ""

        if identifier_lower in prompt or identifier_lower in folder_name.lower() or identifier_lower in run_id:
            matches.append(run)

    if not matches:
        raise click.ClickException(
            f"No run matching '{identifier}'. Use 'reverse-api-engineer list' to see available runs."
        )

    if len(matches) == 1:
        return matches[0]

    # Multiple matches — show picker
    choices = []
    for m in matches:
        prompt_preview = (m.get("prompt") or "")[:50]
        ts = (m.get("timestamp") or "")[:19]
        label = f"{m['run_id']}  {ts}  {prompt_preview}"
        choices.append(questionary.Choice(title=label, value=m))

    selected = questionary.select(
        f"Multiple runs match '{identifier}':",
        choices=choices,
    ).ask()

    if selected is None:
        raise click.Abort()

    return selected


def discover_scripts(run_id: str, output_dir: str | None = None, run_metadata: dict | None = None) -> list[Path]:
    """Find all executable Python scripts in a run's script directory.

    Tries the stored script path from run metadata first, then falls back
    to the current output_dir config.

    Args:
        run_id: The run identifier
        output_dir: Optional custom output directory
        run_metadata: Optional run dict with paths.script_path to resolve from

    Returns:
        Sorted list of .py file Paths (excludes __pycache__, .venv, __init__.py)

    Raises:
        ValueError: If run_id contains invalid characters
    """
    # Validate run_id (same rules as get_scripts_dir)
    if not run_id:
        raise ValueError("run_id cannot be empty")
    if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
        raise ValueError(f"Invalid run_id: {run_id}")
    if len(run_id) > 64:
        raise ValueError(f"run_id too long: {len(run_id)} characters (max 64)")

    # Try stored path from run metadata first
    scripts_dir = None
    if run_metadata:
        script_path = run_metadata.get("paths", {}).get("script_path", "")
        if script_path:
            stored_dir = Path(script_path).parent
            if stored_dir.exists():
                scripts_dir = stored_dir

    # Fall back to current output_dir
    if scripts_dir is None:
        base_dir = get_base_output_dir(output_dir)
        scripts_dir = base_dir / "scripts" / run_id

    if not scripts_dir.exists():
        return []

    exclude_dirs = {"__pycache__", ".venv"}
    exclude_files = {"__init__.py"}

    scripts = []
    for f in scripts_dir.iterdir():
        if f.is_file() and f.suffix == ".py" and f.name not in exclude_files:
            scripts.append(f)
    scripts = [s for s in scripts if not any(part in exclude_dirs for part in s.parts)]

    return sorted(scripts, key=lambda p: p.name)


def extract_domain_from_har(har_path: Path) -> str | None:
    """Extract the primary domain from a HAR file.

    Args:
        har_path: Path to the HAR file

    Returns:
        Domain string or None if extraction fails
    """
    try:
        import json

        with open(har_path) as f:
            har_data = json.load(f)

        entries = har_data.get("log", {}).get("entries", [])
        if not entries:
            return None

        # Get domain from first entry's URL
        first_url = entries[0].get("request", {}).get("url", "")
        if first_url:
            from urllib.parse import urlparse

            parsed = urlparse(first_url)
            return parsed.netloc

        return None
    except Exception:
        return None
