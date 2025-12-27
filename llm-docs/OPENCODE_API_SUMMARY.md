# OpenCode API Summary

## Overview
OpenCode API (version 0.0.3) is a REST API for interacting with the OpenCode AI coding assistant system. The API provides endpoints for managing sessions, projects, AI providers, file operations, and more.

## Core Concepts

### Sessions
Sessions are the primary unit of interaction - they represent conversations with the AI assistant where code changes, commands, and messages are tracked.

### Projects
Projects represent codebases/directories that OpenCode is working with.

### Providers
AI providers (like Anthropic, OpenAI, etc.) that power the AI assistant.

### Agents
Different AI agents with specific roles (build, plan, explore, etc.) that can be used for different tasks.

## API Endpoints

### Global Operations

#### `GET /global/health`
- **Purpose**: Check server health
- **Returns**: Health status and version information

#### `GET /global/event`
- **Purpose**: Subscribe to global events via Server-Sent Events (SSE)
- **Returns**: Event stream

#### `POST /global/dispose`
- **Purpose**: Clean up and dispose all OpenCode instances
- **Returns**: Success boolean

### Project Management

#### `GET /project`
- **Purpose**: List all projects that have been opened
- **Returns**: Array of project objects

#### `GET /project/current`
- **Purpose**: Get the currently active project
- **Returns**: Current project information

#### `PATCH /project/{projectID}`
- **Purpose**: Update project properties (name, icon, color)
- **Returns**: Updated project information

### PTY (Pseudo-Terminal) Sessions

#### `GET /pty`
- **Purpose**: List all active PTY sessions
- **Returns**: Array of PTY session objects

#### `POST /pty`
- **Purpose**: Create a new PTY session for running shell commands
- **Body**: command, args, cwd, title, env
- **Returns**: Created PTY session

#### `GET /pty/{ptyID}`
- **Purpose**: Get details about a specific PTY session
- **Returns**: PTY session information

#### `PUT /pty/{ptyID}`
- **Purpose**: Update PTY session properties (title, size)
- **Returns**: Updated PTY session

#### `DELETE /pty/{ptyID}`
- **Purpose**: Remove and terminate a PTY session
- **Returns**: Success boolean

### Session Management

#### `GET /session`
- **Purpose**: List all sessions
- **Returns**: Array of session objects

#### `POST /session`
- **Purpose**: Create a new session
- **Returns**: Created session

#### `GET /session/{sessionID}`
- **Purpose**: Get details about a specific session
- **Returns**: Session information

#### `DELETE /session/{sessionID}`
- **Purpose**: Delete a session
- **Returns**: Success boolean

#### `POST /session/{sessionID}/abort`
- **Purpose**: Abort an active session and stop ongoing AI processing
- **Returns**: Success boolean

### Session Sharing

#### `POST /session/{sessionID}/share`
- **Purpose**: Create a shareable link for a session
- **Query**: directory (optional)
- **Returns**: Updated session with share link

#### `DELETE /session/{sessionID}/share`
- **Purpose**: Remove shareable link, make session private
- **Returns**: Updated session

### Session Operations

#### `GET /session/{sessionID}/diff`
- **Purpose**: Get all file changes (diffs) made during the session
- **Query**: messageID (optional)
- **Returns**: Array of file diffs

#### `POST /session/{sessionID}/summarize`
- **Purpose**: Generate AI summary of the session
- **Body**: providerID, modelID, auto (optional)
- **Returns**: Success boolean

#### `GET /session/{sessionID}/message`
- **Purpose**: Retrieve all messages in a session
- **Query**: limit (optional)
- **Returns**: Array of messages with parts
- **Note**: Assistant messages include metadata like `providerID`, `modelID`, `cost`, `tokens`, `agent`, and `mode`

#### `POST /session/{sessionID}/message`
- **Purpose**: Send a new message to the session (streaming response)
- **Body**: parts (required), messageID, model, agent, tools, system, noReply
- **Returns**: Created message with AI response

#### `GET /session/{sessionID}/message/{messageID}`
- **Purpose**: Get a specific message from a session
- **Returns**: Message with parts

