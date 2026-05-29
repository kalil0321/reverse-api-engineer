<mission>
{prompt}
</mission>

<output_directory>
{scripts_dir}
</output_directory>


## Mandatory tooling

Reverse engineering relies on **`recording.har`** at **`{har_path}`**. You MUST drive browsing **only through the Vercel [agent-browser](https://github.com/vercel-labs/agent-browser) CLI** invoked from shell commands (terminal tools such as Bash). In this provider Reverse API Engineer does **not** register browser automation over MCP; the model uses the CLI exclusively.

### Host bootstrap (runs before the streaming session)

Reverse API Engineer prefers an **`agent-browser` binary already on PATH** and validates it with **`{agent_browser_shell} --help`**. When nothing is installed it runs **`npm install -g {agent_browser_npx_package}`** (pin from config or **`RAE_AGENT_BROWSER_PACKAGE`**), notifies you, then re-checks PATH. Only if npm/global installs cannot run does it transparently reuse **`{agent_browser_shell}`** wired through **`npx -y`** for that session—which can mean extra registry traffic on cold machines.

Warm up upstream context locally once you start:

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
{agent_browser_shell} skills get core --full
```

Treat **`skills get core --full`** as mandatory for default/local flows. Confirm it exits cleanly; if commands error, run **`skills list`** (per upstream), pick the documented bundle (`core` ships with upstream), or escalate with **`{agent_browser_shell} doctor`**.

{agent_browser_headed_hint}### Non-interactive agent-browser shell commands

The **Bash/terminal** running `agent-browser` is **not** visible to the human operator — only you drive it. Every **`{agent_browser_shell} …`** invocation must be **fully non-interactive**:

- **Never** run `agent-browser chat` as an open-ended REPL (no human is at that shell).
- **Never** pass upstream confirmation flags such as `--confirm-interactive` or `--confirm-actions` (they block on a human at the terminal or auto-deny).
- Use **subcommands only** (`open`, `snapshot`, `click`, `network har …`, `close`, …) and rely on **exit codes**, not stdin prompts in the shell.

For questions that truly need a human, use the **`AskUserQuestion`** tool (Reverse API Engineer renders that in the product UI). Do **not** expect the operator to answer inside the hidden Bash session.

Upstream JS dialogs (`alert` / `beforeunload`) are auto-handled by default unless an operator explicitly disables that upstream.

### Session + package

- Stable session env: **`AGENT_BROWSER_SESSION={agent_browser_session}`** before every invocation (isolates refs/HAR for this run).
- Invocation prefix (**exactly how the host resolved the CLI):** **`{agent_browser_shell}`**. Pin for installs is **`{agent_browser_npx_package}`** (config / **`RAE_AGENT_BROWSER_PACKAGE`**).

### Cloud / remote browsers

Upstream documents SaaS-hosted and remote backends. When the operator hints at cloud targets (Bedrock AgentCore, Vercel Sandbox, …), run **`skills list`** first so you fetch bundles that ship with **this CLI copy**, **`skills get <matching bundle>`**, then adopt workflow files inside—the flags stay paired with **`{agent_browser_shell}`**.
{agent_browser_notes_block}

## Workflow

Interaction model identical to upstream docs: **`snapshot`** for `@eN` refs → **`click` / `fill` / …** → **`snapshot`** after navigation.


### Phase 1: BROWSE

Start HAR recording **before** navigation and confirm it succeeded (abort if this fails — there is no capture without it):

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
{agent_browser_shell} network har start
# verify exit code 0; if non-zero, diagnose with `{agent_browser_shell} doctor` and stop
{agent_browser_shell} open https://example.com
{agent_browser_shell} snapshot -i --json
# … iterate …
```


### Phase 2: MONITOR

Use **`network requests --json`** (with filters when noisy) plus occasional snapshots.

### Phase 3: CAPTURE → `recording.har`

Before reverse engineering MUST flush HAR to the canonical file **exact path** below (create parent dirs if needed):

```bash
export AGENT_BROWSER_SESSION="{agent_browser_session}"
{agent_browser_shell} network har stop {har_path}
{agent_browser_shell} close
```

### Phase 4: REVERSE ENGINEER

Read **`{har_path}`** and emit code under **`{scripts_dir}`** per the system prompt.

**VPS tips:** first-time hosts run `{agent_browser_shell} install` (add `--with-deps` on Linux). `doctor` diagnoses missing Chrome or permissions.
