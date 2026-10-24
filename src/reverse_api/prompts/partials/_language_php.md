**Generate a PHP script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use the `curl` extension (`curl_init`/`curl_exec`) for requests and `json_encode`/`json_decode` for JSON — no Composer dependency is needed for either. `ext-json` is bundled with PHP core and always available, but `ext-curl` is bundled-but-optional and isn't guaranteed enabled on every install — if `curl_init` isn't defined, install it with whatever package manager is available (e.g. `apt-get install -y php-curl`) before retrying
- Reuse one cURL handle across requests rather than creating a new one per call
- Create a separate function for each distinct API endpoint
- Include type declarations on function signatures where they add clarity
- Include example usage at the bottom of the script

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, use the cURL cookie jar (`CURLOPT_COOKIEJAR`/`CURLOPT_COOKIEFILE`) for persistence, populated only with runtime-provided values—not captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
