#!/bin/bash
# Builds Lift.app, the double-click launcher for the app, in ~/Applications,
# and puts a shortcut to it on the Desktop.
#   bash scripts/mac_app/build_app.sh
# setup_mac.sh and the update command run this, so every update rebuilds it the
# same way. The .app itself is never committed: only this script, launch.sh,
# and the icon.
#
# Lift is a small AppleScript app (made with macOS's osacompile) that runs
# launch.sh. A plain folder app whose program is a shell script never gets the
# "Lift would like to access your Desktop folder" question: macOS just refuses.
# An AppleScript app is a real app, so macOS asks once and remembers.
#
# If nothing changed since the last build, the app is left untouched, so macOS
# keeps the permission you gave it.
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

# The launch script, with this Mac's paths filled in.
script="$(cat "$HERE/launch.sh")"
script="${script//@REPO@/$REPO}"
script="${script//@PYTHON@/$PYTHON}"
printf '%s\n' "$script" > "$WORK/launch.sh"

# Fingerprint of everything that goes into the app. Same fingerprint = same app.
FINGERPRINT="$(cat "$WORK/launch.sh" "$HERE/AppIcon-1024.png" "$HERE/build_app.sh" | shasum -a 256 | cut -d' ' -f1)"
if [ -f "$DEST/Contents/Resources/lift-build.sha256" ] &&
   [ "$(cat "$DEST/Contents/Resources/lift-build.sha256")" = "$FINGERPRINT" ]; then
  echo "Lift.app is up to date: $DEST"
else
  APP="$WORK/Lift.app"
  # The app's whole program: run launch.sh from inside the app, quietly.
  osacompile -o "$APP" \
    -e 'do shell script "/bin/bash " & quoted form of (POSIX path of (path to resource "launch.sh")) & " >/dev/null 2>&1"'
  RES="$APP/Contents/Resources"
  cp "$WORK/launch.sh" "$RES/launch.sh"
  chmod 755 "$RES/launch.sh"

  # The icon: every size macOS wants, made from the 1024 px PNG, in place of the
  # standard AppleScript icon.
  ICONSET="$WORK/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$HERE/AppIcon-1024.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$HERE/AppIcon-1024.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$RES/applet.icns"
  rm -f "$RES/Assets.car"   # newer macOS keeps the AppleScript icon here too

  # Name, identity, and the sentence macOS shows when it asks for the Desktop.
  PLIST="$APP/Contents/Info.plist"
  plutil -replace CFBundleName -string "Lift" "$PLIST"
  plutil -replace CFBundleDisplayName -string "Lift" "$PLIST"
  plutil -replace CFBundleIdentifier -string "local.saxscribe.lift" "$PLIST"
  plutil -replace CFBundleShortVersionString -string "1.1" "$PLIST"
  plutil -replace CFBundleIconFile -string "applet" "$PLIST"
  plutil -remove CFBundleIconName "$PLIST" 2>/dev/null || true
  plutil -replace LSUIElement -bool YES "$PLIST"   # starts the app and exits: stays out of the Dock
  plutil -replace NSDesktopFolderUsageDescription \
    -string "Lift runs the transcription app from the saxscribe folder on your Desktop and saves sheet music there." "$PLIST"

  echo "$FINGERPRINT" > "$RES/lift-build.sha256"
  # A local signature, so macOS can remember the permission you give Lift.
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "(Could not sign Lift.app; it still runs.)"
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
