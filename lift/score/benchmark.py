"""The growing benchmark: every confidently matched answer key, scored with the app's live default.

  python -m lift benchmark split            # which records are benchmark, which wait for training
  python -m lift benchmark score            # score them all with today's default (no training)
  python -m lift benchmark score --wait     # same, but first wait for other heavy Mac jobs to end

The list comes from the PDF ledger's matched charts (score/ledger.py), with each chart's recording
and lined-up answer key found the way the Library finds them (app/catalog.py): a PDF or recording
whose fingerprint changed since it was matched is left out.

Split (docs/evaluation/benchmark_split.json holds the rules, ADR-0049):
  test           Austin's own test tunes: scored and reported on their own, never trained on
  benchmark      the E81 benchmark songs (benchmark_tags.json), every record by a held-out
                 player (Byas, Stitt, Marsh, Berg, Mobley, Sims, Bartz, Charles Davis; E84 pre-reg),
                 and, when the rules set extra_share, that share of the other sessions
  session_hold   would be training material, but shares a session with a benchmark or test record
                 (same player and year, or the same album): kept out of training
  seen           a model already trained on it (match_report's in_training): scored for information
  train_reserve  everything else: saved for training later, scored now for the baseline
  skip           no usable recording or key on this Mac (listed in needs_a_look.csv)

Scoring uses the live default for each kind of record: band records run setup D (Filosax separator +
our E77 note finder), solo takes (the etudes) run the standard path. The vocal review mark only marks
notes, so it is left off here. Main score: note F1 ignoring note ends (ADR-0044).

Writes <runs>/benchmark/<name>/: split.csv, rows.jsonl (one experiments row per record),
summary.md, needs_a_look.csv, run.log; and appends each row to <runs>/experiments.jsonl so the
Results page shows it. Take folders are kept under takes/, so a stopped run carries on where it was.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .. import paths

RULES = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "benchmark_split.json"
TIERS = ("test", "benchmark", "session_hold", "seen", "train_reserve", "skip")
SCORED = ("test", "benchmark", "session_hold", "seen", "train_reserve")
HORNS = {"as": "alto", "alto": "alto", "ts": "tenor", "tenor": "tenor", "ss": "soprano", "soprano": "soprano",
         "bs": "baritone", "bari": "baritone", "baritone": "baritone"}
SOLO_KINDS = {"youtube_etude"}           # recorded alone: no band to separate
SETUP_D = {"separator": "filosax", "spans_from": "same", "note_finder": "e77"}
SETUP_SOLO = {"separator": "none", "spans_from": "same", "note_finder": "standard"}
HEAVY = (r"run_keys\.py|match_check\.py|archive_check\.py|video_to_key\.py|second_reader|tuning_regrade\.py|"
         r"file_winners\.py|octave_check\.py|clef_fix\.py|yt-dlp|train8\d\.py")
LOOK_F1 = 0.25                           # no-offset note F1 below this: worth a look
LOOK_FOUND = 0.5                         # sax_found below this: the stem may have lost the sax


def rules(path: Path | None = None) -> dict:
    return json.loads((path or RULES).read_text())


def norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def year_of(cid: str, tag: dict | None = None) -> int | None:
    if tag and tag.get("year"):
        return int(tag["year"])
    m = re.search(r"_((?:18|19|20)\d\d)$", cid or "")
    return int(m.group(1)) if m else None


def read_key(path: Path | None) -> list[dict]:
    """The key's notes [{onset, offset, pitch, heard_ok?}], grace notes left out (as experiments.classify wants)."""
    from .review import notes_in
    if path is None:
        return []
    raw = json.loads(path.read_text())
    raw = raw.get("notes", []) if isinstance(raw, dict) else raw
    graces = {round(float(n.get("onset", n.get("start", -1))), 3) for n in raw
              if isinstance(n, dict) and n.get("grace")}
    heard = {round(float(n.get("onset", n.get("start", -1))), 3): n["heard_ok"] for n in raw
             if isinstance(n, dict) and "heard_ok" in n}
    out = []
    for n in notes_in(path):
        if n["onset"] in graces:
            continue
        if n["onset"] in heard:
            n["heard_ok"] = bool(heard[n["onset"]])
        out.append(n)
    return out


