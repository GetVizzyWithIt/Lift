#!/bin/bash
# Tidies the Saxscribe leftovers off the Desktop after the rename to Lift (ADR-0047).
#
#   bash scripts/desktop_cleanup.sh            dry run: lists everything, changes nothing
#   bash scripts/desktop_cleanup.sh --apply    tidies up
#   bash scripts/desktop_cleanup.sh --undo     puts everything back
#
# What it does:
#   - Old-name links on the Desktop (saxscribe -> ~/dev/lift,
#     Saxscribe_Recent_Downloads -> Lift_Recent_Downloads) are HIDDEN, not removed.
#     Thousands of stored paths (catalog, links.csv, the PDF ledger) still say
#     ~/Desktop/..., and they keep working through the hidden links.
#   - Real Saxscribe files and folders on the Desktop (for example the old
#     pipeline map page) are MOVED to ~/lift-runs/_old_desktop/. Nothing is deleted.
#   - Saved scripts that still say ~/Desktop/saxscribe or
#     ~/Desktop/Saxscribe_Recent_Downloads are switched to the Lift paths
#     (a .pre-desktop-cleanup backup is kept next to each).
#   - Lift.app is rebuilt if it still points at the old folder.
#
# Never touches the Songs in the Key of Life folder. Refuses to run while a
# Lift job is running. Reports go to ~/Library/Logs/Lift/desktop-cleanup/:
#   summary.txt, needs_a_look.txt (empty is good), actions.tsv (the undo list), run.log
set -uo pipefail

H="$HOME"
DESK="$H/Desktop"
CODE="$H/dev/lift"
RUNS="$H/lift-runs"
ARCHIVE="$RUNS/_old_desktop"
REPORT="$H/Library/Logs/Lift/desktop-cleanup"
ACTIONS="$REPORT/actions.tsv"
BAK=".pre-desktop-cleanup"

MODE=dry
case "${1:-}" in
  "") ;;
  --apply) MODE=apply ;;
  --undo) MODE=undo ;;
  *) echo "usage: bash scripts/desktop_cleanup.sh [--apply | --undo]"; exit 2 ;;
esac

mkdir -p "$REPORT"
LOG="$REPORT/run.log"
LOOK="$REPORT/needs_a_look.txt"
: > "$LOOK"
log()  { echo "$*" | tee -a "$LOG"; }
ok()   { log "   ok: $*"; }
look() { log "   LOOK: $*"; echo "$*" >> "$LOOK"; }
STEP=0; STEPS=1
bar() {  # a live progress bar, one step at a time
  STEP=$((STEP + 1))
  local w=30 done=$((STEP * 30 / STEPS)); [ "$done" -gt "$w" ] && done=$w
  local fill; fill="$(printf '%*s' "$done" '' | tr ' ' '#')$(printf '%*s' $((w - done)) '' | tr ' ' '.')"
  log ""; log "[$fill] $STEP/$STEPS  $*"
}
is_songs() { case "$1" in *[Ss]ongs-in-the-[Kk]ey*|*[Ss]ongs\ in\ the\ [Kk]ey*) return 0 ;; esac; return 1; }

log ""
log "=== desktop_cleanup $MODE, $(date '+%Y-%m-%d %H:%M:%S') ==="

# ---------------------------------------------------------------- undo
if [ "$MODE" = undo ]; then
  if [ ! -s "$ACTIONS" ]; then log "Nothing to undo ($ACTIONS is empty or missing)."; exit 0; fi
  STEPS=1; bar "Putting everything back, last change first"
  tail -r "$ACTIONS" 2>/dev/null > "$REPORT/.undo" || tac "$ACTIONS" > "$REPORT/.undo"
  left=0
  while IFS=$'\t' read -r kind a b c; do
    case "$kind" in
      HIDE)
        if chflags -h nohidden "$a" 2>/dev/null; then ok "shown again: $a"; else look "could not show again: $a"; left=1; fi ;;
      MOVE)
        if [ -e "$a" ] || [ -L "$a" ]; then look "not moved back, something is already at $a (it's still in $b)"; left=1
        elif mv "$b" "$a"; then ok "moved back: $a"; else look "could not move back $b"; left=1; fi ;;
      EDIT)
        now="$(shasum -a 256 "$a" 2>/dev/null | cut -c1-64)"
        if [ "$now" != "$c" ]; then look "not restored, $a changed after the cleanup (backup kept: $b)"; left=1
        elif cp -p "$b" "$a" && rm -f "$b"; then ok "restored: $a"; else look "could not restore $a from $b"; left=1; fi ;;
      REBUILD)
        log "   Lift.app was rebuilt; it works from either path, so it is left as it is." ;;
    esac
  done < "$REPORT/.undo"
  rm -f "$REPORT/.undo"
  if [ "$left" = 0 ]; then mv "$ACTIONS" "$ACTIONS.undone-$(date +%Y%m%d-%H%M%S)"; log ""; log "Undo finished. Everything is back."
  else log ""; log "Undo finished, but some items need a look: $LOOK"; fi
  exit 0
