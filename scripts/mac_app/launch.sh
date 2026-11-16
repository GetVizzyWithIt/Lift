#!/bin/bash
# Lift's launcher: what runs when you double-click Lift.app.
# It starts the app quietly in the background, opens it in the browser, and exits.
# build_app.sh copies this into Lift.app and fills in the two paths below; edit
# this file, not the copy inside the app.
REPO="@REPO@"
PYTHON="@PYTHON@"
PORT=8765
URL="http://127.0.0.1:$PORT/"
IDLE_MINUTES=30   # the app quits after this long with no page open (and nothing transcribing)

LOG_DIR="$HOME/Library/Logs/Lift"
mkdir -p "$LOG_DIR"
exec >>"$LOG_DIR/lift.log" 2>&1   # everything goes to the log, never a Terminal window
echo "--- $(date '+%Y-%m-%d %H:%M:%S') Lift opened"

# Apple chip: if macOS started this under Rosetta, start again in native arm64 mode.
if [ "$(/usr/sbin/sysctl -in sysctl.proc_translated 2>/dev/null)" = "1" ]; then
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi

say_problem() {  # a small dialog, since there is no Terminal to read
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"OK\"} default button \"OK\" with title \"Lift\" with icon caution" >/dev/null
}
alive() { /usr/bin/curl -s -o /dev/null --max-time 2 "$URL"; }

# Already running (from Lift or from Terminal): open the page, unless the code was updated
# since it started. Then stop the old app (if it isn't mid-transcription) and start the new code.
if alive; then
  RUNNING="$(/usr/bin/curl -s --max-time 2 "${URL}api/version" | /usr/bin/sed -n 's/.*"code":"\([0-9a-f]*\)".*/\1/p')"
  CURRENT="$(/usr/bin/git -C "$REPO" rev-parse HEAD 2>/dev/null)"
  if [ -n "$CURRENT" ] && [ "$RUNNING" != "$CURRENT" ] && \
     [ "$(/usr/bin/curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST "${URL}api/quit")" = "200" ]; then
    echo "Running old code (${RUNNING:-unknown}); restarting at $CURRENT"
    for _ in $(seq 1 20); do alive || break; sleep 0.5; done
  fi
fi
if alive; then
  echo "Already running; opening $URL"
  /usr/bin/open "$URL"
  exit 0
fi

# Already starting (a second double-click): let the first one finish.
STARTING="$LOG_DIR/starting.pid"
if [ -f "$STARTING" ] && kill -0 "$(cat "$STARTING")" 2>/dev/null; then
  echo "Already starting; nothing to do."
  exit 0
fi

# macOS privacy: an app needs permission to read some folders (the Desktop, Documents).
if ! /bin/ls "$REPO" >/dev/null 2>&1; then
  echo "Cannot read $REPO (macOS privacy setting)."
  /usr/bin/osascript >/dev/null <<'EOF'
set msg to "Lift needs permission to open its folder." & return & return & "In System Settings, go to Privacy & Security, then Files and Folders, and turn on Desktop Folder under Lift. If Lift isn't listed there, add it under Full Disk Access instead. Then open Lift again."
set answer to display dialog msg buttons {"OK", "Open Settings"} default button "Open Settings" with title "Lift" with icon caution
if button returned of answer is "Open Settings" then do shell script "open 'x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders'"
EOF
  exit 1
fi
if [ ! -x "$PYTHON" ]; then
  echo "No Python environment at $PYTHON"
  say_problem "Lift can't find its Python environment. In Terminal, run: cd ~/dev/lift && bash setup_mac.sh"
  exit 1
fi

cd "$REPO" || exit 1
echo "Starting the app from $REPO"
/usr/bin/nohup "$PYTHON" -m lift app --no-browser --quit-when-idle "$IDLE_MINUTES" &
PID=$!
echo "$PID" > "$STARTING"
for _ in $(seq 1 120); do   # the first start can take a while (PyTorch loads)
  if alive; then
    echo "Running (pid $PID); opening $URL"
    rm -f "$STARTING"
    /usr/bin/open "$URL"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "The app stopped while starting; see the lines above."
    rm -f "$STARTING"
    say_problem "Lift couldn't start the app. The details are in ~/Library/Logs/Lift/lift.log."
    exit 1
  fi
  sleep 1
done
echo "Still not answering after 2 minutes."
rm -f "$STARTING"
say_problem "Lift is taking a long time to start. The details are in ~/Library/Logs/Lift/lift.log."
exit 1
