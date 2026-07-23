#!/usr/bin/env bash
# Codesign + (optionally) notarize the rae.app bundle.
#
# Usage:
#   SIGNING_IDENTITY="Developer ID Application: …" \
#   NOTARY_PROFILE="rae-notary" \   # optional — skip notarization if unset
#     ./macos/scripts/sign-and-notarize.sh
#
# Prerequisites: scripts/build-app.sh has already produced build/rae.app.
#
# Apple deprecated `codesign --deep` for production signing because it can
# silently skip nested components or stamp the wrong entitlements on
# bundled helpers. So we walk the embedded Python runtime and sign every
# nested Mach-O explicitly (inside-out) before sealing the outer .app.

set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"

APP_NAME=${APP_NAME:-rae}
APP_BUNDLE="build/$APP_NAME.app"
ENTITLEMENTS="Resources/$APP_NAME.entitlements"

if [ ! -d "$APP_BUNDLE" ]; then
    echo "error: $APP_BUNDLE not found — run scripts/build-app.sh first" >&2
    exit 1
fi

if [ ! -f "$ENTITLEMENTS" ]; then
    echo "error: entitlements file not found at $ENTITLEMENTS" >&2
    exit 1
fi

if [ -z "${SIGNING_IDENTITY:-}" ]; then
    echo "error: SIGNING_IDENTITY is required (Developer ID Application: …)" >&2
    exit 1
fi

# The embedded runtime ships not just .dylib/.so but extensionless Mach-O
# executables too (python3 and console-script shims), all of which must be
# signed or notarization/gatekeeper rejects the bundle. Match by file type
# rather than extension so nothing is missed, and sign each before the outer
# .app is sealed.
EMBEDDED_RUNTIME="$APP_BUNDLE/Contents/Resources/agent-runtime"
if [ -d "$EMBEDDED_RUNTIME" ]; then
    echo "→ signing every Mach-O in the embedded agent runtime"
    while IFS= read -r -d '' f; do
        if file -b "$f" | grep -q "Mach-O"; then
            codesign --force --options runtime --timestamp \
                --sign "$SIGNING_IDENTITY" \
                "$f"
        fi
    done < <(find "$EMBEDDED_RUNTIME" -type f -print0)
fi

echo "→ codesign $APP_BUNDLE with $SIGNING_IDENTITY"
codesign --force --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGNING_IDENTITY" \
    "$APP_BUNDLE"

codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"

if [ -z "${NOTARY_PROFILE:-}" ]; then
    echo "✓ signed; skipping notarization (set NOTARY_PROFILE to enable)"
    exit 0
fi

ZIP_PATH="build/$APP_NAME.zip"
# Clean the artifact on any exit path so the CI/local build dir doesn't
# accumulate stale ZIPs alongside the DMG.
trap 'rm -f "$ZIP_PATH"' EXIT

rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$ZIP_PATH"

echo "→ notarytool submit ($NOTARY_PROFILE)"
xcrun notarytool submit "$ZIP_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait

echo "→ stapler staple"
xcrun stapler staple "$APP_BUNDLE"
xcrun stapler validate "$APP_BUNDLE"

echo "✓ signed + notarized $APP_BUNDLE"
