<mission>
{prompt}
</mission>

<output_directory>
{scripts_dir}
</output_directory>


## Mandatory tooling

Reverse engineering relies on **`recording.har`** at **`{har_path}`**. You MUST drive browsing **only through the Vercel [agent-browser](https://github.com/vercel-labs/agent-browser) CLI** invoked from shell commands (terminal tools such as Bash). In this provider Reverse API Engineer does **not** register browser automation over MCP; the model uses the CLI exclusively.

### Host bootstrap (runs before the streaming session)

Reverse API Engineer probes **`npx -y {agent_browser_npx_package} --help`**. That command forces npm/`npx` to **resolve the pinned package**, which usually **downloads it into npm's cache when it never ran on this disk before**, and repeats quickly afterwards. Failures surfaced there block the session so you don't discover a broken toolchain mid-flight.

Warm up upstream context locally once you start:

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
npx -y {agent_browser_npx_package} skills get core --full
```

Treat **`skills get core --full`** as mandatory for default/local flows. Confirm it exits cleanly; if commands error, rerun with `skills list`, pick the documented bundle (`core` ships with upstream), or escalate with **`npx … doctor`**.

{agent_browser_headed_hint}### Session + package

- Stable session env: **`AGENT_BROWSER_SESSION={agent_browser_session}`** before every invocation (isolates refs/HAR for this run).
- Package pin: **`npx -y {agent_browser_npx_package}`**. Users can override via `RAE_AGENT_BROWSER_PACKAGE` or config `agent_browser_npx_package`.

### Cloud / remote browsers

Upstream documents SaaS-hosted and remote backends. When the operator hints at cloud targets (Bedrock AgentCore, Vercel Sandbox, …), run **`skills list`** first to see what bundles ship with this CLI revision, **`skills get <matching bundle>`**, then adopt the workflow packaged inside so flags stay lined up with **`npx -y {agent_browser_npx_package}`**.
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
