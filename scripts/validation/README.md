# Local live generation check

Run this manually with the Python environment containing the RAE package you
want to validate. Node.js/npm and a supported Playwright browser are required;
PowerShell 7+ is required for the PowerShell case.

```sh
python scripts/validation/generation_e2e.py --language python
python scripts/validation/generation_e2e.py --language powershell
```

The script starts a local website, asks OpenCode to capture its API and generate
a client, then runs that client through `reverse-api-engineer run`. It changes
the server response after generation and checks both the returned data and a new
HTTP request, so cached or hardcoded answers cannot pass.

Only `opencode/big-pickle` is allowed. Its advertised input/output prices must
both be zero; otherwise the check fails without selecting another model. Free
model availability and network access can still affect this optional test.

RAE configuration is redirected inside the test process and CLI subprocesses;
OpenCode uses separate XDG directories and the browser uses an isolated profile.
No existing user configuration is overwritten. The interpreter must be the one
from the installation under test (for example `/path/to/venv/bin/python`).

Logs, HAR capture, generated clients and OpenCode state are retained in the
printed temporary directory. Pass `--artifacts-dir /path/to/new-directory` to
choose a location; an existing directory is rejected. The local fixture server
stops when the test ends, so retained clients need a new matching server before
they can be replayed again.

This check does not run in GitHub Actions. Regular CI keeps the deterministic
unit, CLI startup and real PowerShell execution checks across all three OSes.