#### `POST /session/{sessionID}/prompt_async`
- **Purpose**: Send message asynchronously (non-blocking)
- **Body**: Same as POST /session/{sessionID}/message
- **Returns**: 204 No Content (prompt accepted)

#### `POST /session/{sessionID}/command`
- **Purpose**: Send a command to the session for execution
- **Body**: command, arguments, messageID, agent, model
- **Returns**: Created message with response

#### `POST /session/{sessionID}/shell`
- **Purpose**: Execute a shell command within session context
- **Body**: command, agent, model
- **Returns**: Assistant message

#### `POST /session/{sessionID}/revert`
- **Purpose**: Revert a specific message, undoing its effects
- **Body**: messageID (required), partID (optional)
- **Returns**: Updated session

#### `POST /session/{sessionID}/unrevert`
- **Purpose**: Restore all previously reverted messages
- **Returns**: Updated session

### Message Parts

#### `DELETE /session/{sessionID}/message/{messageID}/part/{partID}`
- **Purpose**: Delete a part from a message
- **Returns**: Success boolean

#### `PATCH /session/{sessionID}/message/{messageID}/part/{partID}`
- **Purpose**: Update a part in a message
- **Body**: Part object
- **Returns**: Updated part

### Permissions

#### `POST /session/{sessionID}/permissions/{permissionID}`
- **Purpose**: Respond to a permission request (approve/deny)
- **Body**: response ("once", "always", or "reject")
- **Returns**: Success boolean

### Commands

#### `GET /command`
- **Purpose**: List all available commands in OpenCode
- **Returns**: Array of command objects

### Provider Management

#### `GET /config/providers`
- **Purpose**: Get configured AI providers and default models
- **Returns**: Object with providers array and default mappings

#### `GET /provider`
- **Purpose**: List all available AI providers (available and connected)
- **Returns**: Object with all providers, default mappings, and connected list

#### `GET /provider/auth`
- **Purpose**: Get authentication methods for all providers
- **Returns**: Object mapping provider IDs to auth methods

#### `POST /provider/{providerID}/oauth/authorize`
- **Purpose**: Initiate OAuth authorization for a provider
- **Body**: method (auth method index)
- **Returns**: Authorization URL and method

#### `POST /provider/{providerID}/oauth/callback`
- **Purpose**: Handle OAuth callback after authorization
- **Body**: method, code (optional)
- **Returns**: Success boolean

### File Operations

#### `GET /file`
- **Purpose**: List files and directories in a path
- **Query**: path (required)
- **Returns**: Array of file/directory nodes

#### `GET /file/content`
- **Purpose**: Read file content
- **Query**: path (required)
- **Returns**: File content (text or base64)

#### `GET /file/status`
- **Purpose**: Get git status of all files
- **Returns**: Array of file status objects

### Search Operations

#### `GET /find`
- **Purpose**: Search for text patterns using ripgrep
- **Query**: pattern (required)
- **Returns**: Array of match results with line numbers

#### `GET /find/file`
- **Purpose**: Search for files by name/pattern
- **Query**: query (required), dirs ("true"/"false")
- **Returns**: Array of file paths

#### `GET /find/symbol`
- **Purpose**: Search for workspace symbols (functions, classes, variables) using LSP
- **Query**: query (required)
- **Returns**: Array of symbol objects

### Logging

#### `POST /log`
- **Purpose**: Write a log entry to server logs
- **Body**: service, level, message, extra (optional)
- **Returns**: Success boolean

### Agents

#### `GET /agent`
- **Purpose**: List all available AI agents
- **Returns**: Array of agent objects

### MCP (Model Context Protocol)

#### `GET /mcp`
- **Purpose**: Get status of all MCP servers
- **Returns**: Object mapping MCP server names to status

#### `POST /mcp`
- **Purpose**: Dynamically add a new MCP server
- **Body**: name, config (local or remote)
- **Returns**: Updated MCP status object

#### `POST /mcp/{name}/auth`
- **Purpose**: Start OAuth authentication flow for an MCP server
- **Returns**: Authorization URL

#### `DELETE /mcp/{name}/auth`
- **Purpose**: Remove OAuth credentials for an MCP server
- **Returns**: Success object

#### `POST /mcp/{name}/auth/callback`
- **Purpose**: Complete OAuth authentication using authorization code
- **Body**: code
- **Returns**: MCP status

