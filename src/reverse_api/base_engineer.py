"""Abstract base class for API reverse engineering."""

import asyncio
import os
import shlex
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import questionary

from .messages import MessageStore
from .session import SessionManager
from .sync import FileSyncWatcher, get_available_directory
from .tui import THEME_PRIMARY, THEME_SECONDARY, ClaudeUI
from .utils import (
    OUTPUT_LANGUAGE_EXTENSIONS,
    generate_folder_name,
    get_docs_dir,
    get_history_path,
    get_scripts_dir,
)

DEBUG = os.environ.get("DEBUG", "0") == "1"

OTHER_OPTION = "Other (type your answer)"

NON_INTERACTIVE_ASK_USER_MESSAGE = (
    "The user is running the CLI in non-interactive mode and cannot answer. "
    "Assume the best reasonable answer from context and continue. "
    "If you truly cannot proceed without a human choice, stop and instruct the caller "
    "to start a new session with a clearer, more specific prompt."
)

# Tokens that separate one sub-command from the next in a Bash tool call —
# see _is_client_verification_command. A run-command token match only
# counts as a real execution if it starts a sub-command (index 0, or right
# after one of these), not when it's buried inside another command's own
# arguments (`echo python api_client.py`, `grep python api_client.py
# history.log` — both contain the token sequence but neither runs it).
#
# Deliberately excludes "||": unlike these three, its right-hand side is
# only *conditionally* run — only if the left side fails. Whether that
# matters here comes down to what the overall Bash tool result's is_error
# actually reflects for each operator (the caller already gates this whole
# method behind `if not is_error`, so a failure the exit code itself
# reveals is already handled):
#   - "&&": the right side only runs if the left succeeded, so a left-side
#     failure makes that `&&` chain's own exit status a failure too. But
#     that only makes is_error=True for the *whole* tool call if the chain
#     is the last status-affecting construct in the command — see
#     _UNSAFE_AFTER_AND_BOUNDARY below for the case where it isn't. Safe
#     to keep as a boundary, with that additional check.
#   - ";" / "|": the right side always runs regardless of the left side's
#     outcome (a pipe's right side starts concurrently; ";" doesn't check
#     the left's exit code at all), so a match right after either one is
#     unconditionally a real execution no matter what precedes or follows
#     it. Safe to keep.
#   - "||": the *opposite* of "&&" — the right side runs only if the left
#     *failed*. If the left side (e.g. a bare `true`) succeeds, the right
#     side (the run command) never executes at all, yet the overall exit
#     status is still success (is_error=False) — so a match right after
#     "||" can be reported as a real execution when it demonstrably wasn't
#     one. No is_error check catches this the way it catches "&&"'s
#     failure case, so "||" has to be excluded from this set entirely
#     rather than treated as an equivalent boundary.
_COMMAND_SEPARATORS = {"&&", ";", "|"}

# Tokens that, if they appear *anywhere after* a "&&"-gated match, break the
# assumption behind treating "&&" as a safe boundary (see _COMMAND_SEPARATORS
# above) — flagged by automated review: `false && python api_client.py;
# true` reports a successful tool result (is_error=False, since the overall
# exit status is `true`'s) even though the client never ran at all, because
# `false` failed and short-circuited the "&&". A trailing ";" always runs
# regardless of the chain's outcome, and a trailing "||" runs precisely
# *because* the chain failed — either way it can reset the overall exit
# status to success independent of whether the matched command actually
# executed. A trailing "&&" doesn't have this problem: if the match didn't
# run, nothing chained after it via "&&" runs either, so the failure still
# propagates to the overall exit status untouched.
_UNSAFE_AFTER_AND_BOUNDARY = {";", "||"}

