"""Auto mode engineers: LLM-controlled browser automation with real-time reverse engineering.

Combines browser automation via MCP with simultaneous API reverse engineering.
"""

import asyncio
import logging
from typing import Any

import httpx
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    ToolPermissionContext,
)

from .engineer import ClaudeEngineer
from .opencode_engineer import OpenCodeEngineer, debug_log, format_error
from .utils import get_har_dir

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(logging.WARNING)


class ClaudeAutoEngineer(ClaudeEngineer):
    """Auto mode using Claude SDK: LLM controls browser via MCP while reverse engineering."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        model: str,
        output_dir: str | None = None,
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
        language_name = {
            "python": "Python",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
        }.get(self.output_language, "Python")

        client_filename = self._get_client_filename()
        run_command = self._get_run_command()

        # Build language-specific generation instructions
        if self.output_language == "javascript":
            generation_instructions = f"""2. **Generate JavaScript API client** at `{self.scripts_dir}/{client_filename}`:
   - Use modern JavaScript (ES2022+) with ESM modules (import/export)
   - Use native `fetch` API for HTTP requests (Node.js 18+ built-in)
   - If advanced features needed (retries, interceptors), use `axios`
   - Include proper authentication handling
   - Create separate async functions for each API endpoint
   - Add JSDoc comments for type documentation
   - Include example usage in main section
   - Make it production-ready and maintainable
   - If using external dependencies, generate package.json

3. **Create documentation** at `{self.scripts_dir}/README.md`:
   - Explain what APIs were discovered
   - How authentication works
   - How to use each function
   - Requirements: Node.js 18+
   - Any limitations or requirements

4. **Test your implementation**:
   - If package.json was generated, first run: npm install
   - Run with: {run_command}
   - You have up to 5 attempts to fix any issues
   - If initial implementation fails, analyze errors and iterate"""
            output_files = f"""1. `{self.scripts_dir}/{client_filename}` - Production JavaScript API client
2. `{self.scripts_dir}/README.md` - Documentation with usage examples
3. `{self.scripts_dir}/package.json` - Only if external dependencies are needed"""

        elif self.output_language == "typescript":
            generation_instructions = f"""2. **Generate TypeScript API client** at `{self.scripts_dir}/{client_filename}`:
   - Use TypeScript with strict typing enabled
   - Use ESM modules (import/export syntax)
   - Use native `fetch` API for HTTP requests (Node.js 18+ built-in)
   - If advanced features needed, use `axios`
   - Define TypeScript interfaces for all request/response types
   - Include proper authentication handling
   - Create separate async functions for each API endpoint
   - Export a class-based API client with proper encapsulation
   - Include example usage in main section
   - Make it production-ready and maintainable
   - Generate package.json with tsx, typescript, @types/node

3. **Create documentation** at `{self.scripts_dir}/README.md`:
   - Explain what APIs were discovered
   - How authentication works
   - How to use each function
   - Requirements: Node.js 18+
   - Any limitations or requirements

4. **Test your implementation**:
   - Run: npm install && {run_command}
   - You have up to 5 attempts to fix any issues
   - If initial implementation fails, analyze errors and iterate"""
            output_files = f"""1. `{self.scripts_dir}/{client_filename}` - Production TypeScript API client
2. `{self.scripts_dir}/README.md` - Documentation with usage examples
3. `{self.scripts_dir}/package.json` - Dependencies and run scripts"""

        else:  # python
            generation_instructions = f"""2. **Generate Python API client** at `{self.scripts_dir}/{client_filename}`:
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
   - Run with: {run_command}
   - You have up to 5 attempts to fix any issues
   - If initial implementation fails, analyze errors and iterate"""
            output_files = f"""1. `{self.scripts_dir}/{client_filename}` - Production Python API client
2. `{self.scripts_dir}/README.md` - Documentation with usage examples"""

        return f"""You are an autonomous AI agent with browser control via MCP tools.
        Your mission is to browse, monitor network traffic, and generate production-ready {language_name} API code.

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
While browsing, periodically call `browser_network_requests()` to monitor API traffic in real-time.
Keep in mind that you will also have access to the full network traffic when closing the browser:
- Analyze requests and responses
- Identify authentication patterns (cookies, tokens, headers)
- Note API endpoints, methods, parameters
- Track response structures

