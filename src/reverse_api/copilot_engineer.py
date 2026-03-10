"""GitHub Copilot SDK implementation for reverse engineering."""

import asyncio
from typing import Any

from .base_engineer import BaseEngineer

# Timeout for waiting on Copilot session completion (10 minutes)
_SESSION_TIMEOUT = 600


class CopilotEngineer(BaseEngineer):
    """Uses GitHub Copilot SDK to analyze HAR files and generate API scripts."""

    def __init__(
        self,
        run_id: str,
        har_path: Any,
        prompt: str,
        copilot_model: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(run_id=run_id, har_path=har_path, prompt=prompt, **kwargs)
        self.copilot_model = copilot_model or "gpt-5"

    def _build_ask_user_tool(self) -> Any:
        """Build the ask_user_question custom tool for Copilot sessions."""
        try:
            from copilot import define_tool
        except ImportError:
            raise ImportError(
                "GitHub Copilot SDK not installed. From source: uv sync --extra copilot. Installed: pip install 'reverse-api-engineer[copilot]'"
            ) from None

        from pydantic import BaseModel, Field

        class QuestionOption(BaseModel):
            label: str = Field(description="Display text for this option")
            description: str = Field(default="", description="Explanation of what this option means")

        class Question(BaseModel):
            question: str = Field(description="The question to ask the user")
            header: str = Field(default="", description="Short label for context")
            options: list[QuestionOption] = Field(default_factory=list, description="Available choices")
            multiSelect: bool = Field(default=False, description="Allow multiple selections")

        class AskUserParams(BaseModel):
            questions: list[Question] = Field(description="Questions to ask the user")

        # Capture self for use in the tool handler
        engineer = self

        @define_tool(description="Ask the user a clarifying question. Use when you need user input to proceed.")  # type: ignore[misc]
        async def ask_user_question(params: AskUserParams) -> str:
            # Convert pydantic models to dicts for the shared method
            question_dicts = [q.model_dump() for q in params.questions]
            answers = await engineer._ask_user_interactive(question_dicts)
            return "\n".join(f"{k}: {v}" for k, v in answers.items())

        return ask_user_question

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis with GitHub Copilot."""
        try:
            from copilot import CopilotClient, PermissionHandler
        except ImportError:
            self.ui.error(
                "GitHub Copilot SDK not installed. From source: uv sync --extra copilot. Installed: pip install 'reverse-api-engineer[copilot]'"
            )
            return None

        self.ui.header(self.run_id, self.prompt, self.copilot_model, self.sdk)
        self.ui.start_analysis()

        prompt = self._build_analysis_prompt()
        self.message_store.save_prompt(prompt)

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
                    self.ui.thinking(delta)

            elif event_type == "assistant.message":
                # Extract usage if available
                if hasattr(event, "data") and hasattr(event.data, "usage"):
                    usage = event.data.usage
                    if isinstance(usage, dict):
                        self.usage_metadata["input_tokens"] = usage.get("prompt_tokens", 0)
                        self.usage_metadata["output_tokens"] = usage.get("completion_tokens", 0)

            elif event_type == "session.idle":
                # Use thread-safe call in case SDK invokes callback from a different thread
                loop.call_soon_threadsafe(done_event.set)

            elif event_type == "session.compaction_start":
                self.ui.console.print("  [dim]session compacting...[/dim]")

            elif event_type == "session.compaction_complete":
                self.ui.console.print("  [dim]session compaction complete[/dim]")

        client = None
        try:
            ask_user_tool = self._build_ask_user_tool()

            client = CopilotClient(
                {
                    "auto_start": True,
                    "use_logged_in_user": True,
                }
            )
            await client.start()

            session = await client.create_session(
                {
                    "model": self.copilot_model,
                    "streaming": True,
                    "infinite_sessions": {"enabled": True},
                    "tools": [ask_user_tool],
                    "on_permission_request": PermissionHandler.approve_all,
                }
            )

            session.on(on_event)

            await session.send({"prompt": prompt})

            # Wait for session to complete with timeout protection
            try:
                await asyncio.wait_for(done_event.wait(), timeout=_SESSION_TIMEOUT)
            except TimeoutError:
                self.ui.error(f"Session timed out after {_SESSION_TIMEOUT // 60} minutes")
                self.message_store.save_error("Session timed out")
                return None

            # Save accumulated thinking text
            if accumulated_text:
                self.message_store.save_thinking("".join(accumulated_text))

            # Build result
            script_path = str(self.scripts_dir / self._get_client_filename())
            local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
            self.ui.success(script_path, local_path)

            # GitHub subscription: cost is $0 (included in Copilot subscription)
            self.usage_metadata["estimated_cost_usd"] = 0.0

            # Display usage if available
            input_tokens = self.usage_metadata.get("input_tokens", 0)
            output_tokens = self.usage_metadata.get("output_tokens", 0)
            if input_tokens > 0 or output_tokens > 0:
                self.ui.console.print("  [dim]Usage:[/dim]")
                if input_tokens > 0:
                    self.ui.console.print(f"  [dim]  input: {input_tokens:,} tokens[/dim]")
                if output_tokens > 0:
                    self.ui.console.print(f"  [dim]  output: {output_tokens:,} tokens[/dim]")
                self.ui.console.print("  [dim]  cost: $0.00 (Copilot subscription)[/dim]")

            result: dict[str, Any] = {
                "script_path": script_path,
                "usage": self.usage_metadata,
            }
            self.message_store.save_result(result)
            return result

        except Exception as e:
            self.ui.error(str(e))
            self.message_store.save_error(str(e))
            self.ui.console.print("\n[dim]Make sure GitHub Copilot CLI is installed and you are logged in: gh auth login[/dim]")
            return None

        finally:
            # Always stop the client to avoid resource leaks
            if client is not None:
                try:
                    await client.stop()
                except Exception:
                    pass
