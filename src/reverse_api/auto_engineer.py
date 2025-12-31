"""Auto mode engineers: LLM-controlled browser automation with real-time reverse engineering.

Combines browser automation via MCP with simultaneous API reverse engineering.
"""

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
import httpx

from .base_engineer import BaseEngineer
from .engineer import ClaudeEngineer
from .opencode_engineer import OpenCodeEngineer, debug_log
from .utils import get_har_dir

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(
    logging.WARNING
)


class ClaudeAutoEngineer(ClaudeEngineer):
    """Auto mode using Claude SDK: LLM controls browser via MCP while reverse engineering."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        model: str,
        output_dir: Optional[str] = None,
        **kwargs,
    ):
        """Initialize auto engineer with expected HAR path (created by MCP)."""
        # Calculate expected HAR path - MCP will create it during execution
        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        # Initialize with expected HAR path (created by MCP via --run-id flag)
        super().__init__(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id

    def _build_auto_prompt(self) -> str:
        """Build autonomous browsing + engineering prompt."""
        return f"""You are an autonomous AI agent with browser control via MCP tools. Your mission is to browse, monitor network traffic, and generate production-ready Python API code.

<mission>
{self.prompt}
</mission>

<output_directory>
{self.scripts_dir}
</output_directory>

## WORKFLOW

Follow this workflow step-by-step:

### Phase 1: BROWSE
Use browser MCP tools to accomplish the mission goal, here are some of the tools you can use.
This list is not exhaustive, but it's a good starting point:
- `browser_navigate` - Navigate to a URL
- `browser_click` - Click an element
- `browser_scroll` - Scroll the page
- `browser_close` - Close the browser
- `browser_evaluate` - Evaluate JavaScript code
- `browser_press_key` - Press a key
- `browser_run_code` - Run Playwright code
- `browser_type` - Type text into input
- `browser_wait_for` - Wait for text to appear or disappear or a specified time to pass
- `browser_snapshot` - Get accessibility tree (useful alternative to screenshots for understanding page structure)
- `browser_take_screenshot` - Take screenshot for context (IMPORTANT: Prefer element-specific screenshots over full-page to avoid size limits)
- And other browser MCP tools available

**Screenshot Guidelines:**
- Screenshots have a 1MB size limit - avoid full-page screenshots when possible
- Prefer taking element-specific screenshots using CSS selectors
- If you need context, take multiple smaller screenshots of key areas
- Use `browser_snapshot()` when you need page structure information without visual details

### Phase 2: MONITOR
While browsing, periodically call `browser_network_requests` to monitor API traffic in real-time if needed, keep in mind that you will also have access to the full network traffic when closing the browser:
- Analyze requests and responses
- Identify authentication patterns (cookies, tokens, headers)
- Note API endpoints, methods, parameters
- Track response structures

### Phase 3: CAPTURE
When you have sufficient data or have accomplished the mission goal, call `browser_close()` to save the HAR file:
- This saves all captured network traffic to: {self.har_path}
- Returns: {{"har_path": str, "resources": {{...}}}}

### Phase 4: REVERSE ENGINEER
Based on the network traffic you observed, generate production-ready Python code:

1. **Analyze the HAR file** you just captured at {self.har_path}
   - Read and parse the HAR file
   - Extract all API calls, authentication, patterns

2. **Generate Python API client** at `{self.scripts_dir}/api_client.py`:
   - Use `requests` library as default (or Playwright if needed for bot detection)
   - Include proper authentication handling
   - Create separate functions for each API endpoint
   - Add type hints, docstrings, error handling
   - Include example usage in main section
   - Make it production-ready and maintainable

3. **Create documentation** at `{self.scripts_dir}/README.md`:
   - Explain what APIs were discovered
   - How authentication works
   - How to use each function
   - Example usage
   - Any limitations or requirements

4. **Test your implementation**:
   - After generating the code, test it to ensure it works
   - You have up to 5 attempts to fix any issues
   - If initial implementation fails, analyze errors and iterate

## IMPORTANT NOTES

- Think step-by-step and narrate your actions as you browse
- Call `browser_network_requests()` frequently to monitor traffic
- Don't rush - ensure you capture all necessary API calls before closing browser
- After generating code, always test it to verify it works
- Handle bot detection by switching to Playwright with CDP if needed
- **Screenshot size limit**: Screenshots must be under 1MB. Prefer element-specific screenshots over full-page screenshots to avoid errors

