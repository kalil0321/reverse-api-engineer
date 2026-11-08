from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Protocol, TextIO

import click
import questionary
import setproctitle
from rich.console import Console
from rich.markup import escape

from . import __version__
from .config import DEFAULT_OPENCODE_MODEL, DEFAULT_OPENCODE_PROVIDER, ConfigManager
from .engineer import run_reverse_engineering
from .session import SessionManager
from .tui import (
    ERROR_CTA,
    RETIRED_MODEL_IDS,
    get_model_choices,
)
from .utils import (
    build_sdk_effort,
    discover_scripts,
    generate_folder_name,
    generate_run_id,
    get_base_output_dir,
    get_config_path,
    get_har_dir,
    get_history_path,
    get_messages_path,
    get_timestamp,
    normalize_url,
    predates_effort,
    recorded_cost,
    resolve_run,
)


class CliEventEmitter(Protocol):
    def __call__(self, event: str, **fields: Any) -> None: ...


setproctitle.setproctitle("reverse-api-engineer")
setproctitle.setthreadtitle("reverse-api-engineer")

console = Console()
config_manager = ConfigManager(get_config_path())
session_manager = SessionManager(get_history_path())


class ModelChoice(click.Choice):
    """The models in the pickers, plus retired ids that configs and scripts still pass; help lists only the current ones."""

    def __init__(self) -> None:
        self.current = [c["value"] for c in get_model_choices()]
        super().__init__(self.current + RETIRED_MODEL_IDS)

    def get_metavar(self, *args: Any, **kwargs: Any) -> str:
        return "[" + "|".join(self.current) + "]"


def default_model_for_configured_sdk(sdk: str | None = None) -> str:
    """Return the configured default model id for the given SDK (or current config SDK)."""
    s = (sdk or config_manager.get("sdk", "claude") or "claude").lower()
    if s == "opencode":
        return str(config_manager.get("opencode_model") or DEFAULT_OPENCODE_MODEL)
    if s == "copilot":
        return str(config_manager.get("copilot_model") or "gpt-5")
    if s == "cursor":
        return str(config_manager.get("cursor_model") or "composer-2.5")
    return str(config_manager.get("claude_code_model") or "claude-sonnet-4-6")


async def _load_opencode_catalog_for_settings() -> dict:
    """Start or reuse OpenCode and load its live provider/model catalog."""
    import httpx2 as httpx

    from .opencode_runtime import (
        ensure_opencode_server,
        get_opencode_model_catalog,
        opencode_base_url,
    )

    base_url = opencode_base_url()
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
    auth = httpx.BasicAuth(username, password) if password else None
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0, auth=auth) as client:
        await ensure_opencode_server(client, base_url=base_url)
        return await get_opencode_model_catalog(client)


def opencode_provider_choices(catalog: dict) -> list[tuple[str, str]]:
    """(provider id, title) for each provider with a tool-capable model, plus ollama for local models."""
    from .opencode_runtime import opencode_model_is_selectable

    choices = []
    for provider in catalog.get("providers", []):
        if not isinstance(provider, dict):
            continue
        models = provider.get("models")
        if not (provider.get("id") and isinstance(models, dict) and any(opencode_model_is_selectable(m) for m in models.values())):
            continue
        provider_id, name = str(provider["id"]), str(provider.get("name") or "")
        choices.append((provider_id, f"{provider_id} — {name}" if name and name != provider_id else provider_id))
    if "ollama" not in {provider_id for provider_id, _ in choices}:
        choices.append(("ollama", "ollama — installed local models"))
    return choices


def opencode_model_choices(catalog: dict, provider_id: str, current_model: str = "") -> list[tuple[str, str]]:
    """(model id, title) for a provider's tool-capable models, the current and default ones first."""
    from .opencode_runtime import opencode_model_is_free, opencode_model_is_selectable

    provider = next((p for p in catalog.get("providers", []) if isinstance(p, dict) and p.get("id") == provider_id), {})
    raw_models, raw_defaults = provider.get("models"), catalog.get("default")
    models: dict[str, Any] = raw_models if isinstance(raw_models, dict) else {}
    defaults: dict[str, Any] = raw_defaults if isinstance(raw_defaults, dict) else {}
    default_model = str(defaults.get(provider_id) or "")
    selectable = [str(m) for m, model in models.items() if opencode_model_is_selectable(model)]
    model_ids = sorted(selectable, key=lambda m: (m not in {current_model, default_model}, m))
    choices = []
    for model_id in model_ids:
        model = models[model_id]
        name = str(model.get("name") or "")
        title = f"{model_id} — {name}" if name and name != model_id else model_id
        markers = (["free"] if opencode_model_is_free(provider_id, model_id, model) else []) + (["default"] if model_id == default_model else [])
        choices.append((model_id, title + (f"  ({', '.join(markers)})" if markers else "")))
    return choices


# Schema version for --json outputs. Wrappers can query it via
# `reverse-api-engineer --json-schema-version`.
AGENT_JSON_SCHEMA_VERSION = 1

# Map of stable usage keys → SDK-specific candidates (first match wins).
# Lets `agent --json` and `engineer --json` emit a stable cost/token shape
# regardless of which SDK (Claude / OpenCode / Copilot) ran underneath.
_STABLE_USAGE_KEYS: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens",),
    "output_tokens": ("output_tokens",),
    "cache_read_tokens": ("cache_read_input_tokens", "cache_read_tokens"),
    "cache_write_tokens": ("cache_creation_input_tokens", "cache_write_tokens", "cache_creation_tokens"),
    "total_cost_usd": ("estimated_cost_usd", "total_cost_usd", "total_cost"),
}


def _normalize_usage(raw: dict | None) -> dict:
    """Return a stable subset of usage fields, keeping the SDK-native dict under .raw.

    Wrappers can rely on the top-level keys; per-SDK extras stay under raw.
    """
    if not raw or not isinstance(raw, dict):
        return {}
    out: dict = {}
    for stable_key, candidates in _STABLE_USAGE_KEYS.items():
        for c in candidates:
            if c in raw:
                out[stable_key] = raw[c]
                break
    out["raw"] = raw
    return out


# Machine-readable error categories. Wrappers can react differently to each
# without pattern-matching on the human-readable `error` string.
ERROR_KINDS = (
    "misuse",            # user input invalid / missing required arg
    "config_invalid",    # config file or env var malformed
    "permission_denied", # filesystem / API perm denied
    "network",           # DNS / TCP / TLS / timeout
    "engine_failure",    # SDK or capture engine crashed mid-run
    "interrupted",       # KeyboardInterrupt / SIGINT
    "unknown",           # default fallback
)


def _format_error_message(error: str | BaseException | None) -> str | None:
    """Render an exception or string into a human-readable error message.

    KeyboardInterrupt has no useful str() — we return the conventional
    "interrupted" so downstream wrappers can match on a stable message.
    Empty exception messages fall back to the class name.
    """
    if error is None:
        return None
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    if isinstance(error, BaseException):
        return str(error) or type(error).__name__
    return error


def _classify_error(error: str | BaseException | None, *, default: str = "unknown") -> str | None:
    """Map an Exception or human error message to one of the ERROR_KINDS.

    Callers may pass a stronger hint by setting `default` (e.g. `misuse` from
    a CLI argument check, before any exception).
    """
    if error is None:
        return None
    if isinstance(error, BaseException):
        if isinstance(error, KeyboardInterrupt):
            return "interrupted"
        if isinstance(error, PermissionError):
            return "permission_denied"
        if isinstance(error, (ConnectionError, TimeoutError)):
            return "network"
        msg = str(error)
    else:
        msg = error
    low = msg.lower()
    if "permission denied" in low or "errno 13" in low:
        return "permission_denied"
    if "interrupted" in low:
        return "interrupted"
    if "is required" in low or "missing required" in low or "no such option" in low or "in non-interactive" in low:
        return "misuse"
    if any(kw in low for kw in ("connection refused", "timeout", "timed out", "dns", "network", "unreachable", "ssl")):
        return "network"
    if "not found" in low or "no run" in low or "produced no run" in low or "produced no result" in low:
        return "engine_failure"
    return default


@contextmanager
def _quiet_consoles_for_json() -> Iterator[TextIO]:
    """Reserve stdout for the final JSON payload; route Rich output to stderr.

    Yields the original stdout file object so the caller can write JSON to it
    after the wrapped block exits cleanly. Rich Console.file is a property that
    lazily resolves to sys.stdout, so we save/restore the underlying _file slot
    rather than the resolved file object.
    """
    real_stdout = sys.stdout
    redirected_consoles: list[tuple[Console, IO[str] | None]] = []
    sys.stdout = sys.stderr
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("reverse_api") or mod is None:
            continue
        candidate = getattr(mod, "console", None)
        if isinstance(candidate, Console):
            redirected_consoles.append((candidate, candidate._file))
            candidate.file = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout
        for c, original_inner in redirected_consoles:
            c._file = original_inner


def _write_json_line(stream: TextIO, line: str) -> None:
    stream.write(line + "\n")
    stream.flush()


def _write_json_stdout(real_stdout: TextIO, payload: dict, *, json_stream: bool) -> None:
    """Write final CLI JSON payload (single doc or NDJSON terminal event)."""
    out = {"event": "result", **payload} if json_stream else payload
    real_stdout.write(json.dumps(out) + "\n")
    real_stdout.flush()


