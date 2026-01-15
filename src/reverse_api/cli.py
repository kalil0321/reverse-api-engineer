import asyncio
import re
from pathlib import Path

import click
import questionary
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PtStyle
from questionary import Choice
from rich.console import Console

from . import __version__
from .browser import ManualBrowser, run_agent_browser
from .config import ConfigManager
from .engineer import run_reverse_engineering
from .messages import MessageStore
from .session import SessionManager
from .tui import (
    ERROR_CTA,
    MODE_COLORS,
    THEME_DIM,
    THEME_PRIMARY,
    THEME_SECONDARY,
    display_banner,
    display_footer,
    get_model_choices,
)
from .utils import (
    generate_folder_name,
    generate_run_id,
    get_actions_path,
    get_config_path,
    get_har_dir,
    get_history_path,
    get_scripts_dir,
    get_timestamp,
    parse_engineer_prompt,
    parse_record_only_tag,
    parse_codegen_tag,
)
from .playwright_codegen import PlaywrightCodeGenerator

console = Console()
config_manager = ConfigManager(get_config_path())
session_manager = SessionManager(get_history_path())

# Mode definitions
MODES = ["manual", "engineer", "agent", "collector"]
MODE_DESCRIPTIONS = {
    "manual": "full pipeline",
    "engineer": "reverse engineer only",
    "agent": "autonomous agent + capture",
    "collector": "ai-powered data collection",
}


