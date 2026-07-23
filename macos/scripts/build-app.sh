#!/usr/bin/env bash
# Build a portable, universal (arm64 + x86_64) rae.app bundle with a
# self-contained Python runtime embedded under Contents/Resources/agent-runtime.
# Drop the result into /Applications and the app just runs — no user-side
# Python or pip needed.
#
# Requires:
#   - swift  (Xcode command line tools)
#   - uv     (https://docs.astral.sh/uv) — used to fetch a standalone Python
#            build and create a relocatable venv inside the .app
#
# Usage:
#   ./macos/scripts/build-app.sh
#   PYTHON_VERSION=3.12 ./macos/scripts/build-app.sh
#   CONFIG=debug ./macos/scripts/build-app.sh         # faster iteration
#   ARCH_FLAGS="--arch arm64" ./macos/scripts/build-app.sh  # single-arch
#
# Output: macos/build/rae.app

set -euo pipefail

APP_NAME=${APP_NAME:-rae}
CONFIG=${CONFIG:-release}
ARCH_FLAGS=${ARCH_FLAGS:-"--arch arm64 --arch x86_64"}
PYTHON_VERSION=${PYTHON_VERSION:-3.12}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/.." && pwd)"
OUT_DIR="$MACOS_DIR/build"
APP_BUNDLE="$OUT_DIR/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS_BIN="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
AGENT_RUNTIME="$RESOURCES/agent-runtime"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not found in PATH" >&2
    exit 1
  }
}

require swift
require uv

# ---------------------------------------------------------------------------
# 1. Scaffold the .app bundle layout
# ---------------------------------------------------------------------------
echo "→ cleaning $APP_BUNDLE"
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_BIN" "$RESOURCES"

# ---------------------------------------------------------------------------
# 2. Universal Swift build
#
# Two invocations: the first actually compiles, the second is `--show-bin-path`
# to recover the products dir (cheap, no rebuild — SwiftPM just prints the
# resolved path).
# ---------------------------------------------------------------------------
cd "$MACOS_DIR"
echo "→ swift build ($CONFIG, $ARCH_FLAGS)"
# shellcheck disable=SC2086
swift build -c "$CONFIG" --product "$APP_NAME" $ARCH_FLAGS

# shellcheck disable=SC2086
BIN_PATH=$(swift build -c "$CONFIG" --product "$APP_NAME" $ARCH_FLAGS --show-bin-path)
BUILT_BIN="$BIN_PATH/$APP_NAME"

if [ ! -f "$BUILT_BIN" ]; then
    echo "error: binary not found at $BUILT_BIN" >&2
    exit 1
fi

cp "$BUILT_BIN" "$MACOS_BIN/$APP_NAME"
chmod +x "$MACOS_BIN/$APP_NAME"

# ---------------------------------------------------------------------------
# 3. Static Info.plist + (optional) AppIcon + bundled SwiftPM resources
# ---------------------------------------------------------------------------
cp "$MACOS_DIR/Resources/Info.plist" "$CONTENTS/Info.plist"

if [ -f "$MACOS_DIR/Resources/AppIcon.icns" ]; then
    cp "$MACOS_DIR/Resources/AppIcon.icns" "$RESOURCES/AppIcon.icns"
fi

# SwiftPM compiles a resource bundle for any target that declares `resources:`
# — we ship Fraunces italic for the brand wordmark this way. The bundle
# lives next to the executable in the build products dir; copy it into the
# .app so Bundle.module finds it at runtime.
SPM_RESOURCE_BUNDLE="$BIN_PATH/ReverseAPI_ReverseAPI.bundle"
if [ -d "$SPM_RESOURCE_BUNDLE" ]; then
    cp -R "$SPM_RESOURCE_BUNDLE" "$RESOURCES/"
fi

# ---------------------------------------------------------------------------
# 4. Embed a self-contained Python runtime with rae-agent installed
#
# We embed a full python-build-standalone interpreter by *copy* rather than a
# `uv venv`. A venv is NOT self-contained: `uv venv --relocatable` still leaves
# bin/python3 as an absolute symlink into the build machine's uv-managed
# CPython and bakes an absolute `home` into pyvenv.cfg, so the interpreter
# dangles on every machine but the builder's (the app then silently falls back
# to /usr/bin/env python3 and the sidecar dies with ModuleNotFoundError).
#
# A python-build-standalone interpreter, by contrast, resolves its stdlib
# relative to the executable, so a plain directory copy works wherever the user
# drops rae.app. We install rae-agent into that interpreter's own site-packages
# (no venv) so everything moves together.
#
# NOTE: python-build-standalone is per-architecture; the embedded interpreter
# matches the build host's arch even though the Swift binary is universal. A
# universal2 embedded Python (lipo of two arch builds) is a follow-up.
#
# Drop any inherited HTTP proxy env vars before `uv` reaches out to fetch the
# interpreter. uv reads HTTP_PROXY / HTTPS_PROXY / ALL_PROXY (either case) from
# the environment — if rae was previously set as the system proxy and the shell
# still has them exported pointing at 127.0.0.1:<rae-port>, fetches fail with
# "Connection refused (os error 61)" the moment rae isn't running.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy NO_PROXY no_proxy
# ---------------------------------------------------------------------------
echo "→ fetching a standalone Python $PYTHON_VERSION"
PY_STAGE="$(mktemp -d)"
trap 'rm -rf "$PY_STAGE"' EXIT
UV_PYTHON_INSTALL_DIR="$PY_STAGE" uv python install "$PYTHON_VERSION"

# uv lays the download out as <stage>/cpython-<full-version>-<platform>/{bin,lib,…}
PY_SRC=$(echo "$PY_STAGE"/cpython-"$PYTHON_VERSION"*/)
if [ ! -x "$PY_SRC/bin/python3" ]; then
    echo "error: standalone interpreter not found under $PY_STAGE" >&2
    exit 1
fi

echo "→ embedding the interpreter under agent-runtime/"
mkdir -p "$AGENT_RUNTIME"
cp -R "$PY_SRC"/. "$AGENT_RUNTIME"/

# Guard against a regression: bin/python3 must not be an *absolute* symlink
# (that is exactly what made the old venv approach non-portable). A relative
# symlink into the runtime is fine — it moves with the bundle.
if [ -L "$AGENT_RUNTIME/bin/python3" ]; then
    target=$(readlink "$AGENT_RUNTIME/bin/python3")
    case "$target" in
        /*) echo "error: embedded python3 is an absolute symlink ($target) — not relocatable" >&2; exit 1 ;;
    esac
fi

echo "→ installing rae-agent into the embedded runtime"
# Use the embedded interpreter's own pip so packages land in its site-packages.
if ! "$AGENT_RUNTIME/bin/python3" -m pip --version >/dev/null 2>&1; then
    "$AGENT_RUNTIME/bin/python3" -m ensurepip --upgrade >/dev/null
fi
"$AGENT_RUNTIME/bin/python3" -m pip install \
  --quiet --disable-pip-version-check \
  "$REPO_ROOT/backend"

# Strip __pycache__ + bundled tests to shave a few MB from the DMG
find "$AGENT_RUNTIME" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$AGENT_RUNTIME" -type d -name "tests" -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
# 5. Smoke check — confirm rae_agent imports inside the embedded runtime
# ---------------------------------------------------------------------------
echo "→ smoke-testing embedded runtime"
"$AGENT_RUNTIME/bin/python3" -c "import rae_agent.server; print('rae_agent ok')"

echo ""
echo "✓ built $APP_BUNDLE"
du -sh "$APP_BUNDLE" 2>/dev/null | awk '{print "  size: " $1}'
