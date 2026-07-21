"""Abstract base class for API reverse engineering."""

import asyncio
import os
import shlex
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import questionary

from .messages import MessageStore
from .session import SessionManager
from .sync import FileSyncWatcher, get_available_directory
from .tui import THEME_PRIMARY, THEME_SECONDARY, ClaudeUI
from .utils import generate_folder_name, get_docs_dir, get_history_path, get_scripts_dir

DEBUG = os.environ.get("DEBUG", "0") == "1"

OTHER_OPTION = "Other (type your answer)"

NON_INTERACTIVE_ASK_USER_MESSAGE = (
    "The user is running the CLI in non-interactive mode and cannot answer. "
    "Assume the best reasonable answer from context and continue. "
    "If you truly cannot proceed without a human choice, stop and instruct the caller "
    "to start a new session with a clearer, more specific prompt."
)


class BaseEngineer(ABC):
    """Abstract base class for API reverse engineering implementations."""

    _OUTPUT_LANGUAGE_EXTENSIONS = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "go": ".go",
        "java": ".java",
        "csharp": ".cs",
    }

    def __init__(
        self,
        run_id: str,
        har_path: Path,
        prompt: str,
        model: str | None = None,
        additional_instructions: str | None = None,
        output_dir: str | None = None,
        verbose: bool = True,
        enable_sync: bool = False,
        sdk: str = "claude",
        is_fresh: bool = False,
        output_language: str = "python",
        output_mode: str = "client",
        interactive: bool = True,
    ):
        self.run_id = run_id
        self.har_path = har_path
        self.prompt = prompt
        self.model = model
        self.additional_instructions = additional_instructions
        self.output_mode = output_mode

        # Select output directory based on mode
        if output_mode == "docs":
            self.scripts_dir = get_docs_dir(run_id, output_dir)
        else:
            self.scripts_dir = get_scripts_dir(run_id, output_dir)

        self.ui = ClaudeUI(verbose=verbose)
        self.usage_metadata: dict[str, Any] = {}
        self.message_store = MessageStore(run_id, output_dir)
        self.enable_sync = enable_sync
        self.sdk = sdk
        self.is_fresh = is_fresh
        self.output_language = self._resolve_output_language(output_language)
        self.existing_client_path = self._get_existing_client_path()
        self.sync_watcher: FileSyncWatcher | None = None
        self.local_scripts_dir: Path | None = None
        self._stderr_error_shown = False
        # When False, _prompt_follow_up() returns None immediately so the
        # conversation loop in subclasses ends after the first generation.
        # Set this from --json / --no-interactive entry points.
        self.interactive = interactive
        self._json_event_sink: Any = None

    def _emit_json_event(self, event: dict[str, Any]) -> None:
        sink = self._json_event_sink
        if sink:
            sink(event)

    @staticmethod
    def _is_ask_user_tool_name(tool_name: str) -> bool:
        n = tool_name.lower().replace("-", "_")
        if n == "askuserquestion":
            return True
        return "ask" in n and "user" in n and "question" in n

    def _handle_cli_stderr(self, line: str) -> None:
        """Filter CLI subprocess stderr. Shows full output in DEBUG mode, otherwise shows a single clean error."""
        if DEBUG:
            self.ui.console.print(f"[dim]  stderr: {line.rstrip()}[/dim]")
            return

        # Known noisy errors from the CLI control protocol — show once
        if "Error in hook callback" in line or "Stream closed" in line:
            if not self._stderr_error_shown:
                self._stderr_error_shown = True
                self.ui.console.print("  [dim]![/dim] [dim]cli stream error (set DEBUG=1 for details)[/dim]")
            return

        # Suppress other common noise (stack traces, source maps)
        if line.startswith("      at ") or "| " in line[:20]:
            return

    def start_sync(self):
        """Start real-time file sync if enabled."""
        if not self.enable_sync:
            return

        # Generate local directory name
        base_name = generate_folder_name(self.prompt, sdk=self.sdk)

        # Choose base path based on output mode
        if self.output_mode == "docs":
            base_path = Path.cwd() / "docs"
        else:
            base_path = Path.cwd() / "scripts"

        # Get available directory (won't overwrite existing non-empty dirs)
        local_dir = get_available_directory(base_path, base_name)

        self.local_scripts_dir = local_dir

        # Create sync watcher
        def on_sync(message):
            self.ui.sync_flash(message)

        def on_error(message):
            self.ui.sync_error(message)

        self.sync_watcher = FileSyncWatcher(
            source_dir=self.scripts_dir,
            dest_dir=local_dir,
            on_sync=on_sync,
            on_error=on_error,
            debounce_ms=500,
        )
        self.sync_watcher.start()
        self.ui.sync_started(str(local_dir))

    def stop_sync(self):
        """Stop real-time file sync."""
        if self.sync_watcher:
            try:
                self.sync_watcher.stop()
            except Exception as e:
                self.ui.sync_error(f"Failed to stop sync watcher: {e}")
            finally:
                self.sync_watcher = None

    def flush_sync(self):
        """Flush pending sync events and ensure all files are synced locally."""
        if self.sync_watcher:
            self.sync_watcher.flush()

    def get_sync_status(self) -> dict | None:
        """Get current sync status."""
        if self.sync_watcher:
            return self.sync_watcher.get_status()
        return None

    async def _ask_user_questions(self, questions: list[dict[str, Any]]) -> dict[str, str]:
        """Resolve AskUserQuestion prompts (interactive UI or non-interactive stub)."""
        if not self.interactive:
            answers: dict[str, str] = {}
            count = 0
            for q in questions:
                question_text = q.get("question", "") if isinstance(q, dict) else getattr(q, "question", "")
                if not question_text:
                    continue
                answers[question_text] = NON_INTERACTIVE_ASK_USER_MESSAGE
                count += 1
            if count:
                self.ui.console.print(
                    f"  [dim]AskUserQuestion skipped ({count} question(s); non-interactive mode)[/dim]"
                )
                self._emit_json_event({"event": "ask_user_skipped", "count": count})
            return answers
        return await self._ask_user_interactive(questions)

    async def _ask_user_interactive(self, questions: list[dict[str, Any]]) -> dict[str, str]:
        """Prompt the user interactively for answers to questions.

        Shared logic used by both ClaudeEngineer and CopilotEngineer.

        Args:
            questions: List of question dicts with keys: question, header, options, multiSelect

        Returns:
            Dict mapping question text to user's answer string.
        """
        answers: dict[str, str] = {}

        self.ui.console.print()
        self.ui.console.print(f"  [{THEME_PRIMARY}]?[/{THEME_PRIMARY}] [bold white]Agent Question[/bold white]")
        self.ui.console.print()

        for q in questions:
            question_text = q.get("question", "") if isinstance(q, dict) else getattr(q, "question", "")
            header = q.get("header", "") if isinstance(q, dict) else getattr(q, "header", "")
            options = q.get("options", []) if isinstance(q, dict) else getattr(q, "options", [])
            multi_select = q.get("multiSelect", False) if isinstance(q, dict) else getattr(q, "multiSelect", False)

            if not question_text:
                continue

            if header:
                self.ui.console.print(f"  [dim]{header}[/dim]")

            try:
                if multi_select:
                    choices = [
                        f"{self._get_opt_field(opt, 'label')} - {self._get_opt_field(opt, 'description')}"
                        if self._get_opt_field(opt, "description")
                        else self._get_opt_field(opt, "label")
                        for opt in options
                    ]
                    if choices:
                        choices.append(OTHER_OPTION)
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

                        has_other = OTHER_OPTION in selected
                        labels = [s.split(" - ")[0] if " - " in s else s for s in selected if s != OTHER_OPTION]

                        if has_other:
                            other_text = await questionary.text(
                                "   > Your answer: ",
                                qmark="",
                                style=questionary.Style([("question", f"fg:{THEME_SECONDARY}")]),
                            ).ask_async()
                            if other_text is None:
                                raise KeyboardInterrupt
                            if other_text.strip():
                                labels.append(other_text.strip())

                        answers[question_text] = ", ".join(labels)
                    else:
                        answer = await questionary.text(
                            f" > {question_text}",
                            qmark="",
                            style=questionary.Style([("question", f"fg:{THEME_SECONDARY}")]),
                        ).ask_async()
                        if answer is None:
                            raise KeyboardInterrupt
                        answers[question_text] = answer.strip()
                else:
                    choices = [
                        f"{self._get_opt_field(opt, 'label')} - {self._get_opt_field(opt, 'description')}"
                        if self._get_opt_field(opt, "description")
                        else self._get_opt_field(opt, "label")
                        for opt in options
                    ]
                    if choices:
                        choices.append(OTHER_OPTION)
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

                        if answer == OTHER_OPTION:
                            answer = await questionary.text(
                                "   > Your answer: ",
                                qmark="",
                                style=questionary.Style([("question", f"fg:{THEME_SECONDARY}")]),
                            ).ask_async()
                            if answer is None:
                                raise KeyboardInterrupt
                            answers[question_text] = answer.strip()
                        else:
                            label = answer.split(" - ")[0] if " - " in answer else answer
                            answers[question_text] = label
                    else:
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
                self.ui.console.print("  [dim]User cancelled question[/dim]")
                answers[question_text] = ""

        self.ui.console.print()
        return answers

    async def _prompt_follow_up(self) -> str | None:
        """Prompt user for a follow-up message. Returns None to finish.

        In non-interactive mode (e.g. --json / --no-interactive) returns None
        immediately so the conversation loop terminates after the first
        generation. Otherwise uses plain input() via executor instead of
        questionary to avoid terminal state issues after the SDK subprocess
        exits.
        """
        if not self.interactive:
            # Still flush sync so any partial output reaches disk before we exit.
            self.flush_sync()
            return None
        # Ensure all files are synced locally before waiting for user input
        self.flush_sync()
        self.ui.console.print()
        self.ui.console.print(f"  [{THEME_PRIMARY}]─[/{THEME_PRIMARY}] [dim]type a follow-up or press Enter to finish[/dim]")
        try:
            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(None, lambda: input("  > "))
            if not answer or not answer.strip():
                return None
            return answer.strip()
        except (KeyboardInterrupt, EOFError):
            return None

    @staticmethod
    def _get_opt_field(opt: Any, field: str) -> str:
        """Get a field from an option, supporting both dict and object access."""
        if isinstance(opt, dict):
            return opt.get(field, "")
        return getattr(opt, field, "")

    def _get_output_extension(self) -> str:
        """Return file extension based on output language."""
        return self._OUTPUT_LANGUAGE_EXTENSIONS.get(self.output_language, ".py")

    def _get_existing_client_candidates(self) -> dict[str, Path]:
        """Return existing API client files keyed by language."""
        if self.output_mode == "docs":
            return {}

        candidates: dict[str, Path] = {}
        for language, extension in self._OUTPUT_LANGUAGE_EXTENSIONS.items():
            client_path = self.scripts_dir / f"api_client{extension}"
            if client_path.exists():
                candidates[language] = client_path
        return candidates

    def _get_recorded_client_path(self, existing_clients: dict[str, Path] | None = None) -> Path | None:
        """Return the last generated client path recorded in session history."""
        if self.output_mode == "docs" or self.is_fresh:
            return None

        try:
            session_manager = SessionManager(get_history_path())
            run_data = session_manager.get_run(self.run_id)
        except Exception:
            return None

        if not run_data:
            return None

        script_path = run_data.get("paths", {}).get("script_path")
        if not script_path:
            return None

        resolved_path = Path(script_path)
        if not resolved_path.exists():
            return None

        candidates = existing_clients or self._get_existing_client_candidates()
        if resolved_path not in candidates.values():
            return None

        return resolved_path

    def _get_preferred_existing_client(self) -> tuple[str, Path] | None:
        """Return the existing client that iterative edits should continue from."""
        if self.output_mode == "docs" or self.is_fresh:
            return None

        existing_clients = self._get_existing_client_candidates()
        if not existing_clients:
            return None

        recorded_client_path = self._get_recorded_client_path(existing_clients)
        if recorded_client_path:
            for language, client_path in existing_clients.items():
                if client_path == recorded_client_path:
                    return language, client_path

        return max(
            existing_clients.items(),
            key=lambda item: item[1].stat().st_mtime_ns,
        )

    def _resolve_output_language(self, requested_language: str) -> str:
        """Keep iterative edits in the same language as the existing client."""
        if self.output_mode == "docs" or self.is_fresh:
            return requested_language

        preferred_client = self._get_preferred_existing_client()
        if preferred_client:
            return preferred_client[0]

        return requested_language

    def _get_existing_client_path(self) -> Path | None:
        """Return the current client path when iterating on an existing run."""
        preferred_client = self._get_preferred_existing_client()
        return preferred_client[1] if preferred_client else None

    def _get_language_name(self) -> str:
        """Return a human-readable language name."""
        return {
            "python": "Python",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "go": "Go",
            "java": "Java",
            "csharp": "C#",
        }.get(self.output_language, "Python")

    def _get_existing_client_guidance(self) -> str:
        """Return prompt guidance for iterative edits on an existing client."""
        if self.output_mode == "docs" or self.is_fresh or not self.existing_client_path:
            return ""

        language_name = self._get_language_name()
        return (
            f"\nThere is already an existing {language_name} client for this run:\n"
            f"<existing_client>\n{self.existing_client_path}\n</existing_client>\n\n"
            f"**IMPORTANT: This is an iterative edit. Update that file in place and "
            f"keep the implementation in {language_name} unless the user explicitly asks "
            f"for a fresh rewrite.**\n"
        )

    def _get_client_filename(self) -> str:
        """Return the output filename based on mode."""
        if self.output_mode == "docs":
            return "openapi.json"
        return f"api_client{self._get_output_extension()}"

    def _get_run_command(self) -> str:
        """Return the command to run the generated client."""
        if self.output_language == "java":
            # Unlike python/node/npx (which happily take a plain relative
            # filename regardless of the agent's actual cwd, scripts_dir.
            # parent.parent — see analyze_and_generate's ClaudeAgentOptions),
            # Maven hard-fails immediately if invoked from a directory with
            # no pom.xml, no upward search. -f points it straight at the
            # right project file regardless of cwd, rather than relying on
            # the agent to cd there itself first. shlex.quote(), not manual
            # double-quoting — output_dir (and so scripts_dir) isn't
            # guaranteed free of shell metacharacters, and naive f'"{path}"'
            # still lets $()/backticks expand inside double quotes.
            # .resolve(): a relative --output-dir would otherwise be
            # re-interpreted against the agent's cwd (scripts_dir.parent.
            # parent) instead of the original cwd it was relative to,
            # pointing -f at the wrong, doubly-nested location.
            # exec:exec (spawn a real java process), not exec:java —
            # exec:java invokes main() reflectively in-process, which fails
            # on the package-private ApiClient class the Java partial
            # requires ("symbolic reference class is not accessible").
            pom = shlex.quote(str(self.scripts_dir.resolve() / "pom.xml"))
            return f"mvn -q -f {pom} compile exec:exec"
        if self.output_language == "csharp":
            # Unlike python/node/npx (which happily take a plain relative
            # filename regardless of the agent's actual cwd, scripts_dir.
            # parent.parent — see analyze_and_generate's ClaudeAgentOptions),
            # a bare `dotnet run` only looks for a project file in the
            # current directory. --project points it straight at this run's
            # own .csproj regardless of cwd, rather than relying on the
            # agent to cd there itself first.
            return f'dotnet run --project "{self.scripts_dir}/ApiClient.csproj"'
        return {
            "python": "python api_client.py",
            "javascript": "node api_client.js",
            "typescript": "npx tsx api_client.ts",
            "go": "go run api_client.go",
        }.get(self.output_language, "python api_client.py")

    def _get_codegen_instructions(self) -> str:
        """Return codegen instructions from the appropriate template partial."""
        from .prompts import load

        if self.output_mode == "docs":
            return load("partials/_docs_instructions", scripts_dir=str(self.scripts_dir))

        return load(
            f"partials/_language_{self.output_language}",
            scripts_dir=str(self.scripts_dir),
            client_filename=self._get_client_filename(),
            run_command=self._get_run_command(),
        )

    def _build_prompts(self) -> tuple[str, str]:
        """Build the (system_prompt, user_message) pair for analysis.

        Returns:
            Tuple of (system_prompt_text, user_message_text).
        """
        from .prompts import load

        is_docs = self.output_mode == "docs"
        language_name = self._get_language_name()

        if is_docs:
            mode_description = "generate an OpenAPI 3.0 specification documenting"
            task_description = "OpenAPI documentation"
        else:
            mode_description = (
                f"reverse engineer API calls and generate production-ready "
                f"{language_name} code that replicates"
            )
            task_description = f"{language_name} API client"

        attempt_log_section = (
            ""
            if is_docs
            else (
                "If your first attempt doesn't work, analyze what went wrong and try again. "
                "Document each attempt and what you learned.\n\n"
                "<attempt_log>\n"
                "For each attempt (up to 5), document:\n"
                "- Attempt number\n"
                "- What approach you tried\n"
                "- What error or issue occurred (if any)\n"
                "- What you changed for the next attempt\n"
                "</attempt_log>\n\n"
            )
        )

        scratchpad_extra = (
            ""
            if is_docs
            else "- Decide whether `requests` will be sufficient or if Playwright is needed"
        )

        system_prompt = load(
            "engineer/system",
            mode_description=mode_description,
            task_description=task_description,
            codegen_instructions=self._get_codegen_instructions(),
            scratchpad_extra=scratchpad_extra,
            attempt_log_section=attempt_log_section,
            after_verb="documenting" if is_docs else "testing",
            quality_check=(
                "The completeness and accuracy of the OpenAPI spec"
                if is_docs
                else "Whether the implementation works"
            ),
            output_type="spec" if is_docs else "code",
        )

        additional_instructions = (
            f"\n\nAdditional instructions:\n{self.additional_instructions}"
            if self.additional_instructions
            else ""
        )

        user_message = load(
            "engineer/user",
            har_path=str(self.har_path),
            prompt=self.prompt,
            scripts_dir=str(self.scripts_dir),
            existing_client_guidance=self._get_existing_client_guidance(),
            additional_instructions=additional_instructions,
            tag_mode_label="Documentation" if is_docs else "Re-engineer",
            run_id=self.run_id,
            har_parent=str(self.har_path.parent),
            existing_label="docs" if is_docs else "scripts",
            messages_path=str(self.message_store.messages_path.parent),
            is_fresh=str(self.is_fresh).lower(),
            existing_artifact="documentation" if is_docs else "script",
        )

        return system_prompt, user_message

    def _get_auto_output_files(self, language_name: str, client_filename: str) -> str:
        """Return the output files list for auto mode prompts."""
        base = (
            f"1. `{self.scripts_dir}/{client_filename}` - Production {language_name} API client\n"
            f"2. `{self.scripts_dir}/README.md` - Documentation with usage examples"
        )
        if self.output_language == "javascript":
            return base + f"\n3. `{self.scripts_dir}/package.json` - Only if external dependencies are needed"
        elif self.output_language == "typescript":
            return base + f"\n3. `{self.scripts_dir}/package.json` - Dependencies and run scripts"
        elif self.output_language == "go":
            return base + (
                f"\n3. `{self.scripts_dir}/go.mod` and `{self.scripts_dir}/go.sum` - "
                "Only if external dependencies are needed"
            )
        elif self.output_language == "java":
            return base + f"\n3. `{self.scripts_dir}/pom.xml` - Maven project file (Gson dependency, exec-maven-plugin)"
        elif self.output_language == "csharp":
            return base + f"\n3. `{self.scripts_dir}/ApiClient.csproj` - .NET project file"
        return base

    @abstractmethod
    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis. Must be implemented by subclasses."""
        pass