## OUTPUT FILES REQUIRED

1. `{self.scripts_dir}/api_client.py` - Production Python API client
2. `{self.scripts_dir}/README.md` - Documentation with usage examples

Your final response should confirm the files were created and provide a brief summary of:
- What APIs were discovered
- The authentication method used
- Whether the implementation works
- Any limitations or caveats
"""

    async def analyze_and_generate(self) -> Optional[Dict[str, Any]]:
        """Run auto mode with MCP browser integration."""
        self.ui.header(self.run_id, self.prompt, self.model)
        self.ui.start_analysis()
        self.message_store.save_prompt(self._build_auto_prompt())


        mcp_config = {
            "type": "stdio",
            "command": "npx",
            "args": [
                "rae-playwright-mcp@latest",
                "run-mcp-server",
                "--run-id",
                self.mcp_run_id,
            ],
        }

        options = ClaudeAgentOptions(
            mcp_servers={"playwright": mcp_config},
            permission_mode="bypassPermissions",  # Auto-accept browser tool usage
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
            ],
            cwd=str(self.scripts_dir.parent.parent),  # Project root
            model=self.model,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(self._build_auto_prompt())

                # Process response and show progress with TUI
                async for message in client.receive_response():
                    # Check for usage metadata
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
            error_msg = str(e)
            self.ui.error(error_msg)
            self.message_store.save_error(error_msg)

            # Handle screenshot buffer size errors specifically
            if (
                "buffer size" in error_msg.lower()
                or "1048576" in error_msg
                or "exceeded maximum buffer" in error_msg.lower()
            ):
                self.ui.console.print(
                    "\n[yellow]⚠ Screenshot too large (exceeds 1MB limit)[/yellow]"
                )
                self.ui.console.print(
                    "[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]"
                )
                self.ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )
            # Provide helpful error messages
            elif "MCP server" in error_msg or "npx" in error_msg:
                self.ui.console.print(
                    "\n[dim]Make sure rae-playwright-mcp is installed: "
                    "npm install -g rae-playwright-mcp[/dim]"
                )
            else:
                self.ui.console.print(
                    "\n[dim]Make sure Claude Code CLI is installed: "
                    "npm install -g @anthropic-ai/claude-code[/dim]"
                )
            return None

        return None


class OpenCodeAutoEngineer(OpenCodeEngineer):
    """Auto mode using OpenCode SDK: Register MCP server dynamically."""

    def __init__(
        self, run_id: str, prompt: str, output_dir: Optional[str] = None, **kwargs
    ):
        """Initialize auto engineer with expected HAR path (created by MCP)."""
        # Calculate expected HAR path - MCP will create it during execution
        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        super().__init__(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id
        self.mcp_name = None  # Will be set to unique name per session

    def _build_auto_prompt(self) -> str:
        """Build autonomous browsing + engineering prompt."""
        # Reuse the same prompt from ClaudeAutoEngineer
        return ClaudeAutoEngineer._build_auto_prompt(self)

    async def analyze_and_generate(self) -> Optional[Dict[str, Any]]:
        """Run auto mode with OpenCode MCP integration."""
        self.opencode_ui.header(self.run_id, self.prompt, self.opencode_model)
        self.opencode_ui.start_analysis()
        self.message_store.save_prompt(self._build_auto_prompt())

        try:
            async with httpx.AsyncClient(
                base_url=self.BASE_URL, timeout=600.0
            ) as client:
                try:
                    health_r = await client.get("/global/health")
                    health_r.raise_for_status()
                    health = health_r.json()
                    self.opencode_ui.health_check(health)
                except Exception as e:
                    debug_log(f"Health check failed: {e}")
                    self.opencode_ui.error(
                        f"OpenCode server not responding. Is it running on {self.BASE_URL}?"
                    )
                    return None

                # Create session first
                session_r = await client.post("/session", json={})
                session_r.raise_for_status()
                session_data = session_r.json()
                self._session_id = session_data["id"]
                self.opencode_ui.session_created(self._session_id)

                # Register MCP server with unique name
                # Format per OpenCode docs: { name, config: { type: "local", command: [...] } }
                self.mcp_name = f"playwright-{self._session_id}"
                mcp_config = {
                    "name": self.mcp_name,
                    "config": {
                        "type": "local",
                        "command": [
                            "npx",
                            "-y",
                            "rae-playwright-mcp@latest",
                            "run-mcp-server",
                            "--run-id",
                            self.mcp_run_id,
                        ],
                        "enabled": True,
                        "timeout": 30000,  # 30 seconds for MCP to start
                    },
                }

                try:
                    debug_log(f"Registering MCP server: {self.mcp_name}")
                    mcp_r = await client.post("/mcp", json=mcp_config)
                    mcp_r.raise_for_status()
                    debug_log("MCP server registered successfully")
                except Exception as e:
                    self.opencode_ui.error(f"Failed to register MCP server: {e}")
                    return None

                # Start event stream BEFORE sending message
                event_task = asyncio.create_task(self._stream_events(client))

                # Give event stream a moment to connect
                await asyncio.sleep(0.1)

                # Send auto prompt
                model_id = self.MODEL_MAP.get(self.opencode_model, self.opencode_model)
                prompt_body = {
                    "model": {
                        "providerID": self.opencode_provider,
                        "modelID": model_id,
                    },
                    "parts": [{"type": "text", "text": self._build_auto_prompt()}],
                }

                prompt_r = await client.post(
                    f"/session/{self._session_id}/message", json=prompt_body
                )
                prompt_r.raise_for_status()

                # Wait for events to complete
                try:
                    await asyncio.wait_for(event_task, timeout=600.0)
                except asyncio.TimeoutError:
                    self._last_error = "Session timed out (10 min)"
                    self.opencode_ui.error(self._last_error)

                # Stop streaming UI
                self.opencode_ui.stop_streaming()

                # Deregister MCP server
                try:
                    if self.mcp_name:
                        debug_log(f"Deregistering MCP server: {self.mcp_name}")
                        await client.delete(f"/mcp/{self.mcp_name}")
                        debug_log("MCP server deregistered")
                except Exception as e:
                    debug_log(f"Failed to deregister MCP server: {e}")

                # Check for errors
                if self._last_error:
                    self.opencode_ui.error(self._last_error)
                    self.message_store.save_error(self._last_error)
                    return None

            # Success
            script_path = str(self.scripts_dir / "api_client.py")

            # Fetch actual provider and model used
            try:
                async with httpx.AsyncClient(
                    base_url=self.BASE_URL, timeout=10.0
                ) as client:
                    messages_r = await client.get(
                        f"/session/{self._session_id}/message"
                    )
                    if messages_r.status_code == 200:
                        messages = messages_r.json()
                        for msg in messages:
                            info = msg.get("info", {})
                            if info.get("role") == "assistant":
                                provider_id = info.get("providerID")
                                model_id = info.get("modelID")
                                if provider_id and model_id:
                                    self.opencode_ui.model_info(provider_id, model_id)
                                    break
            except Exception as e:
                debug_log(f"Failed to fetch session messages: {e}")

            # Show session summary
            self.opencode_ui.session_summary(self.usage_metadata)
            local_path = (
                str(self.local_scripts_dir / "api_client.py")
                if self.local_scripts_dir
                else None
            )
            self.opencode_ui.success(script_path, local_path)

            result_data: Dict[str, Any] = {
                "script_path": script_path,
                "usage": self.usage_metadata,
                "session_id": self._session_id,
            }
            self.message_store.save_result(result_data)
            return result_data

        except httpx.ConnectError:
            self.opencode_ui.error("Connection error")
            self.opencode_ui.console.print(
                "\n[dim]Make sure OpenCode is running: opencode[/dim]"
            )
            self.message_store.save_error("Connection error")
            return None

        except Exception as e:
            error_msg = str(e) if str(e) else "Unknown error"
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)

            # Handle screenshot buffer size errors specifically
            if (
                "buffer size" in error_msg.lower()
                or "1048576" in error_msg
                or "exceeded maximum buffer" in error_msg.lower()
            ):
                self.opencode_ui.console.print(
                    "\n[yellow]⚠ Screenshot too large (exceeds 1MB limit)[/yellow]"
                )
                self.opencode_ui.console.print(
                    "[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]"
                )
                self.opencode_ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )

            return None

        finally:
            # Best effort cleanup - deregister MCP server
            if self.mcp_name:
                try:
                    async with httpx.AsyncClient(
                        base_url=self.BASE_URL, timeout=5.0
                    ) as client:
                        await client.delete(f"/mcp/{self.mcp_name}")
                        debug_log(f"Cleaned up MCP server: {self.mcp_name}")
                except Exception:
                    pass  # Ignore cleanup errors