# ---------------------------------------------------------------- split

def charts(runs: str | Path | None = None) -> list[dict]:
    """Every matched chart (one per chart id) with its player, horn, year, album and files on this Mac."""
    from ..app import catalog
    from . import review
    ok, _, hidden, _, _ = catalog._matched(runs)
    tags = catalog.benchmark_tags()
    report = {e["id"]: e for e in review.load(runs)["entries"]}
    etudes = catalog.etude_links(runs)
    out = []
    for row in ok:
        cid = row.get("chart_id", "")
        tag = tags.get(cid) or {}
        rep = report.get(cid) or {}
        f = catalog.files(runs, row, rep or None, etudes)
        kind = row.get("kind", "")
        horn = HORNS.get((row.get("horn") or "").lower()) or HORNS.get((tag.get("horn") or "").lower()) \
            or catalog.horn_from_name(row.get("pdf", "")) or "alto"
        out.append({"id": cid, "kind": kind, "player": tag.get("player") or catalog.player_name(row.get("performer", "")),
                    "tune": tag.get("title") or row.get("tune", ""), "horn": horn, "year": year_of(cid, tag),
                    "album": tag.get("album") or row.get("recording", "") or "", "mix": kind not in SOLO_KINDS,
                    "audio": str(f["audio"]) if f["audio"] else "", "key": str(f["key"]) if f["key"] else "",
                    "in_training": bool(rep.get("in_training")), "e81": cid in tags,
                    "heard": row.get("heard_agree", "")})
    return out


def split(items: list[dict], rule: dict) -> list[dict]:
    """Give every chart a tier and a reason (see the module notes). Pure: no files read."""
    held = {norm(p) for p in rule.get("held_out_players", [])}
    test_kinds = set(rule.get("test_kinds", ["test_tune"]))
    out = []
    for it in items:
        it = dict(it)
        if not it.get("audio") or not it.get("key"):
            it["tier"], it["why"] = "skip", "no recording on this Mac" if not it.get("audio") else "no lined-up answer key"
        elif it["kind"] in test_kinds:
            it["tier"], it["why"] = "test", "Austin's test tune"
        elif it.get("in_training"):
            it["tier"], it["why"] = "seen", "a model already trained on it"
        elif it.get("e81"):
            it["tier"], it["why"] = "benchmark", "E81 benchmark song"
        elif norm(it.get("player")) in held:
            it["tier"], it["why"] = "benchmark", "held-out player"
        else:
            it["tier"], it["why"] = "train_reserve", ""
        out.append(it)
    # A fixed share of the rest joins the benchmark, a whole session at a time (same player and year;
    # a record without a year is its own session). The pick hashes the session's name, so it never
    # changes as the ledger grows: a record keeps its group once it has one.
    share = float(rule.get("extra_share", 0) or 0)
    if share > 0:
        for it in out:
            if it["tier"] == "train_reserve" and session_pick(session_of(it), share):
                it["tier"], it["why"] = "benchmark", f"sampled session ({session_of(it)})"
    # Session rule: nothing trains on a record from the same session as one we score against.
    guard = [x for x in out if x["tier"] in ("benchmark", "test")]
    for it in out:
        if it["tier"] != "train_reserve":
            continue
        for g in guard:
            same_player = norm(it.get("player")) and norm(it.get("player")) == norm(g.get("player"))
            if same_player and it.get("year") and it.get("year") == g.get("year"):
                it["tier"], it["why"] = "session_hold", f"same player and year as {g['id']}"
                break
            if it.get("album") and g.get("album") and norm(it["album"]) == norm(g["album"]):
                it["tier"], it["why"] = "session_hold", f"same album as {g['id']}"
                break
        else:
            if not it.get("year"):
                it["why"] = "no year on file: session rule could not be checked"
    return out


