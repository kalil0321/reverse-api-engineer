# Setup

Quick steps to run the agent locally.

## 1. Install

```bash
uv sync --extra agent
uv run playwright install chromium
```

The `--extra agent` flag is required — it installs `stagehand` and `browser-use`, which are optional dependencies.

## 2. Environment

Copy the example file and fill in your key:

```bash
cp .env.example .env
```

For the defaults (`stagehand` + `anthropic/claude-sonnet-4-5-20250929`) only `ANTHROPIC_API_KEY` is required. Add `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `BROWSER_USE_API_KEY` only if you switch model.

## 3. Run

```bash
uv run reverse-api-engineer
```

Pick `agent` mode, enter a prompt and (optionally) a starting URL.

## Defaults

| Setting          | Value                                  |
| ---------------- | -------------------------------------- |
| `agent_provider` | `stagehand`                            |
| `agent_model`    | `anthropic/claude-sonnet-4-5-20250929` |

Change them via the CLI menu (`> agent provider` / `> agent model`).
