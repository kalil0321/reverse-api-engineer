**Generate a C# program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `System.Net.Http.HttpClient` and `System.Text.Json` — both are part of the .NET base class library (available since .NET Core 3.0), so no external NuGet package is needed for HTTP or JSON
- Create a minimal project file (`.csproj`) so the program can be run with a single command. Target `net8.0` by default, but this only works if that SDK/runtime is actually installed — if `dotnet run` reports the target framework isn't supported or the required runtime isn't installed, change `<TargetFramework>` to match what's actually there (check `dotnet --version`; a machine with only a newer SDK needs a higher target like `net10.0`, an older one a lower target like `net6.0`) and retry; both libraries above work fine on any of these versions, only the project file's stated target needs to match the installed SDK
- Create a separate method for each distinct API endpoint, with a small record or class for its response shape
- Reuse one `HttpClient` instance across requests rather than creating a new one per call
- Include a `Main` method with example usage

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the program
- The user should be able to run the program immediately with zero configuration — no env vars, no config files, no manual setup beyond what's generated
- If the API uses cookies, construct the `HttpClient` with an `HttpClientHandler` that has a `CookieContainer` set, so cookies persist across requests
- If the API uses Bearer tokens or API keys, hardcode them in the request headers (e.g. via `DefaultRequestHeaders`)
- Handle auth refresh so the program doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the project file to: `{scripts_dir}/ApiClient.csproj`
