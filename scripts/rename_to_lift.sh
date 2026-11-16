#!/bin/bash
# Renames Saxscribe's folders on this Mac to Lift (ADR-0047) and leaves a link
# at every old name, so saved scripts, stored paths, and old commands keep working.
#
#   bash scripts/rename_to_lift.sh            dry run: shows every step, changes nothing
#   bash scripts/rename_to_lift.sh --apply    tests the app, moves and links, tests it again
#   bash scripts/rename_to_lift.sh --check    only the checks (after --apply)
#   bash scripts/rename_to_lift.sh --undo     puts every folder back where it was
#
# Nothing is copied or deleted: each folder is renamed in place (instant, even
# for the 350 GB runs folder) and a link is made at its old name. The undo list
# is saved before the first move. Reports go to ~/Library/Logs/Lift/rename/:
#   summary.txt      what happened, and whether every check passed
#   needs_a_look.txt anything the script could not decide (empty is good)
#   moves.tsv        the undo list
#   before.json / after.json   what the app showed before and after the move
set -uo pipefail

H="$HOME"
REPORT="$H/Library/Logs/Lift/rename"
PORT=8799   # a port of its own, so it never meets an app you have open

# old path | new path, in the order they move.
MOVES=(
  "$H/saxscribe-runs|$H/lift-runs"
  "$H/saxscribe-library|$H/lift-library"
  "$H/.cache/saxscribe|$H/.cache/lift"
  "$H/Library/Application Support/saxscribe|$H/Library/Application Support/Lift"
  "$H/Desktop/saxscribe|$H/dev/lift"
  "$H/Desktop/Saxscribe_Recent_Downloads|$H/Desktop/Lift_Recent_Downloads"
  "$H/lift-runs/catalog/saxscribe_catalog.db|$H/lift-runs/catalog/lift_catalog.db"
)
NEW_CODE="$H/dev/lift"
NEW_PY="$H/Library/Application Support/Lift/python/bin/python"
OLD_PY="$H/Library/Application Support/saxscribe/python/bin/python"

MODE="dry"
case "${1:-}" in
  "") ;;
  --apply) MODE="apply" ;;
  --check) MODE="check" ;;
  --undo) MODE="undo" ;;
  *) echo "Unknown option $1. Use --apply, --check, or --undo (or nothing for a dry run)."; exit 2 ;;
esac

# Run from a copy, under one caffeinate: the script's own folder moves, and the Mac
# must not sleep halfway.
if [ -z "${LIFT_RENAME_COPY:-}" ]; then
  COPY="$(mktemp "${TMPDIR:-/tmp}/rename_to_lift.XXXXXX")"
  cp "$0" "$COPY"
  export LIFT_RENAME_COPY="$COPY" LIFT_RENAME_FROM="$(cd "$(dirname "$0")/.." && pwd -P)"
  if [ "$MODE" = "dry" ]; then exec /bin/bash "$COPY" "$@"; fi
  if [ -x /usr/bin/caffeinate ]; then exec /usr/bin/caffeinate -i /bin/bash "$COPY" "$@"; fi
  exec /bin/bash "$COPY" "$@"
fi

mkdir -p "$REPORT"
LOG="$REPORT/run.log"
NEEDS="$REPORT/needs_a_look.txt"
SUMMARY="$REPORT/summary.txt"
: > "$NEEDS"
STEP=0
STEPS=1
FAILED=0
log() { echo "$*" | tee -a "$LOG"; }
look() { echo "- $*" >> "$NEEDS"; }
bar() {  # a live progress line on screen, one plain line per step in the log
  STEP=$((STEP + 1))
  local width=30 done=$((STEP * 30 / STEPS))
  local fill="" rest="" i
  for ((i = 0; i < done; i++)); do fill="$fill#"; done
  for ((i = done; i < width; i++)); do rest="$rest."; done
  printf '\r[%s%s] %2d/%d %-55s\n' "$fill" "$rest" "$STEP" "$STEPS" "$1"
  echo "$(date '+%H:%M:%S') step $STEP/$STEPS: $1" >> "$LOG"
}
ok() { log "   ok    $*"; }
bad() { log "   FAIL  $*"; FAILED=$((FAILED + 1)); look "$*"; }
code_dir() { if [ -d "$NEW_CODE" ]; then echo "$NEW_CODE"; else echo "$LIFT_RENAME_FROM"; fi; }
python_bin() { if [ -x "$NEW_PY" ]; then echo "$NEW_PY"; else echo "$OLD_PY"; fi; }

