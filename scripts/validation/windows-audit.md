# Windows compatibility audit — issue #134

Inspected on 2026-09-23 against local commit
`dd2528546fffd9ef0a00d545f5fe93ac88055ca0` plus the working-tree fixes.

## Fixed

- Prompt templates and included partials now explicitly use UTF-8. Reading the
  Python partial as GBK reproduced the reported `0x94` error at byte 129 exactly.
- Configuration, history, messages, metadata and the Cursor dependency stamp
  have explicit UTF-8 encodings. Invalid UTF-8 configuration/history uses the
  existing corrupt-file recovery path. Previously generated JSON remains
  compatible because the writers escape non-ASCII characters by default.
- HAR readers use UTF-8 with optional BOM support. Previously a decode error
  could silently hide the domain or entry count.
- Node/npm diagnostic capture uses UTF-8 with replacement of invalid diagnostic
  bytes. Other external-tool diagnostics retain the native locale with tolerant
  decoding. Python client capture explicitly configures both the child pipes
  and the parent decoder for UTF-8, preserving Unicode stdout/stderr in JSON mode.
- Chrome profile discovery uses Windows LOCALAPPDATA and Linux Chrome/XDG
  configuration locations in addition to the existing macOS path. This fixes
  false "profile not found" fallback; it does not import profile cookies.
- Windows agent-browser probes and generated-client runners use the executable
  resolved by `shutil.which`, including `.cmd` launchers. No explicit shell was
  added. OpenCode and Cursor startup already resolved npx/npm this way.

## Verification

`tests/test_windows_compatibility.py` covers GBK and CP1252 text-file defaults,
all ten code-generation languages, recursive partials, Unicode persistence,
HAR files with/without BOM, corrupt-file recovery, platform-specific Chrome
directories, and `.cmd` resolution in interactive and JSON execution paths.

Two checks run actual subprocesses: UTF-8 diagnostics under a simulated GBK
parent, and `run --json` executing a real Python client in a fresh venv beneath
a path containing spaces and Chinese characters. The latter checks exact
Chinese, accented, em-dash and emoji output on stdout and stderr. It requires
no network, package installation or model credentials.

Local results: 1,004 passed, one Windows-only native `.cmd` probe skipped, five
coroutine warnings. The macOS FSEvents backend crashed during the ordinary full
suite; the successful full run substituted watchdog's PollingObserver only in
the test harness, with no production observer changes. Application state was
isolated by patching Path.home into a temporary directory, and uv used no-sync
mode plus a temporary cache. Ruff and mypy passed on application/test code,
excluding pre-existing local generated clients in `src/reverse_api/scripts`.

The existing CI matrix will run these tests on Windows/Python 3.11–3.13 when the
changes are pushed. No native Windows run or live model generation was performed
as part of this local audit.

## Remaining verification boundaries

- Chrome launch, capture finalization and Ctrl+C need a native Windows run.
- Managed OpenCode shutdown terminates its tracked launcher; descendant cleanup
  across npx/cmd/Node needs native verification. This audit did not change it.
- Prompt shell quoting already documents unsupported Windows paths containing
  dollar signs/backticks. cmd.exe and PowerShell have different expansion rules;
  the `.cmd` resolution fix is not a general shell-escaping guarantee.
- Non-Python client output retains the native decoder; replacing invalid bytes
  avoids crashes but cannot guarantee lossless output from arbitrary toolchains.

References: [Python subprocess behavior](https://docs.python.org/3/library/subprocess.html)
and [Chromium user-data locations](https://chromium.googlesource.com/chromium/src/+/main/docs/user_data_dir.md).