def _build_dry_run_payload(
    *,
    prompt: str | None,
    url: str | None,
    model: str | None,
    output_dir: str | None,
    headless: bool,
) -> dict:
    """Validate config / env / deps without launching a browser.

    Returns a payload with the same top-level shape as `_build_agent_payload`
    plus a `checks` array (each item: name, status: ok|warn|error, message)
    and a `would_run` sub-object showing what an actual `agent` invocation
    would do with these inputs. Status is `error` if any check is `error`,
    otherwise `ok`. Misuse errors (missing prompt) get `error_kind=misuse`;
    runtime issues (missing API key, missing node) get `config_invalid`.
    """
    import shutil
    import subprocess

    from .agent_browser import check_agent_browser_runtime

    checks: list[dict] = []
    agent_provider = config_manager.get("agent_provider", "chrome-mcp")
    global_agent_browser = shutil.which("agent-browser")

    # 1. Prompt
    if not prompt or not prompt.strip():
        checks.append({"name": "prompt", "status": "error", "message": "--prompt is required"})
    else:
        checks.append({"name": "prompt", "status": "ok", "message": f"{len(prompt)} chars"})

    # 2. URL (optional, but if given it must look reasonable)
    if url:
        if url.startswith("http://") or url.startswith("https://"):
            checks.append({"name": "url", "status": "ok", "message": url})
        else:
            checks.append({
                "name": "url",
                "status": "error",
                "message": f"url must start with http:// or https://, got {url!r}",
            })
    else:
        checks.append({"name": "url", "status": "ok", "message": "(none — agent will pick a start)"})

    # 3. Agent provider
    if agent_provider in ("auto", "chrome-mcp", "agent-browser"):
        checks.append({"name": "agent_provider", "status": "ok", "message": agent_provider})
    else:
        checks.append({
            "name": "agent_provider",
            "status": "error",
            "message": f"unknown agent_provider {agent_provider!r}; expected 'auto', 'chrome-mcp', or 'agent-browser'",
        })

    # 4. SDK + API key presence (we only check env var existence, not validity)
    sdk = config_manager.get("sdk", "claude")
    sdk_env_var = {
        "claude": "ANTHROPIC_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "copilot": "GITHUB_COPILOT_TOKEN",
        "cursor": "CURSOR_API_KEY",
    }.get(sdk)
    if sdk_env_var is None:
        checks.append({
            "name": "sdk",
            "status": "error",
            "message": f"unknown sdk {sdk!r}; expected 'claude', 'opencode', 'copilot', or 'cursor'",
        })
    elif not os.environ.get(sdk_env_var):
        checks.append({
            "name": f"sdk:{sdk}",
            "status": "warn",
            "message": f"{sdk_env_var} not set in env (the SDK may still resolve auth via a config file)",
        })
    else:
        checks.append({"name": f"sdk:{sdk}", "status": "ok", "message": f"{sdk_env_var} present"})

    # 5. Node.js + npx — MCP providers need both; agent-browser with a global binary does not.
    node = shutil.which("node")
    needs_node_for_browser = agent_provider != "agent-browser" or global_agent_browser is None
    if node is None:
        if needs_node_for_browser:
            checks.append({
                "name": "node",
                "status": "error",
                "message": "node not found in PATH; required for agent-mode browser tooling "
                "(MCP browser servers plus Vercel agent-browser install/bootstrap)",
            })
        else:
            checks.append({
                "name": "node",
                "status": "ok",
                "message": "not on PATH (optional while global `agent-browser` is installed)",
            })
    else:
        try:
            ver = subprocess.run(
                [node, "--version"], capture_output=True, text=True, errors="replace", timeout=5
            ).stdout.strip()
            checks.append({"name": "node", "status": "ok", "message": ver})
        except Exception as e:
            checks.append({"name": "node", "status": "warn", "message": f"could not query version: {e}"})

    npx = shutil.which("npx")
    needs_npx_for_browser = agent_provider in ("auto", "chrome-mcp") or (
        agent_provider == "agent-browser" and global_agent_browser is None
    )
    if npx is None:
        if needs_npx_for_browser:
            checks.append({
                "name": "npx",
                "status": "error",
                "message": "npx not found in PATH; required so npm can spawn MCP helpers and "
                "fetch/run the pinned agent-browser CLI when no global binary is present",
            })
        else:
            checks.append({
                "name": "npx",
                "status": "ok",
                "message": "not on PATH (optional while global `agent-browser` is installed)",
            })
    else:
        checks.append({"name": "npx", "status": "ok", "message": npx})

    # 6. Headed chrome-mcp attaches to the user's running Chrome through auto-connect
    if agent_provider == "chrome-mcp" and not headless:
        from .chrome_mcp import check_auto_connect

        auto_connect = check_auto_connect()
        checks.append({
            "name": "chrome-mcp:auto-connect",
            "status": "ok" if auto_connect.ok else "error",
            "message": auto_connect.message,
        })

    # 7. agent-browser CLI: read-only validation (no npm install during dry-run).
    if agent_provider == "agent-browser":
        ab_setup = check_agent_browser_runtime()
        parts: list[str] = []
        if ab_setup.error:
            parts.append(ab_setup.error)
        elif ab_setup.ok:
            parts.append("`agent-browser` CLI reachable (`--help` OK)")
        if ab_setup.notices:
            parts.extend(ab_setup.notices)
        checks.append({
            "name": "agent-browser:cli",
            "status": "error" if not ab_setup.ok else "ok",
            "message": " | ".join(parts) if parts else "configured",
        })

    # 8. Output dir writability — probe with a unique filename so we never
    # clobber a real user file (a fixed name like `.dry_run_write_probe`
    # could legitimately exist in someone's output dir).
    import secrets

    base = Path(output_dir or config_manager.get("output_dir") or "~/.reverse-api/runs").expanduser()
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / f".rae_dry_run_probe_{os.getpid()}_{secrets.token_hex(4)}"
        # If somehow this exact filename already exists, refuse to touch it.
        if probe.exists():
            raise FileExistsError(f"unique probe path collision: {probe}")
        probe.write_text("")
        probe.unlink()
        checks.append({"name": "output_dir", "status": "ok", "message": str(base)})
    except Exception as e:
        checks.append({
            "name": "output_dir",
            "status": "error",
            "message": f"{base}: {e}",
        })

    # Aggregate
    has_error = any(c["status"] == "error" for c in checks)
    final_error = None
    error_kind = None
    if has_error:
        first_err = next(c for c in checks if c["status"] == "error")
        final_error = f"{first_err['name']}: {first_err['message']}"
        # Misuse for prompt/url; config_invalid otherwise
        error_kind = "misuse" if first_err["name"] in ("prompt", "url") else "config_invalid"

    # `would_run.model` resolution mirrors the live capture path: each SDK
    # has its own model config key, so picking `claude_code_model` for an
    # opencode/copilot session would misreport what would actually run.
    sdk_model_key = {
        "claude": "claude_code_model",
        "opencode": "opencode_model",
        "copilot": "copilot_model",
        "cursor": "cursor_model",
    }.get(sdk, "claude_code_model")
    sdk_default_model = {
        "claude": "claude-sonnet-4-6",
        "opencode": "claude-opus-4-6",
        "copilot": "gpt-5",
        "cursor": "composer-2.5",
    }.get(sdk, "claude-sonnet-4-6")
    resolved_model = model or config_manager.get(sdk_model_key, sdk_default_model)

    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if has_error else "ok",
        "run_id": None,
        "prompt": prompt,
        "url": url,
        "mode": "dry-run",
        "har_path": None,
        "script_path": None,
        "usage": {},
        "error": final_error,
        "error_kind": error_kind,
        "would_run": {
            "agent_provider": agent_provider,
            "sdk": sdk,
            "model": resolved_model,
            "output_dir": str(base),
            "headless": headless,
        },
        "checks": checks,
    }


def _missing_client_error(result: dict) -> str | None:
    """A run can end without an SDK error yet write no client, e.g. when the agent stops on a browser it cannot reach."""
    script_path = result.get("script_path")
    if script_path and not Path(script_path).exists():
        return f"the agent finished without writing a client at {script_path}"
    return None


def _build_agent_payload(
    result: dict | None,
    *,
    prompt: str | None,
    url: str | None,
    output_dir: str | None = None,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize an agent capture result into a stable JSON shape.

    `output_dir` must match the value passed to the underlying capture so the
    HAR path is resolved against the user's chosen run root, not the default.
    """
    result = result or {}
    run_id = result.get("run_id")
    inner_error = result.get("error")
    final_error_obj = error if error is not None else inner_error
    if final_error_obj is None and not run_id:
        final_error_obj = "agent capture produced no run"
    if final_error_obj is None and (missing := _missing_client_error(result)):
        final_error_obj, error_kind_hint = missing, "engine_failure"
    error_str = _format_error_message(final_error_obj)
    error_kind = _classify_error(final_error_obj, default=error_kind_hint) if final_error_obj else None
    if error is None and inner_error is not None and result.get("error_kind"):
        error_kind = result["error_kind"]
    har_path = None
    if run_id:
        candidate = get_har_dir(run_id, output_dir) / "recording.har"
        har_path = str(candidate) if candidate.exists() else None
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "run_id": run_id,
        "prompt": prompt,
        "url": url,
        "mode": result.get("mode"),
        "har_path": har_path,
        "script_path": result.get("script_path"),
        "usage": _normalize_usage(result.get("usage")),
        "error": error_str,
        "error_kind": error_kind,
    }


def _build_engineer_payload(
    result: dict | None,
    *,
    run_id: str,
    prompt: str | None,
    fresh: bool,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize an engineer-mode result into a stable JSON shape.

    Mirrors `_build_agent_payload`'s contract minus the agent-specific fields
    (no `url`, no `mode`, no `har_path`). `prompt` is the value the user passed
    to --prompt (which may have been used as either a full replacement or as
    additional instructions depending on --fresh).
    """
    result = result if isinstance(result, dict) else {}
    inner_error = result.get("error")
    final_error_obj = error if error is not None else inner_error
    if final_error_obj is None and not result:
        final_error_obj = "engineering produced no result"
    if final_error_obj is None and (missing := _missing_client_error(result)):
        final_error_obj, error_kind_hint = missing, "engine_failure"
    error_str = _format_error_message(final_error_obj)
    error_kind = _classify_error(final_error_obj, default=error_kind_hint) if final_error_obj else None
    if error is None and inner_error is not None and result.get("error_kind"):
        error_kind = result["error_kind"]
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "run_id": run_id,
        "prompt": prompt,
        "fresh": fresh,
        "script_path": result.get("script_path"),
        "usage": _normalize_usage(result.get("usage")),
        "error": error_str,
        "error_kind": error_kind,
    }


