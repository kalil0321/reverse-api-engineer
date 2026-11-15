"""OpenAI Codex SDK backend: the Codex app-server, driven through its Python SDK."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import os
import secrets
import shlex
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, NamedTuple

from . import __version__, verification_mcp
from .agent_browser import ensure_agent_browser_runtime, print_agent_browser_setup_notices
from .base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION, BaseEngineer
from .chrome_mcp import CHROME_DEVTOOLS_MCP_PACKAGE
from .config import PLAYWRIGHT_MCP_PACKAGE
from .tui import ClaudeUI
from .utils import get_app_dir, get_har_dir

INSTALL_HELP = "Codex SDK not installed. From source: uv sync --extra codex. Installed: pip install 'reverse-api-engineer[codex]'"
SIGN_IN_HELP = (
    "Codex is not signed in · run `codex login` or sign in from the Codex app, then run again · "
    'a sign-in kept in the system keyring is not shared: set "codex_home" to your Codex home instead'
)
# npx can download the browser MCP server on its first use, which outlasts Codex's 10 second default.
MCP_STARTUP_TIMEOUT_SEC = 60
# Codex's plan statuses as the other SDKs spell them.
PLAN_STATUS = {"inProgress": "in_progress"}
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")
# Codex also writes files from the shell, which the session can only show as a command.
FILE_EDITS = "\n\nCreate and change files with apply_patch, not with shell redirection or heredocs."

logger = logging.getLogger(__name__)


class CodexSetupError(RuntimeError):
    """Codex cannot start: rae's Codex home could not share the user's sign-in."""


def codex_installed() -> bool:
    return importlib.util.find_spec("openai_codex") is not None


def user_codex_home() -> Path:
    """The user's own Codex home, where their Codex keeps its config and sign-in."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().absolute()


def codex_home(configured: str | None = None) -> Path:
    """The Codex home rae runs in: ``configured`` as it is, else rae's own.

    rae's own home keeps the user's Codex config, MCP servers, hooks, skills and AGENTS.md from steering the
    agent, and rae's threads out of their Codex history. Its auth.json links to the user's: Codex
    writes credentials through the link, so both share one sign-in and its refreshed tokens.
    """
    if configured:
        return Path(configured).expanduser()
    home = get_app_dir() / "codex"
    home.mkdir(parents=True, exist_ok=True)
    link, auth = home / "auth.json", user_codex_home() / "auth.json"
    # A sign-in made in rae's home itself is kept; a link follows the user's Codex home when CODEX_HOME moves it.
    # Compared resolved: Windows reports link targets with a \\?\ prefix, and CODEX_HOME may name rae's home itself.
    linked = link.resolve() if link.is_symlink() else None
    if auth.is_file() and (linked is not None or not link.exists()) and linked != auth.resolve():
        staged = home / f".auth.json.{os.getpid()}.{secrets.token_hex(4)}"
        try:
            staged.symlink_to(auth)
            os.replace(staged, link)  # atomic: concurrent runs never see a missing or half-made link
        except OSError as exc:  # Windows without symlink rights
            staged.unlink(missing_ok=True)
            raise CodexSetupError(
                f"could not link {link} to your Codex sign-in at {auth}: {exc} · "
                f'set "codex_home" to "{user_codex_home()}" in ~/.reverse-api/config.json to run in your own Codex home'
            ) from exc
    return home


def codex_config(configured_home: str | None = None) -> Any:
    """The SDK's launch settings: the Codex home, and how rae introduces itself to Codex."""
    from openai_codex import CodexConfig

    # Only the file store writes through rae's auth.json link; a keyring store would replace it.
    # Codex finds the user's skills in ~/.agents/skills whatever its home; this keeps them out of the prompt.
    # Apps are the ChatGPT account's connectors (Gmail, Drive, a hosted browser): tools the agent must not reach for.
    overrides = (
        ()
        if configured_home
        else ('cli_auth_credentials_store="file"', "skills.include_instructions=false", "features.apps=false")
    )
    return CodexConfig(
        env={"CODEX_HOME": str(codex_home(configured_home))},
        config_overrides=overrides,
        client_name="reverse_api_engineer",
        client_title="Reverse API Engineer",
        client_version=__version__,
    )