### Phase 3: CAPTURE
When you have sufficient data or have accomplished the mission goal, call `browser_close()` to save the HAR file:
- This saves all captured network traffic to: {self.har_path}
- Returns: {{"har_path": str, "resources": {{...}}}}

### Phase 4: REVERSE ENGINEER
Based on the network traffic you observed, generate production-ready {language_name} code:

1. **Analyze the HAR file** you just captured at {self.har_path}
   - Read and parse the HAR file
   - Extract all API calls, authentication, patterns

{generation_instructions}

## IMPORTANT NOTES

- Think step-by-step and narrate your actions as you browse
- Call `browser_network_requests()` frequently to monitor traffic
- Don't rush - ensure you capture all necessary API calls before closing browser
- After generating code, always test it to verify it works
- Handle bot detection by switching to Playwright with CDP if needed
- **Screenshot size limit**: Screenshots must be under 1MB. Prefer element-specific screenshots over full-page screenshots to avoid errors

## OUTPUT FILES REQUIRED

{output_files}

Your final response should confirm the files were created and provide a brief summary of:
- What APIs were discovered
- The authentication method used
- Whether the implementation works
- Any limitations or caveats
"""

    async def _handle_tool_permission(self, tool_name: str, input_data: dict[str, Any], context: ToolPermissionContext) -> PermissionResultAllow:
        """Handle tool permission requests, with interactive UI for AskUserQuestion."""
        if tool_name == "AskUserQuestion":
            questions = input_data.get("questions", [])
            answers = await self._ask_user_interactive(questions)
            return PermissionResultAllow(
                updated_input={"questions": questions, "answers": answers},
            )
        # Auto-approve all other tools
        return PermissionResultAllow(updated_input=input_data)

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run auto mode with MCP browser integration.

        Reuses _process_streaming_response and follow-up loop from ClaudeEngineer.
        """
        self.ui.header(self.run_id, self.prompt, self.model, mode="agent")
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
            permission_mode="bypassPermissions",
            can_use_tool=self._handle_tool_permission,
            cwd=str(self.scripts_dir.parent.parent),  # Project root
            model=self.model,
            env={"CLAUDECODE": ""},
            stderr=self._handle_cli_stderr,
        )

        last_result: dict[str, Any] | None = None

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(self._build_auto_prompt())

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

        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result

        except Exception as e:
            error_msg = str(e)
            self.ui.error(error_msg)
            self.message_store.save_error(error_msg)

            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                self.ui.console.print("\n[yellow]Screenshot too large (exceeds 1MB limit)[/yellow]")
                self.ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
                self.ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )
            elif "MCP server" in error_msg or "npx" in error_msg:
                self.ui.console.print("\n[dim]Make sure rae-playwright-mcp is installed: npm install -g rae-playwright-mcp[/dim]")
            else:
                self.ui.console.print("\n[dim]Make sure Claude Code CLI is installed: npm install -g @anthropic-ai/claude-code[/dim]")
            return None


