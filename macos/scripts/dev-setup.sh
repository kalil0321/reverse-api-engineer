#!/usr/bin/env bash
# Prepare a dev environment so `swift run rae` can launch the agent sidecar
# without any manual Python setup.
#
# Creates <repo>/.venv (if missing), installs `rae-agent` from
# <repo>/backend in editable mode, and prints a summary.
#
# Requires uv (https://docs.astral.sh/uv).

set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV="$REPO_ROOT/.venv"

command -v uv >/dev/null 2>&1 || {
  echo "error: 'uv' not found — install from https://docs.astral.sh/uv" >&2
  exit 1
}

if [[ ! -x "$VENV/bin/python3" ]]; then
  echo "→ creating $VENV (python $PYTHON_VERSION)"
  uv venv --python "$PYTHON_VERSION" "$VENV"
fi

echo "→ installing rae-agent (editable) into $VENV"
uv pip install \
  --python "$VENV/bin/python3" \
  --quiet \
  -e "$REPO_ROOT/backend"

echo ""
"$VENV/bin/python3" -c "import rae_agent.server; print('✓ rae_agent importable')"
echo "→ ready: swift run rae will find $VENV"
