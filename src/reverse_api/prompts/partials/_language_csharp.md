**Generate a C# program** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Use `System.Net.Http.HttpClient` and `System.Text.Json` — both are part of the .NET base class library (available since .NET Core 3.0), so no external NuGet package is needed for HTTP or JSON
- Create a minimal project file (`.csproj`) so the program can be run with a single command. Target `net8.0` by default, but this only works if that SDK/runtime is actually installed — if `dotnet run` reports the target framework isn't supported or the required runtime isn't installed, change `<TargetFramework>` to match what's actually there (check `dotnet --version`; a machine with only a newer SDK needs a higher target like `net10.0`, an older one a lower target like `net6.0`) and retry; both libraries above work fine on any of these versions, only the project file's stated target needs to match the installed SDK
- Create a separate method for each distinct API endpoint, with a small record or class for its response shape
- Reuse one `HttpClient` instance across requests rather than creating a new one per call
- Include a `Main` method with example usage

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, use an `HttpClientHandler` with a `CookieContainer` for persistence, populated only with runtime-provided values—not captured HAR values.
- Build Bearer/API-key headers (including `DefaultRequestHeaders`) from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Run: `{run_command}`
- If required secrets are unavailable, report the missing configuration rather than hardcoding credentials. Use placeholders or user-provided environment/runtime values when testing, and document any values the user must supply; fail clearly at startup when required values are missing.
- You have up to 5 attempts to fix issues

Save the program to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the project file to: `{scripts_dir}/ApiClient.csproj`