## Common Query Parameters

Most endpoints accept an optional `directory` query parameter to specify the working directory/project.

## Data Models

### Session
- Contains conversation history, messages, and metadata
- Can be shared via shareable links
- Supports reverting/unreverting messages

### Message
- Contains multiple parts (text, file, agent, subtask)
- Has unique messageID
- Can be reverted

### AssistantMessage (Metadata)
Assistant messages contain rich metadata about AI interactions:
- **providerID**: The AI provider used (e.g., "anthropic", "openai")
- **modelID**: The specific model used (e.g., "claude-3-opus-20240229")
- **cost**: The cost of this message in dollars
- **tokens**: Token usage breakdown:
  - `input`: Input tokens used
  - `output`: Output tokens generated
  - `reasoning`: Reasoning tokens (for reasoning models)
  - `cache`: Cache tokens (read/write)
- **agent**: The agent used (e.g., "build", "plan", "explore")
- **mode**: The mode of operation
- **time**: Timestamps (created, completed)
- **path**: Working directory information (cwd, root)

### Part Types
- **TextPart**: Text content
- **FilePart**: File attachments with mime type and URL
- **AgentPart**: Agent-specific content
- **SubtaskPart**: Subtask definitions

### Provider
- Represents an AI provider (Anthropic, OpenAI, etc.)
- Contains model information, capabilities, costs
- Supports OAuth and API key authentication

### Agent
- Represents different AI agents (build, plan, explore, etc.)
- Has mode (subagent, primary, all)
- Configurable permissions, tools, and model settings

### MCP Status
- Can be: connected, disabled, failed, needs_auth, needs_client_registration
- Contains error information if failed

## Authentication

Providers support multiple authentication methods:
- **OAuth**: For providers that support OAuth (like GitHub Copilot)
- **API Key**: Standard API key authentication
- **Well-known**: Custom authentication method

## Error Responses

Standard error responses:
- **400 Bad Request**: Invalid request parameters
- **404 Not Found**: Resource not found

Both return error objects with descriptive messages.

## Streaming

Some endpoints support streaming responses:
- `/session/{sessionID}/message` (POST) - Streams AI responses
- `/global/event` (GET) - Server-sent events stream

## Getting Session Metadata

To retrieve metadata about a session (provider, model, cost, tokens):

1. **Get all messages**: `GET /session/{sessionID}/message`
2. **Filter for AssistantMessage objects**: Look for messages where `role === "assistant"`
3. **Extract metadata**: Each AssistantMessage contains:
   - `providerID`: Which provider was used
   - `modelID`: Which model was used
   - `cost`: Cost of that message
   - `tokens`: Token usage (input, output, reasoning, cache)
   - `agent`: Which agent was used
   - `mode`: Operation mode

**Example**: To calculate total session cost:
```javascript
const messages = await fetch(`/session/${sessionID}/message`).then(r => r.json());
const assistantMessages = messages.filter(m => m.info.role === 'assistant');
const totalCost = assistantMessages.reduce((sum, m) => sum + (m.info.cost || 0), 0);
const totalTokens = assistantMessages.reduce((acc, m) => ({
  input: acc.input + (m.info.tokens?.input || 0),
  output: acc.output + (m.info.tokens?.output || 0),
  reasoning: acc.reasoning + (m.info.tokens?.reasoning || 0)
}), { input: 0, output: 0, reasoning: 0 });
```

**Note**: There's no dedicated endpoint for aggregated session statistics - you need to calculate them from individual messages.

## Key Features

1. **Session Management**: Full CRUD operations for AI conversation sessions
2. **File Operations**: Read, list, and get git status of files
3. **Search**: Text search, file search, and symbol search via LSP
4. **Provider Management**: Configure and authenticate multiple AI providers
5. **Agent System**: Multiple specialized agents for different tasks
6. **MCP Integration**: Support for Model Context Protocol servers
7. **PTY Sessions**: Terminal emulation for shell command execution
8. **Sharing**: Create shareable links for sessions
9. **Revert/Unrevert**: Undo and restore message effects
10. **Permissions**: Fine-grained permission system for AI actions
11. **Cost Tracking**: Per-message cost and token usage tracking

