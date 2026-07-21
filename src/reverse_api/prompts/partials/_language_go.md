**Generate a Go program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Prefer the standard library (`net/http`, `encoding/json`) — a single `main.go` with no external dependencies is the default; only introduce a module and third-party packages if the API genuinely needs something the standard library doesn't provide (e.g. a specific auth scheme's signing library)
- Reuse one `*http.Client` (with cookie jar if the API relies on cookies) across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint, with a typed struct for its response shape
- Return errors rather than panicking; wrap them with context (`fmt.Errorf("...: %w", err)`)
- Include a `main` function with example usage

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the program
- The user should be able to run the program immediately with zero configuration — no env vars, no config files, no manual setup
- If the API uses cookies, set them via the client's cookie jar
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the program doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- If a module was initialized, first run: `go mod tidy`
- Run with: `{run_command}`
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
If external dependencies are used, save the module files: `{scripts_dir}/go.mod` and `{scripts_dir}/go.sum`