def _build_run_payload(
    *,
    identifier: str,
    run_id: str | None = None,
    script_path: str | None = None,
    script_args: tuple[str, ...] | list[str] = (),
    returncode: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    scripts: list[Path] | None = None,
    error: str | BaseException | None = None,
    error_kind_hint: str = "unknown",
) -> dict:
    """Normalize `run --json` output into a stable machine-readable shape."""
    error_str = _format_error_message(error)
    if error_str is None and returncode not in (None, 0):
        error_str = f"script exited with code {returncode}"
    error_kind = _classify_error(error, default=error_kind_hint) if error_str else None
    if error_str and error is None:
        error_kind = error_kind_hint
    return {
        "schema_version": AGENT_JSON_SCHEMA_VERSION,
        "status": "error" if error_str else "ok",
        "identifier": identifier,
        "run_id": run_id,
        "script_path": script_path,
        "script_args": list(script_args),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "scripts": [
            {
                "name": p.name,
                "path": str(p),
                "size": p.stat().st_size if p.exists() else None,
                "modified": p.stat().st_mtime if p.exists() else None,
            }
            for p in (scripts or [])
        ],
        "error": error_str,
        "error_kind": error_kind,
    }


def _write_json_event(real_stdout: TextIO, payload: dict) -> None:
    real_stdout.write(json.dumps(payload) + "\n")
    real_stdout.flush()


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.pass_context
@click.version_option(version=__version__)
@click.option(
    "--json-schema-version",
    "show_schema_version",
    is_flag=True,
    help="Print the agent/engineer JSON schema_version this binary emits and exit.",
)
def main(ctx: click.Context, show_schema_version: bool) -> None:
    """reverse-api-engineer: reverse engineer apis.

    Run without a subcommand to open the interactive session (agent, manual,
    engineer and collector modes); in a terminal, agent, engineer and collector
    open it too.

    Scripted flags are subcommand-specific: agent, engineer, and run support
    --json, --json-stream, and --no-interactive; list/show support --json.
    Set RAE_DEBUG=1 to include unexpected agent failure tracebacks on stderr.
    See `<cmd> --help` for details. Wrappers that need to gate on the payload
    schema can call `reverse-api-engineer
    --json-schema-version`.
    """
    if show_schema_version:
        click.echo(str(AGENT_JSON_SCHEMA_VERSION))
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        # The session needs a terminal; without one (CI, agent wrappers that forgot the
        # subcommand) it would block on stdin forever, so print --help and exit 2 (misuse).
        if not _in_terminal():
            click.echo(ctx.get_help(), err=True)
            stream = "stdin" if not sys.stdin.isatty() else "stdout"
            click.echo(
                f"\nerror: no subcommand given and {stream} is not a TTY; "
                "the interactive session requires a terminal.",
                err=True,
            )
            sys.exit(2)
        open_session()


def _in_session() -> bool:
    from .repl.bridge import active

    return active() is not None


def _in_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def open_session(
    mode: str = "agent",
    model: str | None = None,
    prompt: str | None = None,
    run: Callable[[], Any] | None = None,
    runner: Callable[[str, str | None], Any] | None = None,
) -> None:
    """The interactive CLI: the full-screen session, in ``mode``.

    A subcommand hands over ``run``, its ``prompt`` with every option bound, and ``runner(prompt, model)``,
    which starts later prompts in that mode with the options that still apply, such as --headless.
    """
    from .repl.app import run_session

    run_session(mode=mode, model=model, first=(prompt, run) if prompt and run else None, runner=runner)


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer agent
  reverse-api-engineer agent -p "capture the jobs api" -u https://example.com --no-interactive
  reverse-api-engineer agent -p "capture the jobs api" --json | jq

\b
JSON output schema (--json):
  {
    "schema_version": 1,
    "status": "ok" | "error",
    "run_id": "<id>" | null,
    "prompt": "...",
    "url": "..." | null,
    "mode": "auto" | "chrome-mcp" | "agent-browser" | null,
    "har_path": "/abs/path/recording.har" | null,
    "script_path": "/abs/path/api_client.py" | null,
    "usage": {
      "input_tokens": ...,
      "output_tokens": ...,
      "cache_read_tokens": ...,
      "cache_write_tokens": ...,
      "total_cost_usd": ...,
      "raw": { ... }
    },
    "error": "<message>" | null,
    "error_kind": "misuse" | "config_invalid" | "permission_denied" | "network" | "engine_failure" | "interrupted" | "unknown" | null
  }

\b
Exit codes:
  0  success
  1  runtime error (capture or engineering failed)
  2  misuse (e.g. --prompt missing under --no-interactive / --json)
"""
)
@click.option("--prompt", "-p", default=None, help="Instruction for the autonomous agent.")
@click.option("--url", "-u", default=None, help="Optional starting URL.")
@click.option(
    "--model",
    "-m",
    type=ModelChoice(),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Fail fast instead of prompting for missing inputs (intended for scripted/agent usage).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit a single JSON result on stdout (logs go to stderr). Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help="Emit NDJSON progress events on stdout during the run, then a final {\"event\":\"result\",...} line. Implies --no-interactive.",
)
@click.option(
    "--headless",
    is_flag=True,
    help=(
        "Launch the MCP-controlled browser in headless mode (required on machines without an X server). "
        "For chrome-mcp this drops --autoConnect since auto-connect requires a headed Chrome instance."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Validate prompt/url/config/env without launching the browser. Emits a manifest of what would run + check results. "
        "Implies --json. Exits 0 if all checks pass, 1 if any error."
    ),
)
def agent(
    prompt: str | None,
    url: str | None,
    model: str | None,
    output_dir: str | None,
    no_interactive: bool,
    as_json: bool,
    json_stream: bool,
    headless: bool,
    dry_run: bool,
) -> None:
    """Run autonomous agent browser session.

    Agent mode runs an integrated capture + reverse-engineering pipeline.
    """
    if url:
        url = normalize_url(url)

    if dry_run:
        # --dry-run is fundamentally about emitting machine-parseable validation
        # results, so it implies --json (and therefore --no-interactive).
        with _quiet_consoles_for_json() as real_stdout:
            payload = _build_dry_run_payload(
                prompt=prompt, url=url, model=model, output_dir=output_dir, headless=headless
            )
        real_stdout.write(json.dumps(payload) + "\n")
        real_stdout.flush()
        sys.exit(0 if payload["status"] == "ok" else 1)

    no_interactive = no_interactive or as_json or json_stream
    machine_output = as_json or json_stream

    if no_interactive and not (prompt and prompt.strip()):
        if machine_output:
            misuse = _build_agent_payload(
                {},
                prompt=prompt,
                url=url,
                output_dir=output_dir,
                error="--prompt is required in non-interactive/--json mode",
                error_kind_hint="misuse",
            )
            if json_stream:
                misuse = {"event": "result", **misuse}
            click.echo(json.dumps(misuse))
        else:
            click.echo("error: --prompt is required when --no-interactive is set", err=True)
        sys.exit(2)

    # Either flag must suppress the post-generation follow-up prompt that would
    # otherwise block on stdin (`input("  > ")`) inside ClaudeAutoEngineer.
    interactive = not no_interactive

    if interactive and _in_terminal():
        open_session(
            "agent",
            model,
            prompt,
            lambda: run_agent_capture(prompt=prompt, url=url, model=model, output_dir=output_dir, headless=headless),
            # --url belongs to the first task; the other options stay for the session.
            lambda p, m: run_agent_capture(prompt=p, model=m or model, output_dir=output_dir, headless=headless),
        )
        return
    if not (prompt and prompt.strip()):
        click.echo("error: --prompt is required outside a terminal", err=True)
        sys.exit(2)

    if not machine_output:
        result = run_agent_capture(
            prompt=prompt,
            url=url,
            model=model,
            output_dir=output_dir,
            interactive=interactive,
            headless=headless,
        )
        if isinstance(result, dict) and "error" in result:
            if interactive and result["error"] == "interrupted":
                return
            if not result.get("error_reported"):
                click.echo(f"error: {result['error'] or 'Agent analysis failed.'}", err=True)
            sys.exit(1)
        return

    from .json_stream import make_json_stream_sink

    with _quiet_consoles_for_json() as real_stdout:
        sink = (
            make_json_stream_sink(lambda line: _write_json_line(real_stdout, line))
            if json_stream
            else None
        )
        try:
            result = run_agent_capture(
                prompt=prompt,
                url=url,
                model=model,
                output_dir=output_dir,
                interactive=interactive,
                headless=headless,
                json_event_sink=sink,
            )
            payload = _build_agent_payload(result, prompt=prompt, url=url, output_dir=output_dir)
        except KeyboardInterrupt as e:
            payload = _build_agent_payload(
                {}, prompt=prompt, url=url, output_dir=output_dir, error=e
            )
        except Exception as e:
            # Pass the exception object so _classify_error can use isinstance
            # (PermissionError → permission_denied, ConnectionError → network, ...)
            payload = _build_agent_payload(
                {}, prompt=prompt, url=url, output_dir=output_dir, error=e
            )

        _write_json_stdout(real_stdout, payload, json_stream=json_stream)
    sys.exit(0 if payload["status"] == "ok" else 1)


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer collector -p "collect companies hiring browser automation engineers"
  reverse-api-engineer collector
"""
)
@click.option("--prompt", "-p", default=None, help="Collection instructions.")
@click.option(
    "--model",
    "-m",
    type=ModelChoice(),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory for run metadata and messages.")
def collector(prompt: str | None, model: str | None, output_dir: str | None) -> None:
    """Run AI-powered data collection."""
    if _in_terminal():
        open_session(
            "collector",
            model,
            prompt,
            lambda: run_collector(prompt=prompt, model=model, output_dir=output_dir),
            lambda p, m: run_collector(prompt=p, model=m, output_dir=output_dir),
        )
        return
    if not prompt:
        click.echo("error: --prompt is required outside a terminal", err=True)
        sys.exit(2)

    result = run_collector(prompt=prompt, model=model, output_dir=output_dir)
    if result is None or (isinstance(result, dict) and result.get("error")):
        sys.exit(1)


def run_manual_capture(
    prompt: str | None = None,
    url: str | None = None,
    reverse_engineer: bool = True,
    model: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any] | None:
    """Shared logic for manual capture."""
    output_dir = output_dir or config_manager.get("output_dir")

    # Manual mode drives a local Playwright browser, which ships in the optional
    # [manual] extra. Fail fast — before prompting the user or recording a run —
    # so a base-only install never leaves a phantom "manual" run in history.
    try:
        from .browser import ManualBrowser
    except ImportError as exc:
        raise click.ClickException(
            "Manual capture mode requires the Playwright browser stack, which is "
            "not installed by default. Install it with:\n\n"
            "    pip install 'reverse-api-engineer[manual]'\n"
            "    playwright install chromium\n\n"
            "(Agent mode does not need this.)"
        ) from exc

    if not prompt:
        raise click.UsageError("a prompt is required")

    run_id = generate_run_id()
    timestamp = get_timestamp()
    sdk = config_manager.get("sdk", "claude")

    # Record initial session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode="manual",  # Track mode in history
        sdk=sdk,
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    from .repl.bridge import active

    browser = ManualBrowser(run_id=run_id, prompt=prompt, output_dir=output_dir)
    session = active()
    if session is not None:
        session.on_stop = browser.stop  # esc ends the browsing; the capture is kept
    try:
        har_path = browser.start(start_url=url)
    finally:
        if session is not None:
            session.on_stop = None
    if browser.stopped:
        # Stopped rather than finished: the capture is saved, and /history can engineer it later.
        return {"run_id": run_id, "error": "interrupted"}

    if reverse_engineer:
        result = run_engineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
        )
        if result:
            sdk = config_manager.get("sdk", "claude")
            session_manager.update_run(
                run_id=run_id,
                sdk=sdk,
                usage=result.get("usage", {}),
                paths={"script_path": result.get("script_path")},
            )
    else:
        console.print(" [dim]>[/dim] [white]recording complete[/white]")
        console.print(f" [dim]>[/dim] [white]run_id: {run_id}[/white]")
        console.print(f" [dim]>[/dim] [dim]use 'reverse-api-engineer engineer {run_id}' to engineer later[/dim]\n")
    return None


