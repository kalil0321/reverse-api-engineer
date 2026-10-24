**Generate a C program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- C has no HTTP client or JSON support in its standard library, unlike every other output language here — use `libcurl` for requests and vendor `cJSON` (a small, widely-used, permissively-licensed single-file JSON library) for JSON, rather than hand-rolling either from scratch
- Don't hand-write or reconstruct `cJSON.c`/`cJSON.h` from memory — fetch the exact, pinned upstream source instead, so the vendored copy is the real, complete library rather than a possibly incomplete or subtly wrong approximation:
  - `curl -fsSL -o {scripts_dir}/cJSON.c https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.c`
  - `curl -fsSL -o {scripts_dir}/cJSON.h https://raw.githubusercontent.com/DaveGamble/cJSON/v1.7.18/cJSON.h`
- **cJSON ownership: only ever delete a full parsed tree once, from its root — never delete individual fields you pulled out of it.** `cJSON_GetObjectItem`/`cJSON_GetObjectItemCaseSensitive` return a pointer *into* the existing tree, not an independent copy, and `cJSON_Delete` on any node walks and frees that node *and every sibling after it* in the same object/array (it follows the node's `next` pointer in a loop) — not just the one node you passed it. Pulling two sibling fields out of the same parsed object (e.g. `args` and `headers` from one response) and then calling `cJSON_Delete` on each separately frees the first field's siblings too, so the second `cJSON_Delete` call double-frees an already-freed pointer. This is a real, confirmed-live bug, not a theoretical one — it reliably produces `STATUS_HEAP_CORRUPTION` on Windows, and the equivalent memory corruption on Linux/macOS, which can silently "work" for a while before crashing somewhere unrelated instead of failing immediately the way Windows does. If you need to keep using individual fields after you're done with the parsed response, either delete the whole root exactly once when it's truly no longer needed (`cJSON_Delete(json)` — never its individual children), or call `cJSON_DetachItemFromObject`/`cJSON_DetachItemFromObjectCaseSensitive` first to properly unlink a field from its parent before deleting it standalone.
- `libcurl` itself is a system library this project can't fetch or vendor — if compilation fails because `curl/curl.h` isn't found, stop and report a clear error naming the missing prerequisite (e.g. "libcurl development headers not found — install libcurl4-openssl-dev (Debian/Ubuntu) or curl (Homebrew) and retry") rather than running a package manager yourself; installing system packages is a host change the user should make and confirm, not something to do silently inside an auto-authorized session
- Reuse one `CURL` handle across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint, with a small struct for its response shape
- Check every `libcurl`/allocation return value; don't ignore errors
- Keep the code warning-clean under `-Wall -Wextra` — no unused parameters or variables
- Include a `main` function with example usage

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, use libcurl's cookie engine (`CURLOPT_COOKIEFILE`, e.g. an in-memory/empty string) for persistence, populated only with runtime-provided values—not captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Unlike every other language here, this needs a compile step before it can run — a single `{run_command}` handles both
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the vendored JSON library to: `{scripts_dir}/cJSON.c` and `{scripts_dir}/cJSON.h`