log ""
log "=== rename_to_lift $MODE, $(date '+%Y-%m-%d %H:%M:%S') ==="

# ---------------------------------------------------------------- jobs running?
running_jobs() {  # programs working on Lift's folders; viewers such as tail or less don't count
  /bin/ps -axo pid=,command= \
    | grep -v -E "^ *[0-9]+ +[^ ]*/?(tail|less|more|vi|vim|nano|cat|open|man|mdworker[^ ]*|mds[^ ]*) " \
    | grep -E "saxscribe|lift-runs|-m lift|run_keys|stem_contour|pdf_ledger|archive_fetch|archive_check|file_archive|key_batch|homr|review/server.py|match_check" \
    | grep -v -E "grep|rename_to_lift|LIFT_RENAME|lift app --no-browser --port $PORT --hold-jobs" || true
}

# ---------------------------------------------------------------- the app, seen from outside
SNAP_PY="$(mktemp "${TMPDIR:-/tmp}/lift_snapshot.XXXXXX")"
cat > "$SNAP_PY" <<'PY'
"""Ask the running app for every page and list it shows, and summarise the answers
so before and after can be compared. Stored paths in the catalog are counted too."""
import json, os, sqlite3, sys, urllib.request
from pathlib import Path

port, out = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"

def get(path, peek=False):
    """Status and body; peek reads only the first bytes (recordings, PDFs)."""
    try:
        with urllib.request.urlopen(base + path, timeout=120) as r:
            return r.status, (r.read(16) if peek else r.read())
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return f"error: {e.__class__.__name__}", b""

def shape(body):
    try:
        data = json.loads(body)
    except Exception:
        return {"bytes": len(body) > 0}
    if isinstance(data, list):
        return {"items": len(data)}
    if isinstance(data, dict):
        return {k: (len(v) if isinstance(v, (list, dict)) else type(v).__name__) for k, v in sorted(data.items())}
    return {"value": type(data).__name__}

snap = {"pages": {}, "songs": {}, "takes": {}, "catalog_paths": {}}
for p in ["/", "/library", "/results", "/api/library", "/api/results", "/api/review", "/api/takes"]:
    status, body = get(p)
    snap["pages"][p] = {"status": status, "shape": shape(body)}

status, body = get("/api/library")
songs = json.loads(body) if status == 200 else []
if isinstance(songs, dict):
    songs = songs.get("songs") or songs.get("items") or []
for s in songs:
    sid = s.get("id") if isinstance(s, dict) else None
    if not sid or s.get("kind") == "take":
        continue
    st, b = get(f"/api/library/{sid}")
    info = json.loads(b) if st == 200 else {}
    row = {"info": st, "pages": info.get("pages"), "pdf_error": bool(info.get("pdf_error"))}
    row["key"] = get(f"/api/library/{sid}/key")[0]
    for extra in ("pdf", "audio/record", "audio/stem"):
        row[extra] = get(f"/api/library/{sid}/{extra}", peek=True)[0]
    snap["songs"][sid] = row
    print(f"\r   songs checked: {len(snap['songs'])}/{len(songs)}", end="", file=sys.stderr, flush=True)
print("", file=sys.stderr)

st, b = get("/api/takes")
for t in (json.loads(b) if st == 200 else []):
    tid = t.get("id")
    if tid:
        snap["takes"][tid] = {"info": get(f"/api/takes/{tid}")[0], "pages": get(f"/api/takes/{tid}/pages")[0]}

# Stored paths in the catalog: how many still point at a real file.
home = Path.home()
for name in ("lift-runs", "saxscribe-runs"):
    db = home / name / "catalog" / "saxscribe_catalog.db"
    if db.exists():
        break
if db.exists():
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for table, col in [("audio_files", "path"), ("transcriptions", "path"), ("key_checks", "key_folder"), ("key_checks", "audio_path")]:
        try:
            vals = [v for (v,) in con.execute(f"select {col} from {table}") if v]
        except sqlite3.Error:
            continue
        found = sum(1 for v in vals if Path(os.path.expanduser(str(v))).exists())
        snap["catalog_paths"][f"{table}.{col}"] = {"stored": len(vals), "found": found}