def codex_check(configured_home: str | None = None) -> dict[str, str]:
    """agent --dry-run's check, without starting Codex: the SDK is installed and a sign-in is there."""
    name = "sdk:codex"
    if not codex_installed():
        return {"name": name, "status": "error", "message": INSTALL_HELP}
    home = Path(configured_home).expanduser() if configured_home else get_app_dir() / "codex"
    # rae's own home links to the user's sign-in on its first run.
    auths = [home / "auth.json"] if configured_home else [home / "auth.json", user_codex_home() / "auth.json"]
    if any(auth.exists() for auth in auths):
        return {"name": name, "status": "ok", "message": f"signed in, Codex home {home}"}
    return {"name": name, "status": "warn", "message": SIGN_IN_HELP}


@contextlib.asynccontextmanager
async def open_codex(configured_home: str | None = None) -> AsyncIterator[Any]:
    """A started AsyncCodex, closed on the way out.

    The SDK starts the app-server in a worker thread that cancelling does not stop, and its own cleanup
    skips cancellation, so a start cancelled midway is waited out and then closed.
    """
    from openai_codex import AsyncCodex

    codex = AsyncCodex(config=codex_config(configured_home))
    starting = asyncio.ensure_future(codex.__aenter__())
    try:
        await asyncio.shield(starting)
        yield codex
    finally:
        with contextlib.suppress(Exception):  # a failed start already closed itself
            await starting
        await codex.close()


class CodexModel(NamedTuple):
    """A model Codex offers the signed-in account, with the reasoning efforts it takes."""

    model: str
    name: str
    is_default: bool
    default_effort: str
    efforts: tuple[tuple[str, str], ...]  # (effort, what it is for)


async def codex_models(configured_home: str | None = None) -> list[CodexModel]:
    if not codex_installed():
        raise RuntimeError(INSTALL_HELP)
    async with open_codex(configured_home) as codex:
        catalog = await codex.models()
    return [
        CodexModel(
            m.model,
            m.display_name or m.model,
            bool(m.is_default),
            _value(m.default_reasoning_effort),
            tuple((_value(option.reasoning_effort), option.description) for option in m.supported_reasoning_efforts),
        )
        for m in catalog.data
    ]


def _value(field: Any) -> str:
    """An SDK enum's wire value."""
    return str(getattr(field, "value", field))


def _root(model: Any) -> Any:
    """The variant inside one of the SDK's union models."""
    return getattr(model, "root", model)


def _command_text(command: str) -> str:
    """The command as the agent wrote it, without the login shell Codex runs it in: ``/bin/zsh -lc '…'``."""
    with contextlib.suppress(ValueError):
        argv = shlex.split(command)
        if len(argv) == 3 and argv[1] in ("-c", "-lc"):
            return argv[2]
    return command


def _mcp_text(result: Any) -> str | None:
    """The text an MCP tool returned; screenshots and other media are left out."""
    if result is None:
        return None
    texts = [block.get("text") for block in result.content if isinstance(block, dict) and block.get("type") == "text"]
    return "\n".join(text for text in texts if isinstance(text, str)) or None


def _file_change(change: Any) -> tuple[str, dict[str, Any]]:
    """A file a patch changed, as the step rae shows: Write with the new file, Edit, or Delete."""
    kind = _root(change.kind).type
    if kind == "add":
        return "Write", {"file_path": change.path, "content": change.diff}  # an added file's diff is its content
    return ("Delete" if kind == "delete" else "Edit"), {"file_path": change.path}


def _web_step(item: Any) -> tuple[str, dict[str, Any]]:
    """Codex's web search item as the step rae shows: a search with its query, or a fetch of the page it opened."""
    action: Any = _root(item.action) if item.action is not None else None
    kind = getattr(action, "type", None)
    if kind == "openPage" and action.url:
        return "WebFetch", {"url": action.url}
    if kind == "findInPage":
        return "WebSearch", {"query": " on ".join(part for part in (action.pattern, action.url) if part)}
    queries = getattr(action, "queries", None) or []
    return "WebSearch", {"query": item.query or getattr(action, "query", None) or ", ".join(queries)}


