# Setup

```bash
uv sync --extra agent
uv run playwright install chromium
export ANTHROPIC_API_KEY=sk-ant-...
uv run reverse-api-engineer
```

Defaults: `stagehand` + `anthropic/claude-sonnet-4-5-20250929`.
