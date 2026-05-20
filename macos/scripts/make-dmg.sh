#!/usr/bin/env bash
# Wrap the signed rae.app into a distributable DMG with a /Applications
# symlink so the install gesture is the familiar "drag the app into
# Applications" pattern.
#
# Usage:
#   ./macos/scripts/make-dmg.sh                   # unsigned DMG
#   SIGNING_IDENTITY="…" ./macos/scripts/make-dmg.sh  # also signs the DMG
#
# Prerequisite: scripts/build-app.sh has produced build/rae.app, and
# optionally scripts/sign-and-notarize.sh has signed it.

set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"

APP_NAME=${APP_NAME:-rae}
APP_BUNDLE="build/$APP_NAME.app"
DMG_PATH="build/$APP_NAME.dmg"

if [ ! -d "$APP_BUNDLE" ]; then
    echo "error: $APP_BUNDLE not found — run scripts/build-app.sh first" >&2
    exit 1
fi

STAGING=$(mktemp -d)
# EXIT trap so an hdiutil failure (or anything else) doesn't leak the
# staging dir into /var/folders.
trap 'rm -rf "$STAGING"' EXIT

cp -R "$APP_BUNDLE" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG_PATH"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG_PATH"

if [ -n "${SIGNING_IDENTITY:-}" ]; then
    echo "→ codesign DMG with $SIGNING_IDENTITY"
    codesign --force --sign "$SIGNING_IDENTITY" --timestamp "$DMG_PATH"
fi

echo "✓ $DMG_PATH"
du -h "$DMG_PATH" 2>/dev/null | awk '{print "  size: " $1}'
