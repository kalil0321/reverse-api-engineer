<div align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-banner.svg" alt="Reverse API Engineer Banner">
  <br><br>
  <a href="https://pypi.org/project/reverse-api-engineer/"><img src="https://img.shields.io/pypi/v/reverse-api-engineer?style=flat-square&color=red" alt="PyPI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-red?style=flat-square" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-red?style=flat-square" alt="License"></a>
</div>

<p align="center">
CLI tool that captures browser traffic and automatically generates production-ready Python API clients.<br>
No more manual reverse engineering—just browse, capture, and get clean API code.
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/rae-autoscout.gif" alt="Agent Mode Demo">
  <br>
  <em>Agent mode</em>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-engineer.gif" alt="Manual Mode Demo">
  <br>
  <em>Manual mode</em>
</p>

## Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Modes](#-usage-modes)
  - [Manual Mode](#manual-mode)
  - [Engineer Mode](#engineer-mode)
  - [Agent Mode](#agent-mode)
  - [Collector Mode](#collector-mode)
- [Tags](#tags)
- [Configuration](#-configuration)
  - [Model Selection](#model-selection)
  - [Agent Configuration](#agent-configuration)
  - [SDK Selection](#sdk-selection)
- [CLI Commands](#-cli-commands)
- [Claude Code Plugin](#-claude-code-plugin)
- [Chrome Extension](#-chrome-extension)
- [Examples](#-examples)
- [Development](#-development)
- [Contributing](#-contributing)

## ✨ Features

- 🌐 **Browser Automation**: Built on Playwright with stealth mode for realistic browsing
- 🤖 **Autonomous Agent Mode**: Fully automated browser interaction using AI agents (auto mode with MCP, browser-use, stagehand)
- 📊 **HAR Recording**: Captures all network traffic in HTTP Archive format
- 🧠 **AI-Powered Generation**: Uses Claude 4.6 to analyze traffic and generate clean Python code
- 🔍 **Collector Mode**: Data collection with automatic JSON/CSV export
- 🔌 **Multi-SDK Support**: Native integration with Claude and OpenCode SDKs
- 💻 **Interactive CLI**: Minimalist terminal interface with mode cycling (Shift+Tab)
- 📦 **Production Ready**: Generated scripts include error handling, type hints, and documentation
- 💾 **Session History**: All runs saved locally with full message logs
- 💰 **Cost Tracking**: Detailed token usage and cost estimation with cache support
- 🏷️ **Tag System**: Powerful tags for fine-grained control (@record-only, @codegen, @docs, @id)

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

By default, Reverse API Engineer includes pricing data for the most common models (Claude 4.6, Gemini 3). For extended model coverage (100+ additional models including OpenAI GPT, Mistral, DeepSeek, and more), install with pricing extras:

```bash
# With uv
uv tool install 'reverse-api-engineer[pricing]'

# With pip
pip install 'reverse-api-engineer[pricing]'
```

This enables automatic pricing lookup via [LiteLLM](https://github.com/BerriAI/litellm) for models not in the built-in database. The pricing system uses a 3-tier fallback:
1. **Local pricing** (highest priority) - Built-in pricing for common models
2. **LiteLLM pricing** (if installed) - Extended coverage for 100+ models
3. **Default pricing** (ultimate fallback) - Uses Claude Sonnet 4.6 pricing

Cost tracking will always work, with or without the pricing extras installed.

## 🚀 Quick Start

Launch the interactive CLI:
```bash
reverse-api-engineer
```

The CLI has four modes (cycle with **Shift+Tab**):
- **manual**: Browser capture + AI generation
- **engineer**: Re-process existing captures
- **agent**: Autonomous AI browser agent (default: auto mode with MCP-based browser + real-time reverse engineering)
- **collector**: AI-powered web data collection (very minimalist version for now)

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

### Collector Mode

Web data collection using Claude Agent SDK:

1. Start CLI and switch to collector mode (Shift+Tab)
2. Enter a natural language prompt describing the data to collect (e.g., "Find 3 JS frameworks")
3. The agent uses WebFetch, WebSearch, and file tools to autonomously collect structured data
4. Data is automatically exported to JSON and CSV formats

**Output locations:**
- `~/.reverse-api/runs/collected/{folder_name}/` (permanent storage)
- `./collected/{folder_name}/` (local copy with readable name)

**Output files:**
- `items.json` - Collected data in JSON format
- `items.csv` - Collected data in CSV format
- `README.md` - Collection metadata and schema documentation

**Model Configuration:**
Collector mode uses the `collector_model` setting (default: `claude-sonnet-4-6`). This can be configured in `~/.reverse-api/config.json`.

Example workflow:
```bash
$ reverse-api-engineer
> Find 3 JS frameworks

# Agent autonomously searches and collects data
# Data saved to: ./collected/js_frameworks/
```

## 🏷️ Tags

Tags provide additional control and functionality within each mode:

### Manual/Agent Mode Tags

- **`@record-only`** - Record HAR file only, skip reverse engineering step
  - Example: `@record-only navigate checkout flow`
  - Useful when you want to capture traffic for later analysis

- **`@codegen`** - Record browser actions and generate Playwright automation script
  - Example: `@codegen navigate to google`
  - Captures clicks, fills, and navigations to create a reusable Playwright script

### Engineer Mode Tags

- **`@id <run_id>`** - Switch context to a specific run ID
  - Example: `@id abc123`
  - Loads a previous capture session for re-engineering

- **`@id <run_id> <prompt>`** - Run engineer on a specific run with instructions
  - Example: `@id abc123 extract user profile`
  - Re-processes a capture with new instructions

- **`@id <run_id> --fresh <prompt>`** - Start fresh (ignore previous scripts)
  - Example: `@id abc123 --fresh restart analysis`
  - Generates new code from scratch, ignoring previous implementations

- **`@docs`** - Generate API documentation (OpenAPI spec) for the latest run
  - Example: `@docs`
  - Creates OpenAPI specification from captured traffic

- **`@id <run_id> @docs`** - Generate API documentation for a specific run
  - Example: `@id abc123 @docs`
  - Creates OpenAPI specification for a specific capture session

## 🔧 Configuration

Settings stored in `~/.reverse-api/config.json`:
```json
{
  "agent_provider": "auto",
  "browser_use_model": "bu-llm",
  "claude_code_model": "claude-sonnet-4-6",
  "collector_model": "claude-sonnet-4-6",
  "opencode_model": "claude-sonnet-4-6",
  "opencode_provider": "anthropic",
  "output_dir": null,
  "output_language": "python",
  "real_time_sync": true,
  "sdk": "claude",
  "stagehand_model": "openai/computer-use-preview-2025-03-11"
}
```

### Model Selection

Choose from Claude 4.6 models for API generation:
- **Sonnet 4.6** (default): Balanced performance and cost
- **Opus 4.6**: Maximum capability for complex APIs
- **Haiku 4.5**: Fastest and most economical

Change in `/settings` or via CLI:
```bash
reverse-api-engineer manual --model claude-sonnet-4-6
```

If you use Opencode, look at the [models](https://models.dev).

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
- `anthropic/claude-sonnet-4-6-20260301` - Requires `ANTHROPIC_API_KEY`
- `anthropic/claude-haiku-4-5-20251001` - Requires `ANTHROPIC_API_KEY`
- `anthropic/claude-opus-4-6-20260301` - Requires `ANTHROPIC_API_KEY`

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

### Output Language

Control the programming language of generated API clients:
- **python** (default): Generate Python API clients
- **javascript**: Generate JavaScript API clients
- **typescript**: Generate TypeScript API clients

Change in `/settings` → "Output Language" or edit `config.json`:
```json
{
  "output_language": "typescript"
}
```

### Real-time Sync

Enable or disable real-time file synchronization during engineering sessions:
- **Enabled** (default): Files are synced to disk as they're generated
- **Disabled**: Files are written only at the end of the session

When enabled, you can see files appear in real-time as the AI generates them. This is useful for monitoring progress and debugging.

Change in `/settings` → "Real-time Sync" or edit `config.json`:
```json
{
  "real_time_sync": false
}
```

## 💻 CLI Commands

Use these slash commands while in the CLI:
- `/settings` - Configure model, agent, SDK, and output directory
- `/history` - View past runs with costs
- `/messages <run_id>` - View detailed message logs
- `/help` - Show all commands
- `/exit` - Quit

## 🔌 Claude Code Plugin

Install the plugin in [Claude Code](https://claude.com/claude-code):

```bash
claude # Open REPL
/plugin marketplace add kalil0321/reverse-api-engineer
/plugin install reverse-api-engineer@reverse-api-engineer
```

See [plugin documentation](plugins/reverse-api-engineer/README.md) for commands, agents, skills, and usage examples.

## 🌐 Chrome Extension

**⚠️ Work in Progress**

A Chrome extension that provides browser-native integration with reverse-api-engineer. The extension allows you to capture browser traffic directly from Chrome and interact with the reverse engineering process through a side panel interface.

**Features:**
- **HAR Capture**: Record network traffic using Chrome's Debugger API
- **Side Panel UI**: Interactive interface for managing captures and chatting with the AI agent
- **Native Host Integration**: Communicates with the reverse-api-engineer CLI tool

### Setup

**Prerequisites:**
- Node.js and npm
- Chrome browser
- reverse-api-engineer CLI installed (`uv tool install reverse-api-engineer`)
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)

**Steps:**

1. **Build the extension:**
   ```bash
   cd chrome-extension
   npm install
   npm run build
   ```

2. **Load in Chrome:**
   - Go to `chrome://extensions/`
   - Enable **Developer mode** (top-right toggle)
   - Click **Load unpacked** and select the `chrome-extension/dist` directory
   - **Copy the extension ID** (32-character string shown under the extension name)

3. **Install the native host** (connects the extension to the CLI):
   ```bash
   reverse-api-engineer install-host --extension-id YOUR_EXTENSION_ID
   ```

4. **macOS only** — run this once to approve Claude Code through Gatekeeper:
   ```bash
   claude --version
   ```
   If macOS shows a security popup, go to **System Settings > Privacy & Security** and click **Allow Anyway**, then run the command again.

**Development Workflow:**

- `npm run dev` — watch mode (auto-rebuild on changes, then reload in `chrome://extensions/`)
- `npm run build` — production build

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

### Run
```bash
uv run reverse-api-engineer
```

### Build
```bash
./scripts/clean_build.sh
```

## 🔐 Requirements

- Python 3.11+
- Claude Code / OpenCode (for reverse engineering)
- Playwright browsers installed
- API key for agent mode (see [Agent Configuration](#agent-configuration))

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