def run_agent_capture(
    prompt: str | None = None,
    url: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
    interactive: bool = True,
    headless: bool = False,
    json_event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    """Shared logic for agent capture mode."""
    output_dir = output_dir or config_manager.get("output_dir")
    if not prompt:
        raise click.UsageError("a prompt is required")

    agent_provider = config_manager.get("agent_provider", "chrome-mcp")
    return run_auto_capture(
        prompt=prompt,
        url=url,
        model=model,
        output_dir=output_dir,
        agent_provider=agent_provider,
        interactive=interactive,
        headless=headless,
        json_event_sink=json_event_sink,
    )


def run_collector(prompt: str | None = None, model: str | None = None, output_dir: str | None = None) -> dict[str, Any] | None:
    """Run AI-powered data collection with Collector class."""

    from .collector import Collector

    # Generate run ID
    run_id = generate_run_id()
    output_dir = output_dir or config_manager.get("output_dir")

    # Use collector model from config if not specified
    if model is None:
        model = config_manager.get("collector_model", "claude-sonnet-4-6")

    # Initialize session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt or "",
        mode="collector",
        timestamp=get_timestamp(),
    )

    try:
        # Run collector
        collector = Collector(
            run_id=run_id,
            prompt=prompt or "",
            model=model,
            output_dir=output_dir,
        )

        result = asyncio.run(collector.run())

        if result and not result.get("error"):
            # Update session with results
            session_manager.update_run(
                run_id=run_id,
                sdk="claude",
                usage=result.get("usage", {}),
                paths={"output_path": result.get("output_path")},
            )
        return result
    except Exception as e:
        console.print(f" [red]collector error: {escape(str(e))}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()
        return {
            "run_id": run_id,
            "error": str(e) or type(e).__name__,
        }


def _session_browser_note(agent_provider: str, headless: bool) -> str | None:
    """In the full-screen session, one line about the browser; setup steps only show up if connecting fails."""
    from .repl.bridge import active

    if active() is None:
        return None
    if agent_provider == "chrome-mcp":
        if headless:
            return "the agent uses its own headless Chrome"
        return "the agent drives your Chrome through auto-connect · accept Chrome's connection prompt · avoid sensitive sites while it runs"
    if agent_provider == "agent-browser":
        return "the agent drives a browser through the agent-browser CLI"
    return None


def run_auto_capture(
    prompt: str | None = None,
    url: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
    agent_provider: str = "chrome-mcp",
    interactive: bool = True,
    headless: bool = False,
    json_event_sink: Callable[[dict[str, Any]], None] | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Auto mode: LLM-driven browser automation + real-time reverse engineering.

    ``resume`` is a past run's history entry: the run reopens its SDK session instead of starting one.
    """
    output_dir = output_dir or config_manager.get("output_dir")
    if not prompt:
        raise click.UsageError("a prompt is required")

    if url:
        url = normalize_url(url)

    if agent_provider == "chrome-mcp" and not headless:
        from .chrome_mcp import check_auto_connect

        auto_connect = check_auto_connect()
        if not auto_connect.ok:
            console.print()
            console.print(" [dim]chrome devtools mcp (auto-connect)[/dim]")
            console.print(" [dim]auto-connect setup:[/dim]")
            console.print(" [dim] 1. chrome 146+ required[/dim]")
            console.print(" [dim] 2. go to chrome://inspect/#remote-debugging[/dim]")
            console.print(' [dim] 3. click "Enable auto-connect" and keep chrome open[/dim]')
            console.print(" [dim] 4. node.js v20.19+[/dim]")
            console.print(" [dim]or run with --headless, or pick another provider in /settings[/dim]")
            console.print()
            console.print(f" [red]error:[/red] {auto_connect.reason}")
            return {"error": auto_connect.message, "error_kind": "config_invalid", "error_reported": True}

    session_note = _session_browser_note(agent_provider, headless)
    if session_note:
        console.print(session_note)
    elif agent_provider == "chrome-mcp" and not headless:
        console.print()
        console.print(" [dim]chrome devtools mcp (auto-connect)[/dim]")
        console.print(" [dim]controlling your real chrome browser[/dim]")
        console.print(" [dim]accept chrome's connection prompt when it appears[/dim]")
        console.print(" [dim]existing sessions, cookies, and auth available[/dim]")
        console.print()
        console.print(" [dim]warning: the agent will execute actions on your browser[/dim]")
        console.print(" [dim]avoid browsing sensitive sites during the session[/dim]")
        console.print()
    elif agent_provider == "chrome-mcp" and headless:
        console.print()
        console.print(" [dim]chrome devtools mcp (headless)[/dim]")
        console.print(" [dim]auto-connect disabled — mcp will spawn its own headless chrome[/dim]")
        console.print()

    elif agent_provider == "agent-browser":
        console.print()
        console.print(
            " [dim]agent-browser: Vercel CLI via shell (Reverse API Engineer does not attach "
            "Playwright/Chrome browser MCP for this provider).[/dim]"
        )
        console.print(
            " [dim]Startup prefers PATH `agent-browser`, otherwise installs via "
            "`npm install -g <pin>` so Chromium pairs with a stable shim (with a banner); "
            "only falls back to `npx -y` if npm cannot run.[/dim]"
        )
        console.print(
            " [dim]First-time Chrome download: `agent-browser install` (add `--with-deps` on Linux).[/dim]"
        )
        console.print()

    sdk = _session_sdk(resume) or config_manager.get("sdk", "claude")
    if model is None:
        model = default_model_for_configured_sdk(sdk)

    run_id = resume["run_id"] if resume else generate_run_id()
    timestamp = get_timestamp()

    if agent_provider == "chrome-mcp":
        mode_label = "chrome-mcp"
    elif agent_provider == "agent-browser":
        mode_label = "agent-browser"
    else:
        mode_label = "auto"
    if not resume:
        session_manager.add_run(
            run_id=run_id,
            prompt=prompt,
            timestamp=timestamp,
            url=url,
            model=model,
            mode=mode_label,
            paths={"har_dir": str(get_har_dir(run_id, output_dir))},
        )

    try:
        output_language = config_manager.get("output_language", "python")
        from .auto_engineer import ClaudeAutoEngineer, CopilotAutoEngineer, OpenCodeAutoEngineer
        from .cursor_engineer import CursorAutoEngineer

        engineer: ClaudeAutoEngineer | CopilotAutoEngineer | OpenCodeAutoEngineer | CursorAutoEngineer
        if sdk == "opencode":
            from .auto_engineer import OpenCodeAutoEngineer

            engineer = OpenCodeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                output_dir=output_dir,
                agent_provider=agent_provider,
                opencode_provider=_session_provider(resume) or config_manager.get("opencode_provider", DEFAULT_OPENCODE_PROVIDER),
                opencode_model=model or config_manager.get("opencode_model", DEFAULT_OPENCODE_MODEL),
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
                start_url=url,
            )
        elif sdk == "copilot":
            from .auto_engineer import CopilotAutoEngineer

            engineer = CopilotAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                copilot_model=model or config_manager.get("copilot_model", "gpt-5"),
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
                start_url=url,
            )
        elif sdk == "cursor":
            from .cursor_engineer import CursorAutoEngineer

            _cs = config_manager.get("cursor_setting_sources")
            _cursor_src = _cs if isinstance(_cs, list) and all(isinstance(x, str) for x in _cs) else None
            engineer = CursorAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
                start_url=url,
                cursor_model=model or config_manager.get("cursor_model", "composer-2.5"),
                cursor_web_search=bool(config_manager.get("cursor_web_search", True)),
                cursor_setting_sources=_cursor_src,
            )
        else:
            from .auto_engineer import ClaudeAutoEngineer

            engineer = ClaudeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                model=model or config_manager.get("claude_code_model", "claude-sonnet-4-6"),
                output_dir=output_dir,
                agent_provider=agent_provider,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
                interactive=interactive,
                headless=headless,
                start_url=url,
            )

        # CopilotAutoEngineer wraps the CopilotEngineer that owns the session.
        core = engineer._engineer if isinstance(engineer, CopilotAutoEngineer) else engineer
        core.on_session = _session_recorder(run_id, "agent", sdk, model, output_dir, headless=headless)
        if resume:
            core.resume_session, core.cost_before = _resume_point(resume)
            # A new browser stretch records its own HAR instead of replacing the run's capture.
            engineer.mcp_run_id = f"{run_id}-{int(time.time())}"

        if json_event_sink is not None:
            from .json_stream import attach_json_stream_to_engineer

            attach_json_stream_to_engineer(
                engineer,
                json_event_sink,
                mode=mode_label,
                url=url,
                command="agent",
            )

        # Start sync before analysis
        engineer.start_sync()

        interrupted = False
        cancelled = False
        try:
            result = asyncio.run(engineer.analyze_and_generate())
            interrupted = isinstance(result, dict) and result.get("error") == "interrupted"
        except KeyboardInterrupt as exc:
            result = getattr(exc, "partial_result", None)
            # Python 3.11+ Runner translates SIGINT cancellation to
            # KeyboardInterrupt, with the tagged CancelledError as context.
            if result is None and isinstance(exc.__context__, asyncio.CancelledError):
                result = getattr(exc.__context__, "partial_result", None)
            interrupted = True
            console.print("\n  [dim]run aborted[/dim]")
        except asyncio.CancelledError as exc:
            result = getattr(exc, "partial_result", None)
            cancelled = True
        finally:
            # Always stop sync when done
            engineer.stop_sync()

        # Update session with results
        if result:
            usage = result.get("usage", {})
            session_manager.update_run(
                run_id=run_id,
                usage=_run_totals(resume.get("usage") or {}, usage) if resume else usage,
                paths={"script_path": result.get("script_path")},
            )
            _keep_session_cost(run_id, core.cost_before, usage)

        return {
            "run_id": run_id,
            "mode": mode_label,
            "script_path": (result or {}).get("script_path"),
            "usage": (result or {}).get("usage", {}),
            **(
                {"error": "interrupted"}
                if interrupted
                else {"error": "Agent analysis cancelled."}
                if cancelled
                else {"error": "Agent analysis produced no result."}
                if result is None
                else {}
            ),
        }

    except Exception as e:
        message = str(e) or type(e).__name__
        click.echo(f"error: {message}", err=True)
        click.echo(ERROR_CTA, err=True)
        if os.environ.get("RAE_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        else:
            logging.getLogger(__name__).debug("Auto mode failed", exc_info=True)
        return {
            "run_id": run_id,
            "mode": mode_label,
            "script_path": None,
            "usage": {},
            "error": message,
            "error_reported": True,
        }


@main.command(
    epilog="""\b
Examples:
  reverse-api-engineer engineer abc123def456
  reverse-api-engineer engineer abc123def456 -p "add pagination support"
  reverse-api-engineer engineer abc123def456 --fresh -p "extract auth flow only"
  reverse-api-engineer engineer abc123def456 --json | jq

\b
JSON output schema (--json):
  {
    "schema_version": 1,
    "status": "ok" | "error",
    "run_id": "<id>",
    "prompt": "..." | null,
    "fresh": false,
    "script_path": "/abs/path/api_client.py" | null,
    "usage": {
      "input_tokens": ...,
      "output_tokens": ...,
      "cache_read_tokens": ...,
      "cache_write_tokens": ...,
      "total_cost_usd": ...,
      "raw": { ... }
    },
    "error": "<message>" | null,
    "error_kind": "misuse" | "config_invalid" | "permission_denied" | "network" | "engine_failure" | "interrupted" | "unknown" | null
  }

\b
Exit codes:
  0  success
  1  runtime error (engineering failed, run not found)
  2  misuse
"""
)
@click.argument("run_id", required=False)
@click.option(
    "--prompt",
    "-p",
    default=None,
    help=(
        "With --fresh: replace the captured run's original goal. "
        "Without --fresh: layered as additional instructions on top of the original prompt."
    ),
)
@click.option(
    "--fresh",
    is_flag=True,
    help="Ignore previously generated scripts and re-engineer from scratch.",
)
@click.option(
    "--model",
    "-m",
    type=ModelChoice(),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Reserved for symmetry with `agent`/`run`; engineer mode is non-interactive by design.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit a single JSON result on stdout (logs go to stderr). Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help="Emit NDJSON progress events on stdout during the run, then a final {\"event\":\"result\",...} line. Implies --no-interactive.",
)
def engineer(
    run_id: str | None,
    prompt: str | None,
    fresh: bool,
    model: str | None,
    output_dir: str | None,
    no_interactive: bool,
    as_json: bool,
    json_stream: bool,
) -> None:
    """Run reverse engineering on a previous run."""
    # `run_id` is declared optional at the click level so that wrappers using
    # --json get a JSON misuse payload instead of Click's plain-text "missing
    # argument" error. We re-validate inline to preserve the same exit-2 UX
    # for non-JSON invocations.
    if not run_id:
        machine_output = as_json or json_stream
        if machine_output:
            misuse = _build_engineer_payload(
                None,
                run_id="",
                prompt=prompt,
                fresh=fresh,
                error="RUN_ID is required",
                error_kind_hint="misuse",
            )
            if json_stream:
                with _quiet_consoles_for_json() as real_stdout:
                    _write_json_stdout(real_stdout, misuse, json_stream=True)
            else:
                click.echo(json.dumps(misuse))
        else:
            click.echo("Usage: reverse-api-engineer engineer [OPTIONS] RUN_ID", err=True)
            click.echo("\nError: Missing argument 'RUN_ID'.", err=True)
        sys.exit(2)

    # --fresh treats --prompt as a full replacement of the original goal;
    # without --fresh, --prompt is additive so the captured run's context is preserved.
    main_prompt = prompt if fresh else None
    additional = prompt if (prompt and not fresh) else None
    # Either flag must suppress the post-generation follow-up prompt that
    # would otherwise block on stdin (`input("  > ")`) inside ClaudeEngineer.
    no_interactive = no_interactive or as_json or json_stream
    interactive = not no_interactive
    machine_output = as_json or json_stream

    if interactive and _in_terminal():
        open_session(
            "engineer",
            model,
            prompt or run_id,
            lambda: run_engineer(
                run_id, prompt=main_prompt, additional_instructions=additional, model=model, output_dir=output_dir, is_fresh=fresh
            ),
            lambda p, m: engineer_from_prompt(p, m or model, output_dir),
        )
        return
    if not machine_output:
        result = run_engineer(
            run_id,
            prompt=main_prompt,
            additional_instructions=additional,
            model=model,
            output_dir=output_dir,
            is_fresh=fresh,
            interactive=interactive,
        )
        if isinstance(result, dict) and result.get("error_kind") == "misuse":
            sys.exit(2)
        return

    from .json_stream import make_json_stream_sink

    with _quiet_consoles_for_json() as real_stdout:
        sink = (
            make_json_stream_sink(lambda line: _write_json_line(real_stdout, line))
            if json_stream
            else None
        )
        result = None
        try:
            result = run_engineer(
                run_id,
                prompt=main_prompt,
                additional_instructions=additional,
                model=model,
                output_dir=output_dir,
                is_fresh=fresh,
                interactive=interactive,
                json_event_sink=sink,
            )
            payload = _build_engineer_payload(result, run_id=run_id, prompt=prompt, fresh=fresh)
        except KeyboardInterrupt as e:
            payload = _build_engineer_payload(
                None, run_id=run_id, prompt=prompt, fresh=fresh, error=e
            )
        except Exception as e:
            # Pass the exception object so _classify_error can use isinstance.
            payload = _build_engineer_payload(
                None, run_id=run_id, prompt=prompt, fresh=fresh, error=e
            )

        _write_json_stdout(real_stdout, payload, json_stream=json_stream)
    if isinstance(result, dict) and result.get("error_kind") == "misuse":
        sys.exit(2)
    sys.exit(0 if payload["status"] == "ok" else 1)


def engineer_from_prompt(text: str, model: str | None = None, output_dir: str | None = None) -> dict[str, Any] | None:
    """A prompt in engineer mode: a known run id re-engineers that run; anything else is an instruction for the latest run."""
    if session_manager.get_run(text):
        return run_engineer(text, model=model, output_dir=output_dir)
    # Collector runs capture no traffic; run_engineer explains any other run that has none.
    latest = next((r for r in session_manager.get_history(limit=50) if r.get("mode") != "collector"), None)
    if latest is None:
        raise RuntimeError("no captured runs yet · start one in agent or manual mode")
    return run_engineer(latest["run_id"], model=model, output_dir=output_dir, additional_instructions=text)


def run_engineer(
    run_id: str,
    har_path: Path | None = None,
    prompt: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
    additional_instructions: str | None = None,
    is_fresh: bool = False,
    output_mode: str = "client",
    interactive: bool = True,
    json_event_sink: Callable[[dict[str, Any]], None] | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Shared logic for reverse engineering. ``resume`` is the run's history entry when reopening its session."""
    if not har_path or not prompt:
        # Load from history if possible
        run_data = session_manager.get_run(run_id)
        if not run_data:
            # Fallback to file search if not in history
            har_dir = get_har_dir(run_id, output_dir)
            har_path = har_dir / "recording.har"
            if not har_path.exists():
                console.print(f" [red]not found:[/red] {run_id}")
                return None
            if not prompt:
                prompt = "Reverse engineer captured APIs" if output_mode == "client" else "Generate OpenAPI documentation"
        else:
            if not prompt:
                prompt = run_data["prompt"]
            # Detect where it was saved
            paths = run_data.get("paths", {})
            har_dir = Path(paths.get("har_dir", get_har_dir(run_id, None)))
            har_path = har_dir / "recording.har"
            if not har_path.exists() and not resume:
                if run_data.get("mode") == "chrome-mcp":
                    message = (
                        f"run {run_id} was captured with chrome-mcp, which saves no HAR, so engineer cannot "
                        "regenerate it; run `agent` again, or set agent_provider to \"auto\" to keep a HAR"
                    )
                else:
                    message = f"run {run_id} has no HAR at {har_path}"
                console.print(f" [red]error:[/red] {message}")
                return {"error": message, "error_kind": "misuse", "error_reported": True}

    sdk = _session_sdk(resume) or config_manager.get("sdk", "claude")
    enable_sync = config_manager.get("real_time_sync", True)
    output_language = config_manager.get("output_language", "python")
    resume_session, cost_before = _resume_point(resume) if resume else (None, 0.0)
    # OpenCode and Copilot take their model from settings, except when reopening a session made with another.
    resume_model = (resume or {}).get("sdk_session", {}).get("model")
    session_model = {
        "opencode": resume_model or config_manager.get("opencode_model", DEFAULT_OPENCODE_MODEL),
        "copilot": resume_model or config_manager.get("copilot_model", "gpt-5"),
        "cursor": model or config_manager.get("cursor_model", "composer-2.5"),
    }.get(sdk) or model or config_manager.get("claude_code_model", "claude-sonnet-4-6")
    on_session = _session_recorder(run_id, "engineer", sdk, session_model, output_dir, output_mode)

    if sdk == "opencode":
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            sdk=sdk,
            opencode_provider=_session_provider(resume) or config_manager.get("opencode_provider", DEFAULT_OPENCODE_PROVIDER),
            opencode_model=session_model,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
            resume_session=resume_session,
            cost_before=cost_before,
            on_session=on_session,
        )
    elif sdk == "copilot":
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            sdk=sdk,
            copilot_model=session_model,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
            resume_session=resume_session,
            cost_before=cost_before,
            on_session=on_session,
        )
    elif sdk == "cursor":
        _cs = config_manager.get("cursor_setting_sources")
        _cursor_src = _cs if isinstance(_cs, list) and all(isinstance(x, str) for x in _cs) else None
        _cm = model or config_manager.get("cursor_model", "composer-2.5")
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=_cm,
            output_dir=output_dir,
            sdk=sdk,
            cursor_model=_cm,
            cursor_web_search=bool(config_manager.get("cursor_web_search", True)),
            cursor_setting_sources=_cursor_src,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
            resume_session=resume_session,
            cost_before=cost_before,
            on_session=on_session,
        )
    else:
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model or config_manager.get("claude_code_model", "claude-sonnet-4-6"),
            output_dir=output_dir,
            sdk=sdk,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
            json_event_sink=json_event_sink,
            resume_session=resume_session,
            cost_before=cost_before,
            on_session=on_session,
        )

    # A run stopped before its first turn finished has nothing to copy or record.
    if result and result.get("script_path"):
        # Skip manual copy if real-time sync is enabled (files already synced)
        if not enable_sync:
            # Automatically copy to current directory with a readable name
            output_dir_path = Path(result["script_path"]).parent
            base_name = generate_folder_name(prompt, sdk=sdk)

            # Choose base path based on output mode
            if output_mode == "docs":
                base_path = Path.cwd() / "docs"
            else:
                base_path = Path.cwd() / "scripts"

            from .sync import get_available_directory

            # Get available directory (won't overwrite existing non-empty dirs)
            local_dir = get_available_directory(base_path, base_name)
            local_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            for item in output_dir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, local_dir / item.name)

            from .repl.bridge import active

            # The session's card already names a client; there only docs and the copy are news.
            if (session := active()) is not None:
                if output_mode == "docs":
                    session.docs_ready(Path(result["script_path"]))
                session.copied(local_dir.resolve())
            elif output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./docs/{local_dir.name}[/white]\n")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./scripts/{local_dir.name}[/white]\n")
        elif _in_session():
            if output_mode == "docs":
                from .repl.bridge import active

                if (session := active()) is not None:
                    session.docs_ready(Path(result["script_path"]))
        else:
            # With sync enabled, just show completion
            if output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
            console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]\n")

        usage = result.get("usage", {})
        session_manager.update_run(
            run_id=run_id,
            sdk=sdk,
            output_mode=output_mode,
            usage=_run_totals(resume.get("usage") or {}, usage) if resume else usage,
            paths={"script_path": result.get("script_path")},
        )
        _keep_session_cost(run_id, cost_before, usage)
    return result


