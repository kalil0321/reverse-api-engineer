**Generate a JavaScript module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment:

- Use modern JavaScript (ES2022+) with ESM modules
- Prefer native `fetch` (Node.js 18+); use `axios` only if you need retries or interceptors
- Create separate async functions for each endpoint
- Add JSDoc comments and error handling where they add clarity
- Include example usage in a main section
- If using external deps, generate a `package.json` with `"type": "module"`

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, accept cookie values only through runtime inputs and use an appropriate session mechanism; never copy captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- If `package.json` was generated, first run: `npm install`
- Run with: `{run_command}`
- You have up to 5 attempts to fix issues
- If required secrets are unavailable, report the missing configuration rather than hardcoding credentials. Use placeholders or user-provided environment/runtime values when testing, and document any values the user must supply.

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
If external dependencies are used, save: `{scripts_dir}/package.json`