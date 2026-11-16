"""The Review page: questions only Austin's ears can settle, one at a time.

Automatic checks always run first. A Mac script adds a question here only when every
automatic way to decide it has been tried and they still disagree (the "human review last"
rule). So this module never makes questions; it reads the ones the scripts wrote, shows
each with the chart, the recording at the right moment, and the answer key as soft tones,
and saves the answer.

Where things live (all under the runs folder, ~/lift-runs):

  review/queues/<queue>/items.json   one file per queue, written by the Mac scripts:
      {"queue": "match_check", "plugin": "match_check", "title": "...", "why": "...",
       "items": [ITEM, ...]}
  review/answers.jsonl               every answer, appended (an "undo" line takes one back);
                                     the same file the older review hub (review/server.py) uses

An ITEM is one question. Only "id" and "question" are required:

  id           unique within its queue
  question     the one question, in plain words ("Do bars 17 to 24 match what you hear?")
  listen_for   what to listen for ("the run into bar 21")
  why          why the machines could not settle it
  tried        list of the automatic checks already run, one line each
  song         a label, when there is no chart_id ("Cool Blues, Charlie Parker")
  chart_id     the chart's id in the PDF ledger: brings its PDF pages, horn, recording and key
  bars         [first, last]: the bars in question, drawn from the answer key and found on the page
  focus_bar    the bar to listen hardest to (drawn highlighted)
  loop         [start, end] in seconds of the recording; by default the bars' span, 1 s padded
  page         the chart page to show (from 1); top and bottom (0..1) crop it to a strip
  audio, stem, key, pdf   paths (runs-folder relative or absolute) when not the chart's own
  guesses      start_point only: [{"label": "A", "time": 31.0}, ...] places the start might be
  choices      listen only: [{"value": "sax", "label": "Sax"}, ...] (default sax / another instrument)

The plugin says which screen the item gets: match_check (is this chart this recording?),
start_point (where does the chart start in the recording?) or listen (one short question
about one spot). The hub's older names map onto these (ab_match, page_start, yes_no_listen).
Note-end tapping (note_ends) was retired on 2026-11-14 and is never shown.

A match_check answer about a chart in the match report is also written to
keys/match_review.jsonl (score/review.py), so the Library and the benchmark see it.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .. import paths
from ..score import review

PLUGINS = {"match_check": "match_check", "ab_match": "match_check",
           "start_point": "start_point", "page_start": "start_point",
           "listen": "listen", "yes_no_listen": "listen"}
RETIRED = {"note_ends"}  # Austin, 2026-11-14: page-key note ends are unreliable; no more tapping
KIND_NAMES = {"match_check": "Match check", "start_point": "Where it starts", "listen": "Quick listen"}
SECONDS = {"match_check": 60, "start_point": 30, "listen": 15}  # about how long one takes
MATCH_ANSWERS = [{"value": "same", "label": "Yes, same performance"},
                 {"value": "different", "label": "No, different take or player"},
                 {"value": "bar_wrong", "label": "Same, but a bar is wrong"},
                 {"value": "cant_tell", "label": "Can't tell"}]
LISTEN_ANSWERS = [{"value": "sax", "label": "Sax"}, {"value": "other", "label": "Another instrument"},
                  {"value": "cant_tell", "label": "Can't tell"}]
TO_VERDICT = {"same": "good", "bar_wrong": "good", "different": "wrong", "cant_tell": "unsure"}
AUDIO = review.AUDIO
PAD = 1.0  # seconds of recording kept either side of the bars in question


def runs_dir(runs: str | Path | None) -> Path:
    return Path(runs).expanduser() if runs else paths.runs()


def review_dir(runs: str | Path | None) -> Path:
    return runs_dir(runs) / "review"


# ---- reading the queues and the answers

def queues(runs: str | Path | None = None) -> list[dict]:
    """Every queue file that has a screen, in name order; unreadable files are skipped."""
    out = []
    for f in sorted((review_dir(runs) / "queues").glob("*/items.json")):
        try:
            q = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(q, dict):
            continue
        name = str(q.get("queue") or f.parent.name)
        plugin = PLUGINS.get(str(q.get("plugin") or name))
        if name in RETIRED or plugin is None:
            continue
        items = [it for it in q.get("items") or [] if isinstance(it, dict) and it.get("id") and it.get("question")]
        out.append({"queue": name, "plugin": plugin, "title": q.get("title") or KIND_NAMES[plugin],
                    "why": q.get("why", ""), "items": items})
    return out


def answers(runs: str | Path | None = None) -> dict[tuple[str, str], dict]:
    """The latest answer per (queue, item); an "undo" line takes the answer back."""
    path = review_dir(runs) / "answers.jsonl"
    out: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            a = json.loads(line)
        except ValueError:
            continue
        if not isinstance(a, dict) or not a.get("queue") or not a.get("item"):
            continue
        key = (str(a["queue"]), str(a["item"]))
        if a.get("answer") == "undo":
            out.pop(key, None)
        else:
            out[key] = a
    return out


def _label(item: dict, chart: dict | None) -> str:
    if item.get("song"):
        return str(item["song"])
    if chart:
        return ", ".join(x for x in (chart.get("title"), chart.get("player")) if x)
    return str(item.get("chart_id") or "")


def inbox(runs: str | Path | None = None) -> dict:
    """{left, minutes, items: [summary], done: n}: the questions still waiting, oldest queue first."""
    got = answers(runs)
    charts = _chart_rows(runs)
    waiting, done = [], 0
    for q in queues(runs):
        for it in q["items"]:
            if (q["queue"], str(it["id"])) in got:
                done += 1
                continue
            row = charts.get(str(it.get("chart_id") or ""))
            waiting.append({"queue": q["queue"], "id": str(it["id"]), "plugin": q["plugin"],
                            "kind": KIND_NAMES[q["plugin"]], "question": it["question"],
                            "song": _label(it, _chart_fields(row) if row else None),
                            "why": it.get("why") or q.get("why") or "",
                            "seconds": SECONDS[q["plugin"]]})
    seconds = sum(w["seconds"] for w in waiting)
    return {"left": len(waiting), "minutes": math.ceil(seconds / 60) if seconds else 0,
            "done": done, "items": waiting}


def find(runs: str | Path | None, queue: str, item_id: str) -> tuple[dict, dict]:
    """(the queue, the item); KeyError when either is gone."""
    for q in queues(runs):
        if q["queue"] == queue:
            for it in q["items"]:
                if str(it["id"]) == item_id:
                    return q, it
    raise KeyError(f"{queue}/{item_id}")


# ---- the chart, recording and key behind an item

def _chart_rows(runs: str | Path | None) -> dict[str, dict]:
    """Ledger rows by chart id, any status (questions are mostly about charts not yet matched).
    A chart listed twice keeps its first row whose PDF is still there."""
    from . import catalog
    from ..score import ledger
    found = ledger.full_rows(runs)
    out: dict[str, dict] = {}
    for row in (found[0] if found else []):
        cid = row.get("chart_id") or ""
        if not cid or (cid in out and catalog.fingerprint_ok(runs, out[cid]) == "ok"):
            continue
        out[cid] = row
    return out


def _chart_fields(row: dict) -> dict:
    from . import catalog
    return {"title": row.get("tune") or row.get("chart_id", ""),
            "player": catalog.player_name(row.get("performer", "")),
            "horn": catalog.HORNS.get((row.get("horn") or "").lower()) or catalog.horn_from_name(row.get("pdf", ""))}


def _path(runs: str | Path | None, value, suffixes: set[str] | None = None) -> Path | None:
    """A path an item names: absolute, ~, under the runs folder, or under review/."""
    if not value:
        return None
    p = review.resolve(runs, str(value))
    if p is None:
        cand = review_dir(runs) / str(value)
        p = cand if cand.exists() else None
    if p is None or not p.is_file() or (suffixes and p.suffix.lower() not in suffixes):
        return None
    return p


def files(runs: str | Path | None, item: dict) -> dict:
    """{pdf, audio, stem, key, row}: the item's own paths first, then its chart's (catalog.files).
    A chart PDF whose fingerprint changed since the ledger saw it is left out."""
    from . import catalog
    row = _chart_rows(runs).get(str(item.get("chart_id") or "")) if item.get("chart_id") else None
    base = {"pdf": None, "audio": None, "stem": None, "key": None}
    if row is not None:
        rep = {e["id"]: e for e in review.load(runs)["entries"]}.get(row.get("chart_id"))
        base = catalog.files(runs, row, rep, catalog.etude_links(runs))
        if catalog.fingerprint_ok(runs, row) != "ok":
            base["pdf"] = None
        # a chart not in the match report yet: its key and recording sit next to its PDF, by its id
        home = catalog.local_path(runs, row.get("pdf", ""))
        cid = row.get("chart_id", "")
        if home is not None and home.parent.is_dir():
            if base["key"] is None:
                base["key"] = _path(runs, home.parent / f"{cid}_key.json", {".json"})
            if base["audio"] is None:
                base["audio"] = next((p for ext in sorted(AUDIO) if (p := home.parent / f"{cid}{ext}").is_file()), None)
    out = {"pdf": _path(runs, item.get("pdf"), {".pdf"}) or base["pdf"],
           "audio": _path(runs, item.get("audio"), AUDIO) or base["audio"],
           "stem": _path(runs, item.get("stem"), AUDIO) or base["stem"],
           "key": _path(runs, item.get("key"), {".json"}) or base["key"],
           "row": row}
    return out


def _bars(item: dict) -> tuple[int, int] | None:
    b = item.get("bars")
    try:
        if isinstance(b, (list, tuple)) and len(b) == 2:
            a, z = int(b[0]), int(b[1])
            return (min(a, z), max(a, z))
        if b is not None:
            return (int(b), int(b))
    except (TypeError, ValueError):
        pass
    return None


def bar_times(key: Path | None, bars: tuple[int, int] | None) -> list[dict]:
    """[{bar, start, end}] for the bars in question, from the key's notes (the recording's clock).
    A bar with no notes (a rest bar) is left out."""
    if key is None or bars is None:
        return []
    try:
        data = json.loads(key.read_text())
    except (OSError, ValueError):
        return []
    notes = data.get("notes", []) if isinstance(data, dict) else data
    spans: dict[int, list[float]] = {}
    for n in notes if isinstance(notes, list) else []:
        if not isinstance(n, dict) or n.get("bar") is None or n.get("onset") is None:
            continue
        try:
            bar, t0 = int(n["bar"]), float(n["onset"])
            t1 = float(n.get("offset") if n.get("offset") is not None else t0)
        except (TypeError, ValueError):
            continue
        if bars[0] <= bar <= bars[1]:
            s = spans.setdefault(bar, [t0, t1])
            s[0], s[1] = min(s[0], t0), max(s[1], t1)
    return [{"bar": b, "start": round(s[0], 3), "end": round(s[1], 3)} for b, s in sorted(spans.items())]


def last_bar(key: Path | None) -> int | None:
    try:
        data = json.loads(key.read_text()) if key else None
    except (OSError, ValueError):
        return None
    notes = data.get("notes", []) if isinstance(data, dict) else data or []
    bars = [int(n["bar"]) for n in notes if isinstance(n, dict) and isinstance(n.get("bar"), (int, float))]
    return max(bars) if bars else None


def page_guess(item: dict, pages: int, bars: tuple[int, int] | None, total_bars: int | None) -> dict | None:
    """Which chart page to show: the item's own page (exact), else a guess from where the bars fall
    in the chart (bars spread evenly over the pages), marked approximate."""
    if not pages:
        return None
    if item.get("page"):
        try:
            n = max(1, min(pages, int(item["page"])))
        except (TypeError, ValueError):
            n = 1
        crop = None
        try:
            top, bottom = float(item["top"]), float(item["bottom"])
            if 0 <= top < bottom <= 1:
                crop = {"top": top, "bottom": bottom}
        except (KeyError, TypeError, ValueError):
            pass
        return {"page": n, "exact": True, "crop": crop}
    if bars and total_bars:
        frac = (bars[0] - 0.5) / total_bars
        return {"page": max(1, min(pages, int(frac * pages) + 1)), "exact": False, "crop": None,
                "at": round(frac * pages - int(frac * pages), 3)}
    return {"page": 1, "exact": False, "crop": None}


def choices_for(plugin: str, item: dict) -> list[dict]:
    """The answer buttons; start_point builds its own from the guesses and a tap."""
    if plugin == "match_check":
        return MATCH_ANSWERS
    if plugin == "listen":
        own = [{"value": str(c["value"]), "label": str(c["label"])} for c in item.get("choices") or []
               if isinstance(c, dict) and c.get("value") and c.get("label")]
        return own or LISTEN_ANSWERS
    return []


def detail(runs: str | Path | None, queue: str, item_id: str) -> dict:
    """Everything the item's screen shows. KeyError when the item is gone."""
    q, it = find(runs, queue, item_id)
    f = files(runs, it)
    chart = _chart_fields(f["row"]) if f["row"] else {"title": "", "player": "", "horn": ""}
    bars = _bars(it)
    times = bar_times(f["key"], bars)
    loop = None
    try:
        if it.get("loop"):
            loop = {"start": float(it["loop"][0]), "end": float(it["loop"][1])}
    except (TypeError, ValueError, IndexError):
        loop = None
    if loop is None and times and q["plugin"] != "start_point":  # where it starts is the open question
        loop = {"start": round(max(0.0, times[0]["start"] - PAD), 2), "end": round(times[-1]["end"] + PAD, 2)}
    pages = 0
    if f["pdf"] is not None:
        from . import pdf_pages
        try:
            pages = pdf_pages.count(f["pdf"])
        except Exception:
            pages = 0
    plugin = q["plugin"]
    choices = choices_for(plugin, it)
    guesses = []
    for g in it.get("guesses") or []:
        try:
            guesses.append({"label": str(g.get("label") or chr(65 + len(guesses))), "time": float(g["time"])})
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
    prev = answers(runs).get((queue, item_id))
    return {"queue": queue, "id": item_id, "plugin": plugin, "kind": KIND_NAMES[plugin],
            "question": it["question"], "listen_for": it.get("listen_for", ""),
            "why": it.get("why") or q.get("why") or "", "tried": [str(t) for t in it.get("tried") or []],
            "song": _label(it, chart if f["row"] else None), "chart_id": it.get("chart_id") or "",
            "horn": chart["horn"], "bars": list(bars) if bars else None,
            "focus_bar": it.get("focus_bar"), "bar_times": times, "loop": loop, "guesses": guesses,
            "choices": choices, "pages": pages,
            "page": page_guess(it, pages, bars, last_bar(f["key"])),
            "has_audio": f["audio"] is not None, "has_stem": f["stem"] is not None,
            "has_key": f["key"] is not None, "can_draw": f["key"] is not None and bars is not None,
            "answered": {"answer": prev.get("answer"), "note": prev.get("note", ""), "time": prev.get("time")}
            if prev else None}