fi

# ---------------------------------------------------------------- jobs running?
running_jobs() {
  /bin/ps -axo pid=,command= \
    | grep -v -E "^ *[0-9]+ +[^ ]*/?(tail|less|more|vi|vim|nano|cat|open|man|mdworker[^ ]*|mds[^ ]*) " \
    | grep -E "saxscribe|lift-runs|-m lift|run_keys|stem_contour|pdf_ledger|archive_fetch|archive_check|file_archive|key_batch|homr|review/server.py|match_check" \
    | grep -v -E "grep|desktop_cleanup" || true
}

STEPS=6
[ "$MODE" = apply ] && [ -s "$ACTIONS" ] && { log "An earlier cleanup is still recorded in $ACTIONS. Run --undo first, or move that file away."; exit 1; }

bar "Jobs running now"
jobs_now="$(running_jobs)"
if [ -n "$jobs_now" ]; then
  log "$jobs_now"
  if [ "$MODE" = apply ]; then log "   A Lift job is running. Run this again when it's done (nothing was changed)."; exit 1; fi
  log "   (--apply will refuse to run until these finish)"
else ok "nothing running"; fi

# ---------------------------------------------------------------- what's on the Desktop
bar "Saxscribe items on the Desktop"
ITEMS="$REPORT/.items"; : > "$ITEMS"
find "$DESK" -maxdepth 1 -mindepth 1 -iname '*saxscribe*' 2>/dev/null | sort > "$ITEMS"
if [ ! -s "$ITEMS" ]; then ok "none left"; fi

# stored paths that go through a Desktop link (counted, never changed)
count_stored() {  # $1 = old Desktop path; prints how many data files and catalog rows still use it
  local p="$1" rel="${1#$H/}" files rows db
  files="$(grep -rlF --include='*.csv' --include='*.jsonl' --include='*.txt' \
            --exclude-dir='.venv*' --exclude-dir=.git --exclude-dir=site-packages --exclude-dir=_old_desktop \
            -e "$p" -e "~/$rel" "$RUNS/" "$H/lift-library/" 2>/dev/null | wc -l | tr -d ' ')"
  db="$RUNS/catalog/saxscribe_catalog.db"
  rows=0
  if [ -f "$db" ]; then
    rows="$(python3 - "$db" "$p" "~/$rel" <<'PY' 2>/dev/null || echo "?"
import sqlite3, sys
db, *needles = sys.argv[1:]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
n = 0
for (t,) in con.execute("select name from sqlite_master where type='table'"):
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    for c in cols:
        for s in needles:
            n += con.execute(f'select count(*) from "{t}" where instr("{c}", ?) > 0', (s,)).fetchone()[0]
print(n)
PY
)"
  fi
  echo "$files data files, $rows catalog values"
}

