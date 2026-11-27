"""Chrome DevTools MCP provider: package pin and auto-connect detection.

Headed chrome-mcp runs attach to the user's own Chrome through ``--autoConnect``,
which only works after remote debugging is enabled at chrome://inspect/#remote-debugging.
Chrome then writes ``DevToolsActivePort`` into its user data directory; that file plus
an open port is what chrome-devtools-mcp looks for.

A Chrome on another host or in a container (no shared user data directory) is reached
instead through ``chrome_browser_url`` in the config or ``RAE_CHROME_BROWSER_URL``: rae then
passes ``--browserUrl`` to chrome-devtools-mcp and skips auto-connect.
"""

from __future__ import annotations

import os
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Pinned to a minor line: tool signatures change between releases (1.12 requires pageId).
CHROME_DEVTOOLS_MCP_PACKAGE = "chrome-devtools-mcp@1.12"

AUTO_CONNECT_SETUP = (
    "enable remote debugging in Chrome 146+ at chrome://inspect/#remote-debugging "
    "(click \"Enable auto-connect\"), keep Chrome open, or run with --headless"
)


@dataclass(frozen=True)
class AutoConnectStatus:
    ok: bool
    reason: str

    @property
    def message(self) -> str:
        return self.reason if self.ok else f"{self.reason}; {AUTO_CONNECT_SETUP}"


def chrome_user_data_dir() -> Path | None:
    """Default user data directory of stable Google Chrome, the channel --autoConnect uses."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) / "Google" / "Chrome" / "User Data" if local else None
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        # Chrome on Linux prefers CHROME_CONFIG_HOME over XDG_CONFIG_HOME.
        config_home = os.environ.get("CHROME_CONFIG_HOME") or os.environ.get("XDG_CONFIG_HOME")
        return Path(config_home or Path.home() / ".config") / "google-chrome"


def check_auto_connect(user_data_dir: Path | None = None, timeout: float = 1.0) -> AutoConnectStatus:
    """Report whether a running Chrome accepts auto-connect, without launching anything."""
    data_dir = user_data_dir if user_data_dir is not None else chrome_user_data_dir()
    if data_dir is None:
        return AutoConnectStatus(False, "could not locate the Chrome profile directory")
    port_file = data_dir / "DevToolsActivePort"
    try:
        port = int(port_file.read_text(encoding="utf-8").splitlines()[0].strip())
    except FileNotFoundError:
        return AutoConnectStatus(False, "Chrome remote debugging is not enabled")
    except (OSError, ValueError, IndexError) as e:
        return AutoConnectStatus(False, f"could not read {port_file}: {e}")
    if not 0 < port < 65536:
        return AutoConnectStatus(False, f"could not read {port_file}: invalid port {port}")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            pass
    except OSError:
        return AutoConnectStatus(False, f"Chrome is not running with remote debugging on port {port}")
    return AutoConnectStatus(True, f"Chrome remote debugging reachable on port {port}")


def _configured_browser_url() -> Any:
    """``chrome_browser_url`` from the config file (engines have no loaded config at hand)."""
    from .config import ConfigManager
    from .utils import get_config_path

    return ConfigManager(get_config_path()).get("chrome_browser_url")


def chrome_browser_url(config_get: Callable[..., Any] | None = None) -> str | None:
    """DevTools HTTP endpoint of a running Chrome to attach to, or None for auto-connect.

    ``RAE_CHROME_BROWSER_URL`` overrides the ``chrome_browser_url`` config key. ``config_get``
    reads the key from an already loaded config; without it the config file is read.
    """
    env = os.environ.get("RAE_CHROME_BROWSER_URL", "").strip()
    if env:
        return env
    try:
        value = config_get("chrome_browser_url") if config_get is not None else _configured_browser_url()
    except Exception:
        return None
    if not value:
        return None
    return str(value).strip() or None


def chrome_connect_args(headless: bool, browser_url: str | None = None) -> list[str]:
    """chrome-devtools-mcp flags choosing how to reach Chrome.

    ``--headless`` launches its own Chrome; a browser URL attaches to that Chrome;
    otherwise ``--autoConnect`` attaches to the local Chrome.
    """
    if headless:
        return ["--headless"]
    url = browser_url if browser_url is not None else chrome_browser_url()
    if url:
        return ["--browserUrl", url]
    return ["--autoConnect"]


def check_browser_url(url: str, timeout: float = 3.0) -> AutoConnectStatus:
    """Report whether a DevTools endpoint answers ``/json/version``, without opening a page."""
    endpoint = url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout) as resp:  # noqa: S310 - user-configured URL
            info = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return AutoConnectStatus(False, f"no Chrome DevTools endpoint at {url} ({e})")
    browser = info.get("Browser", "Chrome") if isinstance(info, dict) else "Chrome"
    return AutoConnectStatus(True, f"{browser} reachable at {url}")


def check_chrome_connection(config_get: Callable[..., Any] | None = None) -> tuple[str, AutoConnectStatus]:
    """Preflight for headed chrome-mcp: the check name and its status."""
    url = chrome_browser_url(config_get)
    if url:
        return "chrome-mcp:browser-url", check_browser_url(url)
    return "chrome-mcp:auto-connect", check_auto_connect()
