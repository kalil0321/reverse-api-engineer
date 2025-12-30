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
    get_config_path,
    get_har_dir,
    get_history_path,
    get_timestamp,
    parse_engineer_prompt,
)

console = Console()
config_manager = ConfigManager(get_config_path())
session_manager = SessionManager(get_history_path())

# Mode definitions
MODES = ["manual", "engineer", "agent"]
MODE_DESCRIPTIONS = {
    "manual": "full pipeline",
    "engineer": "reverse engineer only",
    "agent": "autonomous agent + capture",
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
            # Tag completion in engineer mode
            elif mode_state["mode"] == "engineer" and text:
                if text.startswith("@"):
                    # Tag completion
                    tags = ["@id", "@help"]  # @docs, @build coming in next phases

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
                        # Suggest tags
                        for tag in tags:
                            if tag.startswith(text):
                                yield Completion(tag, start_position=-len(text))

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

        context = ""
        if mode == "engineer":
            try:
                history = session_manager.get_history(limit=1)
                if history:
                    context = f": {history[0]['run_id']}"
            except Exception:
                pass

        return HTML(
            f'<style fg="{mode_color}">[{mode}{context}]</style> <style fg="{mode_color}" bold="true">&gt;</style> '
        )

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
    console.print("  [dim]shift+tab to cycle modes: manual | engineer | agent[/dim]")
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
                elif cmd.startswith("/messages"):
                    parts = cmd.split(maxsplit=1)
                    if len(parts) > 1:
                        handle_messages(parts[1].strip(), mode_color)
                    else:
                        console.print(" [red]usage:[/red] /messages <run_id>")
                else:
                    # Unknown command - show error and available commands
                    console.print(f" [red]Unknown command:[/red] {cmd}")
                    console.print(
                        " [dim]Available commands: /settings, /history, /messages, /help, /exit[/dim]"
                    )
                continue

            mode = options.get("mode", "manual")

            # Handle different modes
            if mode == "engineer":
                # Engineer mode
                raw_input = options.get("run_id")

                # Handle empty input
                if not raw_input:
                    console.print(" [dim]Usage:[/dim] @id <run_id> [instructions]")
                    console.print(" [dim]       [/dim] <run_id> (to switch context)")
                    continue

                # Parse tag
                parsed = parse_engineer_prompt(raw_input)

                target_run_id = parsed["run_id"]
                is_fresh = parsed["fresh"]
                user_text = parsed["prompt"]

                main_prompt = None
                add_instr = None

                if parsed["is_tag_command"]:
                    # Explicit @id command
                    if not target_run_id:
                        console.print(" [red]error:[/red] invalid @id syntax")
                        continue

                    # If fresh, user text is new prompt. Else, it's additive.
                    if is_fresh:
                        main_prompt = user_text if user_text else None
                    else:
                        add_instr = user_text if user_text else None

                else:
                    # Implicit mode - check if input is a valid run_id
                    if session_manager.get_run(user_text):
                        target_run_id = user_text
                    else:
                        # Input is neither a tag command nor a valid run ID
                        console.print(f" [red]error:[/red] run '{user_text}' not found")
                        console.print(" [dim]Use @id <run_id> or type a valid run ID[/dim]")
                        continue

                run_engineer(
                    target_run_id,
                    prompt=main_prompt,
                    model=options.get("model"),
                    additional_instructions=add_instr,
                    is_fresh=is_fresh,
                )
                continue

                # Parse tag
                parsed = parse_engineer_prompt(raw_input)

                target_run_id = parsed["run_id"]
                is_fresh = parsed["fresh"]
                user_text = parsed["prompt"]

                main_prompt = None
                add_instr = None

                if parsed["is_tag_command"]:
                    # Explicit @id command
                    if not target_run_id:
                        console.print(" [red]error:[/red] invalid @id syntax")
                        continue

                    # If fresh, user text is new prompt. Else, it's additive.
                    if is_fresh:
                        main_prompt = user_text if user_text else None
                    else:
                        add_instr = user_text if user_text else None

                else:
                    # Implicit mode - check if input is a valid run_id
                    if session_manager.get_run(user_text):
                        # Just context switching / selecting run
                        # We do NOT run engineer automatically on selection unless instructed?
                        # The original code ran engineer. But wait, if I select a run, do I want to RE-run it?
                        # Usually user selects run to then do something.
                        # But prompt says "remove last run fallback".

                        target_run_id = user_text

                        # If just run_id provided, maybe we just set context?
                        # But run_engineer expects to DO something.
                        # If run_engineer is called without new prompt, it uses old prompt.
                        # Let's assume selecting a run_id triggers a re-run with existing prompt (default behavior)
                        pass
                    else:
                        # Input is neither a tag command nor a valid run ID
                        console.print(f" [red]error:[/red] run '{user_text}' not found")
                        console.print(" [dim]Use @id <run_id> or type a valid run ID[/dim]")
                        continue

                run_engineer(
                    target_run_id,
                    prompt=main_prompt,
                    model=options.get("model"),
                    additional_instructions=add_instr,
                    is_fresh=is_fresh,
                )
                continue

                # Parse tag
                parsed = parse_engineer_prompt(raw_input)

                target_run_id = parsed["run_id"]
                is_fresh = parsed["fresh"]
                user_text = parsed["prompt"]

                main_prompt = None
                add_instr = None

                if parsed["is_tag_command"]:
                    # Explicit @id command
                    if not target_run_id:
                        console.print(" [red]error:[/red] invalid @id syntax")
                        continue

                    # If fresh, user text is new prompt. Else, it's additive.
                    if is_fresh:
                        main_prompt = user_text if user_text else None
                    else:
                        add_instr = user_text if user_text else None

                else:
                    # Implicit mode
                    # Check if input is just a run_id
                    if session_manager.get_run(user_text):
                        target_run_id = user_text
                        # Just switching run, no new instructions
                    else:
                        # Implicit @id on latest run
                        latest_runs = session_manager.get_history(limit=1)
                        if not latest_runs:
                            console.print(" [red]error:[/red] no runs found in history")
                            continue
                        target_run_id = latest_runs[0]["run_id"]

                        # Treat input as additive instructions
                        add_instr = user_text

                run_engineer(
                    target_run_id,
                    prompt=main_prompt,
                    model=options.get("model"),
                    additional_instructions=add_instr,
                    is_fresh=is_fresh,
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


def handle_settings(mode_color=THEME_PRIMARY):
    """Display and manage settings with improved layout and descriptions."""
    from rich.table import Table

    console.print()

    # Create a table for current configuration
    config_table = Table(show_header=False, box=None, padding=(0, 1))
    config_table.add_column(style="dim", justify="left")
    config_table.add_column(style=mode_color, justify="left")

    for k, v in config_manager.config.items():
        display_val = str(v) if v is not None else "default"
        # Make the key more readable
        key_display = k.replace("_", " ").title()
        config_table.add_row(key_display, display_val)

    # Display in a clean format
    console.print(" [bold white]Settings[/bold white] [dim]Current Configuration[/dim]")
    console.print(config_table)
    console.print()

    # Settings menu
    choices = [
        Choice(title="Claude Code Model", value="claude_code_model"),
        Choice(title="SDK", value="sdk"),
        Choice(title="OpenCode Provider", value="opencode_provider"),
        Choice(title="OpenCode Model", value="opencode_model"),
        Choice(title="Agent Provider", value="agent_provider"),
        Choice(title="Browser-Use Model", value="browser_use_model"),
        Choice(title="Stagehand Model", value="stagehand_model"),
        Choice(title="Real-time Sync", value="real_time_sync"),
        Choice(title="Output Directory", value="output_dir"),
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
        model_choices = [
            Choice(title=c["name"].lower(), value=c["value"]) for c in get_model_choices()
        ]
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

    elif action == "agent_provider":
        provider_choices = [
            Choice(title="browser-use", value="browser-use"),
            Choice(title="stagehand", value="stagehand"),
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
        instruction = "(Format: 'openai/model' or 'anthropic/model', e.g., 'openai/computer-use-preview-2025-03-11' or 'anthropic/claude-sonnet-4-5-20250929')"

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

    browser = ManualBrowser(run_id=run_id, prompt=prompt, output_dir=output_dir)
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

    run_id = generate_run_id()
    timestamp = get_timestamp()
    sdk = config_manager.get("sdk", "claude")

    # Get agent models and provider from config
    browser_use_model = config_manager.get("browser_use_model", "bu-llm")
    stagehand_model = config_manager.get(
        "stagehand_model", "openai/computer-use-preview-2025-03-11"
    )
    agent_provider = config_manager.get("agent_provider", "browser-use")

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
    except Exception as e:
        console.print(f" [red]agent mode error: {e}[/red]")
        import traceback

        traceback.print_exc()


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
                prompt = "Reverse engineer captured APIs"  # Default
        else:
            if not prompt:
                prompt = run_data["prompt"]
            # Detect where it was saved
            paths = run_data.get("paths", {})
            har_dir = Path(paths.get("har_dir", get_har_dir(run_id, None)))
            har_path = har_dir / "recording.har"

    sdk = config_manager.get("sdk", "claude")
    enable_sync = config_manager.get("real_time_sync", True)

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
        )

    if result:
        # Skip manual copy if real-time sync is enabled (files already synced)
        if not enable_sync:
            # Automatically copy scripts to current directory with a readable name
            scripts_dir = Path(result["script_path"]).parent
            base_name = generate_folder_name(prompt, sdk=sdk)
            scripts_base_path = Path.cwd() / "scripts"

            from .sync import get_available_directory

            # Get available directory (won't overwrite existing non-empty dirs)
            local_dir = get_available_directory(scripts_base_path, base_name)
            local_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            for item in scripts_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, local_dir / item.name)

            console.print(" [dim]>[/dim] [white]decoding complete[/white]")
            console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]")
            console.print(f" [dim]>[/dim] [white]copied to ./scripts/{local_dir.name}[/white]\n")
        else:
            # With sync enabled, just show completion
            console.print(" [dim]>[/dim] [white]decoding complete[/white]")
            console.print(f" [dim]>[/dim] [white]{result['script_path']}[/white]\n")

        session_manager.update_run(
            run_id=run_id,
            sdk=sdk,
            usage=result.get("usage", {}),
            paths={"script_path": result.get("script_path")},
        )
    return result


if __name__ == "__main__":
    main()