PLAN="$REPORT/.plan"; : > "$PLAN"
while IFS= read -r item; do
  [ -z "$item" ] && continue
  name="${item##*/}"
  if is_songs "$item"; then log "   skip (Songs in the Key of Life): $name"; continue; fi
  if [ -L "$item" ]; then
    target="$(cd "$item" 2>/dev/null && pwd -P || readlink "$item")"
    case "$target" in
      "$CODE"|"$CODE"/*|"$DESK/Lift_Recent_Downloads"*|"$RUNS"*|"$H/lift-library"*)
        log "   $name  (link to ${target/#$H/~})  -> hide; still used by $(count_stored "$item")"
        printf 'HIDE\t%s\n' "$item" >> "$PLAN" ;;
      *)
        look "link $name points somewhere unexpected ($target); left alone" ;;
    esac
  else
    size="$(du -sh "$item" 2>/dev/null | cut -f1)"
    refs="$(grep -rlF --include='*.py' --include='*.sh' --include='*.command' -e "$item" -e "~/Desktop/$name" \
             --exclude-dir='.venv*' --exclude-dir=.git --exclude-dir=site-packages "$RUNS/" "$CODE/" 2>/dev/null | head -3)"
    if [ -n "$refs" ]; then
      look "$name is used by saved scripts, so it stays put: $(echo "$refs" | tr '\n' ' ')"
    else
      log "   $name  ($size)  -> move to ~/lift-runs/_old_desktop/"
      printf 'MOVE\t%s\n' "$item" >> "$PLAN"
    fi
  fi
done < "$ITEMS"

# ---------------------------------------------------------------- saved scripts with old Desktop paths
bar "Saved scripts that still say ~/Desktop/saxscribe or Saxscribe_Recent_Downloads"
SCRIPTS="$REPORT/.scripts"; : > "$SCRIPTS"
{
  grep -rlE --include='*.py' --include='*.sh' --include='*.command' --include='*.zsh' \
    --exclude-dir='.venv*' --exclude-dir=.git --exclude-dir=site-packages --exclude-dir=node_modules --exclude-dir=_old_desktop \
    'Desktop/(saxscribe|Saxscribe_Recent_Downloads)' "$RUNS/" 2>/dev/null
  ls "$CODE"/config.local.* 2>/dev/null | while read -r f; do grep -lE 'Desktop/(saxscribe|Saxscribe_Recent_Downloads)' "$f"; done
} | grep -v "$BAK\$" | sort -u > "$SCRIPTS"
if [ -s "$SCRIPTS" ]; then
  while IFS= read -r f; do log "   ${f/#$H/~}  -> switch to the Lift paths"; done < "$SCRIPTS"
else ok "none"; fi
# the capitalised ~/Desktop/Saxscribe (old sheet-music folder) is listed, not rewritten
grep -rlE --include='*.py' --include='*.sh' --exclude-dir='.venv*' --exclude-dir=.git --exclude-dir=site-packages --exclude-dir=_old_desktop \
  'Desktop/Saxscribe([^_]|$)' "$RUNS/" 2>/dev/null | grep -v "$BAK\$" | while read -r f; do
  look "script mentions ~/Desktop/Saxscribe (old sheet-music folder; works, same folder as the code): $f"
done

# ---------------------------------------------------------------- Lift.app, settings, scheduled jobs
bar "Lift.app, shell settings, and scheduled jobs"
APP="$H/Applications/Lift.app"
NEED_REBUILD=0
if [ -d "$APP" ]; then
  if grep -rqF "Desktop/saxscribe" "$APP" 2>/dev/null; then log "   Lift.app still points at ~/Desktop/saxscribe -> rebuild"; NEED_REBUILD=1
  else ok "Lift.app points at ~/dev/lift"; fi
else look "no ~/Applications/Lift.app (build it with: cd ~/dev/lift && bash scripts/mac_app/build_app.sh)"; fi
for f in "$H/.zshrc" "$H/.zprofile" "$H/.bash_profile" "$H/.bashrc" "$H/.profile"; do
  [ -f "$f" ] && grep -n "Desktop/[sS]axscribe" "$f" | while read -r line; do look "shell setting uses the old Desktop path (still works): ${f/#$H/~}:$line"; done
done
grep -l "Desktop/[sS]axscribe" "$H"/Library/LaunchAgents/*.plist 2>/dev/null | while read -r f; do look "scheduled job uses the old Desktop path (still works): $f"; done
crontab -l 2>/dev/null | grep "Desktop/[sS]axscribe" | while read -r line; do look "crontab line uses the old Desktop path (still works): $line"; done
ok "checked"

# ---------------------------------------------------------------- dry run ends here
if [ "$MODE" = dry ]; then
  bar "Dry run done"
  log ""
  log "Nothing was changed. To tidy up, run:  bash scripts/desktop_cleanup.sh --apply"
  log "Needs a look: $(wc -l < "$LOOK" | tr -d ' ') lines ($LOOK)"
  rm -f "$ITEMS" "$PLAN" "$SCRIPTS"
  exit 0
fi

# ---------------------------------------------------------------- apply
bar "Tidying up"
: > "$ACTIONS"
while IFS=$'\t' read -r kind item; do
  case "$kind" in
    HIDE)
      if chflags -h hidden "$item"; then printf 'HIDE\t%s\n' "$item" >> "$ACTIONS"; ok "hidden: ${item##*/} (still works)"
      else look "could not hide $item"; fi ;;
    MOVE)
      mkdir -p "$ARCHIVE"
      dest="$ARCHIVE/${item##*/}"; n=2
      while [ -e "$dest" ] || [ -L "$dest" ]; do dest="$ARCHIVE/${item##*/} ($n)"; n=$((n + 1)); done
      printf 'MOVE\t%s\t%s\n' "$item" "$dest" >> "$ACTIONS"
      if mv "$item" "$dest"; then ok "moved: ${item##*/} -> ${dest/#$H/~}"
      else look "could not move $item"; fi ;;
  esac