def prompt_interactive_options(
    prompt: str | None = None,
    url: str | None = None,
    reverse_engineer: bool | None = None,
    model: str | None = None,
    current_mode: str = "manual",
) -> dict:
    """Prompt user for essential options interactively (Browgents style).

    Shift+Tab cycles through modes: manual ↔ engineer ↔ agent
    """

    # Slash command completer
    commands = [
        "/settings",
        "/history",
        "/messages",
        "/help",
        "/exit",
        "/quit",
        "/commands",
    ]

    class EnhancedCompleter(Completer):
        """Autocomplete for slash commands and run IDs."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor

            # Slash command completion
            if text.startswith("/"):
                # Check if we're after /messages command
                if text.startswith("/messages "):
                    # Run ID completion for /messages
                    run_id_prefix = text[10:]  # Everything after "/messages "
                    for run_id in self._get_run_ids():
                        if run_id.startswith(run_id_prefix):
                            yield Completion(
                                run_id,
                                start_position=-len(run_id_prefix),
                                display_meta=self._get_run_meta(run_id),
                            )
                elif " " not in text:
                    # Regular slash command completion (no space yet)
                    for cmd in commands:
                        if cmd.startswith(text):
                            yield Completion(cmd, start_position=-len(text))
            # Tag completion for manual/agent modes
            elif mode_state["mode"] in ("manual", "agent") and text.startswith("@"):
                # Tags for manual/agent modes with descriptions
                tags = [
                    ("@record-only", "record HAR only, skip reverse engineering"),
                    ("@codegen", "record actions and generate Playwright script"),
                    ("@help", "show mode-specific help"),
                ]
                for tag, meta in tags:
                    if tag.startswith(text):
                        yield Completion(
                            tag,
                            start_position=-len(text),
                            display_meta=meta,
                        )
            # Tag completion in engineer mode
            elif mode_state["mode"] == "engineer" and text:
                if text.startswith("@"):
                    # Tag completion with descriptions
                    tags = [
                        ("@id", "switch context to run ID"),
                        ("@docs", "generate API documentation"),
                        ("@help", "show engineer mode help"),
                    ]

                    # specific check for @id completion
                    id_match = re.match(r"@id\s+(.*)", text)
                    if id_match:
                        prefix = id_match.group(1)
                        for run_id in self._get_run_ids():
                            if run_id.startswith(prefix):
                                yield Completion(
                                    run_id,
                                    start_position=-len(prefix),
                                    display_meta=self._get_run_meta(run_id),
                                )
                    else:
                        # Suggest tags with descriptions
                        for tag, meta in tags:
                            if tag.startswith(text):
                                yield Completion(
                                    tag,
                                    start_position=-len(text),
                                    display_meta=meta,
                                )

                else:
                    for run_id in self._get_run_ids():
                        if run_id.startswith(text):
                            yield Completion(
                                run_id,
                                start_position=-len(text),
                                display_meta=self._get_run_meta(run_id),
                            )

        def _get_run_ids(self):
            """Get all run IDs from history (newest first)."""
            try:
                history = session_manager.get_history(limit=50)
                return [run["run_id"] for run in history]
            except Exception:
                return []

        def _get_run_meta(self, run_id):
            """Get metadata for a run ID (timestamp + prompt snippet)."""
            try:
                run = session_manager.get_run(run_id)
                if run:
                    timestamp = run.get("timestamp", "")[:16]  # YYYY-MM-DD HH:MM
                    prompt = run.get("prompt", "")[:30]
                    return f"[{timestamp}] {prompt}"
            except Exception:
                pass
            return ""

    command_completer = EnhancedCompleter()

    # Track mode state (mutable container for closure)
    mode_state = {"mode": current_mode, "mode_index": MODES.index(current_mode)}

    # Create key bindings for mode cycling and autocomplete
    kb = KeyBindings()

    @kb.add("s-tab")  # Shift+Tab
    def cycle_mode(event):
        """Cycle to next mode."""
        mode_state["mode_index"] = (mode_state["mode_index"] + 1) % len(MODES)
        mode_state["mode"] = MODES[mode_state["mode_index"]]
        # Force prompt refresh by invalidating the app
        event.app.invalidate()

    @kb.add("right")  # Right arrow
    def accept_completion(event):
        """Accept the current autocomplete suggestion with right arrow."""
        buff = event.app.current_buffer
        if buff.complete_state:
            # Save the current completion before closing
            completion = buff.complete_state.current_completion
            if completion:
                buff.apply_completion(completion)
            else:
                # No completion selected, just move cursor right
                buff.cursor_right()
        else:
            # If no completion, just move cursor right
            buff.cursor_right()

    def get_prompt():
        """Generate prompt with current mode indicator."""
        mode = mode_state["mode"]
        mode_color = MODE_COLORS.get(mode, THEME_PRIMARY)

        return HTML(f'<style fg="{mode_color}">[{mode}]</style> <style fg="{mode_color}" bold="true">&gt;</style> ')

    if prompt is None:
        pt_style = PtStyle.from_dict(
            {
                "prompt": f"{THEME_PRIMARY} bold",
                "": THEME_SECONDARY,
            }
        )

        session = PromptSession(
            message=get_prompt,  # Dynamic prompt function
            completer=command_completer,
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True,
            style=pt_style,
            key_bindings=kb,
        )

        prompt = session.prompt()

    if prompt is None:  # Handle Ctrl+D or Ctrl+C if not caught
        raise click.Abort()

    prompt = prompt.strip()
    if not prompt:
        return {"command": "/empty", "mode": mode_state["mode"]}

    if prompt.startswith("/"):
        return {"command": prompt.lower(), "mode": mode_state["mode"]}

    if prompt.strip() == "@help":
        return {"command": "@help", "mode": mode_state["mode"]}

    # Return mode in all cases
    result_mode = mode_state["mode"]

    # Engineer mode: prompt is the run_id
    if result_mode == "engineer":
        return {
            "mode": result_mode,
            "run_id": prompt,
            "model": model or config_manager.get("claude_code_model", "claude-sonnet-4-5"),
        }

    # Agent mode: similar to manual but uses autonomous browser
    if result_mode == "agent":
        if url is None:
            try:
                url = questionary.text(
                    " > url",
                    instruction="(Enter for none)",
                    qmark="",
                    style=questionary.Style(
                        [
                            ("question", f"fg:{THEME_SECONDARY}"),
                            ("instruction", f"fg:{THEME_DIM} italic"),
                        ]
                    ),
                ).ask()
                if url is None:  # questionary returns None on Ctrl+C
                    raise click.Abort()
            except KeyboardInterrupt:
                raise click.Abort()

        if model is None:
            model = config_manager.get("claude_code_model", "claude-sonnet-4-5")

        return {
            "mode": result_mode,
            "prompt": prompt,
            "url": url if url else None,
            "reverse_engineer": False,  # Agent mode doesn't auto-reverse engineer
            "model": model,
        }

    # Collector mode: just needs prompt
    if result_mode == "collector":
        if model is None:
            model = config_manager.get("collector_model", "claude-sonnet-4-5")

        return {
            "mode": result_mode,
            "prompt": prompt,
            "model": model,
        }

    # Manual mode: need URL
    if url is None:
        try:
            url = questionary.text(
                " > url",
                instruction="(Enter for none)",
                qmark="",
                style=questionary.Style(
                    [
                        ("question", f"fg:{THEME_SECONDARY}"),
                        ("instruction", f"fg:{THEME_DIM} italic"),
                    ]
                ),
            ).ask()
            if url is None:  # questionary returns None on Ctrl+C
                raise click.Abort()
        except KeyboardInterrupt:
            raise click.Abort()

    # Use settings defaults for the rest
    if reverse_engineer is None:
        reverse_engineer = True

    if model is None:
        model = config_manager.get("claude_code_model", "claude-sonnet-4-5")

    return {
        "mode": result_mode,
        "prompt": prompt,
        "url": url if url else None,
        "reverse_engineer": reverse_engineer,
        "model": model,
    }


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=__version__)
def main(ctx: click.Context):
    """Reverse API - Capture browser traffic for API reverse engineering."""
    if ctx.invoked_subcommand is None:
        repl_loop()


def repl_loop():
    """Main interactive loop for the CLI."""
    # Get current SDK and model from config
    sdk = config_manager.get("sdk", "claude")
    if sdk == "opencode":
        model = config_manager.get("opencode_model", "claude-sonnet-4-5")
    else:
        model = config_manager.get("claude_code_model", "claude-sonnet-4-5")

    display_banner(console, sdk=sdk, model=model)
    console.print("  [dim]shift+tab to cycle modes: manual | engineer | agent | collector[/dim]")
    display_footer(console)

    current_mode = "manual"

    while True:
        try:
            options = prompt_interactive_options(current_mode=current_mode)

            # Update current mode for next iteration
            current_mode = options.get("mode", "manual")

            if "command" in options:
                cmd = options["command"]
                mode_color = MODE_COLORS.get(current_mode, THEME_PRIMARY)

                if cmd == "/empty":
                    continue
                if cmd == "/exit" or cmd == "/quit":
                    return  # Exit the loop and return to main
                elif cmd == "/settings":
                    handle_settings(mode_color)
                elif cmd == "/history":
                    handle_history(mode_color)
                elif cmd == "/help" or cmd == "/commands":
                    handle_help(mode_color)
                elif cmd == "@help":
                    if current_mode == "engineer":
                        handle_engineer_help(mode_color)
                    elif current_mode == "agent":
                        handle_agent_help(mode_color)
                    elif current_mode == "collector":
                        handle_collector_help(mode_color)
                    elif current_mode == "manual":
                        handle_manual_help(mode_color)
                elif cmd.startswith("/messages"):
                    parts = cmd.split(maxsplit=1)
                    if len(parts) > 1:
                        handle_messages(parts[1].strip(), mode_color)
                    else:
                        console.print(" [red]usage:[/red] /messages <run_id>")
                else:
                    # Unknown command - show error and available commands
                    console.print(f" [red]Unknown command:[/red] {cmd}")
                    console.print(" [dim]Available commands: /settings, /history, /messages, /help, /exit[/dim]")
                continue

            mode = options.get("mode", "manual")

            # Handle different modes
            if mode == "engineer":
                # Engineer mode
                raw_input = options.get("run_id")

                # Handle empty input
                if not raw_input:
                    console.print(" [dim]Usage:[/dim] @id <run_id> [instructions]")
                    console.print(" [dim]       [/dim] @docs (generate docs for latest run)")
                    console.print(" [dim]       [/dim] @id <run_id> @docs [prompt]")
                    console.print(" [dim]       [/dim] <run_id> (to switch context)")
                    continue

                # Parse tag with session_manager to resolve latest run centrally
                parsed = parse_engineer_prompt(raw_input, session_manager)

                # Handle parser errors
                if parsed["error"]:
                    console.print(f" [red]error:[/red] {parsed['error']}")
                    continue

                target_run_id = parsed["run_id"]
                is_fresh = parsed["fresh"]
                is_docs = parsed["docs"]
                user_text = parsed["prompt"]

                main_prompt = None
                add_instr = None

                if parsed["is_tag_command"]:
                    # Explicit @id or @docs command
                    # Validate HAR file exists for @docs mode
                    if is_docs and target_run_id:
                        run_data = session_manager.get_run(target_run_id)
                        if run_data:
                            paths = run_data.get("paths", {})
                            har_dir = Path(paths.get("har_dir", get_har_dir(target_run_id, None)))
                        else:
                            har_dir = get_har_dir(target_run_id, None)

                        har_path = har_dir / "recording.har"
                        if not har_path.exists():
                            console.print(f" [red]error:[/red] run {target_run_id} has no HAR file")
                            console.print(" [dim]tip:[/dim] use @id <run_id> @docs to specify a run with captured traffic")
                            continue

                    if not target_run_id:
                        console.print(" [red]error:[/red] invalid @id syntax")
                        continue

                    # If fresh, user text is new prompt. Else, it's additive.
                    if is_fresh:
                        main_prompt = user_text if user_text else None
                    else:
                        add_instr = user_text if user_text else None

                else:
                    # Implicit mode - parser already resolved latest run
                    # Check if input is just a run_id (switching context)
                    if session_manager.get_run(user_text):
                        target_run_id = user_text
                        # Just switching run, no new instructions
                    else:
                        # Parser resolved latest run, treat input as additive instructions
                        add_instr = user_text

                run_engineer(
                    target_run_id,
                    prompt=main_prompt,
                    model=options.get("model"),
                    additional_instructions=add_instr,
                    is_fresh=is_fresh,
                    output_mode="docs" if is_docs else "client",
                )
                continue

            if mode == "agent":
                # Agent mode: run autonomous browser agent
                run_agent_capture(
                    prompt=options["prompt"],
                    url=options.get("url"),
                    reverse_engineer=True,  # Enable reverse engineering
                    model=options.get("model"),
                )
                continue

            if mode == "collector":
                # Collector mode: AI-powered data collection
                run_collector(
                    prompt=options["prompt"],
                    model=options.get("model"),
                )
                continue

            # Manual mode: run browser capture
            run_manual_capture(
                prompt=options["prompt"],
                url=options["url"],
                reverse_engineer=options["reverse_engineer"],
                model=options["model"],
            )

        except (click.Abort, KeyboardInterrupt):
            console.print("\n [dim]terminated[/dim]")
            return
        except Exception as e:
            console.print(f" [red]error:[/red] {e}")
            console.print(f" [dim]{ERROR_CTA}[/dim]")


def handle_settings(mode_color=THEME_PRIMARY):
    """Display and manage settings with improved layout and descriptions."""
    from rich.table import Table

    console.print()

    # Create a table for current configuration
    config_table = Table(show_header=False, box=None, padding=(0, 1))
    config_table.add_column(style="dim", justify="left")
    config_table.add_column(style=mode_color, justify="left")

    # Sort config items alphabetically by key
    for k, v in sorted(config_manager.config.items()):
        display_val = str(v) if v is not None else "default"
        # Make the key more readable
        key_display = k.replace("_", " ").title()
        config_table.add_row(key_display, display_val)

    # Display in a clean format
    console.print(" [bold white]Settings[/bold white] [dim]Current Configuration[/dim]")
    console.print(config_table)
    console.print()

    # Settings menu (sorted alphabetically)
    choices = [
        Choice(title="Agent Provider", value="agent_provider"),
        Choice(title="Browser-Use Model", value="browser_use_model"),
        Choice(title="Claude Code Model", value="claude_code_model"),
        Choice(title="OpenCode Model", value="opencode_model"),
        Choice(title="OpenCode Provider", value="opencode_provider"),
        Choice(title="Output Directory", value="output_dir"),
        Choice(title="Output Language", value="output_language"),
        Choice(title="Real-time Sync", value="real_time_sync"),
        Choice(title="SDK", value="sdk"),
        Choice(title="Stagehand Model", value="stagehand_model"),
        Choice(title="Back", value="back"),
    ]

    action = questionary.select(
        "    ",  # Add padding via the question prompt
        choices=choices,
        pointer=">",
        qmark="",
        style=questionary.Style(
            [
                ("pointer", f"fg:{mode_color} bold"),
                ("highlighted", f"fg:{mode_color} bold"),
                ("selected", "fg:white"),
                ("question", ""),  # Hide the question text styling
            ]
        ),
    ).ask()

    if action is None or action == "back":
        return  # Exit settings to main prompt

    if action == "claude_code_model":
        model_choices = [Choice(title=c["name"].lower(), value=c["value"]) for c in get_model_choices()]
        model_choices.append(Choice(title="back", value="back"))
        model = questionary.select(
            "",
            choices=model_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if model and model != "back":
            config_manager.set("claude_code_model", model)
            console.print(f" [dim]updated[/dim] {model}\n")

    elif action == "sdk":
        sdk_choices = [
            Choice(title="opencode", value="opencode"),
            Choice(title="claude", value="claude"),
            Choice(title="back", value="back"),
        ]
        sdk = questionary.select(
            "",
            choices=sdk_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if sdk and sdk != "back":
            config_manager.set("sdk", sdk)
            console.print(f" [dim]updated[/dim] sdk: {sdk}\n")

    elif action == "output_language":
        lang_choices = [
            Choice(title="python", value="python"),
            Choice(title="javascript", value="javascript"),
            Choice(title="typescript", value="typescript"),
            Choice(title="back", value="back"),
        ]
        lang = questionary.select(
            "",
            choices=lang_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if lang and lang != "back":
            config_manager.set("output_language", lang)
            console.print(f" [dim]updated[/dim] output language: {lang}\n")

    elif action == "agent_provider":
        provider_choices = [
            Choice(title="browser-use", value="browser-use"),
            Choice(title="stagehand", value="stagehand"),
            Choice(title="auto", value="auto"),
            Choice(title="back", value="back"),
        ]
        provider = questionary.select(
            "",
            choices=provider_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if provider and provider != "back":
            config_manager.set("agent_provider", provider)
            console.print(f" [dim]updated[/dim] agent provider: {provider}\n")

    elif action == "opencode_provider":
        current = config_manager.get("opencode_provider", "anthropic")
        new_provider = questionary.text(
            " > opencode provider",
            default=current or "anthropic",
            instruction="(e.g., 'anthropic', 'openai', 'google')",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_provider is not None:
            new_provider = new_provider.strip()
            if not new_provider:
                console.print(" [yellow]error:[/yellow] opencode provider cannot be empty\n")
            else:
                config_manager.set("opencode_provider", new_provider)
                console.print(f" [dim]updated[/dim] opencode provider: {new_provider}\n")

    elif action == "opencode_model":
        current = config_manager.get("opencode_model", "claude-sonnet-4-5")
        new_model = questionary.text(
            " > opencode model",
            default=current or "claude-sonnet-4-5",
            instruction="(e.g., 'claude-sonnet-4-5', 'claude-opus-4-5')",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_model is not None:
            new_model = new_model.strip()
            if not new_model:
                console.print(" [yellow]error:[/yellow] opencode model cannot be empty\n")
            else:
                config_manager.set("opencode_model", new_model)
                console.print(f" [dim]updated[/dim] opencode model: {new_model}\n")

    elif action == "browser_use_model":
        from .browser import parse_agent_model

        current = config_manager.get("browser_use_model", "bu-llm")
        instruction = "(Format: 'bu-llm' or 'provider/model', e.g., 'openai/gpt-4')"

        new_model = questionary.text(
            " > browser-use model",
            default=current or "bu-llm",
            instruction=instruction,
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_model is not None:
            new_model = new_model.strip()
            if not new_model:
                console.print(" [yellow]error:[/yellow] browser-use model cannot be empty\n")
            else:
                # Validate format for browser-use
                try:
                    parse_agent_model(new_model, "browser-use")
                    config_manager.set("browser_use_model", new_model)
                    console.print(f" [dim]updated[/dim] browser-use model: {new_model}\n")
                except ValueError as e:
                    console.print(f" [yellow]error:[/yellow] {e}\n")
                    console.print(
                        " [dim]Valid formats:[/dim]\n"
                        " [dim]  - bu-llm[/dim]\n"
                        " [dim]  - openai/model_name (e.g., openai/gpt-4)[/dim]\n"
                        " [dim]  - google/model_name (e.g., google/gemini-pro)[/dim]\n"
                    )

    elif action == "stagehand_model":
        from .browser import parse_agent_model

        current = config_manager.get("stagehand_model", "openai/computer-use-preview-2025-03-11")
        instruction = (
            "(Format: 'openai/model' or 'anthropic/model', e.g., 'openai/computer-use-preview-2025-03-11' or 'anthropic/claude-sonnet-4-5-20250929')"
        )

        new_model = questionary.text(
            " > stagehand model",
            default=current or "openai/computer-use-preview-2025-03-11",
            instruction=instruction,
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_model is not None:
            new_model = new_model.strip()
            if not new_model:
                console.print(" [yellow]error:[/yellow] stagehand model cannot be empty\n")
            else:
                # Validate format for stagehand
                try:
                    parse_agent_model(new_model, "stagehand")
                    config_manager.set("stagehand_model", new_model)
                    console.print(f" [dim]updated[/dim] stagehand model: {new_model}\n")
                except ValueError as e:
                    console.print(f" [yellow]error:[/yellow] {e}\n")
                    console.print(
                        " [dim]Valid formats for stagehand:[/dim]\n"
                        " [dim]  - openai/computer-use-preview-2025-03-11[/dim]\n"
                        " [dim]  - anthropic/claude-sonnet-4-5-20250929[/dim]\n"
                        " [dim]  - anthropic/claude-haiku-4-5-20251001[/dim]\n"
                        " [dim]  - anthropic/claude-opus-4-5-20251101[/dim]\n"
                    )

    elif action == "real_time_sync":
        current = config_manager.get("real_time_sync", True)
        sync_choices = [
            Choice(title="Enabled", value=True),
            Choice(title="Disabled", value=False),
            Choice(title="Back", value="back"),
        ]
        sync = questionary.select(
            "",
            choices=sync_choices,
            pointer=">",
            qmark="",
            style=questionary.Style(
                [
                    ("pointer", f"fg:{mode_color} bold"),
                    ("highlighted", f"fg:{mode_color} bold"),
                ]
            ),
        ).ask()
        if sync is not None and sync != "back":
            config_manager.set("real_time_sync", sync)
            status = "enabled" if sync else "disabled"
            console.print(f"    [dim]updated[/dim] real-time sync: {status}\n")

    elif action == "output_dir":
        current = config_manager.get("output_dir")
        new_dir = questionary.text(
            " > output directory",
            default=current or "",
            instruction="(Enter for default ~/.reverse-api/runs)",
            qmark="",
            style=questionary.Style(
                [
                    ("question", f"fg:{THEME_SECONDARY}"),
                    ("instruction", f"fg:{THEME_DIM} italic"),
                ]
            ),
        ).ask()
        if new_dir is not None:
            config_manager.set("output_dir", new_dir if new_dir.strip() else None)
            console.print(" [dim]updated[/dim] output directory\n")


def handle_history(mode_color=THEME_PRIMARY):
    """Display history of runs."""
    history = session_manager.get_history(limit=15)
    if not history:
        console.print(" [dim]> no logs found[/dim]")
        return

    choices = []
    for run in history:
        cost = run.get("usage", {}).get("estimated_cost_usd", 0)
        cost_str = f"${cost:.3f}" if cost > 0 else "-"
        title = f"{run['run_id']:12}  {run['prompt'][:40]:40}  {cost_str:>8}"
        choices.append(Choice(title=title, value=run["run_id"]))

    choices.append(Choice(title="back", value="back"))

    run_id = questionary.select(
        "",
        choices=choices,
        pointer=">",
        qmark="",
        style=questionary.Style(
            [
                ("pointer", f"fg:{mode_color} bold"),
                ("highlighted", f"fg:{mode_color} bold"),
                ("selected", "fg:white"),
            ]
        ),
    ).ask()

    if not run_id or run_id == "back":
        return

    run = session_manager.get_run(run_id)
    if run:
        from rich.table import Table

        # Create a formatted display of the run details
        details_table = Table(show_header=False, box=None, padding=(0, 1))
        details_table.add_column(style="dim", justify="left", width=20)
        details_table.add_column(style="white", justify="left")

        details_table.add_row("Run ID", run.get("run_id", "-"))
        details_table.add_row("Timestamp", run.get("timestamp", "-"))
        details_table.add_row("Prompt", run.get("prompt", "-"))
        details_table.add_row("Model", run.get("model", "-"))
        details_table.add_row("Mode", run.get("mode", "-"))

        usage = run.get("usage", {})
        if usage:
            cost = usage.get("estimated_cost_usd", 0)
            details_table.add_row("Cost", f"${cost:.4f}" if cost > 0 else "-")
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            if input_tokens or output_tokens:
                details_table.add_row("Tokens", f"{input_tokens:,} in / {output_tokens:,} out")

        console.print()
        console.print(" [bold white]Run Details[/bold white]")
        console.print(details_table)
        console.print()

        if questionary.confirm(" > recode?", qmark="").ask():
            model = run.get("model") or config_manager.get("claude_code_model", "claude-sonnet-4-5")
            run_engineer(run_id, model=model)
    else:
        console.print(" [dim]> not found[/dim]")


def handle_manual_help(mode_color=THEME_PRIMARY):
    """Show help specific to manual mode."""
    from rich.table import Table

    console.print()
    console.print(" [bold white]Manual Mode Help[/bold white]")
    console.print(" [dim]Launch a browser for manual interaction and capture traffic.[/dim]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style=f"{mode_color} bold", justify="left", width=30)
    table.add_column(style="white", justify="left")

    table.add_row("<prompt>", "Describe the task/goal for the session.\n[dim]Example: extract jobs from apple.com[/dim]")
    table.add_row("", "")

    table.add_row("@record-only [prompt]", "Record HAR only, skip reverse engineering.\n[dim]Example: @record-only[/dim]")
    table.add_row("", "")

    table.add_row("@codegen [prompt]", "Record actions and generate Playwright script.\n[dim]Example: @codegen navigate to google[/dim]")
    table.add_row("", "")

    table.add_row("Shift+Tab", "Cycle to other modes (Engineer, Agent).")

    console.print(table)
    console.print()


def handle_agent_help(mode_color=THEME_PRIMARY):
    """Show help specific to agent mode."""
    from rich.table import Table

    console.print()
    console.print(" [bold white]Agent Mode Help[/bold white]")
    console.print(" [dim]Launch an autonomous AI agent to navigate and perform tasks.[/dim]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style=f"{mode_color} bold", justify="left", width=30)
    table.add_column(style="white", justify="left")

    table.add_row("<prompt>", "Instruction for the autonomous agent.\n[dim]Example: Go to google.com and search for 'OpenAI'[/dim]")
    table.add_row("", "")

    table.add_row("@record-only <prompt>", "Record HAR only, skip reverse engineering.\n[dim]Example: @record-only navigate checkout flow[/dim]")
    table.add_row("", "")

    table.add_row("Shift+Tab", "Cycle to other modes (Manual, Engineer).")

    console.print(table)
    console.print()


def handle_collector_help(mode_color=THEME_PRIMARY):
    """Show help specific to collector mode."""
    from rich.table import Table

    console.print()
    console.print(" [bold white]Collector Mode Help[/bold white]")
    console.print(" [dim]AI-powered web data collection. Describe what data you want, get JSON/CSV output.[/dim]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style=f"{mode_color} bold", justify="left", width=30)
    table.add_column(style="white", justify="left")

    table.add_row(
        "<prompt>", "Describe data to collect in natural language.\n[dim]Example: Find 10 YC W24 AI startups with name, website, funding[/dim]"
    )
    table.add_row("", "")

    table.add_row("Output", "JSON + CSV saved to ./collected/<folder>/")
    table.add_row("", "")

    table.add_row("Shift+Tab", "Cycle to other modes.")

    console.print(table)
    console.print()


def handle_engineer_help(mode_color=THEME_PRIMARY):
    """Show help specific to engineer mode."""
    from rich.table import Table

    console.print()
    console.print(" [bold white]Engineer Mode Help[/bold white]")
    console.print(" [dim]Reverse engineer APIs from captured sessions (HAR files).[/dim]")
    console.print()

    # Syntax table
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style=f"{mode_color} bold", justify="left", width=30)
    table.add_column(style="white", justify="left")

    table.add_row("@id <run_id>", "Switch context to a specific run ID.\n[dim]Example: @id abc123[/dim]")
    table.add_row("", "")

    table.add_row("@id <run_id> <prompt>", "Run engineer on a specific run with instructions.\n[dim]Example: @id abc123 extract user profile[/dim]")
    table.add_row("", "")

    table.add_row(
        "@id <run_id> --fresh <prompt>",
        "Start fresh (ignore previous scripts) with new instructions.\n[dim]Example: @id abc123 --fresh restart analysis[/dim]",
    )
    table.add_row("", "")

    table.add_row("<run_id>", "Quick context switch (same as @id <run_id>).\n[dim]Example: abc123[/dim]")
    table.add_row("", "")

    table.add_row("<prompt>", "Run engineer on the *current* context/latest run.\n[dim]Example: improve error handling[/dim]")
    table.add_row("", "")

    table.add_row("@docs", "Generate API documentation (OpenAPI spec) for the latest run.\n[dim]Example: @docs[/dim]")
    table.add_row("", "")

    table.add_row("@id <run_id> @docs", "Generate API documentation for a specific run.\n[dim]Example: @id abc123 @docs[/dim]")

    console.print(table)
    console.print()


def handle_help(mode_color=THEME_PRIMARY):
    """Show enhanced help with command details and examples."""
    from rich.table import Table

    console.print()

    # Commands table
    commands_table = Table(show_header=False, box=None, padding=(0, 1))
    commands_table.add_column(style=f"{mode_color} bold", justify="left", width=20)
    commands_table.add_column(style="white", justify="left")

    commands_table.add_row(
        "/settings",
        "Configure model, SDK, agent provider, and sync settings\n[dim]Usage: /settings[/dim]",
    )
    commands_table.add_row("", "")  # Spacing

    commands_table.add_row(
        "/history",
        "View past runs with timestamps, costs, and status\n[dim]Usage: /history[/dim]",
    )
    commands_table.add_row("", "")

    commands_table.add_row(
        "/messages <run_id>",
        "View detailed message logs from a specific run\n[dim]Usage: /messages abc123[/dim]",
    )
    commands_table.add_row("", "")

    commands_table.add_row("/help", "Show this help message\n[dim]Usage: /help[/dim]")
    commands_table.add_row("", "")

    commands_table.add_row("/exit or /quit", "Exit the application\n[dim]Usage: /exit[/dim]")

    console.print(" [bold white]Available Commands[/bold white]")
    console.print(commands_table)

    # Modes table
    console.print()
    modes_table = Table(show_header=False, box=None, padding=(0, 1))
    modes_table.add_column(style=f"{mode_color} bold", justify="left", width=15)
    modes_table.add_column(style="dim", justify="left")

    modes_table.add_row("manual", "Full pipeline: browser + reverse engineering")
    modes_table.add_row("engineer", "Reverse engineer only (enter run_id)")
    modes_table.add_row("agent", "Autonomous agent + capture")

    console.print(" [bold white]Modes[/bold white] [dim]Shift+Tab to cycle[/dim]")
    console.print(modes_table)
    console.print()


def handle_messages(run_id: str, mode_color=THEME_PRIMARY):
    """Display messages from a previous run."""
    from rich.table import Table

    store = MessageStore(run_id)
    messages = store.load()

    if not messages:
        console.print(f" [dim]>[/dim] [red]no messages found for run:[/red] {run_id}")
        return

    # Create header panel
    header_table = Table(show_header=False, box=None, padding=(0, 0))
    header_table.add_column(style="white", justify="left")
    header_table.add_row(f"Run ID: {run_id}")
    header_table.add_row(f"Total Messages: {len(messages)}")

    console.print()
    console.print(" [bold white]Message Log[/bold white]")
    console.print(header_table)
    console.print()

    for msg in messages:
        msg_type = msg.get("type", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")[:19]  # Truncate to datetime

        if msg_type == "prompt":
            console.print(f" [dim]{timestamp}[/dim] [white]prompt[/white]")
            # Show first 200 chars of prompt
            display = str(content)[:200]
            if len(str(content)) > 200:
                display += "..."
            console.print(f"   [dim]{display}[/dim]")
        elif msg_type == "tool_start":
            name = content.get("name", "tool")
            console.print(f" [dim]{timestamp}[/dim] [white]{name.lower()}[/white]")
        elif msg_type == "tool_result":
            name = content.get("name", "tool")
            is_error = content.get("is_error", False)
            status = "[red]error[/red]" if is_error else "[dim]ok[/dim]"
            console.print(f" [dim]{timestamp}[/dim]   {status}")
        elif msg_type == "thinking":
            display = str(content)[:100].replace("\\n", " ")
            if len(str(content)) > 100:
                display += "..."
            console.print(f" [dim]{timestamp}  .. {display}[/dim]")
        elif msg_type == "error":
            console.print(f" [dim]{timestamp}[/dim] [red]error: {content}[/red]")
        elif msg_type == "result":
            console.print(f" [dim]{timestamp}[/dim] [white]complete[/white]")
            if isinstance(content, dict):
                script_path = content.get("script_path", "")
                if script_path:
                    console.print(f"   [dim]{script_path}[/dim]")

    console.print()


@main.command()
@click.option("--prompt", "-p", default=None, help="Capture description.")
@click.option("--url", "-u", default=None, help="Starting URL.")
@click.option(
    "--reverse-engineer/--no-engineer",
    "reverse_engineer",
    default=True,
    help="Auto-run Claude.",
)
@click.option(
    "--model",
    "-m",
    type=click.Choice(["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"]),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
def manual(prompt, url, reverse_engineer, model, output_dir):
    """Start a manual browser session."""
    run_manual_capture(prompt, url, reverse_engineer, model, output_dir)


def run_manual_capture(prompt=None, url=None, reverse_engineer=True, model=None, output_dir=None):
    """Shared logic for manual capture."""
    output_dir = output_dir or config_manager.get("output_dir")

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=reverse_engineer,
            model=model,
        )
        if "command" in options:
            return  # Should not happen from here
        prompt = options["prompt"]
        url = options["url"]
        reverse_engineer = options["reverse_engineer"]
        model = options["model"]

    # Parse @record-only tag - if present, skip reverse engineering
    prompt, is_record_only = parse_record_only_tag(prompt)
    prompt, is_codegen = parse_codegen_tag(prompt)

    if is_record_only:
        reverse_engineer = False
    if is_codegen:
        reverse_engineer = False

    run_id = generate_run_id()
    timestamp = get_timestamp()
    sdk = config_manager.get("sdk", "claude")

    # Record initial session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode="manual",  # Track mode in history
        sdk=sdk,
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    browser = ManualBrowser(run_id=run_id, prompt=prompt, output_dir=output_dir, enable_action_recording=is_codegen)
    har_path = browser.start(start_url=url)

    if reverse_engineer:
        result = run_engineer(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
        )
        if result:
            sdk = config_manager.get("sdk", "claude")
            session_manager.update_run(
                run_id=run_id,
                sdk=sdk,
                usage=result.get("usage", {}),
                paths={"script_path": result.get("script_path")},
            )
    elif is_codegen:
        # Generate Playwright script from recorded actions
        run_playwright_codegen(run_id, prompt, output_dir, start_url=url)
    elif is_record_only:
        # Show helpful message for record-only mode
        console.print(" [dim]>[/dim] [white]recording complete[/white]")
        console.print(f" [dim]>[/dim] [white]run_id: {run_id}[/white]")
        console.print(f" [dim]>[/dim] [dim]use @id {run_id} <prompt> to engineer later[/dim]\n")


def run_agent_capture(prompt=None, url=None, reverse_engineer=False, model=None, output_dir=None):
    """Shared logic for agent capture mode."""
    output_dir = output_dir or config_manager.get("output_dir")

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=reverse_engineer,
            model=model,
        )
        if "command" in options:
            return
        prompt = options["prompt"]
        url = options["url"]
        reverse_engineer = options["reverse_engineer"]
        model = options["model"]

    # Parse @record-only tag - if present, skip reverse engineering
    prompt, is_record_only = parse_record_only_tag(prompt)
    if is_record_only:
        reverse_engineer = False
        # Agent mode requires a prompt for @record-only
        if not prompt or not prompt.strip():
            console.print(" [red]error:[/red] @record-only requires a prompt in agent mode")
            console.print(" [dim]tip:[/dim] @record-only <prompt> - e.g., @record-only navigate checkout flow")
            return

    run_id = generate_run_id()
    timestamp = get_timestamp()
    sdk = config_manager.get("sdk", "claude")

    # Get agent models and provider from config
    browser_use_model = config_manager.get("browser_use_model", "bu-llm")
    stagehand_model = config_manager.get("stagehand_model", "openai/computer-use-preview-2025-03-11")
    agent_provider = config_manager.get("agent_provider", "browser-use")

    # Route to auto mode if configured
    if agent_provider == "auto":
        return run_auto_capture(
            prompt=prompt,
            url=url,
            model=model,
            output_dir=output_dir,
        )

    # Record initial session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode="agent",  # Track mode in history
        sdk=sdk,
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    # Run agent browser
    try:
        har_path = run_agent_browser(
            run_id=run_id,
            prompt=prompt,
            output_dir=output_dir,
            browser_use_model=browser_use_model,
            stagehand_model=stagehand_model,
            agent_provider=agent_provider,
            start_url=url,
        )

        # Optionally run reverse engineering
        if reverse_engineer:
            engineer_prompt = prompt
            try:
                wants_new_prompt = questionary.confirm(
                    " > new prompt for engineer?",
                    default=False,
                    qmark="",
                    style=questionary.Style(
                        [
                            ("question", f"fg:{THEME_SECONDARY}"),
                            ("instruction", f"fg:{THEME_DIM} italic"),
                        ]
                    ),
                ).ask()

                if wants_new_prompt is None:
                    raise KeyboardInterrupt

                if wants_new_prompt:
                    new_prompt = questionary.text(
                        " > engineer prompt",
                        instruction="(Enter to use original)",
                        default="",
                        qmark="",
                        style=questionary.Style(
                            [
                                ("question", f"fg:{THEME_SECONDARY}"),
                                ("instruction", f"fg:{THEME_DIM} italic"),
                            ]
                        ),
                    ).ask()

                    if new_prompt is None:
                        raise KeyboardInterrupt

                    if new_prompt and new_prompt.strip():
                        engineer_prompt = new_prompt.strip()
            except KeyboardInterrupt:
                pass

            result = run_engineer(
                run_id=run_id,
                har_path=har_path,
                prompt=engineer_prompt,
                model=model,
                output_dir=output_dir,
            )
            if result:
                sdk = config_manager.get("sdk", "claude")
                session_manager.update_run(
                    run_id=run_id,
                    sdk=sdk,
                    usage=result.get("usage", {}),
                    paths={"script_path": result.get("script_path")},
                )
        elif is_record_only:
            # Show helpful message for record-only mode
            console.print(" [dim]>[/dim] [white]recording complete[/white]")
            console.print(f" [dim]>[/dim] [white]run_id: {run_id}[/white]")
            console.print(f" [dim]>[/dim] [dim]use @id {run_id} <prompt> to engineer later[/dim]\n")
    except Exception as e:
        console.print(f" [red]agent mode error: {e}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()


def run_collector(prompt=None, model=None, output_dir=None):
    """Run AI-powered data collection with Collector class."""
    import asyncio

    from .collector import Collector

    # Generate run ID
    run_id = generate_run_id()
    output_dir = output_dir or config_manager.get("output_dir")

    # Use collector model from config if not specified
    if model is None:
        model = config_manager.get("collector_model", "claude-sonnet-4-5")

    # Initialize session
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt or "",
        mode="collector",
        timestamp=get_timestamp(),
    )

    try:
        # Run collector
        collector = Collector(
            run_id=run_id,
            prompt=prompt or "",
            model=model,
            output_dir=output_dir,
        )

        result = asyncio.run(collector.run())

        if result and not result.get("error"):
            # Update session with results
            session_manager.update_run(
                run_id=run_id,
                sdk="claude",
                usage=result.get("usage", {}),
                paths={"output_path": result.get("output_path")},
            )
    except Exception as e:
        console.print(f" [red]collector error: {e}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()


def run_auto_capture(prompt=None, url=None, model=None, output_dir=None):
    """Auto mode: LLM-driven browser automation + real-time reverse engineering."""
    output_dir = output_dir or config_manager.get("output_dir")

    if prompt is None:
        options = prompt_interactive_options(
            prompt=prompt,
            url=url,
            reverse_engineer=False,  # Not applicable for auto mode
            model=model,
        )
        if "command" in options:
            return
        prompt = options["prompt"]
        url = options.get("url")
        model = options["model"]

    run_id = generate_run_id()
    timestamp = get_timestamp()

    # Record initial session with mode="auto"
    session_manager.add_run(
        run_id=run_id,
        prompt=prompt,
        timestamp=timestamp,
        url=url,
        model=model,
        mode="auto",  # Track auto mode in history
        paths={"har_dir": str(get_har_dir(run_id, output_dir))},
    )

    # Get SDK configuration
    sdk = config_manager.get("sdk", "claude")

    # Run auto engineer based on SDK
    try:
        output_language = config_manager.get("output_language", "python")
        if sdk == "opencode":
            from .auto_engineer import OpenCodeAutoEngineer

            engineer = OpenCodeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                output_dir=output_dir,
                opencode_provider=config_manager.get("opencode_provider", "anthropic"),
                opencode_model=config_manager.get("opencode_model", "claude-sonnet-4-5"),
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
            )
        else:
            from .auto_engineer import ClaudeAutoEngineer

            engineer = ClaudeAutoEngineer(
                run_id=run_id,
                prompt=prompt,
                model=model or config_manager.get("claude_code_model", "claude-sonnet-4-5"),
                output_dir=output_dir,
                enable_sync=config_manager.get("real_time_sync", False),
                sdk=sdk,
                output_language=output_language,
            )

        # Start sync before analysis
        engineer.start_sync()

        try:
            result = asyncio.run(engineer.analyze_and_generate())
        finally:
            # Always stop sync when done
            engineer.stop_sync()

        # Update session with results
        if result:
            session_manager.update_run(
                run_id=run_id,
                usage=result.get("usage", {}),
                paths={"script_path": result.get("script_path")},
            )

        return result

    except Exception as e:
        console.print(f" [red]auto mode error: {e}[/red]")
        console.print(f" [dim]{ERROR_CTA}[/dim]")
        import traceback

        traceback.print_exc()
        return None


def run_playwright_codegen(run_id: str, prompt: str, output_dir: str | None = None, start_url: str | None = None):
    """Generate Playwright script from recorded actions."""
    actions_path = get_actions_path(run_id, output_dir)
    if not actions_path.exists():
        console.print(" [red]error:[/red] no actions recorded")
        return

    from .action_recorder import ActionRecorder

    actions = ActionRecorder.load(actions_path)
    action_list = actions.get_actions()

    # If no explicit start_url, extract from first navigate action
    if not start_url and action_list:
        if action_list[0].type == "navigate" and action_list[0].url:
            start_url = action_list[0].url

    generator = PlaywrightCodeGenerator(action_list, start_url=start_url)
    script = generator.generate()

    scripts_dir = get_scripts_dir(run_id, output_dir)

    # Handle duplicate file paths
    script_path = scripts_dir / "automation.py"
    if script_path.exists():
        i = 1
        while (scripts_dir / f"automation_{i}.py").exists():
            i += 1
        script_path = scripts_dir / f"automation_{i}.py"

    script_path.write_text(script)

    # Also write requirements.txt
    (scripts_dir / "requirements.txt").write_text("playwright\n")

    console.print(" [dim]>[/dim] [white]codegen complete[/white]")
    console.print(f" [dim]>[/dim] [white]{script_path}[/white]")
    console.print(f" [dim]>[/dim] [dim]run with: uv run python {script_path}[/dim]\n")


@main.command()
@click.argument("run_id")
@click.option(
    "--model",
    "-m",
    type=click.Choice(["claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5"]),
    default=None,
)
@click.option("--output-dir", "-o", default=None, help="Custom output directory.")
def engineer(run_id, model, output_dir):
    """Run reverse engineering on a previous run."""
    run_engineer(run_id, model=model, output_dir=output_dir)


def run_engineer(
    run_id,
    har_path=None,
    prompt=None,
    model=None,
    output_dir=None,
    additional_instructions=None,
    is_fresh=False,
    output_mode="client",
):
    """Shared logic for reverse engineering."""
    if not har_path or not prompt:
        # Load from history if possible
        run_data = session_manager.get_run(run_id)
        if not run_data:
            # Fallback to file search if not in history
            har_dir = get_har_dir(run_id, output_dir)
            har_path = har_dir / "recording.har"
            if not har_path.exists():
                console.print(f" [red]not found:[/red] {run_id}")
                return None
            if not prompt:
                prompt = "Reverse engineer captured APIs" if output_mode == "client" else "Generate OpenAPI documentation"
        else:
            if not prompt:
                prompt = run_data["prompt"]
            # Detect where it was saved
            paths = run_data.get("paths", {})
            har_dir = Path(paths.get("har_dir", get_har_dir(run_id, None)))
            har_path = har_dir / "recording.har"

    sdk = config_manager.get("sdk", "claude")
    enable_sync = config_manager.get("real_time_sync", True)
    output_language = config_manager.get("output_language", "python")

    if sdk == "opencode":
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model,
            output_dir=output_dir,
            sdk=sdk,
            opencode_provider=config_manager.get("opencode_provider", "anthropic"),
            opencode_model=config_manager.get("opencode_model", "claude-sonnet-4-5"),
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
        )
    else:
        result = run_reverse_engineering(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            model=model or config_manager.get("claude_code_model", "claude-sonnet-4-5"),
            output_dir=output_dir,
            sdk=sdk,
            enable_sync=enable_sync,
            additional_instructions=additional_instructions,
            is_fresh=is_fresh,
            output_language=output_language,
            output_mode=output_mode,
        )

    if result:
        # Skip manual copy if real-time sync is enabled (files already synced)
        if not enable_sync:
            # Automatically copy to current directory with a readable name
            output_dir_path = Path(result["script_path"]).parent
            base_name = generate_folder_name(prompt, sdk=sdk)

            # Choose base path based on output mode
            if output_mode == "docs":
                base_path = Path.cwd() / "docs"
            else:
                base_path = Path.cwd() / "scripts"

            from .sync import get_available_directory

            # Get available directory (won't overwrite existing non-empty dirs)
            local_dir = get_available_directory(base_path, base_name)
            local_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            for item in output_dir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, local_dir / item.name)

            # Different messages for docs vs client mode
            if output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./docs/{local_dir.name}[/white]\n")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
                console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
                console.print(f" [dim]>[/dim] [white]copied to ./scripts/{local_dir.name}[/white]\n")
        else:
            # With sync enabled, just show completion
            if output_mode == "docs":
                console.print(" [dim]>[/dim] [white]documentation complete[/white]")
            else:
                console.print(" [dim]>[/dim] [white]decoding complete[/white]")
            console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]\n")

        session_manager.update_run(
            run_id=run_id,
            sdk=sdk,
            output_mode=output_mode,
            usage=result.get("usage", {}),
            paths={"script_path": result.get("script_path")},
        )
    return result


@main.command("install-host")
@click.option(
    "--extension-id",
    default=None,
    help="Chrome extension ID (required - get from chrome://extensions/)",
)
def install_host(extension_id: str | None):
    """Install the native messaging host for Chrome extension integration."""
    from .native_host import install_native_host

    success, message = install_native_host(extension_id)
    if success:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[red]{message}[/red]")
        raise SystemExit(1)


@main.command("uninstall-host")
def uninstall_host():
    """Uninstall the native messaging host."""
    from .native_host import uninstall_native_host

    success, message = uninstall_native_host()
    if success:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[red]{message}[/red]")
        raise SystemExit(1)


@main.command("run-host")
def run_host_cmd():
    """Run the native messaging host (used by Chrome extension)."""
    from .native_host import run_host

    run_host()


if __name__ == "__main__":
    main()
