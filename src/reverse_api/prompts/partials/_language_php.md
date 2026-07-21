**Generate a PHP script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use the `curl` extension (`curl_init`/`curl_exec`) for requests and `json_encode`/`json_decode` for JSON — both are part of core PHP (`ext-curl` and `ext-json`), so no Composer dependency is needed
- Reuse one cURL handle across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint
- Include type declarations on function signatures where they add clarity
- Include example usage at the bottom of the script

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the script
- The user should be able to run the script immediately with zero configuration — no env vars, no config files, no `composer install`
- If the API uses cookies, configure the cURL handle's cookie jar (`CURLOPT_COOKIEJAR`/`CURLOPT_COOKIEFILE`) so cookies persist automatically across requests
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the script doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
