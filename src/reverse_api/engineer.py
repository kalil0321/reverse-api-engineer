"""Reverse engineering module with SDK dispatch."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CLINotFoundError,
    McpSdkServerConfig,
    PermissionResultAllow,
    ResultError,
    ResultMessage,
    SdkMcpTool,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)

from .base_engineer import REPORT_CLIENT_VERIFIED_INSTRUCTION, BaseEngineer
from .repl.bridge import stream_options
from .utils import SDK_MAX_BUFFER_SIZE, build_sdk_effort, build_sdk_env, build_sdk_settings, is_context_overflow_error

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(logging.WARNING)


class ClaudeEngineer(BaseEngineer):
    """Uses Claude Agent SDK to analyze HAR files and generate Python API scripts."""

    # Set when the session dies with a context-window overflow ("Prompt is
    # too long"). The conversation itself exceeds the model's limit at that
    # point, so no further query on the same client can succeed and the
    # follow-up loop must not offer another turn.
    _context_overflowed = False

    def _note_session(self, message: Any) -> None:
        sid = getattr(message, "session_id", None)
        if sid is None and isinstance(message, SystemMessage):
            sid = message.data.get("session_id")
        self._record_session(sid)

    def _resume_options(self) -> dict[str, Any]:
        return {"resume": self.resume_session} if self.resume_session else {}

    def _report_failure(self, e: Exception) -> str:
        """Shows why the run failed in Claude Code's own words, without the SDK's wrapping, and saves it."""
        if isinstance(e, ResultError):
            message = "; ".join(e.errors) or e.result or e.subtype or "Claude Code stopped with an error"
        else:
            message = str(e) or type(e).__name__
        gone = bool(self.resume_session) and "No conversation found" in message
        if gone:
            message = "Claude Code no longer has this run's conversation on this machine · start a new run, or re-engineer it from its capture"
        self.ui.error(message)
        if not gone:  # the run's conversation did not change, so its log keeps no trace of the attempt
            self.message_store.save_error(message)
        if isinstance(e, CLINotFoundError):
            self.ui.console.print("\n[dim]Make sure Claude Code CLI is installed: npm install -g @anthropic-ai/claude-code[/dim]")
        return message

    def _print_context_overflow_help(self) -> None:
        """Explain a context-window overflow and how to continue."""
        self.ui.console.print()
        self.ui.console.print("  [yellow]The session ran out of context window (too much captured traffic for one conversation).[/yellow]")
        self.ui.console.print("  [dim]This session can't continue, but progress is saved: generated files are in[/dim]")
        self.ui.console.print(f"  [dim]{self.scripts_dir}[/dim]")
        self.ui.console.print(f"  [dim]Start a new run for this target (run id: {self.run_id}) to keep iterating —[/dim]")
        self.ui.console.print("  [dim]it picks up the existing client and HAR from disk. A shorter browsing[/dim]")
        self.ui.console.print("  [dim]session (fewer pages before closing the browser) also keeps the HAR smaller.[/dim]")

    async def _handle_tool_permission(self, tool_name: str, input_data: dict[str, Any], context: ToolPermissionContext) -> PermissionResultAllow:
        """Handle tool permission requests, with interactive UI for AskUserQuestion."""
        if tool_name == "AskUserQuestion":
            questions = input_data.get("questions", [])
            answers = await self._ask_user_questions(questions)
            return PermissionResultAllow(
                updated_input={"questions": questions, "answers": answers},
            )

        # Auto-approve all other tools
        return PermissionResultAllow(updated_input=input_data)

    def _build_verification_tool(self) -> SdkMcpTool[dict[str, Any]]:
        """The report_client_verified SdkMcpTool itself (handler + schema),
        separate from _build_verification_mcp_server's server-wrapping step
        purely so tests can call `.handler(args)` directly — create_sdk_mcp_
        server hands back an opaque MCP `Server` instance with no easy way
        to reach back into an individual tool's handler for a unit test.

        So the agent can explicitly report a real, observed live-
        verification success, instead of the caller trying to infer that
        after the fact from the agent's own Bash tool-call text.

        Replaces the previous approach entirely (see base_engineer.py's
        REPORT_CLIENT_VERIFIED_INSTRUCTION for the full history: eight
        rounds of automated review kept finding new ways a Bash command
        could *look* like a real client execution without being one).
        Suggested directly by the upstream maintainer on the PR this
        shipped in — a deliberate tool call closes that whole bug class by
        construction rather than risking a ninth parsing edge case.

        Built fresh per call (not a module-level singleton): the inner
        tool function is a closure over `self`, so it needs this specific
        engineer instance's `_emit_json_event`/`scripts_dir`/
        `_get_client_filename`, not a shared one. The same closure also
        holds `already_reported`, a per-session (not per-instance) guard —
        flagged by automated review: the tool's own description already
        tells the agent to call it exactly once, but that's prompt text
        only, not enforced, so a misbehaving or confused agent calling it
        twice would otherwise emit two client_executed records for one
        job. A closure-local flag is enough here (no need to touch
        __init__/self for state that only needs to last one session) —
        rebuilt fresh alongside the rest of this tool every time
        analyze_and_generate starts one.
        """
        already_reported = False

        @tool(
            "report_client_verified",
            "Call this exactly once, after you have actually run the generated "
            "client live against the target and personally confirmed it works. "
            "Do not call this speculatively, before a real run, or more than "
            "once per session.",
            {"summary": str},
        )
        async def report_client_verified(args: dict[str, Any]) -> dict[str, Any]:
            nonlocal already_reported
            if already_reported:
                return {
                    "content": [
                        {"type": "text", "text": "Already recorded earlier in this session — no need to call this again."}
                    ]
                }
            already_reported = True
            self._report_workspace()
            # Deliberately no manual message_store/UI logging here — the
            # generic ToolUseBlock/ToolResultBlock handling in
            # _process_streaming_response already logs every tool call,
            # this one included, the same way it does for Bash/Read/etc.
            self._emit_json_event(
                {
                    "event": "client_executed",
                    "script_path": str(self.scripts_dir / self._get_client_filename()),
                }
            )
            return {"content": [{"type": "text", "text": "Recorded — thanks for confirming."}]}

        return report_client_verified

    def _build_verification_mcp_server(self) -> McpSdkServerConfig:
        """In-process MCP server exposing report_client_verified — see
        _build_verification_tool's own docstring for the full reasoning."""
        return create_sdk_mcp_server(
            name="verification", tools=[self._build_verification_tool()]
        )

    def _get_codegen_instructions(self) -> str:
        """BaseEngineer's own codegen instructions, plus the
        report_client_verified tool-call instruction — scoped to this
        Claude-SDK-specific override (inherited by ClaudeAutoEngineer too)
        rather than living in the shared base method, since that tool only
        exists for this backend. Flagged by automated review: appending it
        in BaseEngineer directly meant OpenCode/Copilot/Cursor sessions
        were also being told to call a tool that was never registered in
        their environment. Docs mode still gets no suffix — BaseEngineer's
        own version already returns before any run_command-related content
        would apply, so there's nothing to append here either.
        """
        instructions = super()._get_codegen_instructions()
        if self.output_mode == "docs":
            return instructions
        return instructions + REPORT_CLIENT_VERIFIED_INSTRUCTION

    _USAGE_ACCUMULATE_KEYS = {
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    }

    def _accumulate_usage(self, usage: dict) -> None:
        """Merge usage data, summing token counts instead of replacing."""
        for key, value in usage.items():
            if key in self._USAGE_ACCUMULATE_KEYS and isinstance(value, (int, float)):
                self.usage_metadata[key] = self.usage_metadata.get(key, 0) + value
            else:
                self.usage_metadata[key] = value

    def _record_tool_results(self, blocks: list[Any]) -> None:
        """Tool results come back in user messages: always logged for /messages, shown by the session."""
        for block in blocks:
            if isinstance(block, ToolResultBlock):
                output = block.content
                text = (
                    "\n".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in output)
                    if isinstance(output, list)
                    else str(output or "")
                )
                name = self._tool_names.get(block.tool_use_id, "Tool")
                saved = text if len(text) <= 20000 else f"{text[:20000]}\n[{len(text) - 20000} more characters not saved]"
                self.message_store.save_tool_result(name, bool(block.is_error), saved)
                if getattr(self.ui, "shows_tool_results", False):
                    self.ui.tool_result(name, bool(block.is_error), text)

    def _record_assistant(self, message: AssistantMessage) -> str | None:
        """Shows and logs an assistant message's blocks. Claude Code's own notice of a failed call is returned instead:
        the turn's error result says the same, and a turn Claude Code recovers from needs no error at all."""
        last_tool_name: str | None = None
        notice: str | None = None
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                last_tool_name = block.name
                if tool_id := getattr(block, "id", None):
                    self._tool_names[tool_id] = block.name
                self.ui.tool_start(block.name, block.input)
                self.message_store.save_tool_start(block.name, block.input)
            elif isinstance(block, ToolResultBlock):
                is_error = block.is_error if block.is_error else False

                output = None
                if getattr(block, "content", None) is not None:
                    output = block.content
                elif getattr(block, "result", None) is not None:
                    output = getattr(block, "result", None)
                elif getattr(block, "output", None) is not None:
                    output = getattr(block, "output", None)

                tool_name = last_tool_name or "Tool"
                output_text: str | None
                if isinstance(output, list):
                    output_text = "\n".join(
                        str(item["text"])
                        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
                        else str(item)
                        for item in output
                    )
                else:
                    output_text = str(output) if output is not None else None
                self.ui.tool_result(tool_name, is_error, output_text)
                self.message_store.save_tool_result(tool_name, is_error, output_text)
            elif isinstance(block, TextBlock) and message.error:
                notice = block.text
            elif isinstance(block, TextBlock):
                self.ui.thinking(block.text)
                self.message_store.save_thinking(block.text)
            elif isinstance(block, ThinkingBlock) and (thinking_note := getattr(self.ui, "thinking_note", None)):
                thinking_note(block.thinking)
        return notice

    async def _process_streaming_response(self, client: ClaudeSDKClient) -> dict[str, Any] | None:
        """Process a single streaming response from the SDK client.

        Returns a result dict on success, or None on error.
        """
        notice: str | None = None
        async for message in client.receive_response():
            self._note_session(message)
            if isinstance(message, StreamEvent):
                event = message.event
                delta = event.get("delta") if event.get("type") == "content_block_delta" else None
                if isinstance(delta, dict) and message.parent_tool_use_id is None:
                    if delta.get("type") == "text_delta" and (stream_text := getattr(self.ui, "stream_text", None)):
                        stream_text(delta.get("text", ""))
                    elif delta.get("type") == "thinking_delta" and (stream_thinking := getattr(self.ui, "stream_thinking", None)):
                        stream_thinking(delta.get("thinking", ""))
                continue
            # Only ResultMessage carries billable per-query totals; AssistantMessage.usage
            # repeats for every content block of a response and would double count.
            if isinstance(message, ResultMessage) and isinstance(message.usage, dict):
                self._accumulate_usage(message.usage)

            if isinstance(message, AssistantMessage):
                notice = self._record_assistant(message) or notice

            elif isinstance(message, UserMessage) and isinstance(message.content, list):
                self._record_tool_results(message.content)

            elif isinstance(message, ResultMessage):
                if message.is_error:
                    error_text = message.result or notice or "Unknown error"
                    self.ui.error(error_text)
                    self.message_store.save_error(error_text)
                    if is_context_overflow_error(error_text):
                        self._context_overflowed = True
                        self._print_context_overflow_help()
                    return None
                else:
                    script_path = str(self.scripts_dir / self._get_client_filename())
                    local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
                    self.ui.success(script_path, local_path)

                    if self.usage_metadata:
                        input_tokens = self.usage_metadata.get("input_tokens", 0)
                        output_tokens = self.usage_metadata.get("output_tokens", 0)
                        cache_creation_tokens = self.usage_metadata.get("cache_creation_input_tokens", 0)
                        cache_read_tokens = self.usage_metadata.get("cache_read_input_tokens", 0)

                        from .pricing import calculate_cost

                        # total_cost_usd is the SDK's own figure, cumulative over the session, a resumed one included.
                        cost = (
                            max(0.0, float(message.total_cost_usd) - self.cost_before)
                            if isinstance(message.total_cost_usd, (int, float))
                            else calculate_cost(
                                model_id=self.model,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                cache_creation_tokens=cache_creation_tokens,
                                cache_read_tokens=cache_read_tokens,
                            )
                        )
                        self.usage_metadata["estimated_cost_usd"] = cost
                        self.ui.usage(self.usage_metadata)

                    result: dict[str, Any] = {
                        "script_path": script_path,
                        "usage": self.usage_metadata,
                    }
                    self.message_store.save_result(result)
                    return result

        return None

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with Claude.

        Supports follow-up messages: after the initial analysis completes,
        the user can send follow-ups in the same session for iterative refinement.
        Press Enter or Ctrl+C to finish and return to the REPL.
        """
        self.ui.header(self.run_id, self.prompt, self.model, self.sdk, mode="engineer")
        self.ui.start_analysis()

        # Fresh SDK session, fresh context window: clear any overflow state
        # left over from a previous run on a reused engineer instance.
        self._context_overflowed = False

        system_prompt, user_message = self._build_prompts()

        options = ClaudeAgentOptions(
            max_buffer_size=SDK_MAX_BUFFER_SIZE,
            system_prompt=system_prompt,
            permission_mode="acceptEdits",
            can_use_tool=self._handle_tool_permission,
            cwd=str(self.scripts_dir.parent.parent),
            model=self.model,
            env=build_sdk_env(),
            **build_sdk_settings(),
            **build_sdk_effort(self.model),
            **stream_options(self.model),
            **self._resume_options(),
            stderr=self._handle_cli_stderr,
            mcp_servers={"verification": self._build_verification_mcp_server()},
        )

        last_result: dict[str, Any] | None = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                opening = await self._opening_message(user_message)
                if not opening:
                    return {}
                await client.query(opening)

                # Process initial response
                last_result = await self._process_streaming_response(client)
                if last_result is None:
                    return None

                # Conversation loop: prompt for follow-ups
                while True:
                    follow_up = await self._prompt_follow_up()
                    if not follow_up:
                        return last_result

                    self.ui.console.print()
                    self.message_store.save_prompt(follow_up)
                    await client.query(follow_up)

                    result = await self._process_streaming_response(client)
                    if result is not None:
                        last_result = result
                    elif self._context_overflowed:
                        # The conversation exceeds the context window; every
                        # further query would fail the same way, so end the
                        # follow-up loop instead of offering another turn.
                        return last_result

        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result

        except asyncio.CancelledError:
            # Stopped from the session: the turns already done still reach history and the local copy.
            return {**(last_result or {}), "error": "interrupted"}

        except Exception as e:
            self._report_failure(e)
            return None

        return None


# Keep old class name for backwards compatibility
APIReverseEngineer = ClaudeEngineer


def run_reverse_engineering(
    run_id: str,
    har_path: Path,
    prompt: str,
    model: str | None = None,
    additional_instructions: str | None = None,
    output_dir: str | None = None,
    verbose: bool = True,
    sdk: str = "claude",
    opencode_provider: str | None = None,
    opencode_model: str | None = None,
    copilot_model: str | None = None,
    cursor_model: str | None = None,
    cursor_web_search: bool = True,
    cursor_setting_sources: list[str] | None = None,
    enable_sync: bool = False,
    is_fresh: bool = False,
    output_language: str = "python",
    output_mode: str = "client",
    interactive: bool = True,
    json_event_sink: Any = None,
    resume_session: str | None = None,
    cost_before: float = 0.0,
    on_session: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Run reverse engineering with the specified SDK.

    resume_session, cost_before and on_session reopen and record the SDK session, see BaseEngineer.

    Args:
        sdk: "claude", "opencode", "copilot", or "cursor" - determines which SDK to use
        opencode_provider: Provider ID for OpenCode (e.g., "anthropic")
        opencode_model: Model ID for OpenCode (e.g., "claude-sonnet-4-6")
        copilot_model: Model ID for Copilot (e.g., "gpt-5")
        cursor_model: Model id for Cursor SDK (e.g., "composer-2.5")
        cursor_web_search: When True, load extra Cursor setting layers so WebFetch/WebSearch and plugins apply.
        cursor_setting_sources: Optional explicit list (overrides cursor_web_search), e.g. ["project","user","all"].
        enable_sync: Enable real-time file syncing during engineering
        is_fresh: Whether to start fresh (ignore previous scripts)
        output_language: Target language - "python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", or "c"
        output_mode: Output mode - "client" for API client code, "docs" for OpenAPI specification
    """
    engineer: BaseEngineer
    if sdk == "opencode":
        from .opencode_engineer import OpenCodeEngineer

        engineer = OpenCodeEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            additional_instructions=additional_instructions,
            output_dir=output_dir,
            verbose=verbose,
            opencode_provider=opencode_provider,
            opencode_model=opencode_model,
            enable_sync=enable_sync,
            sdk=sdk,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
        )
    elif sdk == "cursor":
        from .cursor_engineer import CursorEngineer

        engineer = CursorEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            additional_instructions=additional_instructions,
            output_dir=output_dir,
            verbose=verbose,
            enable_sync=enable_sync,
            sdk=sdk,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            cursor_model=cursor_model,
            cursor_web_search=cursor_web_search,
            cursor_setting_sources=cursor_setting_sources,
            interactive=interactive,
        )
    elif sdk == "copilot":
        from .copilot_engineer import CopilotEngineer

        engineer = CopilotEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            additional_instructions=additional_instructions,
            output_dir=output_dir,
            verbose=verbose,
            enable_sync=enable_sync,
            sdk=sdk,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            copilot_model=copilot_model,
            interactive=interactive,
        )
    else:
        engineer = ClaudeEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            additional_instructions=additional_instructions,
            output_dir=output_dir,
            verbose=verbose,
            enable_sync=enable_sync,
            sdk=sdk,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
            interactive=interactive,
        )
    engineer.resume_session, engineer.cost_before, engineer.on_session = resume_session, cost_before, on_session

    if json_event_sink is not None:
        from .json_stream import attach_json_stream_to_engineer

        attach_json_stream_to_engineer(engineer, json_event_sink)

    # Start sync before analysis
    engineer.start_sync()

    try:
        result = asyncio.run(engineer.analyze_and_generate())
    except KeyboardInterrupt:
        # Absorb interrupt so REPL continues instead of exiting
        result = None
    finally:
        # Always stop sync when done
        engineer.stop_sync()

    return result