# Command-modifier prefixes that don't change *what* actually runs, just
# how — `sudo python api_client.py`, `time python api_client.py`. Allowed
# to appear (stacked, in any combination) between a real boundary and the
# run command's own match; see the backward walk in
# _is_client_verification_command. Scoped to bare prefixes with no flags
# of their own (`sudo -u appuser ...` isn't recognized) — only the
# no-flags form has actually been reported.
_COMMAND_MODIFIERS = {"sudo", "nohup", "time", "env"}

# Shell interpreters whose -c/-lc/-ic/-lic flag takes a single quoted
# command string as its next argument (`bash -c '<cmd>'`) — see
# _unwrap_shell_c_flag.
_SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash"}
_SHELL_WRAPPER_FLAGS = {"-c", "-lc", "-ic", "-lic"}

# Every boundary check in this method assumes a token right after "&&"/";"/
# "|" unconditionally runs — true for a flat command list, false the moment
# any of these shell control-flow keywords are involved, since they gate
# whether their body executes at all. Flagged by automated review (round
# 6): `if false; then; python api_client.py; fi` (an explicit empty
# statement right after "then" — valid bash) tokenizes with a bare ";"
# immediately before "python", a trusted boundary, even though the
# condition being false means Bash never runs it. Rather than actually
# parsing compound-command structure (a real shell grammar, well beyond
# what token-boundary matching can do), any occurrence of one of these
# words anywhere in the command conservatively disqualifies the whole
# match — consistent with this method's existing bias (see "||"'s
# exclusion above) toward under-detecting a real verification over
# fabricating one; this only delays a --json-stream consumer's real-time
# "verified" signal, it doesn't affect the job's actual pass/fail outcome.
# Checked against a quote-preserving tokenization (see
# _is_client_verification_command's keyword_check_tokens), not the
# dequoted one, so a *quoted* occurrence like `echo 'if'; python
# api_client.py` — flagged by automated review (round 7) — correctly
# doesn't count; "if" there is a literal echo argument, not real control
# flow, and quoting is the one signal available to tell the two apart
# without a real shell parser. An *unquoted* occurrence still can't be
# told apart this way (`echo done && python api_client.py` still under-
# detects, same as before this round) — accepted, not fixed: this is the
# same bias as everywhere else in this method, a missed real-time signal
# rather than a fabricated one, and unlike quoting there's no token-level
# signal left to lean on short of actually parsing shell grammar.
_SHELL_CONTROL_FLOW_KEYWORDS = {
    "if", "then", "elif", "else", "fi",
    "for", "while", "until", "do", "done",
    "case", "esac", "select", "function", "{", "}",
}


