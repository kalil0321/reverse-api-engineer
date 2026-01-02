<div align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-banner.svg" alt="Reverse API Engineer Banner">
</div>

![PyPI](https://img.shields.io/pypi/v/reverse-api-engineer)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

CLI tool that captures browser traffic and automatically generates production-ready Python API clients. No more manual reverse engineering—just browse, capture, and get clean API code.

![Reverse API Engineer Demo](https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-engineer.gif)

## Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Modes](#-usage-modes)
  - [Manual Mode](#manual-mode)
  - [Engineer Mode](#engineer-mode)
  - [Agent Mode](#agent-mode)
- [Configuration](#-configuration)
  - [Model Selection](#model-selection)
  - [💸 Free Models with Antigravity](#free-model-options-with-antigravity)
  - [Agent Configuration](#agent-configuration)
  - [SDK Selection](#sdk-selection)
- [CLI Commands](#-cli-commands)
- [Examples](#-examples)
- [Development](#-development)
- [Contributing](#-contributing)

## ✨ Features

- 🌐 **Browser Automation**: Built on Playwright with stealth mode for realistic browsing
- 🤖 **Autonomous Agent Mode**: Fully automated browser interaction using AI agents (auto mode with MCP, browser-use, stagehand)
- 📊 **HAR Recording**: Captures all network traffic in HTTP Archive format
- 🧠 **AI-Powered Generation**: Uses Claude 4.5 to analyze traffic and generate clean Python code
- 🔌 **Multi-SDK Support**: Native integration with Claude and OpenCode SDKs
- 💻 **Interactive CLI**: Minimalist terminal interface with mode cycling (Shift+Tab)
- 📦 **Production Ready**: Generated scripts include error handling, type hints, and documentation
- 💾 **Session History**: All runs saved locally with full message logs
- 💰 **Cost Tracking**: Detailed token usage and cost estimation with cache support

### Limitations

- This tool executes code locally using Claude Code—please monitor output
- Some websites employ advanced bot-detection that may limit capture or require manual interaction

## 🚀 Installation

### Using uv (recommended)
```bash
# Basic installation
uv tool install reverse-api-engineer

# With agent mode support (includes browser-use with HAR recording)
uv tool install 'reverse-api-engineer[agent]' --with 'browser-use @ git+https://github.com/browser-use/browser-use.git@49a345fb19e9f12befc5cc1658e0033873892455'
```

### Using pip
```bash
# Basic installation
pip install reverse-api-engineer

# With agent mode support
pip install 'reverse-api-engineer[agent]'
pip install git+https://github.com/browser-use/browser-use.git@49a345fb19e9f12befc5cc1658e0033873892455
```

### Post-installation
Install Playwright browsers:
```bash
playwright install chromium
```

### Enhanced Pricing Support (Optional)

By default, Reverse API Engineer includes pricing data for the most common models (Claude 4.5, Gemini 3). For extended model coverage (100+ additional models including OpenAI GPT, Mistral, DeepSeek, and more), install with pricing extras:

```bash
# With uv
uv tool install 'reverse-api-engineer[pricing]'

# With pip
pip install 'reverse-api-engineer[pricing]'
```

This enables automatic pricing lookup via [LiteLLM](https://github.com/BerriAI/litellm) for models not in the built-in database. The pricing system uses a 3-tier fallback:
1. **Local pricing** (highest priority) - Built-in pricing for common models
2. **LiteLLM pricing** (if installed) - Extended coverage for 100+ models
3. **Default pricing** (ultimate fallback) - Uses Claude Sonnet 4.5 pricing

Cost tracking will always work, with or without the pricing extras installed.

## 🚀 Quick Start

Launch the interactive CLI:
```bash
reverse-api-engineer
```

The CLI has three modes (cycle with **Shift+Tab**):
- **manual**: Browser capture + AI generation
- **engineer**: Re-process existing captures
- **agent**: Autonomous AI browser agent (default: auto mode with MCP-based browser + real-time reverse engineering)

Example workflow:
```bash
$ reverse-api-engineer
> fetch all apple jobs from their careers page

# Browser opens, navigate and interact
# Close browser when done
# AI generates production-ready API client

# Scripts saved to: ./scripts/apple_jobs_api/
```

## 📖 Usage Modes

### Manual Mode

Full pipeline with manual browser interaction:

1. Start the CLI: `reverse-api-engineer`
2. Enter task description (e.g., "Fetch Apple job listings")
3. Optionally provide starting URL
4. Browse and interact with the website
5. Close browser when done
6. AI automatically generates the API client

**Output locations:**
- `~/.reverse-api/runs/scripts/{run_id}/` (permanent storage)
- `./scripts/{descriptive_name}/` (local copy with readable name)

### Engineer Mode

Re-run AI generation on a previous capture:
```bash
# Switch to engineer mode (Shift+Tab) and enter run_id
# Or use command line:
reverse-api-engineer engineer <run_id>
```

### Agent Mode

Fully automated browser interaction using AI agents:

1. Start CLI and switch to agent mode (Shift+Tab)
2. Enter task description (e.g., "Click on the first job listing")
3. Optionally provide starting URL
4. Agent automatically navigates and interacts
5. HAR captured automatically
6. API client generated automatically

**Agent Provider Options:**

- **auto** (default): Uses MCP-based browser automation with Claude Agent SDK & Opencode. Combines browser control and real-time reverse engineering in a single workflow. No additional installation required beyond the base package.
- **browser-use**: Uses browser-use library for browser automation. Requires installation with `[agent]` extra and browser-use from specific git commit (includes HAR recording support).
- **stagehand**: Uses Stagehand for browser automation with Computer Use models.

Change agent provider in `/settings` → "agent provider".

## 🔧 Configuration

Settings stored in `~/.reverse-api/config.json`:
```json
{
  "claude_code_model": "claude-sonnet-4-5",
  "opencode_provider": "anthropic",
  "opencode_model": "claude-sonnet-4-5",
  "sdk": "claude",
  "agent_provider": "auto",
  "browser_use_model": "bu-llm",
  "stagehand_model": "openai/computer-use-preview-2025-03-11",
  "output_dir": null
}
```

### Model Selection

Choose from Claude 4.5 models for API generation:
- **Sonnet 4.5** (default): Balanced performance and cost
- **Opus 4.5**: Maximum capability for complex APIs
- **Haiku 4.5**: Fastest and most economical

Change in `/settings` or via CLI:
```bash
reverse-api-engineer manual --model claude-sonnet-4-5
```

If you use Opencode, look at the [models](https://models.dev). Some are free like `opencode/grok-code`).

### Free Model Options with Antigravity

You can use free models via [Antigravity](https://github.com/NoeFabris/opencode-antigravity-auth) for API generation. See [available models](https://github.com/NoeFabris/opencode-antigravity-auth#available-models) for the full list.

**Setup:**
1. Follow the [Antigravity setup instructions](https://github.com/NoeFabris/opencode-antigravity-auth)
2. In `/settings`, configure:
   - **SDK**: Set to `opencode` (required for Antigravity)
   - **opencode provider**: Set to `google`
   - **opencode model**: Set to `gemini-3-flash` (or any available Antigravity model)

**Available Antigravity Models:**
- `gemini-3-pro-low` - Gemini 3 Pro Low (Antigravity)
- `gemini-3-pro-high` - Gemini 3 Pro High (Antigravity)
- `gemini-3-flash` - Gemini 3 Flash (Antigravity) (recommended)
- `claude-sonnet-4-5` - Claude Sonnet 4.5 (Antigravity)
- `claude-sonnet-4-5-thinking-low` - Claude Sonnet 4.5 Thinking Low (Antigravity)
- `claude-sonnet-4-5-thinking-medium` - Claude Sonnet 4.5 Thinking Medium (Antigravity)
- `claude-sonnet-4-5-thinking-high` - Claude Sonnet 4.5 Thinking High (Antigravity)
- `claude-opus-4-5-thinking-low` - Claude Opus 4.5 Thinking Low (Antigravity)
- `claude-opus-4-5-thinking-medium` - Claude Opus 4.5 Thinking Medium (Antigravity)
- `claude-opus-4-5-thinking-high` - Claude Opus 4.5 Thinking High (Antigravity)
- `gpt-oss-120b-medium` - GPT-OSS 120B Medium (Antigravity)

### Agent Configuration

Configure AI agents for autonomous browser automation.

**Agent Providers:**
- **auto** (default): MCP-based browser automation with real-time reverse engineering. Uses Claude Agent SDK with browser MCP tools. Combines browser control and API reverse engineering in a single unified workflow. Works with Claude SDK (default) or OpenCode SDK.
- **browser-use**: Supports Browser-Use LLM, OpenAI, and Google models. Requires installation with `[agent]` extra.
- **stagehand**: Supports OpenAI and Anthropic Computer Use models

**Agent Models:**

**Browser-Use Provider:**
- `bu-llm` (default) - Requires `BROWSER_USE_API_KEY`
- `openai/gpt-4`, `openai/gpt-3.5-turbo` - Requires `OPENAI_API_KEY`
- `google/gemini-pro`, `google/gemini-1.5-pro` - Requires `GOOGLE_API_KEY`

**Stagehand Provider (Computer Use only):**
- `openai/computer-use-preview-2025-03-11` - Requires `OPENAI_API_KEY`
- `anthropic/claude-sonnet-4-5-20250929` - Requires `ANTHROPIC_API_KEY`
- `anthropic/claude-haiku-4-5-20251001` - Requires `ANTHROPIC_API_KEY`
- `anthropic/claude-opus-4-5-20251101` - Requires `ANTHROPIC_API_KEY`

**Setting API Keys:**
```bash
export BROWSER_USE_API_KEY="your-api-key"  # For Browser-Use
export OPENAI_API_KEY="your-api-key"       # For OpenAI models
export ANTHROPIC_API_KEY="your-api-key"    # For Anthropic models
export GOOGLE_API_KEY="your-api-key"       # For Google models
```

Change in `/settings` → "agent provider" and "agent model"

### SDK Selection

- **Claude** (default): Direct integration with Anthropic's Claude API
- **OpenCode**: Uses OpenCode SDK (requires OpenCode running locally)

Change in `/settings` or edit `config.json` directly.

## 💻 CLI Commands

Use these slash commands while in the CLI:
- `/settings` - Configure model, agent, SDK, and output directory
- `/history` - View past runs with costs
- `/messages <run_id>` - View detailed message logs
- `/help` - Show all commands
- `/exit` - Quit

## 💡 Examples

### Example: Reverse Engineering a Job Board API

```bash
$ reverse-api-engineer
> fetch all apple jobs from their careers page

# Browser opens, you navigate and interact
# Close browser when done

# AI generates:
# - api_client.py (full API implementation)
# - README.md (documentation)
# - example_usage.py (usage examples)

# Scripts copied to: ./scripts/apple_jobs_api/
```

Generated `api_client.py` includes:
- Authentication handling
- Clean function interfaces
- Type hints and docstrings
- Error handling
- Production-ready code

## 🛠️ Development

### Setup
```bash
git clone https://github.com/kalil0321/reverse-api-engineer.git
cd reverse-api-engineer
uv sync
```

### Run locally
```bash
uv run reverse-api-engineer
```

### Build
```bash
./scripts/clean_build.sh
```

## 🗺️ Roadmap

- ✅ **Claude SDK** - Integration with Claude Code
- ✅ **OpenCode SDK** - Integration with OpenCode
- 🔄 **Codex SDK** - Codex SDK support

## 🔐 Requirements

- Python 3.11+
- Claude Code / OpenCode (for reverse engineering)
- Playwright browsers installed
- API key for agent mode (see [Agent Configuration](#agent-configuration))

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