class OpenCodeAutoEngineer(OpenCodeEngineer):
    """Auto mode using OpenCode SDK: Register MCP server dynamically."""

    def __init__(self, run_id: str, prompt: str, output_dir: str | None = None, **kwargs):
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

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run auto mode with OpenCode MCP integration."""
        self.opencode_ui.header(self.run_id, self.prompt, self.opencode_model, mode="agent")
        self.opencode_ui.start_analysis()
        self.message_store.save_prompt(self._build_auto_prompt())

        try:
            auth = self._get_auth()
            async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=600.0, auth=auth) as client:
                try:
                    health_r = await client.get("/global/health")
                    health_r.raise_for_status()
                    health = health_r.json()
                    self.opencode_ui.health_check(health)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        debug_log(f"Health check failed: Authentication required")
                        self.opencode_ui.error("Authentication failed. OpenCode server requires a password.")
                        self.opencode_ui.console.print("\n[dim]Please set OPENCODE_SERVER_PASSWORD environment variable[/dim]")
                        if self.opencode_username != "opencode":
                            self.opencode_ui.console.print(f"[dim]Username: {self.opencode_username}[/dim]")
                        return None
                    raise
                except Exception as e:
                    debug_log(f"Health check failed: {e}")
                    self.opencode_ui.error(f"OpenCode server not responding. Is it running on {self.BASE_URL}?")
                    self.opencode_ui.console.print("\n[dim]Please run: opencode serve[/dim]")
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

                prompt_r = await client.post(f"/session/{self._session_id}/message", json=prompt_body)
                prompt_r.raise_for_status()

                # Wait for events to complete
                try:
                    await asyncio.wait_for(event_task, timeout=600.0)
                except TimeoutError:
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
            script_path = str(self.scripts_dir / self._get_client_filename())

            # Fetch actual provider and model used
            try:
                auth = self._get_auth()
                async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=10.0, auth=auth) as client:
                    messages_r = await client.get(f"/session/{self._session_id}/message")
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
            local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
            self.opencode_ui.success(script_path, local_path)

            result_data: dict[str, Any] = {
                "script_path": script_path,
                "usage": self.usage_metadata,
                "session_id": self._session_id,
            }
            self.message_store.save_result(result_data)
            return result_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                self.opencode_ui.error("Authentication failed. OpenCode server requires a password.")
                self.opencode_ui.console.print("\n[dim]Please set OPENCODE_SERVER_PASSWORD environment variable[/dim]")
                if self.opencode_username != "opencode":
                    self.opencode_ui.console.print(f"[dim]Username: {self.opencode_username}[/dim]")
                self.message_store.save_error("Authentication failed")
                return None
            error_msg = f"HTTP {e.response.status_code}: {str(e)}"
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return None

        except httpx.ConnectError:
            self.opencode_ui.error("Connection error")
            self.opencode_ui.console.print("\n[dim]Make sure OpenCode is running: opencode[/dim]")
            self.message_store.save_error("Connection error")
            return None

        except Exception as e:
            error_msg = format_error(e)
            debug_log(f"Exception in OpenCodeAutoEngineer.analyze_and_generate: {error_msg}")
            self.opencode_ui.error(error_msg)
            self.message_store.save_error(error_msg)

            # Handle screenshot buffer size errors specifically
            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                self.opencode_ui.console.print("\n[yellow]⚠ Screenshot too large (exceeds 1MB limit)[/yellow]")
                self.opencode_ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
                self.opencode_ui.console.print(
                    "[dim]Consider using browser_snapshot() for accessibility tree information when screenshots aren't needed.[/dim]"
                )

            return None

        finally:
            # Best effort cleanup - deregister MCP server
            if self.mcp_name:
                try:
                    auth = self._get_auth()
                    async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=5.0, auth=auth) as client:
                        await client.delete(f"/mcp/{self.mcp_name}")
                        debug_log(f"Cleaned up MCP server: {self.mcp_name}")
                except Exception:
                    pass  # Ignore cleanup errors


class CopilotAutoEngineer:
    """Auto mode using Copilot SDK: LLM controls browser via MCP while reverse engineering.

    Uses composition rather than inheritance since CopilotEngineer requires lazy imports.
    Delegates to CopilotEngineer for the core logic and adds MCP browser integration.
    """

    def __init__(
        self,
        run_id: str,
        prompt: str,
        copilot_model: str | None = None,
        output_dir: str | None = None,
        **kwargs: Any,
    ):
        from .copilot_engineer import CopilotEngineer

        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        self._engineer = CopilotEngineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            copilot_model=copilot_model,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id

    def start_sync(self) -> None:
        self._engineer.start_sync()

    def stop_sync(self) -> None:
        self._engineer.stop_sync()

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run auto mode with Copilot SDK and MCP browser integration."""
        try:
            from copilot import CopilotClient, PermissionHandler
        except ImportError:
            self._engineer.ui.error(
                "GitHub Copilot SDK not installed. From source: uv sync --extra copilot. Installed: pip install 'reverse-api-engineer[copilot]'"
            )
            return None

        eng = self._engineer
        eng.ui.header(eng.run_id, eng.prompt, eng.copilot_model, eng.sdk, mode="agent")
        eng.ui.start_analysis()

        auto_prompt = ClaudeAutoEngineer._build_auto_prompt(eng)
        eng.message_store.save_prompt(auto_prompt)

        done_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        accumulated_text: list[str] = []

        def on_event(event: Any) -> None:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

            if event_type == "assistant.message_delta":
                delta = ""
                if hasattr(event, "data") and hasattr(event.data, "delta_content"):
                    delta = event.data.delta_content or ""
                if delta:
                    accumulated_text.append(delta)
                    eng.ui.thinking(delta)
            elif event_type == "assistant.message":
                if hasattr(event, "data") and hasattr(event.data, "usage"):
                    usage = event.data.usage
                    if isinstance(usage, dict):
                        eng.usage_metadata["input_tokens"] = usage.get("prompt_tokens", 0)
                        eng.usage_metadata["output_tokens"] = usage.get("completion_tokens", 0)
            elif event_type == "session.idle":
                # Use thread-safe call in case SDK invokes callback from a different thread
                loop.call_soon_threadsafe(done_event.set)

        client = None
        try:
            client = CopilotClient(
                {
                    "auto_start": True,
                    "use_logged_in_user": True,
                }
            )
            await client.start()

            mcp_config = {
                "type": "local",
                "command": "npx",
                "args": [
                    "-y",
                    "rae-playwright-mcp@latest",
                    "run-mcp-server",
                    "--run-id",
                    self.mcp_run_id,
                ],
                "tools": ["*"],
                "timeout": 30000,
            }

            async def on_pre_tool_use(input: dict, _invocation: dict) -> dict:
                tool_name = input.get("toolName", "unknown")
                tool_args = input.get("toolArgs") or {}
                eng.ui.tool_start(tool_name, tool_args)
                eng.message_store.save_tool_start(tool_name, tool_args)
                return {"permissionDecision": "allow", "modifiedArgs": tool_args}

            async def on_post_tool_use(input: dict, invocation: dict) -> dict:
                tool_name = input.get("toolName", "unknown")
                is_error = invocation.get("resultType") == "error" if isinstance(invocation, dict) else False
                output = invocation.get("result") if isinstance(invocation, dict) else None
                eng.ui.tool_result(tool_name, is_error=is_error, output=str(output) if output else None)
                eng.message_store.save_tool_result(tool_name, is_error, str(output) if output else None)
                return {}

            session = await client.create_session(
                {
                    "model": eng.copilot_model,
                    "streaming": True,
                    "infinite_sessions": {"enabled": True},
                    "mcp_servers": {"playwright": mcp_config},
                    "on_permission_request": PermissionHandler.approve_all,
                    "hooks": {
                        "on_pre_tool_use": on_pre_tool_use,
                        "on_post_tool_use": on_post_tool_use,
                    },
                }
            )

            session.on(on_event)
            await session.send({"prompt": auto_prompt})

            # Wait with timeout protection (10 minutes)
            try:
                await asyncio.wait_for(done_event.wait(), timeout=600)
            except TimeoutError:
                eng.ui.error("Session timed out (10 min)")
                eng.message_store.save_error("Session timed out")
                return None

            if accumulated_text:
                eng.message_store.save_thinking("".join(accumulated_text))

            script_path = str(eng.scripts_dir / eng._get_client_filename())
            local_path = str(eng.local_scripts_dir / eng._get_client_filename()) if eng.local_scripts_dir else None
            eng.ui.success(script_path, local_path)
            eng.usage_metadata["estimated_cost_usd"] = 0.0

            result: dict[str, Any] = {
                "script_path": script_path,
                "usage": eng.usage_metadata,
            }
            eng.message_store.save_result(result)
            return result

        except Exception as e:
            error_msg = str(e)
            eng.ui.error(error_msg)
            eng.message_store.save_error(error_msg)

            if "buffer size" in error_msg.lower() or "1048576" in error_msg or "exceeded maximum buffer" in error_msg.lower():
                eng.ui.console.print("\n[yellow]Screenshot too large (exceeds 1MB limit)[/yellow]")
                eng.ui.console.print("[dim]Tip: The AI should take element-specific screenshots instead of full-page screenshots.[/dim]")
            else:
                eng.ui.console.print("\n[dim]Make sure GitHub Copilot CLI is installed and you are logged in: gh auth login[/dim]")
            return None

        finally:
            # Always stop the client to avoid resource leaks
            if client is not None:
                try:
                    await client.stop()
                except Exception:
                    pass
