"""Codex CLI adapter for reverse-api-engineer.

Codex runs as a local codex exec --json subprocess. MCP configuration is
passed as per-invocation overrides, so RAE does not edit the user's Codex
configuration file.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base_engineer import BaseEngineer
from .utils import get_har_dir

DEFAULT_CODEX_MODEL = "gpt-6-luna"
RAE_PLAYWRIGHT_MCP_PACKAGE = "rae-playwright-mcp@0.0.9"


def resolve_codex_command() -> list[str] | None:
    """Return a directly executable Codex CLI command, including on Windows.

    npm installs a codex.cmd shim on Windows. Launching its JavaScript
    entrypoint through Node avoids passing model prompts through cmd.exe.
    """
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            app_bin_dir = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            try:
                app_clis = sorted(
                    app_bin_dir.glob("*/codex.exe"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                app_clis = []
            if app_clis:
                return [str(app_clis[0])]

    executable = shutil.which("codex")
    if not executable:
        return None

    if sys.platform == "win32" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        node = shutil.which("node")
        cli_js = Path(executable).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        if node and cli_js.is_file():
            return [node, str(cli_js)]

    return [executable]


def _is_codex_desktop_command(command: list[str]) -> bool:
    """Identify the Windows Desktop CLI that supports automatic approval review."""
    if sys.platform != "win32" or not command or not os.environ.get("LOCALAPPDATA"):
        return False
    root = (Path(os.environ["LOCALAPPDATA"]) / "OpenAI" / "Codex" / "bin").resolve()
    try:
        Path(command[0]).resolve().relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def codex_login_status() -> tuple[bool, str]:
    """Check CLI authentication without returning potentially identifying output."""
    command = resolve_codex_command()
    if not command:
        return False, "Codex CLI not found in PATH"
    try:
        result = subprocess.run(
            [*command, "login", "status"],
            capture_output=True,
            timeout=15,
            check=False,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"could not check Codex CLI login ({type(exc).__name__})"
    if result.returncode != 0:
        return False, "Codex CLI is not logged in; run codex login first"
    return True, "Codex CLI authenticated"


def _toml_string(value: str) -> str:
    """JSON basic strings use the same escapes needed by TOML basic strings."""
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


class CodexEngineer(BaseEngineer):
    """Generate an API client or OpenAPI spec with the authenticated Codex CLI."""

    def __init__(self, *args: Any, codex_model: str | None = None, **kwargs: Any) -> None:
        configured_model = codex_model if codex_model not in (None, "") else kwargs.get("model")
        if not configured_model or str(configured_model).lower() == "default":
            configured_model = DEFAULT_CODEX_MODEL
        kwargs["model"] = configured_model
        kwargs["sdk"] = "codex"
        super().__init__(*args, **kwargs)
        # Prompts and the browser subprocess run inside the output workspace,
        # so relative paths from the caller must not be interpreted there again.
        self.scripts_dir = self.scripts_dir.resolve()
        self.har_path = self.har_path.resolve()
        if self.existing_client_path is not None:
            self.existing_client_path = self.existing_client_path.resolve()
        self.codex_model = configured_model
        self._active_codex_tools: dict[str, str] = {}
        self._mcp_tool_calls: list[str] = []
        self._turn_error: str | None = None

    def _workspace_cwd(self) -> Path:
        """Keep Codex's workspace-write sandbox inside this RAE run directory."""
        return self.scripts_dir.parent.parent.resolve()

    def _codex_mcp_overrides(self, server_name: str, command: str, args: list[str], env: dict[str, str] | None = None) -> list[str]:
        """Build isolated Codex CLI overrides for one stdio MCP server."""
        prefix = f"mcp_servers.{server_name}"
        overrides = [
            f"{prefix}.command={_toml_string(command)}",
            f"{prefix}.args={_toml_array(args)}",
            f"{prefix}.required=true",
        ]
        if env:
            toml_env = "{" + ", ".join(f"{key} = {_toml_string(value)}" for key, value in sorted(env.items())) + "}"
            overrides.append(f"{prefix}.env={toml_env}")
        return [part for override in overrides for part in ("--config", override)]

    def _build_exec_args(self, prompt: str, mcp_overrides: list[str] | None = None) -> list[str]:
        command = resolve_codex_command()
        if not command:
            raise RuntimeError("Codex CLI not found in PATH")

        args = [*command, "exec"]
        args.extend(["--json", "--ignore-user-config"])
        if _is_codex_desktop_command(command):
            # Keep Desktop's approval reviewer; the --sandbox flag conflicts
            # with this mode, so select workspace scope through TOML instead.
            args.extend(["--approve-for-me", "--config", 'sandbox_mode="workspace-write"'])
        else:
            args.extend(["--sandbox", "workspace-write"])
        args.extend(["--cd", str(self._workspace_cwd()), "--skip-git-repo-check"])
        if self.codex_model.strip().lower() not in {"", "default"}:
            args.extend(["--model", self.codex_model])
        if mcp_overrides:
            args.extend(mcp_overrides)
        # Sandbox/cwd options belong to exec, not its resume subcommand.
        if self.resume_session:
            args.extend(["resume", self.resume_session])
        args.append(prompt)
        return args

    @staticmethod
    def _item_text(item: dict[str, Any]) -> str:
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if isinstance(content, list):
            parts = [str(part.get("text")) for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
            return "\n".join(parts)
        return ""

    @staticmethod
    def _tool_result_text(item: dict[str, Any]) -> str | None:
        value = item.get("result", item.get("output"))
        if value is None:
            for field in ("aggregated_output", "stdout", "stderr", "content"):
                value = item.get(field)
                if value is not None:
                    break
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    def _handle_codex_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        if event_type == "thread.started":
            self._record_session(event.get("thread_id"))
            return

        if event_type in {"turn.failed", "error"}:
            error = event.get("error") or event.get("message") or "Codex turn failed"
            self._turn_error = str(error)
            return

        if event_type == "turn.completed":
            usage = event.get("usage")
            if isinstance(usage, dict):
                # Codex input_tokens includes cached input; RAE's buckets are
                # disjoint. Codex TokenUsage::non_cached_input uses this same
                # subtraction: https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs
                total_input = usage.get("input_tokens", 0)
                cached_input = usage.get("cached_input_tokens", 0)
                if isinstance(total_input, (int, float)) and isinstance(cached_input, (int, float)):
                    self.usage_metadata["input_tokens"] = self.usage_metadata.get("input_tokens", 0) + max(
                        0, int(total_input) - int(cached_input)
                    )
                for source, target in (
                    ("cached_input_tokens", "cache_read_tokens"),
                    ("output_tokens", "output_tokens"),
                ):
                    value = usage.get(source)
                    if isinstance(value, (int, float)):
                        self.usage_metadata[target] = self.usage_metadata.get(target, 0) + int(value)
                self._report_usage()
            return

        if event_type not in {"item.started", "item.updated", "item.completed"}:
            return
        item = event.get("item")
        if not isinstance(item, dict):
            return

        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or item.get("item_id") or "")
        if item_type == "agent_message" and event_type == "item.completed":
            text = self._item_text(item)
            if text:
                self.ui.thinking_block(text)
                self.message_store.save_thinking(text)
            return

        if item_type == "mcp_tool_call":
            server = str(item.get("server") or item.get("server_name") or "mcp")
            tool = str(item.get("tool") or item.get("name") or "tool")
            tool_name = f"mcp__{server}__{tool}"
            if server.lower().startswith("playwright") and (
                event_type == "item.started" or item_id not in self._active_codex_tools
            ):
                self._mcp_tool_calls.append(tool_name)
            if event_type == "item.started" and item_id and item_id not in self._active_codex_tools:
                tool_input = item.get("arguments") or item.get("input") or {}
                if not isinstance(tool_input, dict):
                    tool_input = {"arguments": tool_input}
                self._active_codex_tools[item_id] = tool_name
                self.ui.tool_start(tool_name, tool_input, call_id=item_id or None)
                self.message_store.save_tool_start(tool_name, tool_input)
            elif event_type == "item.completed":
                if item_id in self._active_codex_tools:
                    tool_name = self._active_codex_tools.pop(item_id)
                is_error = bool(item.get("is_error") or item.get("status") == "error")
                output = self._tool_result_text(item)
                self.ui.tool_result(tool_name, is_error, output, call_id=item_id or None)
                self.message_store.save_tool_result(tool_name, is_error, output)
            return

        if item_type == "command_execution":
            command = str(item.get("command") or "")
            if event_type == "item.started" and item_id and item_id not in self._active_codex_tools:
                self._active_codex_tools[item_id] = "Bash"
                self.ui.tool_start("Bash", {"command": command}, call_id=item_id or None)
                self.message_store.save_tool_start("Bash", {"command": command})
            elif event_type == "item.completed" and item_id in self._active_codex_tools:
                tool_name = self._active_codex_tools.pop(item_id)
                output = self._tool_result_text(item)
                is_error = bool(item.get("status") in {"failed", "declined", "error"} or item.get("exit_code") not in (None, 0))
                self.ui.tool_result(tool_name, is_error, output, call_id=item_id or None)
                self.message_store.save_tool_result(tool_name, is_error, output)

    async def _run_codex(  # noqa: C901 - stream parsing, process teardown, output validation
        self, prompt: str, mcp_overrides: list[str] | None = None, mode: str = "engineer"
    ) -> dict[str, Any] | None:
        try:
            argv = self._build_exec_args(prompt, mcp_overrides)
        except Exception as exc:
            message = str(exc)
            self.ui.error(message)
            self.message_store.save_error(message)
            return None

        self._turn_error = None
        self._active_codex_tools.clear()
        # Retain capture evidence across code-only follow-up turns.
        self.ui.header(self.run_id, self.prompt, self.codex_model, "codex", mode=mode)
        self.ui.start_analysis()

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace_cwd()),
                env=os.environ.copy(),
                limit=32 * 1024 * 1024,
            )
        except OSError as exc:
            message = f"Failed to start Codex CLI: {type(exc).__name__}: {exc}"
            self.ui.error(message)
            self.message_store.save_error(message)
            return None

        stderr_tail = bytearray()

        async def pump_stderr() -> None:
            assert proc.stderr is not None
            while chunk := await proc.stderr.read(65536):
                stderr_tail.extend(chunk)
                if len(stderr_tail) > 32768:
                    del stderr_tail[:-32768]

        stderr_task = asyncio.create_task(pump_stderr())
        assert proc.stdout is not None
        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=900.0)
                except TimeoutError:
                    self._turn_error = "Codex CLI produced no output for 15 minutes"
                    break
                if not line:
                    break
                try:
                    event = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    self._handle_codex_event(event)

            try:
                await asyncio.wait_for(proc.wait(), timeout=30.0)
            except TimeoutError:
                proc.terminate()
                await proc.wait()
            await asyncio.wait_for(stderr_task, timeout=10.0)
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            stderr_task.cancel()
            raise
        except Exception as exc:
            if self._turn_error is None:
                self._turn_error = f"Codex process error: {type(exc).__name__}: {exc}"
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

        if proc.returncode not in (None, 0) and self._turn_error is None:
            stderr = stderr_tail.decode("utf-8", errors="replace").strip()
            self._turn_error = stderr[-2000:] or f"Codex CLI exited with code {proc.returncode}"
        if self._turn_error:
            self.ui.error(self._turn_error)
            self.message_store.save_error(self._turn_error)
            return None

        if getattr(self, "_require_browser_capture", False):
            validation_error = self._validate_browser_capture()
            if validation_error:
                self.ui.error(validation_error)
                self.message_store.save_error(validation_error)
                return None

        client_path = self.scripts_dir / self._get_client_filename()
        if self.output_mode == "docs":
            client_path = self.scripts_dir / "openapi.yaml"
            if not client_path.exists():
                client_path = self.scripts_dir / "openapi.json"
        if not client_path.is_file():
            message = f"Codex completed without creating the expected output file: {client_path}"
            self.ui.error(message)
            self.message_store.save_error(message)
            return None

        script_path = str(client_path)
        local_path = str(self.local_scripts_dir / client_path.name) if self.local_scripts_dir else None
        self.ui.success(script_path, local_path)
        result = {
            "script_path": script_path,
            "usage": self.usage_metadata,
            "session_id": self.sdk_session_id,
            "mcp_tool_calls": list(self._mcp_tool_calls),
        }
        if getattr(self, "_require_browser_capture", False):
            result["har_path"] = str(self.har_path)
            result["har_entries"] = self._har_entry_count
        self.message_store.save_result(result)
        return result

    def _validate_browser_capture(self) -> str | None:
        if not self._mcp_tool_calls:
            return "Codex completed without calling the required Playwright browser MCP tools"
        if not self.har_path.is_file():
            return f"Playwright MCP did not write the expected HAR: {self.har_path}"
        try:
            har = json.loads(self.har_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return f"Playwright MCP wrote an unreadable HAR ({type(exc).__name__})"
        entries = har.get("log", {}).get("entries", []) if isinstance(har, dict) else []
        if not isinstance(entries, list) or not entries:
            return "Playwright MCP wrote a HAR, but it contains no network entries"
        self._har_entry_count = len(entries)
        return None

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        system_prompt, user_message = self._build_prompts()
        opening = await self._opening_message(user_message)
        if not opening:
            return {}
        prompt = opening if self.resume_session else f"{system_prompt}\n\n{user_message}"
        return await self._run_conversation(prompt)

    async def _run_conversation(
        self, prompt: str, mcp_overrides: list[str] | None = None, mode: str = "engineer"
    ) -> dict[str, Any] | None:
        last_result = await self._run_codex(prompt, mcp_overrides, mode=mode)
        if last_result is None:
            return None
        try:
            while follow_up := await self._prompt_follow_up():
                session_id = self.sdk_session_id or self.resume_session
                if not session_id:
                    self.ui.error("Codex did not report a session ID; cannot continue this conversation")
                    return last_result
                self.resume_session = session_id
                self.message_store.save_prompt(follow_up)
                result = await self._run_codex(follow_up, mcp_overrides, mode=mode)
                if result is not None:
                    last_result = result
        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            exc.partial_result = last_result  # type: ignore[attr-defined]
            raise
        return last_result


class CodexAutoEngineer(CodexEngineer):
    """Capture traffic with browser MCP and generate a client in one Codex run."""

    def __init__(self, run_id: str, prompt: str, output_dir: str | None = None, agent_provider: str = "auto", **kwargs: Any) -> None:
        if agent_provider != "auto":
            raise ValueError("Codex agent capture currently requires agent_provider='auto' (Playwright MCP with HAR)")
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.headless = bool(kwargs.pop("headless", False))
        self.start_url = kwargs.pop("start_url", None)
        har_dir = get_har_dir(run_id, output_dir)
        configured_model = kwargs.pop("codex_model", None)
        if configured_model in (None, ""):
            configured_model = kwargs.get("model")
        if not configured_model or str(configured_model).lower() == "default":
            configured_model = DEFAULT_CODEX_MODEL
        kwargs["model"] = configured_model
        kwargs["sdk"] = "codex"
        super().__init__(run_id=run_id, har_path=har_dir / "recording.har", prompt=prompt, output_dir=output_dir, **kwargs)
        self._require_browser_capture = True
        self._har_entry_count = 0

    def _get_active_prompts(self) -> tuple[str, str]:
        from .prompts import load

        language_name = self._get_language_name()
        client_filename = self._get_client_filename()
        output_files = self._get_auto_output_files(language_name, client_filename)
        system_prompt = load(
            "auto/system",
            browser_tool_label="Playwright MCP",
            language_name=language_name,
            codegen_instructions=self._get_codegen_instructions(),
            output_files=output_files,
        )
        start_url_block = "\n" + load("auto/start_url", start_url=self.start_url) if self.start_url else ""
        user_message = load(
            "auto/user_playwright",
            prompt=self.prompt,
            scripts_dir=str(self.scripts_dir),
            har_path=str(self.har_path),
            start_url_block=start_url_block,
        )
        user_message += (
            "\n\nDo not install packages or execute the generated client during this capture. "
            "Generate it from the captured traffic; it will be inspected and run separately. "
            "Avoid printing the full page body or full network log into the conversation. After identifying "
            "the requested API calls, inspect their responses in the browser and return only the fields needed "
            "to implement the user's request. Use the native "
            "file-edit/apply-patch capability to write "
            "the two requested files in the output directory; do not use Bash to inspect unrelated local files."
        )
        return system_prompt, user_message

    def _playwright_mcp_overrides(self) -> list[str]:
        browser_args = ["-y", RAE_PLAYWRIGHT_MCP_PACKAGE, "--run-id", self.mcp_run_id]
        if self.headless:
            browser_args.append("--headless")
        browser_args.extend(["--browser", "chrome"])
        if os.name == "nt":
            command_line = "npx " + " ".join(browser_args)
            command, args = shutil.which("cmd.exe") or "cmd.exe", ["/d", "/s", "/c", command_line]
        else:
            command, args = (
                shutil.which("npx") or "npx",
                browser_args,
            )
        # HAR is written under <base output dir>/har/<run id>/recording.har.
        har_base = str(self.har_path.parent.parent)
        return self._codex_mcp_overrides(
            "playwright",
            command,
            args,
            env={"PLAYWRIGHT_MCP_SAVE_HAR_PATH": har_base},
        )

    def _validate_browser_capture(self) -> str | None:
        error = super()._validate_browser_capture()
        if error:
            return error
        self._emit_json_event({"event": "browser_capture_verified", "har_path": str(self.har_path), "har_entries": self._har_entry_count})
        return None

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        system_prompt, user_message = self._get_active_prompts()
        opening = await self._opening_message(user_message)
        if not opening:
            return {}
        prompt = opening if self.resume_session else f"{system_prompt}\n\n{user_message}"
        return await self._run_conversation(prompt, self._playwright_mcp_overrides(), mode="agent")
