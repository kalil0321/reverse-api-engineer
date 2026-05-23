# RAE bundled MCP for Vercel `agent-browser`

This directory hosts a minimal **stdio MCP server** (`server.mjs`) that proxies [Vercel agent-browser](https://github.com/vercel-labs/agent-browser) subprocesses so every supported SDK (`claude`, `opencode`, `copilot`, `cursor`) can drive the browser with the **same toolchain**.

## Setup (every machine / after `pip install` upgrades)

```bash
npm install --prefix "$(python -c 'from pathlib import Path; import reverse_api; print(Path(reverse_api.__file__).parent / \"agent_browser_mcp\")')"
npm install -g agent-browser
agent-browser install
# Linux VPS without desktop deps yet:
agent-browser install --with-deps
```

Smoke-test MCP wiring inside reverse-api-engineer:

```bash
reverse-api-engineer agent --dry-run --json | jq '.checks[] | select(.name=="agent-browser:MCP-bundle")'
```

## Why this exists

Agent-browser targets **AI workloads**: accessibility snapshots (`@eN`), batch command mode, guarded sessions, CLI-native HAR export (`network har start|stop`). That aligns with RAE’s need for repeatable **headless** capture paths on VPS/CI shells where Playwright-heavy stacks are inconvenient.

Third-party MCP bridges exist on npm, but none guaranteed RAE-compatible HAR filenames/paths plus prompt/tool naming parity — so we maintain a deliberately small in-tree adapter.

## Roadmap

| Stage | Goal |
|-------|------|
| **Now** | `agent_provider: "agent-browser"` + bundled MCP shim + mirrored tool names (`browser_navigate`, …) |
| **Next** | Optional publish to npm (`rae-agent-browser-mcp`) for faster cold starts (`npx` cache) outside the repo |
| **Later** | Optional extra tools (`batch`, annotated screenshots, tab routing) behind feature flags |

## Development

Requires Node ≥ 18 (`@modelcontextprotocol/sdk` pulls `zod`). After editing `server.mjs`, restart any agent sessions so MCP processes pick up changes.
