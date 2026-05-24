<mission>
{prompt}
</mission>

<output_directory>
{scripts_dir}
</output_directory>


## Mandatory tooling

Reverse engineering relies on **`recording.har`** at **`{har_path}`**. You MUST drive browsing **only through the Vercel [agent-browser](https://github.com/vercel-labs/agent-browser) CLI** invoked from the shell (**Bash** / terminal MCP). Do **not** claim you used browser MCP tools — none are attached in this provider.

Warm up context once:

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
npx -y {agent_browser_npx_package} skills get core --full
```

{agent_browser_headed_hint}### Session + package

- Stable session env: **`AGENT_BROWSER_SESSION={agent_browser_session}`** before every invocation (isolates refs/HAR for this run).
- Package pin: **`npx -y {agent_browser_npx_package}`** (already verified by the host). Users can override via `RAE_AGENT_BROWSER_PACKAGE` or config `agent_browser_npx_package`.

### Cloud / remote browsers

If the operator hints at cloud backends (Bedrock AgentCore, Vercel Sandbox, …), run `skills list` then `skills get <name>` for the relevant skill bundle and prefer those flows—they stay version-matched to the CLI.
{agent_browser_notes_block}

## Workflow

Interaction model identical to upstream docs: **`snapshot`** for `@eN` refs → **`click` / `fill` / …** → **`snapshot`** after navigation.


### Phase 1: BROWSE

Use shell commands shaped like:

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
npx -y {agent_browser_npx_package} network har start
npx -y {agent_browser_npx_package} open https://example.com
npx -y {agent_browser_npx_package} snapshot -i --json
# … iterate …
```


### Phase 2: MONITOR

Use **`network requests --json`** (with filters when noisy) plus occasional snapshots.

### Phase 3: CAPTURE → `recording.har`

Before reverse engineering MUST flush HAR to the canonical file **exact path** below (create parent dirs if needed):

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
npx -y {agent_browser_npx_package} network har stop {har_path}
npx -y {agent_browser_npx_package} close
```

### Phase 4: REVERSE ENGINEER

Read **`{har_path}`** and emit code under **`{scripts_dir}`** per the system prompt.

**VPS tips:** first-time hosts run `npx -y {agent_browser_npx_package} install` (add `--with-deps` on Linux). `doctor` diagnoses missing Chrome or permissions.
