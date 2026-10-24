**Generate a TypeScript module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment:

- Use strict typing with interfaces for request/response types
- Use ESM modules and native `fetch` (Node.js 18+); use `axios` only if needed
- Create separate async functions for each endpoint
- Export a class-based API client with proper encapsulation
- Include example usage in a main section
- Generate a `package.json` with `"type": "module"`, `tsx`, `typescript`, `@types/node`

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, accept cookie values only through runtime inputs and use an appropriate session mechanism; never copy captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Run: `npm install && {run_command}`
- You have up to 5 attempts to fix issues

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the package.json to: `{scripts_dir}/package.json`