class CodexEngineer(BaseEngineer):
    """Reverse engineering with the OpenAI Codex SDK."""

    ui: ClaudeUI
    # Codex has no ask tool outside its plan mode; a question ends the turn and the answer is the next message.
    ask_user = (
        "When running interactively and you need the user to clarify requirements or choose between approaches, "
        "ask in your reply and end your turn: their answer comes as the next message. In non-interactive or "
        "scripted CLI runs, make reasonable assumptions from the HAR and prompt instead."
    )
    ask_user_agent_browser = "For questions that truly need a human, ask in your reply and end your turn; the answer comes as the next message."

    def __init__(
        self,
        run_id: str,
        har_path: Path,
        prompt: str,
        codex_model: str | None = None,
        codex_effort: str | None = None,
        codex_home: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(run_id=run_id, har_path=har_path, prompt=prompt, **kwargs)
        # Codex works in the run's own folder, so the paths its prompts name cannot be relative to rae's.
        self.scripts_dir, self.har_path = self.scripts_dir.absolute(), self.har_path.absolute()
        self.codex_model = codex_model or None  # None runs Codex's default model
        self.codex_effort = codex_effort or None  # None runs the model's default effort
        self.codex_home = codex_home
        self._verified = False
        self._turn_end: Any = None  # the Turn that turn/completed reported
        self._usage_base: dict[str, int] | None = None  # the thread's token counts before this run

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        self.ui.header(self.run_id, self.prompt, self.codex_model, self.sdk, mode="engineer")
        self.ui.start_analysis()
        system_prompt, user_message = self._build_prompts()
        return await self._converse(system_prompt, user_message)

    def _browser_servers(self) -> dict[str, Any]:
        """Browser MCP servers for the thread; engineer mode works from the HAR and has none."""
        return {}

    def _get_codegen_instructions(self) -> str:
        instructions = super()._get_codegen_instructions()
        return instructions if self.output_mode == "docs" else instructions + REPORT_CLIENT_VERIFIED_INSTRUCTION

    def _fail(self, message: str) -> None:
        self.ui.error(message)
        self.message_store.save_error(message)

    async def _converse(self, system_prompt: str, brief: str) -> dict[str, Any] | None:
        """The opening turn and each follow-up, in one Codex thread; returns the last finished turn's result."""
        if not codex_installed():
            self._fail(INSTALL_HELP)
            return None

        last_result: dict[str, Any] | None = None
        try:
            async with open_codex(self.codex_home) as codex:
                if (await codex.account()).account is None:
                    self._fail(SIGN_IN_HELP)
                    return None
                message = await self._opening_message(brief)
                if not message:
                    return {}
                thread = await self._open_thread(codex, system_prompt)
                while message:
                    result = await self._turn(thread, message)
                    if result is not None:
                        last_result = result
                    elif last_result is None:
                        return None
                    message = await self._prompt_follow_up()
                    if message:
                        self.message_store.save_prompt(message)
                return last_result
        except asyncio.CancelledError as exc:
            # Keep cancellation semantics for asyncio callers while retaining
            # the partial result for the CLI, including SIGINT via Runner.
            exc.partial_result = last_result  # type: ignore[attr-defined]
            raise
        except KeyboardInterrupt as exc:
            if not self.interactive:
                exc.partial_result = last_result  # type: ignore[attr-defined]
                raise
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return {**(last_result or {}), "error": "interrupted"}
        except Exception as exc:  # the runtime failing to start, a closed transport, an RPC error
            logger.debug("Codex run failed", exc_info=True)
            self._fail(str(exc) or type(exc).__name__)
            return None

    async def _open_thread(self, codex: Any, system_prompt: str) -> Any:
        """A new thread with rae's instructions, or the run's saved thread when resuming."""
        from openai_codex import ApprovalMode, Sandbox

        servers = {**self._browser_servers(), verification_mcp.SERVER: verification_mcp.server_config()}
        options: dict[str, Any] = {
            # Like rae's other backends the agent runs unsandboxed: toolchains write caches outside the
            # workspace and agent-browser starts Chrome from the shell. Nothing is then left to approve.
            "approval_mode": ApprovalMode.deny_all,
            "sandbox": Sandbox.full_access,
            # The run's own folder: Codex explores its working folder, where other runs would distract it.
            "cwd": str(self.scripts_dir),
            "model": self.codex_model,
            "config": {"mcp_servers": servers},
        }
        if self.resume_session:
            thread = await codex.thread_resume(self.resume_session, **options)
        else:
            thread = await codex.thread_start(developer_instructions=system_prompt + FILE_EDITS, **options)
        self._record_session(thread.id)
        return thread

    async def _turn(self, thread: Any, message: str) -> dict[str, Any] | None:
        """One turn, streamed into the UI: its result, or None once its failure is shown."""
        from openai_codex.types import ReasoningEffort

        self._turn_end = None
        turn = await thread.turn(message, effort=ReasoningEffort(self.codex_effort) if self.codex_effort else None)
        try:
            async with contextlib.aclosing(turn.stream()) as events:
                async for event in events:
                    self._on_event(event.method, event.payload)
        except asyncio.CancelledError:
            # The turn's commands and browser keep running until Codex stops the turn itself.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(turn.interrupt(), timeout=5)
            raise
        end = self._turn_end
        status = _value(end.status) if end is not None else "unfinished"
        if status == "completed":
            return self._finished()
        error = getattr(end, "error", None)
        self._fail(error.message if error is not None and error.message else f"the Codex turn ended {status}")
        return None

    def _finished(self) -> dict[str, Any]:
        """The client the turn left, and the result the CLI records."""
        filename = self._get_client_filename()
        script_path = str(self.scripts_dir / filename)
        self.ui.success(script_path, str(self.local_scripts_dir / filename) if self.local_scripts_dir else None)
        self._report_usage()
        result = {"script_path": script_path, "usage": self.usage_metadata}
        self.message_store.save_result(result)
        return result

    def _on_event(self, method: str, payload: Any) -> None:
        """Shows one Codex notification and keeps it in the run's messages."""
        if method == "item/agentMessage/delta":
            self._stream("stream_text", payload.delta)
        elif method == "item/reasoning/summaryTextDelta":
            self._stream("stream_thinking", payload.delta)
        elif method == "item/started":
            self._item_started(_root(payload.item))
        elif method == "item/completed":
            self._item_completed(_root(payload.item))
        elif method == "turn/plan/updated":
            todos = [{"content": step.step, "status": PLAN_STATUS.get(_value(step.status), _value(step.status))} for step in payload.plan]
            self.ui.todo_updated(todos)
            self.message_store.save_todos(todos)
        elif method == "thread/tokenUsage/updated":
            total, last = payload.token_usage.total, payload.token_usage.last
            if self._usage_base is None:
                # A resumed thread's total includes its earlier runs, which the run's history already counts.
                self._usage_base = {key: getattr(total, key) - getattr(last, key) for key in USAGE_FIELDS}
            used = {key: getattr(total, key) - self._usage_base[key] for key in USAGE_FIELDS}
            # Codex's input count includes the cached tokens, which rae counts apart as Claude reports them.
            self.usage_metadata.update(
                input_tokens=used["input_tokens"] - used["cached_input_tokens"],
                cache_read_tokens=used["cached_input_tokens"],
                output_tokens=used["output_tokens"],
            )
        elif method == "error" and payload.will_retry:
            self.ui.progress(f"codex retries: {payload.error.message}")
        elif method == "thread/compacted":
            self.ui.progress("codex compacted the conversation to fit the model's context")
        elif method == "turn/completed":
            self._turn_end = payload.turn

    def _stream(self, method: str, delta: str) -> None:
        # Only the full-screen session shows text as it arrives; the classic UI prints whole messages.
        if delta and (show := getattr(self.ui, method, None)):
            show(delta)

    def _item_started(self, item: Any) -> None:
        if item.type == "commandExecution":
            self._tool_start("Bash", {"command": _command_text(item.command)}, item.id)
        elif item.type == "mcpToolCall":
            args = item.arguments if isinstance(item.arguments, dict) else {}
            self._tool_start(f"mcp__{item.server}__{item.tool}", args, item.id)

    def _item_completed(self, item: Any) -> None:
        if item.type == "agentMessage" and item.text.strip():
            # The final answer sums the turn up and shows whole; commentary is a passing note.
            final = item.phase is not None and _value(item.phase) == "final_answer"
            (self.ui.thinking_block if final else self.ui.thinking)(item.text)
            self.message_store.save_thinking(item.text)
        elif item.type == "reasoning" and item.summary and (note := getattr(self.ui, "thinking_note", None)):
            note("\n\n".join(item.summary))
        elif item.type == "commandExecution":
            failed = _value(item.status) != "completed" or item.exit_code not in (None, 0)
            self._tool_result("Bash", failed, item.aggregated_output, item.id)
        elif item.type == "mcpToolCall":
            failed = item.error is not None or _value(item.status) == "failed"
            output = item.error.message if item.error is not None else _mcp_text(item.result)
            if (item.server, item.tool) == (verification_mcp.SERVER, verification_mcp.TOOL) and not failed and not self._verified:
                self._verified = True
                self._client_verified()  # before its result, which the session's verified step reads
            self._tool_result(f"mcp__{item.server}__{item.tool}", failed, output, item.id)
        elif item.type == "fileChange":
            failed = _value(item.status) != "completed"
            for index, change in enumerate(item.changes):
                name, args = _file_change(change)
                call_id = f"{item.id}:{index}"
                self._tool_start(name, args, call_id)
                self._tool_result(name, failed, None, call_id)
        elif item.type == "webSearch":
            name, args = _web_step(item)
            self._tool_start(name, args, item.id)
            self._tool_result(name, False, None, item.id)

    def _tool_start(self, name: str, args: dict[str, Any], call_id: str) -> None:
        self.ui.tool_start(name, args, call_id=call_id)
        self.message_store.save_tool_start(name, args, call_id=call_id)

    def _tool_result(self, name: str, failed: bool, output: str | None, call_id: str) -> None:
        self.ui.tool_result(name, failed, output, call_id=call_id)
        self.message_store.save_tool_result(name, failed, output, call_id=call_id)


class CodexAutoEngineer(CodexEngineer):
    """Agent mode via the Codex SDK: a browser MCP server for auto and chrome-mcp, the agent-browser CLI otherwise."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        output_dir: str | None = None,
        agent_provider: str = "auto",
        headless: bool = False,
        start_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        har_path = get_har_dir(run_id, output_dir) / "recording.har"
        super().__init__(run_id=run_id, har_path=har_path, prompt=prompt, output_dir=output_dir, **kwargs)
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.headless = headless
        self.start_url = start_url

    def _browser_servers(self) -> dict[str, Any]:
        if self.agent_provider == "agent-browser":
            return {}  # the agent shells the agent-browser CLI
        if self.agent_provider == "chrome-mcp":
            # Auto-connect attaches to the user's running Chrome, which a headless run has none of.
            name = "chrome-devtools"
            args = [CHROME_DEVTOOLS_MCP_PACKAGE, "--no-usage-statistics", "--headless" if self.headless else "--autoConnect"]
        else:
            name = "playwright"
            args = [PLAYWRIGHT_MCP_PACKAGE, "run-mcp-server", "--run-id", self.mcp_run_id, *(["--headless"] if self.headless else [])]
        return {name: {"command": "npx", "args": ["-y", *args], "startup_timeout_sec": MCP_STARTUP_TIMEOUT_SEC}}

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        from .auto_engineer import ClaudeAutoEngineer

        self.ui.header(self.run_id, self.prompt, self.codex_model, self.sdk, mode="agent")
        self.ui.start_analysis()
        if self.agent_provider == "agent-browser":
            setup = ensure_agent_browser_runtime()
            print_agent_browser_setup_notices(self.ui.console, setup)
            if not setup.ok:
                self._fail(setup.error or "agent-browser setup failed")
                return None
        system_prompt, user_message = ClaudeAutoEngineer._build_auto_prompts(self)
        return await self._converse(system_prompt, user_message)
