"""Hermes Agent backend: the local `hermes` CLI performs the engineering turn.

Every other backend speaks to an SDK — over HTTP for OpenCode, through a node
bridge for Cursor, in-process for Claude and Copilot. Hermes is a CLI that is
already installed and already authenticated on the user's machine, so a run
here is a subprocess: `hermes chat --oneshot --format stream-json` reads the
prompt from stdin and writes one JSON event per line, which this backend turns
into the same tool/thinking UI the other backends feed.

Three consequences worth knowing:

- No credential passes through rae. The model, the provider and the
  authentication are the user's own Hermes configuration; `hermes_model` and
  `hermes_provider` only override which model that configuration runs.
- `--ignore-rules` keeps an AGENTS.md or CLAUDE.md sitting in the workspace
  from steering the run, mirroring the Claude backend's settings isolation.
- Cost is estimated from the token counts the CLI reports, through the same
  pricing table the OpenCode backend uses. A model with no known price keeps
  a 0 cost instead of a wrong one.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any, cast

from .base_engineer import BaseEngineer
from .pricing import calculate_cost, get_model_pricing
from .tui import ClaudeUI

# A hermes build outside PATH (a virtualenv, a wrapper script) is picked from here.
HERMES_BIN_ENV = "RAE_HERMES_BIN"
# Enough turns for read-HAR, write, run and fix; a runaway loop still stops.
DEFAULT_HERMES_MAX_TURNS = 60
# A single event line arriving later than this means the CLI is stuck, not busy.
STREAM_TIMEOUT_S = 900.0


def hermes_binary() -> str | None:
    """The `hermes` CLI to run: RAE_HERMES_BIN when set, otherwise PATH."""
    override = os.environ.get(HERMES_BIN_ENV)
    if override:
        resolved = shutil.which(override)
        if resolved:
            return resolved
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        return None
    return shutil.which("hermes")


def parse_event(line: str) -> dict[str, Any] | None:
    """Decode one NDJSON event; anything else (a banner, a stray log line) is ignored."""
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _as_int(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0


class HermesEngineer(BaseEngineer):
    """Runs the engineering turn through the Hermes CLI."""

    def __init__(
        self,
        *args: Any,
        hermes_model: str | None = None,
        hermes_provider: str | None = None,
        hermes_max_turns: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.hermes_model = hermes_model or None
        self.hermes_provider = hermes_provider or None
        self.hermes_max_turns = hermes_max_turns or DEFAULT_HERMES_MAX_TURNS
        # Assistant text is buffered and flushed as one block per turn, the way Cursor's bridge does it.
        # The base class's UI may be any backend's; ours is always the plain terminal one.
        self.hermes_ui = cast(ClaudeUI, self.ui)
        self._narrative: list[str] = []
        self._stream_model: str | None = None

    # ------------------------------------------------------------------ setup

    def _argv(self, resume_session: str | None) -> list[str]:
        """The CLI invocation, without the prompt: it arrives on stdin (-), so quotes and backticks stay verbatim."""
        binary = hermes_binary()
        if binary is None:
            raise RuntimeError(
                f"the `hermes` CLI was not found. Install Hermes Agent (https://hermes-agent.nousresearch.com/docs) "
                f"or point {HERMES_BIN_ENV} at the binary."
            )
        argv = [
            binary,
            "chat",
            "--query-file",
            "-",
            "--oneshot",
            "--format",
            "stream-json",
            "--in",
            str(self.scripts_dir),
            "--ignore-rules",
            "--max-turns",
            str(self.hermes_max_turns),
        ]
        if resume_session:
            argv += ["--resume", resume_session]
        if self.hermes_model:
            argv += ["-m", self.hermes_model]
        if self.hermes_provider:
            argv += ["--provider", self.hermes_provider]
        return argv

    # ------------------------------------------------------------------- usage

    def _apply_usage(self, event: dict[str, Any]) -> None:
        """Token counts and an estimated cost from the run's closing event."""
        tokens = event.get("tokens")
        if not isinstance(tokens, dict):
            return
        input_tokens = _as_int(tokens.get("input"))
        output_tokens = _as_int(tokens.get("output"))
        cache_read = _as_int(tokens.get("cache_read"))
        cache_write = _as_int(tokens.get("cache_write"))
        self.usage_metadata["input_tokens"] = input_tokens
        self.usage_metadata["output_tokens"] = output_tokens
        self.usage_metadata["cache_read_input_tokens"] = cache_read
        self.usage_metadata["cache_creation_input_tokens"] = cache_write
        self.usage_metadata["total_tokens"] = _as_int(tokens.get("total")) or input_tokens + output_tokens

        model_id = self.hermes_model or self._stream_model
        cost = 0.0
        if model_id and get_model_pricing(model_id) is not None:
            cost = calculate_cost(model_id, input_tokens, output_tokens, cache_write, cache_read)
        elif input_tokens or output_tokens:
            # An unpriced model keeps a 0 cost: a Sonnet fallback would invent a number.
            self.ui.console.print(f"  [dim]no price known for {model_id or 'this model'}; cost left at 0[/dim]")
        self.usage_metadata["cost"] = self.usage_metadata.get("cost", 0.0) + cost
        self.usage_metadata["estimated_cost_usd"] = round(self.cost_before + self.usage_metadata["cost"], 6)

    # ------------------------------------------------------------------ render

    def _flush_narrative(self) -> None:
        text = "".join(self._narrative).strip()
        self._narrative = []
        if not text:
            return
        self.hermes_ui.thinking_block(text)
        self.message_store.save_thinking(text)

    async def _dispatch(self, event: dict[str, Any]) -> tuple[bool, str | None]:
        """Feed one event to the UI. Returns (the run is over, the error when it failed)."""
        kind = event.get("type")
        if kind == "text":
            fragment = event.get("text")
            if isinstance(fragment, str):
                self._narrative.append(fragment)
            return False, None
        if kind == "system":
            model = event.get("model")
            if isinstance(model, str) and model:
                self._stream_model = model
            sid = event.get("session_id")
            self._record_session(sid)
            return False, None
        if kind == "tool_use":
            self._flush_narrative()
            name = str(event.get("name") or "tool")
            raw_input = event.get("input")
            self.ui.tool_start(name, raw_input if isinstance(raw_input, dict) else {})
            self.message_store.save_tool_start(name, raw_input if isinstance(raw_input, dict) else {})
            return False, None
        if kind == "tool_result":
            name = str(event.get("name") or "tool")
            output = event.get("output")
            text = output if isinstance(output, str) else None
            is_error = bool(event.get("is_error"))
            self.ui.tool_result(name, is_error=is_error, output=text)
            self.message_store.save_tool_result(name, is_error=is_error, output=text)
            return False, None
        if kind == "result":
            self._record_session(event.get("session_id"))
            self._apply_usage(event)
            self._flush_narrative()
            code = event.get("exit_code")
            text = event.get("text")
            failure: str | None = None
            if isinstance(code, int) and code != 0:
                failure = (text if isinstance(text, str) else "").strip() or f"hermes exited with code {code}"
            return True, failure
        return False, None

    # -------------------------------------------------------------------- turn

    async def _one_turn(self, prompt: str, resume_session: str | None) -> dict[str, Any]:
        """Run one CLI turn and stream its events. Returns {} on success or {"error": ...}."""
        self._narrative = []
        try:
            argv = self._argv(resume_session)
        except RuntimeError as e:
            return {"error": str(e)}

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.scripts_dir),
            env=os.environ.copy(),
        )

        stderr_acc = bytearray()

        async def _pump_stderr() -> None:
            if proc.stderr is None:
                return
            try:
                while True:
                    chunk = await proc.stderr.read(65536)
                    if not chunk:
                        break
                    stderr_acc.extend(chunk)
            except Exception:
                return

        if proc.stdin is not None:
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        assert proc.stdout is not None
        stderr_task = asyncio.create_task(_pump_stderr())
        error: str | None = None
        try:
            while True:
                try:
                    line_b = await asyncio.wait_for(proc.stdout.readline(), timeout=STREAM_TIMEOUT_S)
                except TimeoutError:
                    error = f"hermes produced no output for {int(STREAM_TIMEOUT_S)}s"
                    break
                if not line_b:
                    break
                event = parse_event(line_b.decode("utf-8", errors="replace"))
                if event is None:
                    continue
                done, failure = await self._dispatch(event)
                if done:
                    error = failure
                    break
        except asyncio.CancelledError:
            self._terminate(proc)
            raise
        finally:
            try:
                await asyncio.wait_for(proc.wait(), timeout=120.0)
            except TimeoutError:
                self._terminate(proc)
            try:
                await asyncio.wait_for(stderr_task, timeout=10.0)
            except Exception:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

        if error:
            extra = stderr_acc.decode("utf-8", errors="replace").strip()
            return {"error": f"{error}\n{extra}" if extra else error}
        if proc.returncode not in (None, 0) and not self.usage_metadata:
            extra = stderr_acc.decode("utf-8", errors="replace").strip()
            return {"error": extra or f"hermes exited with code {proc.returncode}"}
        return {}

    @staticmethod
    def _terminate(proc: asyncio.subprocess.Process) -> None:
        """Stop the CLI without leaving a half-written client behind."""
        try:
            proc.terminate()
        except ProcessLookupError:
            return

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with the Hermes CLI."""
        self.ui.header(self.run_id, self.prompt, self.hermes_model or "hermes default", self.sdk, mode="engineer")
        self.ui.start_analysis()

        if hermes_binary() is None:
            msg = (
                f"the `hermes` CLI was not found. Install Hermes Agent "
                f"(https://hermes-agent.nousresearch.com/docs) or point {HERMES_BIN_ENV} at the binary."
            )
            self.ui.error(msg)
            self.message_store.save_error(msg)
            return None

        system_prompt, user_message = self._build_prompts()
        opening = await self._opening_message(user_message)
        if not opening:
            return {}
        # A resumed Hermes session already holds the brief; it only gets the user's message.
        turn_prompt = opening if self.resume_session else f"{system_prompt}\n\n{user_message}"
        resume_session = self.resume_session
        last_result: dict[str, Any] | None = None

        while True:
            res = await self._one_turn(turn_prompt, resume_session)
            if res.get("error"):
                msg = str(res["error"])
                self.ui.error(msg)
                self.message_store.save_error(msg)
                return None

            if self.sdk_session_id:
                resume_session = self.sdk_session_id

            client_path = self.scripts_dir / self._get_client_filename()
            if not client_path.exists():
                msg = f"hermes finished without writing {client_path.name} in {self.scripts_dir}"
                self.ui.error(msg)
                self.message_store.save_error(msg)
                return None

            local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
            self.usage_metadata.setdefault("estimated_cost_usd", 0.0)
            self.ui.success(str(client_path), local_path)
            self._report_usage()
            self._report_workspace()

            last_result = {
                "script_path": str(client_path),
                "usage": self.usage_metadata,
                "session_id": self.sdk_session_id,
            }
            self.message_store.save_result(last_result)

            if not self.interactive:
                return last_result

            follow = await self._prompt_follow_up()
            if not follow:
                return last_result
            turn_prompt = follow
            self.message_store.save_prompt(turn_prompt)