def resumable(run: dict[str, Any] | None) -> bool:
    return bool(((run or {}).get("sdk_session") or {}).get("id"))



def _session_sdk(resume: dict[str, Any] | None) -> str | None:
    """The SDK a resumed run's session belongs to; sessions saved before the SDK was recorded were Claude's."""
    if not resume:
        return None
    return str(resume["sdk_session"].get("sdk") or "claude")


def _session_provider(resume: dict[str, Any] | None) -> str | None:
    """The OpenCode provider a resumed session ran with; its saved model only exists there."""
    return str((resume or {}).get("sdk_session", {}).get("provider") or "") or None


def _resume_point(resume: dict[str, Any]) -> tuple[str, float]:
    """The session to reopen and what that session (not the whole run) had cost so far."""
    session = resume["sdk_session"]
    # Sessions saved before their own cost was kept fall back to the run's total, which was theirs then.
    cost = session["cost"] if "cost" in session else (resume.get("usage") or {}).get("estimated_cost_usd")
    return str(session["id"]), float(cost or 0)


def _session_recorder(
    run_id: str, mode: str, sdk: str, model: str | None, output_dir: str | None, output_mode: str = "client", headless: bool = False
) -> Callable[[str], None]:
    """Saves an engine's SDK session on its run as soon as the SDK names it, so even a cut-short run can be resumed.

    The session keeps what reopening it needs: its SDK and model, and the output folder, which fixes the
    workspace the SDK filed the session under.
    """
    session: dict[str, Any] = {
        "mode": mode,
        "sdk": sdk,
        "model": model,
        "output_dir": str(get_base_output_dir(output_dir).resolve()),
        "output_mode": output_mode,
    }
    if sdk == "opencode":
        session["provider"] = config_manager.get("opencode_provider", DEFAULT_OPENCODE_PROVIDER)
    if sdk == "claude" and not predates_effort(model):
        from .repl.view import default_effort

        # The effort the run thinks at, for the card a resume replays.
        session["effort"] = build_sdk_effort(model).get("effort") or default_effort(model)
    if headless:
        session["headless"] = True  # a resume keeps its own browser rather than attaching to the user's Chrome
    return lambda sid: session_manager.update_run(run_id=run_id, sdk_session={**session, "id": sid, "cost": 0.0})


