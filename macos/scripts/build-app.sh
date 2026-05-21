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
# 4. Embed a relocatable Python runtime with rae-agent installed
#
# `uv venv --relocatable` rewrites shebangs + activator so the venv can be
# moved to its final path. `uv pip install --python <interp>` targets the
# embedded interpreter so deps land inside the bundled venv's site-packages.
# ---------------------------------------------------------------------------
echo "→ creating embedded Python $PYTHON_VERSION runtime"
uv venv --relocatable --python "$PYTHON_VERSION" "$AGENT_RUNTIME"

echo "→ installing rae-agent into the embedded runtime"
uv pip install \
  --python "$AGENT_RUNTIME/bin/python3" \
  --quiet \
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
