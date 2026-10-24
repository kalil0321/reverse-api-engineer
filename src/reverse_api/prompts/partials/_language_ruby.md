**Generate a Ruby script** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `net/http` and `json` for requests and JSON — both are part of Ruby's standard library, so no gem/Bundler dependency is needed
- Reuse persistent connections (`Net::HTTP.start` held open across calls) rather than opening a new connection per request — use a separate connection per distinct scheme/host/port, since one is bound to a single origin and captured traffic may span several (e.g. separate login, API, and upload hosts)
- Create a separate method for each distinct API endpoint
- Include example usage at the bottom of the script

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, store cookies set by the script's own responses and send them according to cookie scope/expiry rules; accept initial cookie values only through runtime inputs. Never copy captured HAR cookie values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the script to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
