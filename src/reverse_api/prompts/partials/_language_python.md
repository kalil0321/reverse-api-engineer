**Generate a Python script** using `requests` that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Prefer `requests` with a `Session` for connection reuse and cookie persistence
- Create separate functions for each distinct API endpoint
- Include type hints, docstrings, and error handling where they add clarity
- Include a `main` section with example usage

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, use a `requests.Session` for persistence, populated only with runtime-provided values—not captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Bot detection:**
- If you encounter bot detection or anti-scraping measures, first try `httpcloak` to cloak your HTTP fingerprint (TLS, HTTP/2, header order)
- If `httpcloak` cannot bypass the protection, fall back to making fetch requests through the browser via Playwright CDP
- As a last resort, use full Playwright browser automation

**Testing:**
- After generating the code, test it: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`