# ---- the engraved bars

def engraved(runs: str | Path | None, queue: str, item_id: str, library_root: Path) -> dict:
    """{svg, bars}: the bars in question drawn from the answer key (the same engraving as the
    Library play-along: page rhythm when the page reading lines up, key pitch), written for the
    chart's horn. LookupError when there is no key or no bars to draw."""
    from . import catalog, key_take, score_view
    _, it = find(runs, queue, item_id)
    f = files(runs, it)
    bars = _bars(it)
    if f["key"] is None or bars is None:
        raise LookupError("This question has no answer key or bars to draw.")
    chart = _chart_fields(f["row"]) if f["row"] else {"horn": ""}
    cid = str(it.get("chart_id") or f["key"].stem.removesuffix("_key"))
    horn = chart["horn"] or ""
    folder = Path(library_root) / "_review" / cid / "take"
    take = key_take.build(f["key"], catalog.bars_file(runs, cid, f["key"]), horn, folder,
                          catalog.masks(runs, cid) if it.get("chart_id") else "")
    xml = (take.written_musicxml(horn) if horn else take.musicxml).read_text(encoding="utf-8")
    tk = score_view.toolkit()
    tk.setOptions({"pageWidth": 1500, "pageHeight": 60000, "adjustPageHeight": True, "scale": 48,
                   "svgViewBox": True, "header": "none", "footer": "none", "breaks": "auto",
                   "pageMarginTop": 30, "pageMarginBottom": 30, "pageMarginLeft": 30, "pageMarginRight": 30})
    if not tk.loadData(xml):
        raise ValueError("Verovio could not read the answer key")
    tk.select({"measureRange": f"{bars[0]}-{bars[1]}"})
    tk.redoLayout()
    svg = "".join(tk.renderToSVG(p) for p in range(1, tk.getPageCount() + 1))
    nota = json.loads(take.notation.read_text())
    numbers = [b for b in nota.get("bar_numbers") or [] if bars[0] <= b <= bars[1]] or list(range(bars[0], bars[1] + 1))
    return {"svg": svg, "bars": numbers, "horn": horn or "concert"}


