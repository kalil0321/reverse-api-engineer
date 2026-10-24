**Generate a PowerShell module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Target PowerShell 7+ (`pwsh`), not Windows PowerShell 5.1. Do not use Windows-only cmdlets or `System.Web` types that require .NET Framework
- Module file is a single `.psm1` with one or more advanced functions. Every public function:
  - Uses an approved verb (`Get-Verb` list) — `Get-`, `Invoke-`, `New-`, `Set-`, `Remove-`, etc. Never invent unapproved verbs like `Fetch-` or `Do-`
  - Has `[CmdletBinding()]` and typed `[Parameter()]` blocks (mandatory/optional, `[string]`, `[hashtable]`, `[switch]` etc. — no untyped params)
  - Is exported explicitly via `Export-ModuleMember -Function <Name>` at the bottom of the file. Do not use wildcard export (`Export-ModuleMember -Function *`)
- HTTP calls use `Invoke-RestMethod` (or `Invoke-WebRequest` only when raw headers/status codes are needed). Never shell out to `curl.exe` or `curl`
- Session/cookie handling: use `-SessionVariable`/`-WebSession` with `[Microsoft.PowerShell.Commands.WebRequestSession]`, not manual cookie header construction, unless the API requires a cookie value that PowerShell's cookie jar can't express
- Error handling: every network call wrapped in a `try`/`catch` block with `-ErrorAction Stop` on the call itself. Catch blocks should surface `$_.Exception.Message` and, where the failure is an HTTP error, the response body if retrievable, then rethrow with `throw`; never swallow the error or only call `Write-Error` and continue
- Use `[PSCustomObject]` for structured return values, not raw hashtables, so downstream `ConvertTo-Json` and property access behave predictably
- Prefer `ConvertTo-Json`/`ConvertFrom-Json` (built-in) over any third-party JSON handling
- No `Write-Host` for data output — use `Write-Output`/return values. `Write-Verbose`/`Write-Error` are fine for diagnostics
- Create a separate exported function for each distinct API endpoint

**Authentication & credentials:**
- Never put credentials, cookies, tokens, session IDs, or auth headers from captured traffic into source, examples, logs, or summaries.
- Read required secrets from environment variables or explicit runtime parameters and document the required setup; do not claim zero-configuration execution.
- If cookies are needed, use a `WebRequestSession` for persistence, populated only with runtime-provided values—not captured HAR values.
- Build Bearer/API-key headers from runtime-provided values, never recorded values.
- Implement refresh flows only when they use user-managed runtime credentials; never replay secrets extracted from traffic.

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
The example uses fixed demonstration arguments. CLI argument overrides are not supported; document how to edit the example or import the module and call its functions directly.

Save the example script to: `{scripts_dir}/Example.ps1`, which does:
```powershell
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '{client_filename}') -Force -ErrorAction Stop
# Invoke the exported function(s), using valid demonstration arguments.
# Serialize returned data with ConvertTo-Json -Depth 20.
# Let terminating errors propagate so pwsh exits nonzero on failure.
```
Do not generate a `.psd1` module manifest.
