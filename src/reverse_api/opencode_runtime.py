"""OpenCode server discovery and managed startup.

Reverse API Engineer reuses an already-running OpenCode server when possible.
When the configured local server is unavailable, it can start the latest npm
release through ``npx`` and keep that process alive for the current RAE run.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .utils import get_config_path

DEFAULT_OPENCODE_BASE_URL = "http://127.0.0.1:4096"
DEFAULT_OPENCODE_PACKAGE = "opencode-ai@latest"
_START_TIMEOUT_SECONDS = 120.0

_PROCESS: subprocess.Popen[bytes] | None = None
_PROCESS_URL: str | None = None
_PROCESS_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


class OpenCodeSetupError(RuntimeError):
    """Raised when a local OpenCode server cannot be prepared."""


@dataclass(frozen=True)
class OpenCodeServerStatus:
    """Result of locating or starting the OpenCode server."""

    health: dict[str, Any]
    started: bool = False
    package: str | None = None


def _config_manager_snapshot() -> dict[str, Any]:
    """Load config defaults merged with the user's RAE config."""

    try:
        from .config import ConfigManager

        return ConfigManager(get_config_path()).config.copy()
    except Exception:
        return {}


def opencode_base_url() -> str:
    """Return the OpenCode server URL, with an environment override."""

    env = os.environ.get("OPENCODE_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    configured = str(_config_manager_snapshot().get("opencode_base_url") or DEFAULT_OPENCODE_BASE_URL)
    return configured.rstrip("/")


def opencode_npx_package() -> str:
    """Return the npm package used for managed OpenCode startup."""

    env = os.environ.get("RAE_OPENCODE_PACKAGE", "").strip()
    if env:
        return env
    return str(_config_manager_snapshot().get("opencode_npx_package") or DEFAULT_OPENCODE_PACKAGE)


def opencode_auto_start() -> bool:
    """Return whether RAE may start OpenCode when no server is listening."""

    env = os.environ.get("RAE_OPENCODE_AUTO_START")
    if env is not None:
        return env.strip().lower() not in {"0", "false", "no", "off"}
    return bool(_config_manager_snapshot().get("opencode_auto_start", True))


def _server_address(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    if parsed.scheme != "http" or not host or parsed.path not in {"", "/"}:
        raise OpenCodeSetupError(f"Cannot auto-start OpenCode for {base_url!r}. Use a plain local http URL or start the custom server yourself.")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise OpenCodeSetupError(f"Refusing to auto-start OpenCode on non-loopback host {host!r}. Start that server yourself or disable auto-start.")
    try:
        port = parsed.port or 80
    except ValueError as e:
        raise OpenCodeSetupError(f"Invalid OpenCode server URL {base_url!r}: {e}") from e
    return host, port


def _start_managed_server(base_url: str) -> tuple[subprocess.Popen[bytes], str, bool]:
    """Start the configured OpenCode npm package once for this process."""

    global _ATEXIT_REGISTERED, _PROCESS, _PROCESS_URL

    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None:
            if _PROCESS_URL != base_url:
                raise OpenCodeSetupError(f"RAE already manages OpenCode at {_PROCESS_URL}; it cannot also start {base_url} in the same process.")
            return _PROCESS, opencode_npx_package(), False

        host, port = _server_address(base_url)
        npx = shutil.which("npx")
        if npx is None or shutil.which("node") is None:
            raise OpenCodeSetupError(
                "OpenCode is not running and Node.js/npx is unavailable. Install Node.js 20+ or start `opencode serve` manually."
            )

        package = opencode_npx_package()
        argv = [npx, "-y", package, "serve", "--hostname", host, "--port", str(port)]
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
                start_new_session=True,
            )
        except OSError as e:
            raise OpenCodeSetupError(f"Could not start `{package}` through npx: {e}") from e

        _PROCESS = process
        _PROCESS_URL = base_url
        if not _ATEXIT_REGISTERED:
            atexit.register(stop_managed_opencode_server)
            _ATEXIT_REGISTERED = True
        return process, package, True


async def ensure_opencode_server(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    timeout: float = _START_TIMEOUT_SECONDS,
) -> OpenCodeServerStatus:
    """Reuse a healthy server or start the configured OpenCode release locally."""

    try:
        response = await client.get("/global/health", timeout=2.0)
        response.raise_for_status()
        return OpenCodeServerStatus(health=response.json())
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as initial_error:
        if not opencode_auto_start():
            raise OpenCodeSetupError(
                f"OpenCode is not responding at {base_url} and automatic startup is disabled. Run `opencode serve` first."
            ) from initial_error

    process, package, started = _start_managed_server(base_url)
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise OpenCodeSetupError(f"`npx -y {package} serve` exited with status {process.returncode} before becoming healthy.")
        try:
            response = await client.get("/global/health", timeout=2.0)
            response.raise_for_status()
            return OpenCodeServerStatus(health=response.json(), started=started, package=package)
        except httpx.HTTPStatusError:
            if started:
                stop_managed_opencode_server()
            raise
        except httpx.RequestError as e:
            last_error = e
            import asyncio

            await asyncio.sleep(0.25)

    if started:
        stop_managed_opencode_server()
    raise OpenCodeSetupError(f"Timed out after {timeout:.0f}s waiting for `npx -y {package} serve` at {base_url}.") from last_error


def stop_managed_opencode_server() -> None:
    """Stop the OpenCode child process started by RAE, if any."""

    global _PROCESS, _PROCESS_URL

    with _PROCESS_LOCK:
        process = _PROCESS
        _PROCESS = None
        _PROCESS_URL = None

    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