Path(out).write_text(json.dumps(snap, indent=1, sort_keys=True))
print(f"   {len(snap['songs'])} songs, {len(snap['takes'])} takes, {sum(v['found'] for v in snap['catalog_paths'].values())} catalog paths found")
PY

APP_PID=""
trap 'stop_app' EXIT
trap 'echo; echo "Stopped by you. Undo list so far: $REPORT/moves.tsv (run --undo to put moves back)."; exit 130' INT TERM
start_app() {
  local dir py
  dir="$(code_dir)"; py="$(python_bin)"
  if /usr/bin/curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; then
    log "   something already answers on port $PORT; stopping it (a leftover from an interrupted run)"
    pkill -f "lift app --no-browser --port $PORT --hold-jobs" 2>/dev/null; sleep 2
    if /usr/bin/curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; then return 1; fi
  fi
  # --hold-jobs: waiting transcriptions stay waiting, and no take is changed.
  (cd "$dir" && exec "$py" -m lift app --no-browser --port "$PORT" --hold-jobs >> "$REPORT/app.log" 2>&1) &
  APP_PID=$!
  for _ in $(seq 1 180); do
    if /usr/bin/curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; then return 0; fi
    if ! kill -0 "$APP_PID" 2>/dev/null; then return 1; fi
    sleep 1
  done
  return 1
}
stop_app() {
  if [ -n "$APP_PID" ]; then
    pkill -P "$APP_PID" 2>/dev/null; kill "$APP_PID" 2>/dev/null; wait "$APP_PID" 2>/dev/null
  fi
  APP_PID=""
}
snapshot() {  # $1 = before or after
  rm -f "$REPORT/$1.json"
  if start_app; then
    "$(python_bin)" "$SNAP_PY" "$PORT" "$REPORT/$1.json" 2>&1 | tee -a "$LOG"
    if [ "${PIPESTATUS[0]}" -eq 0 ] && [ -f "$REPORT/$1.json" ]; then
      ok "app answered on port $PORT ($1 the move)"
    else
      bad "could not record what the app shows ($1 the move); see run.log"
    fi
  else
    bad "the app did not start ($1 the move); see $REPORT/app.log"
  fi
  stop_app
}

