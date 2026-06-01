#!/usr/bin/env bash
# Build macos/Resources/AppIcon.icns from the Fraunces brand asterisk.
#
# Runs three stages:
#   1. `render-icon.swift` produces a 1024×1024 master PNG (pink tile +
#      cream asterisk).
#   2. `sips` downsamples the master to every size the .icns format
#      wants (16, 32, 64, 128, 256, 512, 1024).
#   3. `iconutil` composes the .iconset folder into the final .icns
#      file at macos/Resources/AppIcon.icns. `scripts/build-app.sh`
#      already copies that file into the .app bundle if it exists, so
#      simply running this once is enough — no other wiring needed.
#
# Usage:
#     ./macos/scripts/build-icon.sh

set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"

FONT_PATH="$HERE/Sources/ReverseAPI/Resources/Fraunces-VariableFont.ttf"
WORK_DIR="$HERE/build/icon-work"
ICONSET="$WORK_DIR/AppIcon.iconset"
MASTER_PNG="$WORK_DIR/icon-1024.png"
OUTPUT_ICNS="$HERE/Resources/AppIcon.icns"

if [ ! -f "$FONT_PATH" ]; then
    echo "error: $FONT_PATH not found" >&2
    exit 1
fi

# Clean any leftover work from a previous run, then prepare fresh
# scratch directories. Trap cleans up everything on exit so failures
# don't litter the build tree.
rm -rf "$WORK_DIR"
mkdir -p "$ICONSET"
trap 'rm -rf "$WORK_DIR"' EXIT

# 1. Render the master 1024×1024 PNG via Swift.
echo "→ rendering master PNG (1024×1024)"
swift "$HERE/scripts/render-icon.swift" "$FONT_PATH" "$MASTER_PNG" 1024

# 2. Downsample to every size the .icns format wants. The naming
#    convention is fixed by Apple: <name>_<W>x<H>.png and the @2x
#    variants which are simply the next-size-up tile renamed.
echo "→ downsampling tiles"
declare -A iconset_files=(
    [16]="icon_16x16.png"
    [32]="icon_16x16@2x.png icon_32x32.png"
    [64]="icon_32x32@2x.png"
    [128]="icon_128x128.png"
    [256]="icon_128x128@2x.png icon_256x256.png"
    [512]="icon_256x256@2x.png icon_512x512.png"
    [1024]="icon_512x512@2x.png"
)
for size in 16 32 64 128 256 512 1024; do
    temp="$WORK_DIR/tile-${size}.png"
    sips -s format png -z "$size" "$size" "$MASTER_PNG" --out "$temp" >/dev/null
    for filename in ${iconset_files[$size]}; do
        cp "$temp" "$ICONSET/$filename"
    done
done

# 3. Compose into .icns.
mkdir -p "$HERE/Resources"
echo "→ composing .icns"
iconutil -c icns "$ICONSET" -o "$OUTPUT_ICNS"

echo ""
echo "✓ wrote $OUTPUT_ICNS"
du -h "$OUTPUT_ICNS" 2>/dev/null | awk '{print "  size: " $1}'
