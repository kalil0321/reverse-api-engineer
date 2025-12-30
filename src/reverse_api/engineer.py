"""Reverse engineering module with SDK dispatch."""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
)

from .base_engineer import BaseEngineer

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(
    logging.WARNING
)


class ClaudeEngineer(BaseEngineer):
    """Uses Claude Agent SDK to analyze HAR files and generate Python API scripts."""

    async def analyze_and_generate(self) -> Optional[Dict[str, Any]]:
        """Run the reverse engineering analysis with Claude."""
        self.ui.header(self.run_id, self.prompt, self.model)
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
            cwd=str(self.scripts_dir.parent.parent),  # Project root
            model=self.model,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(self._build_analysis_prompt())

                # Process response and show progress with TUI
                async for message in client.receive_response():
                    # Check for usage metadata in message if applicable
                    if hasattr(message, "usage") and isinstance(
                        getattr(message, "usage"), dict
                    ):
                        self.usage_metadata.update(getattr(message, "usage"))

                    if isinstance(message, AssistantMessage):
                        last_tool_name = None
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                last_tool_name = block.name
                                self.ui.tool_start(block.name, block.input)
                                self.message_store.save_tool_start(
                                    block.name, block.input
                                )
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
                            self.message_store.save_error(
                                message.result or "Unknown error"
                            )
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
                                input_tokens = self.usage_metadata.get(
                                    "input_tokens", 0
                                )
                                output_tokens = self.usage_metadata.get(
                                    "output_tokens", 0
                                )
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
                                self.ui.console.print(f"  [dim]Usage:[/dim]")
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
                                self.ui.console.print(
                                    f"  [dim]  total cost: ${cost:.4f}[/dim]"
                                )

                            result: Dict[str, Any] = {
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
    model: Optional[str] = None,
    additional_instructions: Optional[str] = None,
    output_dir: Optional[str] = None,
    verbose: bool = True,
    sdk: str = "claude",
    opencode_provider: Optional[str] = None,
    opencode_model: Optional[str] = None,
    enable_sync: bool = False,
) -> Optional[Dict[str, Any]]:
    """Run reverse engineering with the specified SDK.

    Args:
        sdk: "opencode" or "claude" - determines which SDK to use
        opencode_provider: Provider ID for OpenCode (e.g., "anthropic")
        opencode_model: Model ID for OpenCode (e.g., "claude-sonnet-4-5")
        enable_sync: Enable real-time file syncing during engineering
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
        )

    # Start sync before analysis
    engineer.start_sync()

    try:
        result = asyncio.run(engineer.analyze_and_generate())
    finally:
        # Always stop sync when done
        engineer.stop_sync()

    return result