def session_of(it: dict) -> str:
    """Same player and year; a record without a year is its own session (needs_a_look lists it)."""
    if not it.get("year") or not norm(it.get("player")):
        return f"record:{it['id']}"
    return f"{norm(it['player'])}:{it['year']}"


def session_pick(session: str, share: float) -> bool:
    import hashlib
    h = int(hashlib.sha256(session.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < share


SPLIT_COLS = ["id", "tier", "why", "kind", "player", "tune", "horn", "year", "album", "mix", "audio", "key"]


def write_split(rows: list[dict], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "split.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, SPLIT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (TIERS.index(r["tier"]), r["id"])))
    return path


def split_counts(rows: list[dict]) -> dict:
    return {t: sum(r["tier"] == t for r in rows) for t in TIERS}


# ---------------------------------------------------------------- score

def heavy_jobs(pattern: str = HEAVY) -> list[str]:
    """Other heavy Mac jobs running now (never run two at once: the Mac crashed with two)."""
    try:
        out = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True).stdout
    except (OSError, ValueError):
        return []
    me = str(os.getpid())
    return [ln for ln in out.splitlines() if ln.strip() and not ln.startswith(me + " ")]


def wait_for_quiet(log, every: int = 60) -> None:
    t0, first = time.time(), True
    while jobs := heavy_jobs():
        log(f"waiting for another heavy job to finish ({len(jobs)} running, {int(time.time() - t0) // 60} min so far)",
            live=not first)  # the first line goes to the log too
        first = False
        time.sleep(every)
    if not first:
        log(f"the other job finished after {int(time.time() - t0) // 60} min; carrying on")


class Progress:
    """A live Terminal bar: done/total, the current record, time left. The log gets one plain line each."""

    def __init__(self, total: int, log_path: Path):
        self.total, self.done, self.t0, self.log_path = total, 0, time.time(), log_path

    def line(self, msg: str, live: bool = False) -> None:
        stamp = time.strftime("%H:%M")
        if live and sys.stdout.isatty():
            sys.stdout.write(f"\r{stamp} {msg[:110]:<110}")
            sys.stdout.flush()
            return
        print(f"{stamp} {msg}", flush=True)
        with self.log_path.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    def bar(self, current: str, scored_new: int) -> None:
        width = 30
        fill = int(width * self.done / max(1, self.total))
        spent = time.time() - self.t0
        left = spent / scored_new * (self.total - self.done) if scored_new else None
        eta = f"{int(left // 3600)} h {int(left % 3600 // 60):02d} min left" if left is not None else "timing..."
        msg = f"[{'#' * fill}{'.' * (width - fill)}] {self.done}/{self.total}  {current}  {eta}"
        if sys.stdout.isatty():
            sys.stdout.write(f"\r{msg[:150]:<150}")
            sys.stdout.flush()


def score_one(item: dict, folder: Path) -> dict:
    """Transcribe one record with the live default and score it against its key; an experiments row."""
    from ..pipeline import transcribe
    from . import experiments, metrics
    from .refs import Reference
    key = read_key(Path(item["key"]))
    if not key:
        raise ValueError("the answer key has no notes")
    mix = bool(item["mix"])
    setup = SETUP_D if mix else SETUP_SOLO
    take = transcribe(Path(item["audio"]), folder, mix=mix, horn=item["horn"],
                      notes_tool="filosax" if mix else "auto", separator="filosax" if mix else "demucs")
    ref = Reference(id=item["id"], audio=Path(item["audio"]), notes=key, tune=item.get("tune", ""),
                    player=item.get("player", ""), is_mix=mix, partial=True, extra={"horn": item["horn"]})
    m = metrics.score_take(ref, take)
    notes = json.loads(take.notes.read_text())["notes"]
    cuts = take.read_manifest().get("layers", {}).get("notes", {}).get("sax_cuts") or []
    breakdown = experiments.classify(key, notes, cuts=[tuple(c) for c in cuts])
    keep = ("note_f1", "note_f1_no_offset", "onset_f1", "pitch_accuracy", "sax_found", "sax_purity",
            "octave_errors", "onset_recall", "onset_precision")
    rec = experiments.row("benchmark-v2", item["id"], setup, {k: m[k] for k in keep if k in m},
                          default=True, breakdown=breakdown, entry="B2", note=item["tier"])
    rec["title"] = f"{item.get('tune', '')} ({item.get('player', '')})".strip()
    rec["key"] = {**rec.get("key", {}), "kind": item["kind"], "tier": item["tier"]}
    return rec


def mean(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def pct(v: float | None) -> str:
    return "-" if v is None else f"{100 * v:.1f}"


def summary(split_rows: list[dict], recs: list[dict], errors: dict[str, str]) -> str:
    by_id = {r["record"]: r for r in recs}
    lines = ["# Benchmark v2: baseline with today's default (no training)", "",
             f"Made {time.strftime('%Y-%m-%d %H:%M')}. Band records: Filosax separator + E77 note finder (setup D); "
             "solo etudes: the standard path. Main score: note F1 ignoring note ends. Averages are per record.", "",
             "| Group | Records | Scored | Note F1, no ends | Note F1 | Onset F1 | Pitch |", "|---|---|---|---|---|---|---|"]
    for tier in TIERS:
        ids = [r["id"] for r in split_rows if r["tier"] == tier]
        got = [by_id[i]["metrics"] for i in ids if i in by_id]
        lines.append(f"| {tier} | {len(ids)} | {len(got)} | {pct(mean([g.get('note_f1_no_offset') for g in got]))} | "
                     f"{pct(mean([g.get('note_f1') for g in got]))} | {pct(mean([g.get('onset_f1') for g in got]))} | "
                     f"{pct(mean([g.get('pitch_accuracy') for g in got]))} |")
    allm = [r["metrics"] for r in recs]
    lines.append(f"| **all scored** | {len(split_rows)} | {len(recs)} | **{pct(mean([g.get('note_f1_no_offset') for g in allm]))}** | "
                 f"{pct(mean([g.get('note_f1') for g in allm]))} | {pct(mean([g.get('onset_f1') for g in allm]))} | "
                 f"{pct(mean([g.get('pitch_accuracy') for g in allm]))} |")
    lines += ["", "## By kind of chart", "", "| Kind | Scored | Note F1, no ends |", "|---|---|---|"]
    kinds = sorted({r["kind"] for r in split_rows})
    for k in kinds:
        got = [by_id[r["id"]]["metrics"] for r in split_rows if r["kind"] == k and r["id"] in by_id]
        lines.append(f"| {k} | {len(got)} | {pct(mean([g.get('note_f1_no_offset') for g in got]))} |")
    lines += ["", "## Every record (worst first)", "", "| Record | Group | Note F1, no ends | Note F1 | Sax found |",
              "|---|---|---|---|---|"]
    tier = {r["id"]: r["tier"] for r in split_rows}
    for r in sorted(recs, key=lambda r: r["metrics"].get("note_f1_no_offset", 0)):
        m = r["metrics"]
        lines.append(f"| {r['record']} | {tier.get(r['record'], '')} | {pct(m.get('note_f1_no_offset'))} | "
                     f"{pct(m.get('note_f1'))} | {pct(m.get('sax_found'))} |")
    if errors:
        lines += ["", f"## Could not score ({len(errors)})", ""] + [f"- {k}: {v}" for k, v in sorted(errors.items())]
    return "\n".join(lines) + "\n"


def needs_a_look(split_rows: list[dict], recs: list[dict], errors: dict[str, str]) -> list[dict]:
    by_id = {r["record"]: r for r in recs}
    out = []
    for s in split_rows:
        r = by_id.get(s["id"])
        why = []
        if s["tier"] == "skip":
            why.append(s["why"])
        if s["id"] in errors:
            why.append(f"could not score: {errors[s['id']]}")
        if s["tier"] == "session_hold":
            why.append(f"kept out of training: {s['why']} (check it really is the same session)")
        if s["tier"] == "train_reserve" and s.get("why"):
            why.append(s["why"])
        if r:
            m = r["metrics"]
            if m.get("note_f1_no_offset", 1) < LOOK_F1:
                why.append(f"note F1 without ends only {pct(m.get('note_f1_no_offset'))}: key or recording may be off")
            if m.get("sax_found", 1) < LOOK_FOUND:
                why.append(f"sax found only {pct(m.get('sax_found'))}: the stem may have lost the sax")
        if why:
            out.append({"id": s["id"], "tier": s["tier"], "player": s.get("player", ""), "tune": s.get("tune", ""),
                        "why": "; ".join(why)})
    return out


def run_split(runs: str | Path | None = None, name: str = "v2") -> tuple[list[dict], Path]:
    base = (Path(runs).expanduser() if runs else paths.runs()) / "benchmark" / name
    rows = split(charts(runs), rules())
    write_split(rows, base)
    return rows, base


def run_score(runs: str | Path | None = None, name: str = "v2", tiers: tuple[str, ...] = SCORED,
              limit: int | None = None, wait: bool = False) -> dict:
    rows, base = run_split(runs, name)
    todo = [r for r in rows if r["tier"] in tiers]
    if limit:
        todo = todo[:limit]
    prog = Progress(len(todo), base / "run.log")
    counts = split_counts(rows)
    prog.line("split: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if wait:
        wait_for_quiet(prog.line)
    elif jobs := heavy_jobs():
        prog.line("Another heavy job is running; start again with --wait to queue behind it:\n  " + "\n  ".join(jobs))
        raise SystemExit(2)
    os.environ["LIFT_MUSESCORE"] = "off"  # a scorecard never needs PDFs
    rows_path = base / "rows.jsonl"
    done = {}
    for line in rows_path.read_text().splitlines() if rows_path.exists() else []:
        try:
            rec = json.loads(line)
            done[rec["record"]] = rec
        except (json.JSONDecodeError, KeyError):
            continue
    errors: dict[str, str] = {}
    new = 0
    for item in todo:
        prog.bar(item["id"], new)
        if item["id"] in done:
            prog.done += 1
            continue
        if heavy_jobs():  # one started after we did: never run two heavy jobs at once
            wait_for_quiet(prog.line)
        try:
            rec = score_one(item, base / "takes" / item["id"])
        except (ValueError, OSError, RuntimeError, SystemExit) as exc:
            errors[item["id"]] = str(exc)[:200]
            prog.done += 1
            prog.line(f"[{prog.done}/{prog.total}] {item['id']}: could not score ({errors[item['id']]})")
            continue
        from . import experiments
        with rows_path.open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        experiments.append(rec, runs)
        done[item["id"]] = rec
        new += 1
        prog.done += 1
        m = rec["metrics"]
        prog.line(f"[{prog.done}/{prog.total}] {item['id']} ({item['tier']}): note F1 no ends "
                  f"{pct(m.get('note_f1_no_offset'))}, with ends {pct(m.get('note_f1'))}")
    recs = [done[r["id"]] for r in rows if r["id"] in done]
    (base / "summary.md").write_text(summary(rows, recs, errors))
    look = needs_a_look(rows, recs, errors)
    with (base / "needs_a_look.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["id", "tier", "player", "tune", "why"])
        w.writeheader()
        w.writerows(look)
    prog.line(f"BENCHMARK_DONE: {len(recs)} scored, {len(errors)} could not be scored, {len(look)} need a look. "
              f"Summary: {base / 'summary.md'}")
    return {"split": counts, "scored": len(recs), "errors": len(errors), "look": len(look), "folder": str(base)}