def page_png(pdf: Path, n: int, crop: dict | None = None) -> bytes:
    """Page n of the chart as PNG bytes, cut to the strip top..bottom (fractions of the height) when asked."""
    import io
    from PIL import Image
    from . import catalog, pdf_pages
    path = pdf_pages.png(pdf, catalog.sha256(pdf), n)
    if not crop:
        return path.read_bytes()
    with Image.open(path) as im:
        h = im.height
        box = (0, int(h * crop["top"]), im.width, max(int(h * crop["top"]) + 1, int(h * crop["bottom"])))
        buf = io.BytesIO()
        im.crop(box).save(buf, format="PNG", optimize=True)
        return buf.getvalue()


# ---- saving an answer

def save(runs: str | Path | None, queue: str, item_id: str, answer: str, note: str = "",
         extra: dict | None = None) -> dict:
    """Append Austin's answer (or "undo"). ValueError for an answer the item doesn't offer;
    KeyError when the item is gone."""
    q, it = find(runs, queue, item_id)
    plugin = q["plugin"]
    extra = {k: v for k, v in (extra or {}).items() if k in ("time", "bar", "choice")}
    if answer != "undo":
        allowed = {c["value"] for c in choices_for(plugin, it)}
        if plugin == "start_point":
            allowed = {"guess", "tap", "not_here", "cant_tell"}
        if answer not in allowed:
            raise ValueError(f"answer must be one of {', '.join(sorted(allowed))}")
        if plugin == "start_point" and answer in ("guess", "tap"):
            try:
                extra["time"] = round(float(extra["time"]), 3)
            except (KeyError, TypeError, ValueError):
                raise ValueError("a start time (seconds) is needed")
        if answer == "bar_wrong":
            try:
                extra["bar"] = int(extra["bar"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("which bar is wrong?")
    rec = {"queue": queue, "item": item_id, "plugin": plugin, "answer": answer, "note": str(note)[:2000],
           "chart_id": it.get("chart_id") or "", "via": "app",
           "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **extra}
    path = review_dir(runs) / "answers.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    _mirror(runs, plugin, it, answer, rec)
    return rec


def _mirror(runs, plugin: str, item: dict, answer: str, rec: dict) -> None:
    """A match-check answer about a pair in the match report also goes to match_review.jsonl."""
    if plugin != "match_check":
        return
    pair = str(item.get("pair_id") or item.get("chart_id") or "")
    known = {e["id"] for e in review.load(runs)["entries"]}
    if pair not in known:
        return
    verdict = None if answer == "undo" else TO_VERDICT.get(answer)
    note = rec["note"]
    if answer == "bar_wrong":
        note = f"bar {rec['bar']} wrong on the chart" + (f": {note}" if note else "")
    review.save(runs, pair, verdict, note)
