#!/bin/bash
# Builds Lift.app, the double-click launcher for the app, in ~/Applications,
# and puts a shortcut to it on the Desktop.
#   bash scripts/mac_app/build_app.sh
# setup_mac.sh and the update command run this, so every update rebuilds it the
# same way. The .app itself is never committed: only this script, launch.sh,
# Info.plist, and the icon. If nothing changed, the app is left untouched, so
# macOS keeps any permission you gave it.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PYTHON="$HOME/Library/Application Support/saxscribe/python/bin/python"
DEST_DIR="${LIFT_APP_DIR:-$HOME/Applications}"
DEST="$DEST_DIR/Lift.app"

if [ ! -x "$PYTHON" ]; then
  echo "No Python environment at $PYTHON yet. Run: bash setup_mac.sh"
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/Lift.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$HERE/Info.plist" "$APP/Contents/Info.plist"

# The launch script, with this Mac's paths filled in.
script="$(cat "$HERE/launch.sh")"
script="${script//@REPO@/$REPO}"
script="${script//@PYTHON@/$PYTHON}"
printf '%s\n' "$script" > "$APP/Contents/MacOS/launch"
chmod 755 "$APP/Contents/MacOS/launch"

# The icon: every size macOS wants, made from the 1024 px PNG, packed into one .icns.
ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$HERE/AppIcon-1024.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$HERE/AppIcon-1024.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
# Fingerprint of the source PNG: the check below compares this instead of the .icns,
# which can differ byte for byte between builds of the same picture.
shasum -a 256 "$HERE/AppIcon-1024.png" | cut -d" " -f1 > "$APP/Contents/Resources/AppIcon.source-sha256"

if [ -d "$DEST" ] && diff -rq -x _CodeSignature -x AppIcon.icns "$APP" "$DEST" >/dev/null 2>&1; then
  echo "Lift.app is up to date: $DEST"
else
  # A local signature, so macOS can remember the permissions you give Lift.
  codesign --force --sign - "$APP" >/dev/null 2>&1 || echo "(Could not sign Lift.app; it still runs.)"
  mkdir -p "$DEST_DIR"
  rm -rf "$DEST"
  mv "$APP" "$DEST"
  touch "$DEST"   # so Finder and the Dock pick up the icon
  echo "Built Lift.app: $DEST"
fi

# A shortcut on the Desktop (a Finder alias), made once.
if [ ! -e "$HOME/Desktop/Lift" ] && [ ! -e "$HOME/Desktop/Lift.app" ]; then
  if osascript -e "tell application \"Finder\" to make alias file to (POSIX file \"$DEST\") at (path to desktop folder)" -e 'set name of result to "Lift"' >/dev/null 2>&1; then
    echo "Put a Lift shortcut on the Desktop."
  else
    ln -s "$DEST" "$HOME/Desktop/Lift.app" && echo "Put a Lift shortcut on the Desktop."
  fi
fi
echo "Double-click Lift to start the app. Its log is in ~/Library/Logs/Lift/lift.log."