done < "$PLAN"

while IFS= read -r f; do
  [ -z "$f" ] && continue
  if [ -e "$f$BAK" ]; then look "backup already exists, left alone: $f$BAK"; continue; fi
  cp -p "$f" "$f$BAK" || { look "could not back up $f; left alone"; continue; }
  if python3 - "$f" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="surrogateescape").read()
t = s.replace("Desktop/Saxscribe_Recent_Downloads", "Desktop/Lift_Recent_Downloads")
t = re.sub(r"Desktop/saxscribe(?![\w-])", "dev/lift", t)
open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
PY
  then
    sum="$(shasum -a 256 "$f" | cut -c1-64)"
    printf 'EDIT\t%s\t%s\t%s\n' "$f" "$f$BAK" "$sum" >> "$ACTIONS"
    ok "switched: ${f/#$H/~}"
  else cp -p "$f$BAK" "$f"; rm -f "$f$BAK"; look "could not switch $f; left as it was"; fi
done < "$SCRIPTS"

if [ "$NEED_REBUILD" = 1 ]; then
  if (cd "$CODE" && bash scripts/mac_app/build_app.sh >> "$LOG" 2>&1); then
    printf 'REBUILD\t%s\n' "$APP" >> "$ACTIONS"; ok "Lift.app rebuilt from ~/dev/lift"
  else look "Lift.app rebuild failed; see $LOG"; fi
fi

bar "Checking"
for p in "$DESK/saxscribe" "$DESK/Saxscribe_Recent_Downloads"; do
  if [ -L "$p" ]; then
    if [ -d "$p/" ]; then ok "${p/#$H/~} still works (hidden)"; else look "${p/#$H/~} link no longer reaches its folder"; fi
  fi
done
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    *.py) python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8", errors="surrogateescape").read())' "$f" 2>/dev/null && ok "still reads as Python: ${f##*/}" || look "Python can't read $f after the switch (undo restores it)" ;;
    *.sh|*.command|*.zsh) bash -n "$f" 2>/dev/null && ok "still reads as a script: ${f##*/}" || look "bash can't read $f after the switch (undo restores it)" ;;
  esac
done < "$SCRIPTS"

rm -f "$ITEMS" "$PLAN" "$SCRIPTS"
{
  echo "desktop_cleanup --apply, $(date '+%Y-%m-%d %H:%M:%S')"
  echo "hidden links: $(grep -c '^HIDE' "$ACTIONS")"
  echo "moved to ~/lift-runs/_old_desktop: $(grep -c '^MOVE' "$ACTIONS")"
  echo "scripts switched to Lift paths: $(grep -c '^EDIT' "$ACTIONS")"
  echo "needs a look: $(wc -l < "$LOOK" | tr -d ' ') lines"
} > "$REPORT/summary.txt"
log ""
cat "$REPORT/summary.txt" | tee -a "$LOG"
log "To put everything back: bash scripts/desktop_cleanup.sh --undo"
