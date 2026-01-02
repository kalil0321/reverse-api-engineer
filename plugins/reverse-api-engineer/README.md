# Reverse API Engineer Plugin

Claude Code plugin for reverse engineering web APIs by capturing browser traffic and generating production-ready Python API clients.

## Features

- **Manual Mode**: Control browser with HAR recording, then AI generates API client
- **Engineer Mode**: Re-analyze existing HAR captures to generate new clients
- **Agent Mode**: Autonomous browser navigation with automatic HAR capture and generation
- **Proactive Agent**: Automatically suggests reverse engineering when working with APIs

## Installation

### From Marketplace

```bash
claude # Open REPL
/plugin marketplace add kalil0321/reverse-api-engineer
/plugin install reverse-api-engineer@reverse-api-engineer
```

### Local Development

```bash
claude
/plugin marketplace add .
/plugin install reverse-api-engineer@reverse-api-engineer
```

## Prerequisites

- **Playwright MCP**: The plugin uses `rae-playwright-mcp` for browser control
- **Node.js**: Required for running the MCP server

The MCP server will be automatically installed when the plugin loads.

## Usage

### Commands

#### `/reverse-api-engineer:manual [task] [url]`

Launch a browser with HAR recording enabled. Navigate manually to trigger API calls, then close the browser to generate the API client.

**Examples:**
```
/reverse-api-engineer:manual "fetch Apple jobs" https://jobs.apple.com
/reverse-api-engineer:manual "scrape product data"
```

**Workflow:**
1. Browser opens with HAR recording
2. Navigate and interact with the website
3. Close browser when done
4. AI analyzes HAR and generates Python API client
5. Scripts saved to `./scripts/{task_name}/`

#### `/reverse-api-engineer:engineer <run_id|har_path>`

Re-run AI generation on a previous HAR capture.

**Examples:**
```
/reverse-api-engineer:engineer abc-123-def
/reverse-api-engineer:engineer ~/.reverse-api/runs/har/xyz-789/recording.har
/reverse-api-engineer:engineer ./captures/my-traffic.har
```

**Use cases:**
- Regenerate client with different approach
- Extract additional endpoints from same capture
- Improve existing client implementation

#### `/reverse-api-engineer:agent [task] [url]`

Fully autonomous browser navigation using Playwright MCP. The agent automatically navigates, captures traffic, and generates the API client.

**Examples:**
```
/reverse-api-engineer:agent "find all job listings" https://jobs.apple.com
/reverse-api-engineer:agent "search for products"
```

**Workflow:**
1. Agent autonomously navigates the website
2. HAR automatically captured
3. AI generates API client
4. Scripts saved to `./scripts/{task_name}/`

### Proactive Agent

The plugin includes a proactive agent that automatically triggers when you mention:
- "reverse engineer an API"
- "create API client for..."
- "automate interactions with..."
- "scrape data from..."
- "HAR file analysis"

**Example:**
```
You: "I need to automate fetching data from this website's API"
Agent: "I can help reverse engineer that API! I'll launch a browser with HAR recording..."
```

### Skill

The `reverse-engineering-api` skill provides guidance for:
- Browser capture with HAR recording
- HAR file analysis and filtering
- Authentication pattern detection
- API client code generation
- Testing and refinement

This skill automatically activates when you mention API reverse engineering tasks.

## Output Structure

### HAR Files

Captured traffic is saved to:
```
~/.reverse-api/runs/har/{run_id}/recording.har
```

### Generated Scripts

API clients are saved to:
```
./scripts/{task_name}/
├── api_client.py    # Main API client class
└── README.md        # Usage documentation
```

### Run History

All runs are tracked in:
```
~/.reverse-api/history.json
```

## How It Works

1. **Browser Capture**: Playwright launches with HAR recording enabled
2. **Traffic Analysis**: HAR file is analyzed to identify API endpoints, authentication, and patterns
3. **Code Generation**: AI generates production-ready Python code with:
   - Type hints
   - Error handling
   - Authentication support
   - Comprehensive documentation
4. **Testing**: Generated client is tested and refined

## Generated Code Quality

All generated API clients include:
- ✅ Type hints for all parameters and return values
- ✅ Docstrings for all public methods
- ✅ Error handling with proper exceptions
- ✅ Logging for debugging
- ✅ Session management for connection reuse
- ✅ Authentication handling (Bearer tokens, API keys, OAuth, etc.)
- ✅ Clean function interfaces
- ✅ Production-ready code

## Tips

- **Manual Mode**: Best when you need precise control over interactions
- **Agent Mode**: Best for simple, automatable tasks
- **Engineer Mode**: Best for iterating on existing captures
- **Multiple Captures**: Capture different user flows to discover all endpoints
- **Authentication**: Make sure to log in during capture to record auth patterns

## Examples

### Example 1: Job Board API

```
You: /reverse-api-engineer:manual "fetch all Apple jobs" https://jobs.apple.com

[Browser opens]
1. Navigate to jobs.apple.com
2. Search for jobs, browse listings
3. Close browser

[AI generates]
Scripts saved to: ./scripts/apple_jobs_api/
- api_client.py (with search_jobs(), get_job_details() methods)
- README.md (usage documentation)
```

### Example 2: Re-engineer Existing Capture

```
You: /reverse-api-engineer:engineer ~/.reverse-api/runs/abc-123/har/recording.har

[AI analyzes HAR]
Found endpoints:
- GET /api/v1/jobs/search
- GET /api/v1/jobs/{id}

[AI generates improved client]
Scripts saved to: ./scripts/jobs_api/
```

## Support

For issues, questions, or contributions, visit:
https://github.com/kalil0321/reverse-api-engineer

## License

MIT License - See LICENSE file for details
