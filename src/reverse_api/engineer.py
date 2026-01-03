"""Reverse engineering module with SDK dispatch."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

import questionary

from .base_engineer import BaseEngineer
from .tui import THEME_PRIMARY, THEME_SECONDARY

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(
    logging.WARNING
)


class ClaudeEngineer(BaseEngineer):
    """Uses Claude Agent SDK to analyze HAR files and generate Python API scripts."""

    async def _handle_ask_user_question(
        self, tool_name: str, input_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle AskUserQuestion tool by prompting the user interactively."""
        if tool_name != "AskUserQuestion":
            # Default allow for other tools in acceptEdits mode
            return {"behavior": "allow", "updatedInput": input_params}

        questions = input_params.get("questions", [])
        answers = {}

        # Display header
        self.ui.console.print()
        self.ui.console.print(
            f"  [{THEME_PRIMARY}]?[/{THEME_PRIMARY}] [bold white]Agent Question[/bold white]"
        )
        self.ui.console.print()

        for q in questions:
            question_text = q.get("question", "")
            header = q.get("header", "")
            options = q.get("options", [])
            multi_select = q.get("multiSelect", False)

            if not question_text:
                continue

            # Show context if header exists
            if header:
                self.ui.console.print(f"  [dim]{header}[/dim]")

            try:
                if multi_select:
                    # Multi-select question
                    choices = [
                        f"{opt.get('label', '')} - {opt.get('description', '')}"
                        if opt.get("description")
                        else opt.get("label", "")
                        for opt in options
                    ]
                    if choices:
                        selected = await questionary.checkbox(
                            f" > {question_text}",
                            choices=choices,
                            qmark="",
                            style=questionary.Style(
                                [
                                    ("pointer", f"fg:{THEME_PRIMARY} bold"),
                                    ("highlighted", f"fg:{THEME_PRIMARY} bold"),
                                    ("selected", f"fg:{THEME_PRIMARY}"),
                                ]
                            ),
                        ).ask_async()

                        if selected is None:
                            raise KeyboardInterrupt

                        # Extract just the labels (before the " - " separator)
                        labels = [
                            s.split(" - ")[0] if " - " in s else s
                            for s in selected
                        ]
                        answers[question_text] = ", ".join(labels)
                    else:
                        # Text input fallback
                        answer = await questionary.text(
                            f" > {question_text}",
                            qmark="",
                            style=questionary.Style([("question", f"fg:{THEME_SECONDARY}")]),
                        ).ask_async()
                        if answer is None:
                            raise KeyboardInterrupt
                        answers[question_text] = answer.strip()

                else:
                    # Single select question
                    choices = [
                        f"{opt.get('label', '')} - {opt.get('description', '')}"
                        if opt.get("description")
                        else opt.get("label", "")
                        for opt in options
                    ]
                    if choices:
                        answer = await questionary.select(
                            f" > {question_text}",
                            choices=choices,
                            qmark="",
                            style=questionary.Style(
                                [
                                    ("pointer", f"fg:{THEME_PRIMARY} bold"),
                                    ("highlighted", f"fg:{THEME_PRIMARY} bold"),
                                ]
                            ),
                        ).ask_async()

                        if answer is None:
                            raise KeyboardInterrupt

                        # Extract just the label (before the " - " separator)
                        label = answer.split(" - ")[0] if " - " in answer else answer
                        answers[question_text] = label
                    else:
                        # Text input fallback
                        answer = await questionary.text(
                            f" > {question_text}",
                            qmark="",
                            style=questionary.Style([("question", f"fg:{THEME_SECONDARY}")]),
                        ).ask_async()
                        if answer is None:
                            raise KeyboardInterrupt
                        answers[question_text] = answer.strip()

                self.ui.console.print(f"  [dim]→ {answers[question_text]}[/dim]")

            except KeyboardInterrupt:
                self.ui.console.print(f"  [dim]User cancelled question[/dim]")
                answers[question_text] = ""

        self.ui.console.print()

        return {
            "behavior": "allow",
            "updatedInput": {"questions": questions, "answers": answers},
        }

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with Claude."""
        self.ui.header(self.run_id, self.prompt, self.model, self.sdk)
        self.ui.start_analysis()
        self.message_store.save_prompt(self._build_analysis_prompt())

        options = ClaudeAgentOptions(
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
            ],
            permission_mode="acceptEdits",
            can_use_tool=self._handle_ask_user_question,
            cwd=str(self.scripts_dir.parent.parent),  # Project root
            model=self.model,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(self._build_analysis_prompt())

                # Process response and show progress with TUI
                async for message in client.receive_response():
                    # Check for usage metadata in message if applicable
                    if hasattr(message, "usage") and isinstance(message.usage, dict):
                        self.usage_metadata.update(message.usage)

                    if isinstance(message, AssistantMessage):
                        last_tool_name = None
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                last_tool_name = block.name
                                self.ui.tool_start(block.name, block.input)
                                self.message_store.save_tool_start(block.name, block.input)
                            elif isinstance(block, ToolResultBlock):
                                is_error = block.is_error if block.is_error else False

                                # Extract output from ToolResultBlock
                                output = None
                                if hasattr(block, "content"):
                                    output = block.content
                                elif hasattr(block, "result"):
                                    output = block.result
                                elif hasattr(block, "output"):
                                    output = block.output

                                tool_name = last_tool_name or "Tool"
                                self.ui.tool_result(tool_name, is_error, output)
                                self.message_store.save_tool_result(
                                    tool_name, is_error, str(output) if output else None
                                )
                            elif isinstance(block, TextBlock):
                                self.ui.thinking(block.text)
                                self.message_store.save_thinking(block.text)

                    elif isinstance(message, ResultMessage):
                        if message.is_error:
                            self.ui.error(message.result or "Unknown error")
                            self.message_store.save_error(message.result or "Unknown error")
                            return None
                        else:
                            script_path = str(self.scripts_dir / "api_client.py")
                            local_path = (
                                str(self.local_scripts_dir / "api_client.py")
                                if self.local_scripts_dir
                                else None
                            )
                            self.ui.success(script_path, local_path)

                            # Calculate estimated cost if we have usage data
                            if self.usage_metadata:
                                input_tokens = self.usage_metadata.get("input_tokens", 0)
                                output_tokens = self.usage_metadata.get("output_tokens", 0)
                                cache_creation_tokens = self.usage_metadata.get(
                                    "cache_creation_input_tokens", 0
                                )
                                cache_read_tokens = self.usage_metadata.get(
                                    "cache_read_input_tokens", 0
                                )

                                # Calculate cost using shared pricing module
                                from .pricing import calculate_cost

                                cost = calculate_cost(
                                    model_id=self.model,
                                    input_tokens=input_tokens,
                                    output_tokens=output_tokens,
                                    cache_creation_tokens=cache_creation_tokens,
                                    cache_read_tokens=cache_read_tokens,
                                )
                                self.usage_metadata["estimated_cost_usd"] = cost

                                # Display usage breakdown
                                self.ui.console.print("  [dim]Usage:[/dim]")
                                if input_tokens > 0:
                                    self.ui.console.print(
                                        f"  [dim]  input: {input_tokens:,} tokens[/dim]"
                                    )
                                if cache_creation_tokens > 0:
                                    self.ui.console.print(
                                        f"  [dim]  cache creation: {cache_creation_tokens:,} tokens[/dim]"
                                    )
                                if cache_read_tokens > 0:
                                    self.ui.console.print(
                                        f"  [dim]  cache read: {cache_read_tokens:,} tokens[/dim]"
                                    )
                                if output_tokens > 0:
                                    self.ui.console.print(
                                        f"  [dim]  output: {output_tokens:,} tokens[/dim]"
                                    )
                                self.ui.console.print(f"  [dim]  total cost: ${cost:.4f}[/dim]")

                            result: dict[str, Any] = {
                                "script_path": script_path,
                                "usage": self.usage_metadata,
                            }
                            self.message_store.save_result(result)
                            return result

        except Exception as e:
            self.ui.error(str(e))
            self.message_store.save_error(str(e))
            self.ui.console.print(
                "\n[dim]Make sure Claude Code CLI is installed: "
                "npm install -g @anthropic-ai/claude-code[/dim]"
            )
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
    enable_sync: bool = False,
    is_fresh: bool = False,
) -> dict[str, Any] | None:
    """Run reverse engineering with the specified SDK.

    Args:
        sdk: "opencode" or "claude" - determines which SDK to use
        opencode_provider: Provider ID for OpenCode (e.g., "anthropic")
        opencode_model: Model ID for OpenCode (e.g., "claude-sonnet-4-5")
        enable_sync: Enable real-time file syncing during engineering
        is_fresh: Whether to start fresh (ignore previous scripts)
    """
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
        )

    # Start sync before analysis
    engineer.start_sync()

    try:
        result = asyncio.run(engineer.analyze_and_generate())
    finally:
        # Always stop sync when done
        engineer.stop_sync()

    return result