def _keep_session_cost(run_id: str, cost_before: float, usage: dict[str, Any]) -> None:
    """Stores the session's own running cost: what a later resume takes off the SDK's whole-session total."""
    session = (session_manager.get_run(run_id) or {}).get("sdk_session")
    if session:
        cost = cost_before + float(usage.get("estimated_cost_usd") or 0)
        session_manager.update_run(run_id=run_id, sdk_session={**session, "cost": cost})


def _counter(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _run_totals(before: dict[str, Any], now: dict[str, Any]) -> dict[str, Any]:
    """A resumed run's usage: every counter of this stretch (tokens, costs, whatever the SDK reports) added to the run's."""
    totals = {**before, **now}
    for key, value in now.items():
        if _counter(value) and _counter(before.get(key)):
            totals[key] = before[key] + value
    return totals


def resume_run(run_id: str) -> dict[str, Any] | None:
    """Reopen a past run's SDK session with the SDK it ran on; the user's next message continues that conversation."""
    run = session_manager.get_run(run_id)
    if run is None or not resumable(run):
        console.print(f" [dim]run {escape(run_id)} has no saved session to resume[/dim]")
        return None
    session = run["sdk_session"]
    model = session.get("model") or run.get("model") or None
    output_dir = session.get("output_dir")
    if session.get("mode") == "agent":
        provider = str(run["mode"]) if run.get("mode") in ("chrome-mcp", "agent-browser") else "auto"
        return run_auto_capture(
            prompt=run["prompt"],
            url=run.get("url"),
            model=model,
            output_dir=output_dir,
            agent_provider=provider,
            headless=bool(session.get("headless")),
            resume=run,
        )
    return run_engineer(run_id, model=model, output_dir=output_dir, output_mode=session.get("output_mode") or "client", resume=run)


def _get_run_details(run: dict) -> dict:
    """Enrich a history entry with filesystem info."""
    run_id = run.get("run_id", "")
    output_dir = config_manager.get("output_dir")
    base_dir = get_base_output_dir(output_dir)
    script_dir = base_dir / "scripts" / run_id

    files = []
    if script_dir.exists():
        files = sorted(f.name for f in script_dir.iterdir() if f.is_file())

    # Scan ./scripts/ subdirectories to find local copy
    local_path = None
    local_scripts = Path.cwd() / "scripts"
    if local_scripts.exists() and files:
        files_set = set(files)
        for subdir in local_scripts.iterdir():
            if subdir.is_dir():
                local_files = {f.name for f in subdir.iterdir() if f.is_file()}
                if local_files and local_files == files_set:
                    local_path = f"./scripts/{subdir.name}/"
                    break

    cost = recorded_cost(run.get("usage"))

    return {
        "run_id": run_id,
        "prompt": run.get("prompt", ""),
        "timestamp": run.get("timestamp", ""),
        "model": run.get("model", ""),
        "mode": run.get("mode", ""),
        "sdk": run.get("sdk", ""),
        "cost": cost,
        "script_dir": str(script_dir),
        "files": files,
        "file_count": len(files),
        "local_path": local_path,
    }


@main.command(
    "list",
    epilog="""\b
Examples:
  reverse-api-engineer list
  reverse-api-engineer list --mode auto --search jobs --json | jq

JSON output (--json) is always a flat array (possibly empty []).
""",
)
@click.option("--json", "as_json", is_flag=True, help="Output as flat JSON array.")
@click.option("--full", is_flag=True, help="Show all columns (default: compact view).")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results.")
@click.option("--mode", "-m", type=str, default=None, help="Filter by mode (auto/manual/agent/engineer/collector).")
@click.option("--model", type=str, default=None, help="Filter by model name.")
@click.option("--search", "-s", type=str, default=None, help="Case-insensitive substring match on prompt.")
def list_runs(as_json: bool, full: bool, limit: int | None, mode: str | None, model: str | None, search: str | None) -> None:
    """List generated scripts and runs with optional filters."""
    from rich.table import Table

    runs = list(session_manager.history)

    if mode:
        runs = [r for r in runs if r.get("mode", "") == mode]
    if model:
        runs = [r for r in runs if model.lower() in (r.get("model") or "").lower()]
    if search:
        runs = [r for r in runs if search.lower() in (r.get("prompt") or "").lower()]

    if not runs:
        if as_json:
            click.echo(json.dumps([]))
        elif not session_manager.history:
            console.print("No runs found.", style="dim")
        else:
            console.print("No matching runs found.")
        return

    if limit is not None:
        runs = runs[:limit]

    results = [_get_run_details(r) for r in runs]

    if as_json:
        click.echo(json.dumps(results, indent=2))
        return

    if full:
        table = Table(show_lines=False)
        table.add_column("run_id", style="cyan")
        table.add_column("prompt", max_width=40)
        table.add_column("timestamp")
        table.add_column("model")
        table.add_column("mode")
        table.add_column("sdk")
        table.add_column("cost", justify="right")
        table.add_column("script_dir")
        table.add_column("files", justify="right")
        for r in results:
            prompt = r["prompt"][:40] + ("..." if len(r["prompt"]) > 40 else "")
            cost_str = f"${r['cost']:.2f}" if r["cost"] is not None else ""
            table.add_row(
                r["run_id"],
                prompt,
                r["timestamp"],
                r["model"] or "",
                r["mode"] or "",
                r["sdk"] or "",
                cost_str,
                r["script_dir"],
                str(r["file_count"]),
            )
    else:
        table = Table(show_lines=False)
        table.add_column("run_id", style="cyan")
        table.add_column("prompt", max_width=40)
        table.add_column("timestamp")
        table.add_column("script_dir")
        for r in results:
            prompt = r["prompt"][:40] + ("..." if len(r["prompt"]) > 40 else "")
            table.add_row(
                r["run_id"],
                prompt,
                r["timestamp"],
                r["script_dir"],
            )

    console.print(table)


@main.command(
    "show",
    epilog="""\b
Examples:
  reverse-api-engineer show
  reverse-api-engineer show <run_id> --json | jq

\b
Exit codes (--json):
  0  run found
  1  run not found / no history
""",
)
@click.argument("run_id", required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON object.")
def show_run(run_id: str | None, as_json: bool) -> None:
    """Show detailed info for a specific run."""
    from rich.table import Table
    from rich.text import Text

    def _show_error_payload(message: str, rid: str | None = None) -> dict:
        return {
            "schema_version": AGENT_JSON_SCHEMA_VERSION,
            "status": "error",
            "run_id": rid,
            "error": message,
            "error_kind": _classify_error(message, default="engine_failure"),
        }

    if run_id:
        run = session_manager.get_run(run_id)
    elif session_manager.history:
        run = session_manager.history[0]
    else:
        if as_json:
            click.echo(json.dumps(_show_error_payload("no runs found")))
            sys.exit(1)
        console.print("No runs found.", style="dim")
        return

    if run is None:
        if as_json:
            click.echo(json.dumps(_show_error_payload("run not found", run_id)))
            sys.exit(1)
        console.print(f"Run not found: {run_id}")
        return

    details = _get_run_details(run)
    rid = details["run_id"]
    output_dir = config_manager.get("output_dir")
    base_dir = get_base_output_dir(output_dir)

    # Extra fields
    details["url"] = run.get("url")
    details["output_mode"] = run.get("output_mode", "client")

    # Each SDK names its cache counts differently; the keys of show --json stay Claude's.
    usage = _normalize_usage(run.get("usage"))
    details["input_tokens"] = usage.get("input_tokens", 0)
    details["output_tokens"] = usage.get("output_tokens", 0)
    details["cache_creation_input_tokens"] = usage.get("cache_write_tokens", 0)
    details["cache_read_input_tokens"] = usage.get("cache_read_tokens", 0)

    # Artifact paths with existence
    har_dir = base_dir / "har" / rid
    messages_path = get_messages_path(rid, output_dir)
    script_dir = Path(details["script_dir"])

    details["har_dir"] = str(har_dir)
    details["har_dir_exists"] = har_dir.exists()
    details["messages_path"] = str(messages_path)
    details["messages_path_exists"] = messages_path.exists()
    details["script_dir_exists"] = script_dir.exists()

    # HAR entry count
    har_entries = None
    if har_dir.exists():
        recording = har_dir / "recording.har"
        if recording.exists():
            try:
                har_data = json.loads(recording.read_text(encoding="utf-8-sig"))
                har_entries = len(har_data.get("log", {}).get("entries", []))
            except Exception:
                pass
    details["har_entries"] = har_entries

    if as_json:
        details["schema_version"] = AGENT_JSON_SCHEMA_VERSION
        details["status"] = "ok"
        details["error"] = None
        details["error_kind"] = None
        click.echo(json.dumps(details, indent=2))
        return

    # Rich table output
    table = Table(show_header=False, show_lines=True)
    table.add_column(style="bold cyan")
    table.add_column()

    def _path_val(path_str: str, exists: bool) -> Text:
        t = Text(path_str + " ")
        t.append("✓" if exists else "✗", style="green" if exists else "red")
        return t

    rows: list[tuple[str, Text | str | None]] = [
        ("prompt", details["prompt"]),
        ("timestamp", details["timestamp"]),
        ("model", details["model"]),
        ("mode", details["mode"]),
        ("sdk", details["sdk"]),
        ("output_mode", details["output_mode"]),
        ("url", details.get("url")),
        ("cost", f"${details['cost']:.2f}" if details["cost"] is not None else None),
        ("input_tokens", str(details["input_tokens"])),
        ("output_tokens", str(details["output_tokens"])),
        ("cache_creation", str(details["cache_creation_input_tokens"])),
        ("cache_read", str(details["cache_read_input_tokens"])),
        ("har_dir", _path_val(details["har_dir"], details["har_dir_exists"])),
        ("har_entries", str(har_entries) if har_entries is not None else None),
        ("script_dir", _path_val(details["script_dir"], details["script_dir_exists"])),
    ]

    files = details["files"]
    if files:
        rows.append(("files", ", ".join(files) + f" ({len(files)})"))

    rows.append(("local_path", details.get("local_path")))
    rows.append(("messages", _path_val(details["messages_path"], details["messages_path_exists"])))

    for key, val in rows:
        if val is None or val == "":
            continue
        table.add_row(key, val if isinstance(val, Text) else str(val))

    console.print(f"\nRun {rid}")
    console.print(table)


def _extract_missing_module(stderr: str) -> str | None:
    """Extract a missing top-level module name from a ModuleNotFoundError message.

    Returns None if no module name is found or the name is not a plain Python
    identifier — a genuine ModuleNotFoundError always names one, and rejecting
    anything else prevents a crafted error message from smuggling pip options
    or arbitrary install targets.
    """
    import re as _re

    match = _re.search(r"No module named ['\"]([^'\"]+)['\"]", stderr)
    if not match:
        return None
    missing = match.group(1).split(".")[0]
    # fullmatch, since $ in re.match would accept a trailing newline
    if not _re.fullmatch(r"[a-zA-Z0-9_]+", missing) or len(missing) > 64:
        return None
    return missing


def _run_non_python_script(script: Path, script_args: tuple[str, ...]) -> None:
    """Run a non-Python generated client with its language's toolchain and exit."""
    import shutil
    import subprocess

    from .runtime_commands import resolve_windows_command
    from .utils import build_script_commands

    try:
        steps, tool = build_script_commands(script, script_args)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    executable = shutil.which(tool)
    if executable is None:
        raise click.ClickException(f"cannot run {script.name}: '{tool}' is missing from PATH — install it and retry")
    if sys.platform == "win32":
        try:
            steps[0] = resolve_windows_command([executable, *steps[0][1:]])
        except ValueError as e:
            raise click.ClickException(str(e)) from e
    returncode = 0
    for cmd in steps:
        returncode = subprocess.run(cmd, cwd=str(script.parent)).returncode
        if returncode != 0:
            break
    raise SystemExit(returncode)


def _run_script_machine_payload(
    *,
    identifier: str,
    script_args: tuple[str, ...],
    file_name: str | None,
    list_scripts: bool,
    auto_install: bool,
    emit_event: CliEventEmitter,
) -> dict:
    """Run or list generated scripts without prompts and with JSON-safe stdout."""
    import subprocess

    from .runtime_commands import decode_process_output

    run_id: str | None = None
    script: Path | None = None
    scripts: list[Path] = []

    try:
        run = resolve_run(identifier, session_manager, interactive=False)
        run_id = run["run_id"]
        output_dir = config_manager.get("output_dir")
        scripts = discover_scripts(run_id, output_dir, run_metadata=run)
        emit_event("run_resolved", run_id=run_id, script_count=len(scripts))

        if not scripts:
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                error=f"No runnable scripts found for run {run_id}",
                error_kind_hint="engine_failure",
            )

        if list_scripts:
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                returncode=0,
            )

        if file_name:
            matching = [s for s in scripts if s.name == file_name]
            if not matching:
                available = ", ".join(s.name for s in scripts)
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    scripts=scripts,
                    error=f"'{file_name}' not found. Available: {available}",
                    error_kind_hint="misuse",
                )
            script = matching[0]
        elif len(scripts) == 1:
            script = scripts[0]
        else:
            available = ", ".join(s.name for s in scripts)
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                scripts=scripts,
                error=(f"multiple scripts found for run {run_id}; pass --file <name> to choose. Available: {available}"),
                error_kind_hint="misuse",
            )

        emit_event("script_selected", run_id=run_id, script_path=str(script))

        if script.suffix != ".py":
            import shutil

            from .utils import build_script_commands

            try:
                steps, tool = build_script_commands(script, script_args)
            except ValueError as e:
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    scripts=scripts,
                    error=str(e),
                    error_kind_hint="misuse",
                )
            executable = shutil.which(tool)
            if executable is None:
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    scripts=scripts,
                    error=f"cannot run {script.name}: '{tool}' is missing from PATH — install it and retry",
                    error_kind_hint="config_invalid",
                )
            if sys.platform == "win32":
                from .runtime_commands import resolve_windows_command

                try:
                    steps[0] = resolve_windows_command([executable, *steps[0][1:]])
                except ValueError as e:
                    return _build_run_payload(
                        identifier=identifier,
                        run_id=run_id,
                        script_path=str(script),
                        script_args=script_args,
                        scripts=scripts,
                        error=str(e),
                        error_kind_hint="config_invalid",
                    )
            binary_result = None
            for cmd in steps:
                emit_event("process_started", run_id=run_id, script_path=str(script))
                binary_result = subprocess.run(cmd, cwd=str(script.parent), capture_output=True)
                if binary_result.returncode != 0:
                    break
            assert binary_result is not None, "build_script_commands returned no execution steps"
            return _build_run_payload(
                identifier=identifier,
                run_id=run_id,
                script_path=str(script),
                script_args=script_args,
                returncode=binary_result.returncode,
                stdout=decode_process_output(binary_result.stdout),
                stderr=decode_process_output(binary_result.stderr),
                scripts=scripts,
            )

        from .utils import get_base_output_dir as _get_base

        venv_dir = _get_base(output_dir) / ".venv"
        venv_bin = "Scripts" if sys.platform == "win32" else "bin"
        venv_python = venv_dir / venv_bin / ("python.exe" if sys.platform == "win32" else "python")
        venv_pip = venv_dir / venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")

        if not venv_dir.exists():
            emit_event("venv_setup_started", run_id=run_id, path=str(venv_dir))
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True, text=True, errors="replace")
            subprocess.run([str(venv_pip), "install", "-q", "requests"], check=True, capture_output=True, text=True, errors="replace")
            emit_event("venv_setup_completed", run_id=run_id, path=str(venv_dir))

        requirements = script.parent / "requirements.txt"
        if requirements.exists():
            emit_event("requirements_install_started", run_id=run_id, path=str(requirements))
            subprocess.run([str(venv_pip), "install", "-q", "-r", str(requirements)], check=True, capture_output=True, text=True, errors="replace")
            emit_event("requirements_install_completed", run_id=run_id, path=str(requirements))

        cmd = [str(venv_python), str(script), *script_args]
        emit_event("process_started", run_id=run_id, script_path=str(script))
        def run_client() -> subprocess.CompletedProcess[str]:
            captured = subprocess.run(
                cmd, capture_output=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            return subprocess.CompletedProcess(
                captured.args, captured.returncode,
                decode_process_output(captured.stdout, utf8_stream=True),
                decode_process_output(captured.stderr, utf8_stream=True),
            )

        result = run_client()

        stderr = result.stderr or ""
        if result.returncode != 0 and "ModuleNotFoundError: No module named" in stderr:
            missing = _extract_missing_module(stderr)
            if missing:
                emit_event("dependency_missing", run_id=run_id, package=missing)
                if auto_install:
                    emit_event("dependency_install_started", run_id=run_id, package=missing)
                    subprocess.run([str(venv_pip), "install", "-q", missing], check=True, capture_output=True, text=True, errors="replace")
                    emit_event("dependency_install_completed", run_id=run_id, package=missing)
                    emit_event("process_retried", run_id=run_id, script_path=str(script))
                    result = run_client()
                else:
                    return _build_run_payload(
                        identifier=identifier,
                        run_id=run_id,
                        script_path=str(script),
                        script_args=script_args,
                        returncode=result.returncode,
                        stdout=result.stdout or "",
                        stderr=stderr,
                        scripts=scripts,
                        error=f"missing dependency: {missing}",
                        error_kind_hint="engine_failure",
                    )
            elif auto_install:
                # Keep the refusal observable instead of falling through to a
                # generic script-exit error
                return _build_run_payload(
                    identifier=identifier,
                    run_id=run_id,
                    script_path=str(script),
                    script_args=script_args,
                    returncode=result.returncode,
                    stdout=result.stdout or "",
                    stderr=stderr,
                    scripts=scripts,
                    error="refusing to auto-install: no safe package name could be extracted from the ModuleNotFoundError output",
                    error_kind_hint="engine_failure",
                )

        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script),
            script_args=script_args,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            scripts=scripts,
        )
    except click.ClickException as e:
        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script) if script else None,
            script_args=script_args,
            scripts=scripts,
            error=e.message,
            error_kind_hint="misuse",
        )
    except Exception as e:
        return _build_run_payload(
            identifier=identifier,
            run_id=run_id,
            script_path=str(script) if script else None,
            script_args=script_args,
            scripts=scripts,
            error=e,
            error_kind_hint="engine_failure",
        )