def _tokenize_command(command: str) -> list[str]:
    """Like shlex.split, but "&&"/"||"/";"/"|" always come back as their own
    token even with no surrounding whitespace — plain shlex.split only ever
    splits on whitespace/quoting, so `false && python api_client.py ||true`
    (no space before `true`) tokenizes to a single fused `"||true"` token
    that can never equal-match `_UNSAFE_AFTER_AND_BOUNDARY`'s bare `"||"`,
    silently defeating that check. Flagged by automated review (round 5)
    against exactly that command. shlex's own `punctuation_chars=True` mode
    exists specifically for this — it still fully respects quoting (a
    quoted `'||'` argument survives as a literal token, not an operator;
    confirmed live), so `bash -c 'python api_client.py'`-style wrapping and
    the existing "quoted mention" rejection tests are unaffected. Raises
    ValueError on unparseable input, same as shlex.split (unbalanced
    quotes) — callers already handle that identically either way.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _tokenize_command_raw(command: str) -> list[str]:
    """Same token boundaries as _tokenize_command (confirmed live: the two
    always agree on token count/positions for the same input — punctuation_
    chars mode decides *where* to split independent of posix quote removal)
    but with posix=False, so quote characters survive in each token's text
    instead of being stripped (`'if'` stays `"'if'"`, not bare `if`). Used
    only to tell a bare shell keyword from the same word appearing quoted as
    a literal argument — see _SHELL_CONTROL_FLOW_KEYWORDS's own comment and
    _is_client_verification_command's keyword scan for why that distinction
    matters. Never call this instead of _tokenize_command for anything that
    needs the actual dequoted argument text (the run-command match itself,
    _unwrap_shell_c_flag's inner-command content) — it's for this one
    quoted-vs-bare check alone.
    """
    lexer = shlex.shlex(command, posix=False, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _unwrap_shell_c_flag(tokens: list[str], raw_tokens: list[str]) -> tuple[list[str], list[str]]:
    """`(["bash", "-c", "<cmd>", ...rest], <raw-mode equivalent>)` ->
    re-tokenized `<cmd>` + rest, both tokenizations in lockstep so they stay
    index-aligned afterward too — unchanged (both) otherwise.

    shlex.split necessarily collapses the whole quoted inner command into
    one token (`bash -c 'python api_client.py'` -> `["bash", "-c", "python
    api_client.py"]`), so without this, a genuine verification run
    launched this way (a real, plausible agent pattern — e.g. to force a
    login shell) would never match the run command's own multi-token
    sequence at all. Scoped to the wrapper appearing as the very first
    command only (not `cd X && bash -c ...`) — only the bare case has
    actually been reported; generalizing further trades simplicity for a
    case that hasn't come up.

    Re-tokenizes `tokens[2]` (the already-dequoted posix inner command
    text) in *both* modes to get the inner command's own raw-mode
    equivalent — not `raw_tokens[2]`, which is still wrapped in the outer
    quote marks `bash -c` itself used and would tokenize as one opaque
    quoted blob instead of the inner command's real structure.
    """
    if len(tokens) >= 3 and tokens[0] in _SHELL_WRAPPERS and tokens[1] in _SHELL_WRAPPER_FLAGS:
        try:
            inner = _tokenize_command(tokens[2])
            inner_raw = _tokenize_command_raw(tokens[2])
        except ValueError:
            return tokens, raw_tokens
        return inner + tokens[3:], inner_raw + raw_tokens[3:]
    return tokens, raw_tokens


class BaseEngineer(ABC):
    """Abstract base class for API reverse engineering implementations."""

    # Single source of truth lives in utils.OUTPUT_LANGUAGE_EXTENSIONS so
    # script discovery and the run command dispatch stay in sync with codegen.
    _OUTPUT_LANGUAGE_EXTENSIONS = OUTPUT_LANGUAGE_EXTENSIONS

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
            "php": "PHP",
            "ruby": "Ruby",
            "c": "C",
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

    @staticmethod
    def _quote_path(path) -> str:
        """Shell-quote a path for the platform's default shell.

        shlex.quote is POSIX-only: cmd.exe/PowerShell pass its single quotes
        through literally, so a spaced Windows path would break apart.
        list2cmdline applies the double-quoting rules cmd.exe/CreateProcess
        parse. Known boundary: PowerShell still expands `$` and backtick
        inside double quotes, and no quoting satisfies cmd.exe and PowerShell
        simultaneously for such paths — cmd-safe is the chosen baseline, and
        paths whose components contain `$`/backtick are not supported on
        Windows.
        """
        if sys.platform == "win32":
            return subprocess.list2cmdline([str(path)])
        return shlex.quote(str(path))

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
            pom = self._quote_path(str(self.scripts_dir.resolve() / "pom.xml"))
            return f"mvn -q -f {pom} compile exec:exec"
        if self.output_language == "csharp":
            # Unlike python/node/npx (which happily take a plain relative
            # filename regardless of the agent's actual cwd, scripts_dir.
            # parent.parent — see analyze_and_generate's ClaudeAgentOptions),
            # a bare `dotnet run` only looks for a project file in the
            # current directory. --project points it straight at this run's
            # own .csproj regardless of cwd, rather than relying on the
            # agent to cd there itself first. shlex.quote(), not manual
            # double-quoting — output_dir (and so scripts_dir) isn't
            # guaranteed free of shell metacharacters, and naive f'"{path}"'
            # still lets $()/backticks expand inside double quotes.
            # .resolve(): a relative --output-dir would otherwise be
            # re-interpreted against the agent's cwd (scripts_dir.parent.
            # parent) instead of the original cwd it was relative to,
            # pointing --project at the wrong, doubly-nested location.
            csproj = self._quote_path(str(self.scripts_dir.resolve() / "ApiClient.csproj"))
            return f"dotnet run --project {csproj}"
        if self.output_language == "php":
            # Full path, not a bare relative "php api_client.php": the
            # agent's cwd for the whole session is scripts_dir.parent.parent
            # (see analyze_and_generate's ClaudeAgentOptions), not
            # scripts_dir itself where the script is actually saved. python/
            # node/npx get away with a bare relative filename here since
            # this is already how they're shipped and evidently work in
            # practice, but there's no reason to leave a new language
            # exposed to the same ambiguity when it's this cheap to remove.
            # shlex.quote(), not manual double-quoting — output_dir (and so
            # scripts_dir) isn't guaranteed free of shell metacharacters,
            # and naive f'"{path}"' still lets $()/backticks expand inside
            # double quotes (confirmed live: shlex.quote handles this, plain
            # double-quoting doesn't).
            # .resolve(): a relative --output-dir would otherwise be
            # re-interpreted against the agent's cwd (scripts_dir.parent.
            # parent) instead of the original cwd it was relative to,
            # pointing this command at the wrong, doubly-nested location.
            path = self._quote_path(str(self.scripts_dir.resolve() / self._get_client_filename()))
            return f"php {path}"
        if self.output_language == "ruby":
            # Full path, not a bare relative "ruby api_client.rb": the
            # agent's cwd for the whole session is scripts_dir.parent.parent
            # (see analyze_and_generate's ClaudeAgentOptions), not
            # scripts_dir itself where the script is actually saved — the
            # same working-directory ambiguity fixed for Go/Java/C#/PHP.
            # shlex.quote (not manual double-quoting) so shell metacharacters
            # in the path can't be interpreted as command substitution.
            # .resolve(): a relative --output-dir would otherwise be
            # re-interpreted against the agent's cwd (scripts_dir.parent.
            # parent) instead of the original cwd it was relative to,
            # pointing this command at the wrong, doubly-nested location.
            path = self._quote_path(str(self.scripts_dir.resolve() / self._get_client_filename()))
            return f"ruby {path}"
        if self.output_language == "c":
            # Unlike every other language here, C needs an explicit compile
            # step before it can run at all — one shell command chains
            # both. Full paths throughout, not bare relative filenames: the
            # agent's cwd for the whole session is scripts_dir.parent.parent
            # (see analyze_and_generate's ClaudeAgentOptions), not
            # scripts_dir where the source/output actually live.
            # shlex.quote (not manual double-quoting) so shell metacharacters
            # in any of these three paths can't be interpreted as command
            # substitution. .resolve(): a relative --output-dir would
            # otherwise be re-interpreted against the agent's cwd (scripts_
            # dir.parent.parent) instead of the original cwd it was relative
            # to, pointing all three at the wrong, doubly-nested location.
            resolved = self.scripts_dir.resolve()
            source = self._quote_path(str(resolved / self._get_client_filename()))
            cjson = self._quote_path(str(resolved / "cJSON.c"))
            binary = self._quote_path(str(resolved / "api_client"))
            return f"cc {source} {cjson} -lcurl -o {binary} && {binary}"
        return {
            "python": "python api_client.py",
            "javascript": "node api_client.js",
            "typescript": "npx tsx api_client.ts",
            "go": "go run api_client.go",
        }.get(self.output_language, "python api_client.py")

    def _is_client_verification_command(self, tool_name: str | None, tool_input: Any) -> bool:
        """True if a Bash tool call looks like it ran the generated client to
        verify it, for `--json-stream` consumers that want to react as soon as
        a live-verified client exists instead of only finding out from the
        final result.

        Matches against `_get_run_command()`'s own return value — the exact
        command the agent is told to test with (see `_get_codegen_
        instructions`'s `run_command=` interpolation, used verbatim in every
        `partials/_language_*.md`, e.g. "test it: `{run_command}`") — rather
        than a simpler check like "does the command mention the client's
        filename". That simpler check can't work at all for every compiled
        language here: Java's run command (`mvn -f <pom> compile exec:exec`)
        never references `ApiClient.java`, it builds the whole Maven project;
        C#'s (`dotnet run --project <csproj>`) references the project file,
        not the source; C's is a multi-step compile-then-run chain. Matching
        against the one thing already correct for every language avoids
        duplicating that per-language dispatch a second time at each call
        site.

        Compares tokenized (_tokenize_command) command sequences, not raw
        substring containment — a plain substring check can be fooled by a
        command that merely *mentions* the run command's text without
        executing it, several variants of which were independently flagged
        across multiple rounds of automated PR review:

        - Quoted mention: `echo 'python api_client.py'`, `grep 'python
          api_client.py' file.txt`. _tokenize_command collapses a quoted
          argument into a single token (`["echo", "python api_client.py"]`),
          which can never equal-match the run command's own multi-token
          sequence `["python", "api_client.py"]`.
        - Unquoted mention as *arguments* to an unrelated command: `echo
          python api_client.py`, `grep python api_client.py history.log`.
          Both contain the run command's token sequence contiguously, so a
          plain "does this sequence appear anywhere" search (this method's
          first revision) still matched them — the fix is requiring the
          match to *start* a sub-command (index 0, or immediately after a
          `_COMMAND_SEPARATORS` token) rather than merely appear somewhere
          in the token list. `python api_client.py --extra` is correctly
          still a match under this rule (and under the original one) — it
          really does run the client, an extra trailing argument doesn't
          change that; a third example along those lines in the same
          review round was not a real instance of this bug.
        - Filename-only mention: `cat api_client.py`, `rm api_client.py` —
          the client's filename alone is never enough, only the earlier-
          matched two-token run command sequence is (see the module-level
          comment on why a filename check can't work for every language
          here regardless).

        A wrapped invocation still matches: `cd /tmp && python
        api_client.py` (a `_COMMAND_SEPARATORS` boundary immediately before
        the match), `sudo python api_client.py` / `time python
        api_client.py` (a `_COMMAND_MODIFIERS` prefix — see its own
        comment for why these don't change what actually runs, and why
        `||` is deliberately *not* one of the separators), and `bash -lc
        'python api_client.py'` (unwrapped by _unwrap_shell_c_flag before
        the token search runs — see its own docstring for why a plain
        whitespace-only split can't see through a `-c`/`-lc` argument on
        its own) — all still count as real executions. A compiled language's own
        `&&`-chained run command (C) matches as one contiguous window
        starting the sub-command, same as any other language's — its
        internal `&&` needs no special handling since the boundary check
        only cares about the token(s) *immediately before* the match, not
        about parsing the whole command into sub-command groups.

        A `&&`-gated match is rejected, even though `&&` is otherwise a
        trusted boundary, if a `;` or `||` appears anywhere later in the
        command: `false && python api_client.py; true` looks like a
        successful tool call (is_error=False, since the overall exit status
        is `true`'s) even though the client never actually ran — see
        `_UNSAFE_AFTER_AND_BOUNDARY`'s own comment for the full reasoning.

        A match is also rejected if a shell control-flow keyword (`if`,
        `for`, `do`, ...) appears anywhere *before* it — see
        `_SHELL_CONTROL_FLOW_KEYWORDS`'s own comment. Every boundary check
        above assumes a flat command list; a match sitting inside a
        conditional/loop/function body breaks that assumption regardless of
        which boundary token happens to precede it. That check runs against
        a quote-preserving tokenization, not the dequoted one used
        everywhere else in this method, specifically so a *quoted*
        occurrence of one of those words (`echo 'if'; python api_client.py`
        — "if" there is a literal argument, not real syntax) doesn't cause
        a false rejection — see `_tokenize_command_raw`'s own docstring.

        An unparseable command (unbalanced quotes) is treated as a
        non-match rather than raising, same posture as every other
        unexpected-shape check in this method.
        """
        if tool_name != "Bash" or not isinstance(tool_input, dict):
            return False
        command = tool_input.get("command")
        if not isinstance(command, str):
            return False
        try:
            command_tokens, keyword_check_tokens = _unwrap_shell_c_flag(
                _tokenize_command(command), _tokenize_command_raw(command)
            )
            run_tokens = _tokenize_command(self._get_run_command())
        except ValueError:
            return False
        if not run_tokens:
            return False
        window = len(run_tokens)
        for i in range(len(command_tokens) - window + 1):
            if command_tokens[i : i + window] != run_tokens:
                continue
            # See _SHELL_CONTROL_FLOW_KEYWORDS — a keyword anywhere *before*
            # this candidate match means it can sit inside a conditional/
            # loop/function body, where a boundary token no longer
            # guarantees unconditional execution the way every check below
            # assumes. Scoped to tokens before the match, not the whole
            # command: a keyword *after* it (an `echo done` tail, say)
            # can't retroactively un-run something that already executed,
            # and rejecting on those too would falsely reject common, safe
            # commands that just happen to use one of these words normally.
            #
            # Checked against keyword_check_tokens (raw/quote-preserving),
            # not command_tokens (posix/dequoted) — flagged by automated
            # review (round 7): `echo 'if'; python api_client.py` never
            # actually involves any control flow, "if" here is just a
            # literal argument to echo, but posix-mode tokenizing strips
            # the quotes and leaves a bare "if" indistinguishable from a
            # real keyword. A quoted occurrence stays quoted in raw mode
            # (`"'if'"`, not `"if"`), so it correctly never equals a bare
            # entry in _SHELL_CONTROL_FLOW_KEYWORDS. Multi-word quoted
            # phrases ("Checking if this works") don't even need this —
            # quoting already collapses them into one token that can never
            # equal a single keyword either way; this only matters for a
            # standalone quoted-or-bare word that happens to exactly match
            # one of these keywords.
            if any(t in _SHELL_CONTROL_FLOW_KEYWORDS for t in keyword_check_tokens[:i]):
                continue
            # Walk back over any stacked modifier prefixes (`sudo time
            # python api_client.py` skips both) to find the token that
            # actually has to be a real boundary.
            j = i
            while j > 0 and command_tokens[j - 1] in _COMMAND_MODIFIERS:
                j -= 1
            if j == 0:
                return True
            boundary = command_tokens[j - 1]
            if boundary not in _COMMAND_SEPARATORS:
                continue
            if boundary == "&&" and any(
                t in _UNSAFE_AFTER_AND_BOUNDARY for t in command_tokens[i + window :]
            ):
                # See _UNSAFE_AFTER_AND_BOUNDARY — something later in the
                # command can mask a skipped "&&" right-hand side as an
                # overall success. Keep scanning; a later window (if any)
                # might still be a genuine, safely-bounded match.
                continue
            return True
        return False

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
        elif self.output_language == "c":
            return base + (
                f"\n3. `{self.scripts_dir}/cJSON.c` and `{self.scripts_dir}/cJSON.h` - "
                "Vendored JSON library"
            )
        return base

    @abstractmethod
    async def analyze_and_generate(self) -> dict[str, Any] | None:
        """Run the reverse engineering analysis. Must be implemented by subclasses."""
        pass