# ---------------------------------------------------------------- checks
check_all() {
  local dir py
  dir="$(code_dir)"; py="$(python_bin)"

  bar "Links at the old names lead to the new folders"
  for pair in "${MOVES[@]}"; do
    old="${pair%%|*}"; new="${pair##*|}"
    if [ -L "$old" ] && [ -e "$old" ] && [ "$(readlink "$old")" = "$new" ]; then
      ok "$old -> $(readlink "$old")"
    elif [ ! -e "$new" ] && [ ! -e "$old" ]; then
      ok "$old: not on this Mac, nothing to link"
    else
      bad "$old is not a working link to $new"
    fi
  done

  bar "Health check: python -m lift check and python -m saxscribe check"
  if (cd "$dir" && "$py" -m lift check >> "$LOG" 2>&1); then ok "python -m lift check"; else bad "python -m lift check failed (see run.log)"; fi
  if (cd "$dir" && "$py" -m saxscribe check >> "$LOG" 2>&1); then ok "python -m saxscribe check (old command)"; else bad "python -m saxscribe check failed"; fi

  bar "Full test suite (python -m pytest), about 5 to 10 minutes"
  if (cd "$dir" && "$py" -m pytest -q -p no:cacheprovider > "$REPORT/pytest.log" 2>&1); then
    ok "all tests passed: $(tail -1 "$REPORT/pytest.log")"
  else
    bad "the test suite did not pass: $(tail -1 "$REPORT/pytest.log") (details in pytest.log)"
  fi

  bar "Other Python environments start (page reader, tools, MuQ, rd)"
  for env in "$H"/lift-runs/.venv-* "$H"/saxscribe-runs/.venv-*; do
    [ -x "$env/bin/python" ] || continue
    case "$env" in "$H"/saxscribe-runs/*) [ -L "$H/saxscribe-runs" ] && continue ;; esac
    if "$env/bin/python" -c "import sys" 2>/dev/null; then ok "$env"; else bad "$env/bin/python does not start"; fi
  done
  for tool in pip; do
    if "$H/lift-runs/.venv-omr/bin/$tool" --version >/dev/null 2>&1; then ok ".venv-omr/bin/$tool (made under the old path) runs"; fi
  done

  bar "Saved Mac scripts still find their folders"
  for sub in catalog/_tools keys/transcribed/_tools review; do
    [ -d "$H/lift-runs/$sub" ] || continue   # not on this Mac
    if [ "$(ls "$H/saxscribe-runs/$sub" 2>/dev/null)" = "$(ls "$H/lift-runs/$sub")" ]; then
      ok "~/saxscribe-runs/$sub and ~/lift-runs/$sub show the same files"
    else
      bad "~/saxscribe-runs/$sub doesn't show the same files as ~/lift-runs/$sub"
    fi
  done
  if [ -e "$H/lift-runs/catalog/lift_catalog.db" ]; then
    if "$py" -c "import sqlite3,sys; [sqlite3.connect('file:'+p+'?mode=ro', uri=True).execute('select count(*) from sqlite_master').fetchone() for p in sys.argv[1:]]" \
         "$H/saxscribe-runs/catalog/saxscribe_catalog.db" "$H/lift-runs/catalog/lift_catalog.db" 2>>"$LOG"; then
      ok "the catalog opens under its old and new names"
    else
      bad "the catalog doesn't open under both its old and new names"
    fi
  fi

  bar "Lift.app points at the new code folder"
  if grep -q "$NEW_CODE" "$H/Applications/Lift.app/Contents/Resources/launch.sh" 2>/dev/null; then
    ok "Lift.app starts the app from $NEW_CODE"
  else
    bad "Lift.app does not point at $NEW_CODE yet (run: bash $NEW_CODE/scripts/mac_app/build_app.sh)"
  fi
}

compare() {
  bar "The app shows the same songs, takes, pages, and results as before"
  "$(python_bin)" - "$REPORT/before.json" "$REPORT/after.json" <<'PY' | tee -a "$LOG"
import json, sys
try:
    a, b = (json.load(open(p)) for p in sys.argv[1:3])
except Exception as e:
    print(f"   FAIL  could not compare: {e}"); sys.exit(1)
bad = 0
for part in ("pages", "songs", "takes", "catalog_paths"):
    for k in sorted(set(a[part]) | set(b[part])):
        if a[part].get(k) != b[part].get(k):
            bad += 1
            print(f"   FAIL  {part} {k}: before {a[part].get(k)}, after {b[part].get(k)}")
for k, v in b["catalog_paths"].items():
    if a["catalog_paths"].get(k) == v:
        print(f"   ok    catalog {k}: {v['found']} of {v['stored']} stored paths found, same as before")
print(f"   {'ok   ' if not bad else 'FAIL '} {len(b['songs'])} songs, {len(b['takes'])} takes, {len(b['pages'])} pages compared; {bad} differences")
sys.exit(1 if bad else 0)
PY
  if [ "${PIPESTATUS[0]}" -ne 0 ]; then FAILED=$((FAILED + 1)); look "the app showed something different after the move (see run.log)"; fi
}

scan_leftovers() {
  bar "Other places that still say saxscribe"
  for f in "$H/.zshrc" "$H/.zprofile" "$H/.bash_profile" "$H/.bashrc" "$H/.profile"; do
    [ -f "$f" ] && grep -n -i "saxscribe" "$f" | sed "s|^|$f:|" | while read -r line; do look "shell setting mentions the old name (still works through the links): $line"; done
  done
  grep -l -i saxscribe "$H"/Library/LaunchAgents/*.plist 2>/dev/null | while read -r f; do look "scheduled job mentions the old name: $f"; done
  crontab -l 2>/dev/null | grep -i saxscribe | while read -r line; do look "crontab line mentions the old name: $line"; done
  find "$H" -maxdepth 2 -iname "*saxscribe*" -not -path "$H/Library/*" 2>/dev/null | while read -r f; do
    known=0
    for pair in "${MOVES[@]}"; do [ "$f" = "${pair%%|*}" ] && known=1; done
    [ "$known" = 0 ] && look "a folder or file still named saxscribe that this script doesn't move: $f"
  done
  # The app's sheet-music copies used to go to ~/Desktop/Saxscribe, which macOS treats as
  # the same folder as the code. Anything the code doesn't track there is listed.
  local dir; dir="$(code_dir)"
  (cd "$dir" && git status --porcelain --untracked-files=normal 2>/dev/null | grep '^??' | cut -c4-) | while read -r f; do
    look "in the code folder but not part of the code (maybe an old sheet-music copy): $dir/$f"
  done
  log "   (anything found is in needs_a_look.txt)"
}

# ---------------------------------------------------------------- dry run
if [ "$MODE" = "dry" ]; then
  STEPS=3
  bar "Jobs that would block the move"
  jobs_now="$(running_jobs)"
  if [ -n "$jobs_now" ]; then log "   These are running now; --apply will wait for them to finish:"; log "$jobs_now"; else ok "nothing running"; fi
  bar "Moves --apply would make (old name stays as a link)"
  for pair in "${MOVES[@]}"; do
    old="${pair%%|*}"; new="${pair##*|}"
    if [ -L "$old" ]; then log "   done  $old already links to $(readlink "$old")"
    elif [ -e "$new" ]; then log "   STOP  $new already exists; --apply will stop here"
    elif [ -e "$old" ] || [ "$old" = "$H/lift-runs/catalog/saxscribe_catalog.db" ]; then log "   move  $old  ->  $new"
    else log "   skip  $old (not on this Mac)"; fi
  done
  log "   then: point the code's .venv at the new Python folder, rebuild Lift.app, run every check"
  scan_leftovers
  log ""
  log "Dry run only; nothing changed. When it looks right, run: bash scripts/rename_to_lift.sh --apply"
  log "Needs a look: $NEEDS ($(wc -l < "$NEEDS" | tr -d ' ') lines)"
  exit 0
fi

# ---------------------------------------------------------------- undo
if [ "$MODE" = "undo" ]; then
  [ -f "$REPORT/moves.tsv" ] || { log "No undo list at $REPORT/moves.tsv; nothing to undo."; exit 1; }
  jobs_now="$(running_jobs)"
  if [ -n "$jobs_now" ]; then log "These are running; stop them first:"; log "$jobs_now"; exit 1; fi
  STEPS=$(wc -l < "$REPORT/moves.tsv" | tr -d ' ')
  REVERSED="$(mktemp "${TMPDIR:-/tmp}/lift_undo.XXXXXX")"; LEFT="$REVERSED.left"
  sed '1!G;h;$!d' "$REPORT/moves.tsv" > "$REVERSED"; : > "$LEFT"
  while IFS=$'\t' read -r old new; do   # not a pipe, so failures are counted
    bar "Put back $old"
    if [ -e "$new" ] && { [ -L "$old" ] || [ ! -e "$old" ]; }; then
      if { [ ! -L "$old" ] || rm "$old"; } && mv "$new" "$old"; then ok "$new -> $old"
      else bad "could not put back $old"; printf '%s\t%s\n' "$old" "$new" >> "$LEFT"; fi
    else
      bad "could not put back $old ($new is missing, or $old is a real folder now)"; printf '%s\t%s\n' "$old" "$new" >> "$LEFT"
    fi
  done < "$REVERSED"
  if [ -L "$H/Desktop/saxscribe/.venv" ]; then ln -sfn "$H/Library/Application Support/saxscribe/python" "$H/Desktop/saxscribe/.venv"; fi
  if [ "$FAILED" = 0 ]; then
    mv "$REPORT/moves.tsv" "$REPORT/moves.undone-$(date +%Y%m%d-%H%M%S).tsv"
    log "Undo finished. Rebuild the launcher with: cd ~/Desktop/saxscribe && bash scripts/mac_app/build_app.sh"
    exit 0
  fi
  sed '1!G;h;$!d' "$LEFT" > "$REPORT/moves.tsv"   # only what is still moved, in the original order
  log "$FAILED could not be put back; they stay in $REPORT/moves.tsv for another --undo. See needs_a_look.txt."
  exit 1
fi

# ---------------------------------------------------------------- check only
if [ "$MODE" = "check" ]; then
  STEPS=7
  check_all
  scan_leftovers
  { echo "Check $(date '+%Y-%m-%d %H:%M'): $FAILED failed checks."; echo "Needs a look: $NEEDS"; } | tee "$SUMMARY"
  exit $([ "$FAILED" = 0 ] && echo 0 || echo 1)
fi

# ---------------------------------------------------------------- apply
STEPS=$((3 + ${#MOVES[@]} + 3 + 8))
bar "Waiting until no jobs are running"
shown=""
while true; do
  jobs_now="$(running_jobs)"
  [ -z "$jobs_now" ] && break
  if [ -z "$shown" ]; then
    log "   Waiting for these to finish (nothing has moved; Ctrl-C stops safely):"; log "$jobs_now"; shown=1
  fi
  printf '\r   still running, checking again every 60 s (%s)   ' "$(date '+%H:%M')"
  sleep 60
done
ok "nothing running"

bar "Stopping before anything moves if a new name is already taken"
rm -f "$REPORT/before.json" "$REPORT/after.json"
for pair in "${MOVES[@]}"; do
  old="${pair%%|*}"; new="${pair##*|}"
  [ -L "$old" ] && continue   # moved on an earlier run
  case "$new" in   # the catalog's new name, as it is before ~/lift-runs exists
    "$H/lift-runs/"*) alt="$H/saxscribe-runs/${new#"$H/lift-runs/"}" ;;
    *) alt="$new" ;;
  esac
  for n in "$new" "$alt"; do
    if [ -e "$n" ]; then log "   STOP  $n already exists. Nothing was moved."; exit 1; fi
  done
done
ok "all new names are free"
CAT="$H/saxscribe-runs/catalog/saxscribe_catalog.db"
if [ -f "$CAT" ] && [ ! -L "$CAT" ]; then
  # Fold any write-ahead log into the catalog, so nothing is left in a -wal file under the old name.
  "$(python_bin)" -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()" "$CAT" 2>>"$LOG"
  for side in -wal -shm -journal; do
    if [ -s "$CAT$side" ]; then log "   STOP  $CAT$side still holds changes (is a catalog script running?). Nothing was moved."; exit 1; fi
    rm -f "$CAT$side"
  done
  ok "catalog has no pending changes"
fi

bar "What the app shows before the move"
snapshot before
if [ ! -f "$REPORT/before.json" ]; then log "   STOP  no picture of the app before the move, so nothing was moved."; exit 1; fi

touch "$REPORT/moves.tsv"
for pair in "${MOVES[@]}"; do
  old="${pair%%|*}"; new="${pair##*|}"
  bar "Move $(basename "$old")"
  if [ -L "$old" ]; then ok "already moved: $old -> $(readlink "$old")"; continue; fi
  if [ ! -e "$old" ]; then ok "not on this Mac: $old"; continue; fi
  if [ -e "$new" ]; then bad "$new appeared after the check; stopping here. Run --undo to put back what moved."; exit 1; fi
  mkdir -p "$(dirname "$new")"
  if ! mv "$old" "$new"; then bad "could not move $old; stopping here. Run --undo to put back what moved."; exit 1; fi
  printf '%s\t%s\n' "$old" "$new" >> "$REPORT/moves.tsv"   # written before the link, so undo knows of it
  if ln -s "$new" "$old"; then
    ok "$old -> $new (link left at the old name)"
  else
    bad "moved $old but could not leave a link there; stopping here. Run --undo to put it back."
    exit 1
  fi
done

bar "Point the code's .venv at the new Python folder"
if [ -L "$NEW_CODE/.venv" ] && [ -d "$H/Library/Application Support/Lift/python" ]; then
  ln -sfn "$H/Library/Application Support/Lift/python" "$NEW_CODE/.venv" && ok ".venv -> $(readlink "$NEW_CODE/.venv")"
else
  look "the code folder's .venv isn't a link; left as it is"
fi

bar "Rebuild Lift.app from the new code folder"
if (cd "$NEW_CODE" && bash scripts/mac_app/build_app.sh >> "$LOG" 2>&1); then ok "Lift.app rebuilt"; else bad "Lift.app rebuild failed (see run.log)"; fi

bar "What the app shows after the move"
snapshot after
compare
check_all
scan_leftovers

{
  echo "Lift rename, $(date '+%Y-%m-%d %H:%M')"
  echo "Moved (old name left as a link):"
  awk -F'\t' '{print "  " $1 "  ->  " $2}' "$REPORT/moves.tsv"
  if [ "$FAILED" = 0 ]; then echo "Every check passed."; else echo "$FAILED checks FAILED: see needs_a_look.txt and run.log. To put everything back: bash ~/dev/lift/scripts/rename_to_lift.sh --undo"; fi
  echo "Needs a look: $(wc -l < "$NEEDS" | tr -d ' ') lines in $NEEDS"
  echo "From now on the code is in ~/dev/lift (cd ~/Desktop/saxscribe still works)."
} | tee "$SUMMARY"
exit $([ "$FAILED" = 0 ] && echo 0 || echo 1)