@main.command(
    "run",
    epilog="""\b
Examples:
  reverse-api-engineer run a450e520ca30
  reverse-api-engineer run ashby --ls
  reverse-api-engineer run ashby --file api_client.py -- --org acme --limit 10
  reverse-api-engineer run a450e520ca30 --file api_client.py --no-interactive --auto-install
  reverse-api-engineer run a450e520ca30 --file api_client.py --json | jq
  reverse-api-engineer run a450e520ca30 --file api_client.py --json-stream

\b
Exit codes:
  <script's exit code>  the underlying script's return code (0 on success)
  1                     no script found for the run
  non-zero              missing --file when multiple scripts exist under --no-interactive
""",
)
@click.argument("identifier")
@click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--file", "-f", "file_name", default=None, help="Script filename to run (e.g. api_client.py).")
@click.option("--ls", "list_scripts", is_flag=True, help="List available scripts without executing.")
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Fail fast on script-picker / missing-dependency prompts (intended for scripted/agent usage).",
)
@click.option(
    "--auto-install",
    is_flag=True,
    help="Auto-install missing dependencies on retry without prompting (implies --no-interactive for the picker).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit one JSON result on stdout with captured script stdout/stderr. Implies --no-interactive.",
)
@click.option(
    "--json-stream",
    "json_stream",
    is_flag=True,
    help='Emit NDJSON progress events on stdout, then a final {"event":"result",...} line. Implies --no-interactive.',
)
@click.pass_context
def run_script(
    ctx: click.Context,
    identifier: str,
    script_args: tuple[str, ...],
    file_name: str | None,
    list_scripts: bool,
    no_interactive: bool,
    auto_install: bool,
    as_json: bool,
    json_stream: bool,
) -> None:
    """Run a generated script from a previous run.

    IDENTIFIER is a run ID or search term to match against prompts.
    Any extra arguments after the identifier are passed to the script.

    Examples:

        reverse-api-engineer run a450e520ca30

        reverse-api-engineer run ashby --ls

        reverse-api-engineer run ashby --file api_client.py

        reverse-api-engineer run ashby -- --org acme --limit 10
    """
    import subprocess
    import sys

    from rich.table import Table

    machine_output = as_json or json_stream
    no_interactive = no_interactive or machine_output

    if machine_output:
        with _quiet_consoles_for_json() as real_stdout:

            def emit_event(event: str, **fields: Any) -> None:
                if json_stream:
                    _write_json_event(real_stdout, {"event": event, **fields})

            payload = _run_script_machine_payload(
                identifier=identifier,
                script_args=script_args,
                file_name=file_name,
                list_scripts=list_scripts,
                auto_install=auto_install,
                emit_event=emit_event,
            )
            _write_json_stdout(real_stdout, payload, json_stream=json_stream)

        if payload["returncode"] not in (None, 0):
            raise SystemExit(payload["returncode"])
        raise SystemExit(0 if payload["status"] == "ok" else 1)

    # Resolve which run
    run = resolve_run(identifier, session_manager, interactive=not no_interactive)
    run_id = run["run_id"]
    output_dir = config_manager.get("output_dir")

    # Discover scripts (prefer stored path from run metadata, fall back to output_dir)
    scripts = discover_scripts(run_id, output_dir, run_metadata=run)

    prompt_preview = (run.get("prompt") or "")[:80]
    ts = (run.get("timestamp") or "")[:19]
    console.print(f"{run_id}  {ts}  {prompt_preview}", style="dim")
    if scripts:
        console.print(f"{scripts[0].parent}", style="dim")

    if not scripts:
        console.print(f"[red]No runnable scripts found for run {run_id}[/red]")
        raise SystemExit(1)

    # --ls: just list and exit
    if list_scripts:
        table = Table(title=f"Scripts in run {run_id}")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Modified")
        for s in scripts:
            stat = s.stat()
            size = f"{stat.st_size:,} B"
            from datetime import datetime

            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            table.add_row(s.name, size, modified)
        console.print(table)
        return

    # Select script
    if file_name:
        # Exact filename match
        matching = [s for s in scripts if s.name == file_name]
        if not matching:
            available = ", ".join(s.name for s in scripts)
            raise click.ClickException(f"'{file_name}' not found. Available: {available}")
        script = matching[0]
    elif len(scripts) == 1:
        script = scripts[0]
    elif no_interactive or auto_install:
        available = ", ".join(s.name for s in scripts)
        raise click.ClickException(
            f"multiple scripts found for run {run_id}; pass --file <name> to choose. Available: {available}"
        )
    else:
        # Interactive picker
        choices = [questionary.Choice(title=s.name, value=s) for s in scripts]
        script = questionary.select(
            "Select script to run:",
            choices=choices,
        ).ask()
        if script is None:
            raise click.Abort()

    # Non-Python clients: dispatch on extension, no venv involved
    if script.suffix != ".py":
        _run_non_python_script(script, script_args)

    # Shared venv at ~/.reverse-api/runs/.venv (with requests pre-installed)
    from .utils import get_base_output_dir as _get_base

    venv_dir = _get_base(output_dir) / ".venv"
    venv_bin = "Scripts" if sys.platform == "win32" else "bin"
    venv_python = venv_dir / venv_bin / ("python.exe" if sys.platform == "win32" else "python")
    venv_pip = venv_dir / venv_bin / ("pip.exe" if sys.platform == "win32" else "pip")

    if not venv_dir.exists():
        console.print("Setting up shared venv...", style="dim")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        subprocess.run([str(venv_pip), "install", "-q", "requests"], check=True)
        console.print("Shared venv ready.", style="dim")

    # Install per-run requirements.txt if present
    scripts_dir = script.parent
    requirements = scripts_dir / "requirements.txt"
    if requirements.exists():
        subprocess.run([str(venv_pip), "install", "-q", "-r", str(requirements)], check=True)

    python_path = str(venv_python)

    # Execute with real-time stdout, capture stderr for import error detection
    cmd = [python_path, str(script), *script_args]
    launch_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        env=launch_env,
    )

    # Print stderr so the user sees it, then check for missing imports
    if result.stderr:
        sys.stderr.write(result.stderr)

    if result.returncode != 0:
        if "ModuleNotFoundError: No module named" in (result.stderr or ""):
            missing = _extract_missing_module(result.stderr)
            if missing:
                console.print(f"[yellow]Missing dependency: {missing}[/yellow]")

                if auto_install:
                    install = True
                elif no_interactive:
                    install = False
                else:
                    install = questionary.confirm(
                        f"Install '{missing}' and retry?", default=True
                    ).ask()
                if install:
                    subprocess.run([str(venv_pip), "install", "-q", missing], check=True)
                    console.print(f"Installed [green]{missing}[/green]. Retrying...")
                    retry_result = subprocess.run(cmd, env=launch_env)
                    raise SystemExit(retry_result.returncode)

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
