# Setup and configuration

## Requirements

- Python 3.11+ and `uv` (or `pipx` / `pip`).
- Node.js 20.19+ with `npx` on `PATH` for agent mode.
- Headed `chrome-mcp` runs: Chrome 146+ running, with remote debugging enabled at `chrome://inspect/#remote-debugging`.
- Manual mode only: `uv tool install "reverse-api-engineer[manual]"`, then `playwright install chromium`.

## Model access

rae calls a model through the SDK selected in its config:

| `sdk` | Auth |
|---|---|
| `claude` (default) | `ANTHROPIC_API_KEY`, or an existing Claude Code login |
| `opencode` | An OpenCode server rae starts or reuses. Defaults to a free model; can route to local models through Ollama |
| `copilot` | GitHub Copilot credentials (`GITHUB_COPILOT_TOKEN`) |
| `cursor` | `CURSOR_API_KEY` |
| `codex` | Existing local Codex CLI login; on Windows, Codex Desktop's bundled CLI is preferred when present, then `codex` on `PATH` |

`agent --dry-run` reports which of these it can see. A missing env var is a warning, not an error, because some SDKs find credentials on their own. Codex defaults to `gpt-6-luna` unless `codex_model` or `--model` overrides it.

## Settings

Settings live in `~/.reverse-api/config.json`. Only two have per-run flags on `agent`: `-o/--output-dir` and `-m/--model` (for the `claude` and `codex` SDKs). Change the others by editing that file, and only with the user's agreement since it affects every later run. Keys that matter most:

| Key | Values |
|---|---|
| `agent_provider` | `chrome-mcp` (the user's real Chrome, no HAR; default for new configs in recent versions), `auto` (Playwright MCP, records a HAR; the default in older versions), `agent-browser` (Vercel agent-browser CLI, records a HAR) |
| `output_language` | `python`, `javascript`, `typescript`, `go`, `java`, `csharp`, `php`, `ruby`, `c`, `powershell` |
| `sdk` | `claude`, `opencode`, `copilot`, `cursor`, `codex` |
| `claude_code_model` | Model for the `claude` SDK; `agent -m` overrides it per run |
| `codex_model` | Optional model for the `codex` SDK; defaults to `gpt-6-luna` |
| `output_dir` | Where runs are stored; `null` means `~/.reverse-api/runs` |

The user can also change them interactively by running `reverse-api-engineer` and typing `/settings`.

Language notes: C needs a POSIX toolchain with libcurl headers. PowerShell needs `pwsh` 7+.

For Codex agent runs, model selection uses the per-run --model override, then codex_model, then gpt-6-luna. A selected value of default also resolves to gpt-6-luna rather than the Codex CLI configured default. Choosing Codex in /settings also selects the required auto browser provider.
