#!/usr/bin/env bash
# Build a portable rae.app bundle with a self-contained Python runtime.
#
# Output: <repo>/macos/dist/rae.app — drop into /Applications and it just runs.
# No user-side Python or pip required.
#
# Requires:
#   - swift (Xcode command line tools)
#   - uv  (https://docs.astral.sh/uv) — used to fetch a standalone Python build
#     and create a relocatable venv inside the .app
#
# Usage:
#   ./macos/scripts/build-app.sh              # builds release
#   PYTHON_VERSION=3.12 ./macos/scripts/build-app.sh   # pin the Python version

set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/.." && pwd)"
DIST_DIR="$MACOS_DIR/dist"
APP_DIR="$DIST_DIR/rae.app"
CONTENTS="$APP_DIR/Contents"
MACOS_BIN="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
AGENT_RUNTIME="$RESOURCES/agent-runtime"

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: '$1' not found in PATH" >&2; exit 1; }
}

require swift
require uv

# ---------------------------------------------------------------------------
# 1. Clean & scaffold the .app bundle layout
# ---------------------------------------------------------------------------
echo "→ cleaning $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$MACOS_BIN" "$RESOURCES"

# ---------------------------------------------------------------------------
# 2. Build the Swift release binary
# ---------------------------------------------------------------------------
echo "→ swift build (release)"
cd "$MACOS_DIR"
swift build -c release --product rae
cp "$MACOS_DIR/.build/release/rae" "$MACOS_BIN/rae"
chmod +x "$MACOS_BIN/rae"

# ---------------------------------------------------------------------------
# 3. Embed a relocatable Python runtime with rae-agent installed
#
#    uv venv --relocatable rewrites the activator + shebangs so the venv can
#    be moved (or shipped) to a different absolute path. uv pip install with
#    --python <interp> targets that specific interpreter so all deps land
#    inside the venv's site-packages, not the host's.
# ---------------------------------------------------------------------------
echo "→ creating embedded Python $PYTHON_VERSION runtime"
uv venv --relocatable --python "$PYTHON_VERSION" "$AGENT_RUNTIME"

echo "→ installing rae-agent into the embedded runtime"
uv pip install \
  --python "$AGENT_RUNTIME/bin/python3" \
  --quiet \
  "$REPO_ROOT/backend"

# Strip __pycache__ + tests to shave a few MB
find "$AGENT_RUNTIME" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$AGENT_RUNTIME" -type d -name "tests" -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
# 4. Info.plist — minimal so macOS treats the binary as a regular GUI app
#    (Dock icon, menu bar, keyboard focus, the works).
# ---------------------------------------------------------------------------
cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>app.rae.reverseapi</string>
    <key>CFBundleName</key>
    <string>rae</string>
    <key>CFBundleDisplayName</key>
    <string>rae</string>
    <key>CFBundleExecutable</key>
    <string>rae</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
</dict>
</plist>
PLIST

# ---------------------------------------------------------------------------
# 5. Smoke check — make sure rae_agent imports inside the embedded runtime
# ---------------------------------------------------------------------------
echo "→ smoke-testing embedded runtime"
"$AGENT_RUNTIME/bin/python3" -c "import rae_agent.server; print('rae_agent ok')"

echo ""
echo "✓ built $APP_DIR"
du -sh "$APP_DIR" 2>/dev/null | awk '{print "  size: " $1}'
