**Generate a C program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- C has no HTTP client or JSON support in its standard library, unlike every other output language here — use `libcurl` for requests and vendor `cJSON` (a small, widely-used, permissively-licensed single-file JSON library) for JSON, rather than hand-rolling either from scratch
- Don't hand-write or reconstruct `cJSON.c`/`cJSON.h` from memory — fetch the exact, pinned upstream source instead, so the vendored copy is the real, complete library rather than a possibly incomplete or subtly wrong approximation:
  - `curl -fsSL -o {scripts_dir}/cJSON.c https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.c`
  - `curl -fsSL -o {scripts_dir}/cJSON.h https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.h`
- `libcurl` itself is a system library this project can't fetch or vendor — if compilation fails because `curl/curl.h` isn't found, stop and report a clear error naming the missing prerequisite (e.g. "libcurl development headers not found — install libcurl4-openssl-dev (Debian/Ubuntu) or curl (Homebrew) and retry") rather than running a package manager yourself; installing system packages is a host change the user should make and confirm, not something to do silently inside an auto-authorized session
- Reuse one `CURL` handle across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint, with a small struct for its response shape
- Check every `libcurl`/allocation return value; don't ignore errors
- Keep the code warning-clean under `-Wall -Wextra` — no unused parameters or variables
- Include a `main` function with example usage

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the program
- The user should be able to run the program immediately with zero configuration — no env vars, no config files, no manual setup beyond what's generated
- If the API uses cookies, enable `libcurl`'s cookie engine (`CURLOPT_COOKIEFILE`, e.g. pointed at an in-memory/empty string to just turn it on) so cookies persist automatically across requests on the same handle
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the program doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Unlike every other language here, this needs a compile step before it can run — a single `{run_command}` handles both
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the vendored JSON library to: `{scripts_dir}/cJSON.c` and `{scripts_dir}/cJSON.h`
