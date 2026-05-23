<mission>
{prompt}
</mission>

<output_directory>
{scripts_dir}
</output_directory>


## Workflow

Uses **Vercel [agent-browser](https://github.com/vercel-labs/agent-browser)** (Rust CLI invoked through MCP). Interaction model: take an accessibility **snapshot** to obtain `@eN` element refs, then **click**, **fill**, or **type** using those refs. Run `snapshot` again after navigations before assuming refs are valid.

### Phase 1: BROWSE
Use MCP tools (names mirror the Playwright MCP style for familiarity):

| Tool | Role |
|------|------|
| `browser_navigate` | Open URLs |
| `browser_snapshot` | Accessibility tree (`-i` by default); use refs like `@e1` |
| `browser_click`, `browser_fill`, `browser_type`, `browser_press_key` | Interactions |
| `browser_wait_for` | Wait by selector **or** milliseconds **or** visible text substring |
| `browser_scroll` | Scroll the page |
| `browser_evaluate` | Execute JavaScript in the page |
| `browser_take_screenshot` | Optional visual aid (prefer snapshots to save tokens and avoid large images) |

### Phase 2: MONITOR
Call `browser_network_requests` periodically. Watch for APIs, tokens, cookies, redirects, CORS quirks, and graph-style endpoints (`/graphql`, protobuf, etc.).

### Phase 3: CAPTURE
When you have explored enough traffic, call `browser_close` once to **flush HAR JSON** into the canonical path `{har_path}` and shut down Chromium. Omitting this prevents reverse engineering later.

### Phase 4: REVERSE ENGINEER
Analyze `recording.har` at `{har_path}` and emit the scripted client/source files under `{scripts_dir}` using the codegen rules from the system prompt.

**Headless VPS tips:** Provider default is usually headless. First-time setups run `npm install -g agent-browser && agent-browser install` so Chrome/Chromium for Testing downloads; Linux may need `agent-browser install --with-deps`. `agent-browser doctor` diagnoses environment issues.

