"""/settings inside the session: every setting in one list, each one changed where it stands."""

from __future__ import annotations

from typing import Any

from .view import model_label

LANGUAGES = ("python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", "c", "powershell")
SDKS = (
    ("claude", "Claude Agent SDK"),
    ("copilot", "GitHub Copilot SDK"),
    ("cursor", "Cursor SDK"),
    ("opencode", "an OpenCode server, with any of its providers"),
)
PROVIDERS = (
    ("chrome-mcp", "your own Chrome, through Chrome DevTools MCP"),
    ("auto", "Playwright MCP in a fresh browser, records a HAR"),
    ("agent-browser", "Vercel's agent-browser CLI"),
)
# key, label, kind: a choice opens a list, a toggle flips, text takes what is typed, opencode loads the server's catalog.
SETTINGS = (
    ("sdk", "sdk", "choice"),
    ("agent_provider", "agent provider", "choice"),
    ("claude_code_model", "claude model", "choice"),
    ("opencode", "opencode provider / model", "opencode"),
    ("copilot_model", "copilot model", "text"),
    ("cursor_model", "cursor model", "text"),
    ("cursor_web_search", "cursor web search", "toggle"),
    ("output_language", "output language", "choice"),
    ("output_dir", "output directory", "text"),
    ("real_time_sync", "real-time sync", "toggle"),
)
LABELS = {key: label for key, label, _ in SETTINGS}
KINDS = {key: kind for key, _, kind in SETTINGS}
SUGGESTIONS = {
    "copilot_model": (("gpt-5", "gpt-5", ""), ("gpt-4.1", "gpt-4.1", "")),
    "cursor_model": (("composer-2.5", "composer-2.5", ""), ("composer-2", "composer-2", "")),
    "output_dir": (("", "default", "~/.reverse-api/runs"),),
}
NOTES = {
    "chrome-mcp": "the agent drives your Chrome · turn on auto-connect at chrome://inspect/#remote-debugging (Chrome 146+)",
    "agent-browser": "rae installs agent-browser on the first run · `agent-browser install` downloads its Chrome",
}


def shown(cfg: Any, key: str) -> str:
    """A setting's value as the list shows it."""
    if key == "opencode":
        return f"{cfg.get('opencode_provider') or 'opencode'} / {cfg.get('opencode_model') or 'default'}"
    value = cfg.get(key)
    if key == "claude_code_model":
        return model_label(value)
    if key == "output_dir":
        return value or "default · ~/.reverse-api/runs"
    if isinstance(value, bool):
        return "on" if value else "off"
    return "default" if value is None else str(value)


def choices(key: str, model_choices: list[dict[str, str]], current: Any) -> list[tuple[str, str, str]]:
    """The values a choice setting can take, as (value, label, description)."""
    if key == "sdk":
        return [(value, value, note) for value, note in SDKS]
    if key == "agent_provider":
        return [(value, value, note) for value, note in PROVIDERS]
    if key == "output_language":
        return [(value, value, "") for value in LANGUAGES]
    items = [(c["value"], model_label(c["value"]), c["name"].split("[")[-1].rstrip("]").lower()) for c in model_choices]
    if current and current not in [value for value, _, _ in items]:
        items.insert(0, (str(current), model_label(str(current)), "current"))
    return items
