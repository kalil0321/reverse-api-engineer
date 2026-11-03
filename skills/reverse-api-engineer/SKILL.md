---
name: reverse-api-engineer
description: Reverse engineer a website's private HTTP API into a typed, runnable client (Python, TypeScript, Go and 7 more) with the reverse-api-engineer CLI. A browser performs the task while rae reads the site's real network traffic, then a model writes the client. Use when the user wants to call a site programmatically and it has no public API, or the public one lacks what the browser can do. Skip it when an official API or SDK already covers the task.
---

# Reverse API Engineer

`reverse-api-engineer` (rae) drives a browser through a task, reads the requests the website makes, and turns them into an API client. The `chrome-mcp` provider works in the user's own Chrome, so their logins carry over. The `auto` provider (Playwright) uses a fresh browser and records a HAR file, which lets a run be re-engineered later without browsing again. Which one runs depends on the user's config and rae version; step 3 shows how to check.

This skill only supplies instructions. It drives the CLI through its scripted, JSON-emitting commands.

## 1. Check the install

```bash
reverse-api-engineer --version
```

If the command is missing, ask the user before installing anything, then:

```bash
uv tool install reverse-api-engineer   # or: pipx install reverse-api-engineer
```

Agent mode also needs Node.js 20.19+ on `PATH` (it launches browser tooling through `npx`). See [setup and configuration](references/setup.md) for model access and settings.

## 2. Reuse an earlier capture when one exists

```bash
reverse-api-engineer list --search "<site or task>" --json
```

`list` also includes failed and interrupted attempts, so check a candidate before reusing it:

```bash
reverse-api-engineer show <run_id> --json
```

- `file_count > 0` means a client was generated: verify it in step 5 and reuse it if it covers the task.
- `har_entries > 0` means the traffic was saved: you can improve the client with `engineer` (step 6) instead of browsing again. `chrome-mcp` runs keep no HAR (`mode: "chrome-mcp"`), so they cannot be re-engineered.
- Otherwise, capture again from step 3.

## 3. Preflight

```bash
reverse-api-engineer agent -p "<goal>" -u "<start url>" --dry-run
```

This validates the prompt, URL, config and environment without opening a browser. Fix every `error` check before running. A `warn` on the API key is fine when the SDK authenticates another way (for example a logged-in Claude Code).

`would_run.agent_provider` in the output is the browser the run will use. `chrome-mcp` means the user's own Chrome with their logins; `auto` and `agent-browser` start a fresh browser without them. When the task needs the user's login and the provider is not `chrome-mcp`, ask before switching it (see [sessions](references/sessions.md)).

The `codex` SDK reuses the local Codex CLI login. In the current RAE adapter, Codex agent capture requires `agent_provider: "auto"` so Playwright MCP records the HAR; it does not support `chrome-mcp` or `agent-browser` capture. `agent --dry-run` reports Codex login and browser-provider checks before opening a browser.

For `chrome-mcp`, the `chrome-mcp:auto-connect` check covers the connection to the user's Chrome:

- `ok`: Chrome is reachable. The user still has to accept Chrome's connection prompt when the run starts.
- `error`: it is not. If the site needs the user's login, ask them to open Chrome 146+ and enable remote debugging at `chrome://inspect/#remote-debugging` ("Enable auto-connect"), then run the preflight again. For public data, add `--headless`: rae then starts its own headless Chrome, without the user's sessions, and skips the check.
- `warn`: this rae version cannot test the connection. Ask the user to confirm Chrome is open with auto-connect enabled before a headed run, or use `--headless` for public data.

Write the goal as the data the user wants, not the clicks: "fetch open roles with title, location and team from the careers page, including pagination" works better than "click the jobs tab".

## 4. Capture and generate

A run takes several minutes, often longer than a shell tool's default timeout. Start it in the background from the outset, with your shell tool's background option when it has one, or with `&`:

```bash
reverse-api-engineer agent -p "<goal>" -u "<start url>" --json-stream > rae-run.ndjson 2> rae-run.log &
echo $! > rae-run.pid
```

`--json-stream` writes one NDJSON event per line and ends with a `{"event":"result",...}` line. The run is finished when that line appears in `rae-run.ndjson`, or when the process in `rae-run.pid` has exited (`kill -0 "$(cat rae-run.pid)"` fails). Check progress with `tail rae-run.log`. Never start a second capture while one is still running: it repeats the work and the cost.

- Without `--headless`, `chrome-mcp` opens its own tab in the user's Chrome and closes only that tab. Tell the user before starting, since it acts in their browser, and ask them to accept the connection prompt Chrome shows: if nobody accepts it, the run times out without a client.
- Add `--headless` for public sites, or on machines without a display.
- Add `-o <dir>` to write runs somewhere other than `~/.reverse-api/runs`.
- `--json` prints the same result as a single object at the end, with no progress. Use it only when the shell can wait for the whole run.
- See [sessions and blocked sites](references/sessions.md) for logged-in sites and providers.

The final result line has these fields:

| Field | Meaning |
|---|---|
| `status` | `ok` or `error` |
| `run_id` | Id for `engineer`, `run` and `show` |
| `script_path` | The generated client, inside `<runs>/scripts/<run_id>/` next to its `README.md` |
| `har_path` | The raw capture; `null` for `chrome-mcp` runs, which keep no HAR |
| `usage.total_cost_usd` | Model cost of the run; report it to the user |
| `error_kind` | Set on failure; see [troubleshooting](references/troubleshooting.md) |

Exit codes: `0` success, `1` capture or engineering failed, `2` misuse.

## 5. Verify the client

Read the generated client and its `README.md` before running anything: it is model-written code. Then run it:

```bash
reverse-api-engineer run <run_id> --ls                       # list generated files
reverse-api-engineer run <run_id> --file <client file> --json -- <script args>
```

`--auto-install` installs missing dependencies without prompting; ask the user first. Check that the output contains real data from the site, not just a 200 status.

## 6. Iterate on the same capture

```bash
reverse-api-engineer engineer <run_id> -p "add pagination and a typed Job model" --json
reverse-api-engineer engineer <run_id> --fresh -p "only the search endpoint" --json
```

Without `--fresh`, the prompt is layered on top of the original goal and the existing client. With `--fresh`, the client is regenerated from the HAR. `engineer` needs a HAR, so it only works on runs from the `auto` or `agent-browser` providers and from manual mode; on a `chrome-mcp` run it exits `2` with `error_kind: misuse`. For those, or when the capture itself is missing an endpoint, run `agent` again with a more specific goal.

## 7. Hand it over

The client lives at `script_path` from the result. When `real_time_sync` is on (the default), rae also copies it to `./scripts/<descriptive_name>/` in the working directory; copy it from `script_path` when that folder is missing. Adapt names and types to their codebase, and keep the generated `README.md` as usage notes. Tell the user which endpoints it wraps and how auth is handled (cookies, bearer token, CSRF), since captured credentials expire.

## Boundaries

- Only capture sites the user is allowed to access, and respect their terms and rate limits.
- Captures can contain cookies and tokens. Do not paste HAR contents into chats, issues or commits.
- When a site needs a human (captcha, 2FA, unusual login), ask the user to capture it in manual mode, then continue with `engineer`. See [sessions and blocked sites](references/sessions.md).
