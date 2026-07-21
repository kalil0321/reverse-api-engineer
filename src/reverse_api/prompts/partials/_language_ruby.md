**Generate a Ruby script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `net/http` and `json` for requests and JSON — both are part of Ruby's standard library, so no gem/Bundler dependency is needed
- Reuse persistent connections (`Net::HTTP.start` held open across calls) rather than opening a new connection per request — use a separate connection per distinct scheme/host/port, since one is bound to a single origin and captured traffic may span several (e.g. separate login, API, and upload hosts)
- Create a separate method for each distinct API endpoint
- Include example usage at the bottom of the script

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the script
- The user should be able to run the script immediately with zero configuration — no env vars, no config files, no `bundle install`
- `net/http` has no built-in cookie jar, unlike some other languages' HTTP clients — if the API uses cookies, capture each `Set-Cookie` header's name/value and its domain, path, and secure attributes, and send back only the cookies matching a given request's origin and path in the `Cookie` header, rather than replaying every captured cookie on every request (a multi-origin trace can otherwise leak a session cookie to the wrong host or send an invalid header)
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the script doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
