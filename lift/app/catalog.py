"""The Library: every answer key that is confidently matched to its recording, plus finished takes.

An answer key is a PDF chart paired with its recording. The list comes from the PDF ledger
(score/ledger.py): only rows whose status is "matched" are shown, so the Library grows as the
matching work finishes. Before a chart is shown, its PDF is checked against the fingerprint
(sha256) the ledger recorded; a PDF that moved or changed since it was matched is left out and
counted, never shown with a stale match.

Songs the app transcribed itself (finished takes) are listed too, marked as made by Lift.

Read-only: nothing here writes to the runs folder or the ledger. Paths and fingerprints stay
on the Mac; the page only gets the fields below.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from .. import paths
from ..score import ledger, review
from . import covers

TAGS = Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "benchmark_tags.json"
HORNS = {"as": "alto", "alto": "alto", "ts": "tenor", "tenor": "tenor", "ss": "soprano", "soprano": "soprano",
         "bs": "baritone", "baritone": "baritone"}
KINDS = {"transcribed": "Transcribed solo", "book_split": "Book transcription", "youtube_etude": "Etude",
         "test_tune": "Your test tune", "site_pdf": "Transcription site", "excerpt": "Excerpt"}
# "48 Famous Studies (Ferling) p. Etude No. 1, Adagio" / "Selected Studies ... (ed. Voxman, Rubank) p.13 Ferling Etude No. 8"
ETUDE = re.compile(r"^(?P<book>.+?)\s*\((?P<paren>[^)]*)\)\s*p\.\s*(?P<page>\d*)\s*(?P<rest>.*)$")

_hashes: dict[tuple[str, int, int], str] = {}  # (path, size, mtime_ns) -> sha256, so each PDF is read once


def sha256(path: Path) -> str:
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _hashes:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        _hashes[key] = h.hexdigest()
    return _hashes[key]


def runs_dir(runs: str | Path | None) -> Path:
    return Path(runs).expanduser() if runs else paths.runs()


def local_path(runs: str | Path | None, value: str) -> Path | None:
    """A ledger path on this machine. The ledger writes ~/saxscribe-runs/... (or ~/lift-runs/...);
    either prefix maps to the runs folder the app was started with."""
    if not value:
        return None
    for prefix in paths.runs_prefixes():
        if value.startswith(prefix):
            return runs_dir(runs) / value[len(prefix):]
    return Path(value).expanduser()


def fingerprint_ok(runs: str | Path | None, row: dict) -> str:
    """"ok", "missing" (no file there) or "changed" (the file differs from the one that was matched)."""
    p = local_path(runs, row.get("pdf", ""))
    if p is None or not p.is_file():
        return "missing"
    want = (row.get("sha256") or "").strip().lower()
    if want and sha256(p) != want:
        return "changed"
    return "ok"


def benchmark_tags() -> dict:
    try:
        return json.loads(TAGS.read_text()).get("songs", {})
    except (OSError, ValueError):
        return {}


def fraction(v) -> float | None:
    """Ledger scores come as percent (85.0) or as a fraction (0.85); the page gets a fraction."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f / 100 if f > 1 else f, 3)


def year_of(chart_id: str) -> int | None:
    m = re.search(r"_((?:18|19|20)\d\d)$", chart_id or "")
    return int(m.group(1)) if m else None


def etude(row: dict) -> dict:
    """Etudes group under their composer (Ferling, Voxman, Luft), like a player; whoever played the
    recording is listed as the recording."""
    cid = row.get("chart_id", "")
    composer = re.match(r"[a-z]+", cid)
    composer = composer.group(0).title() if composer else ""
    tune = row.get("tune", "")
    m = ETUDE.match(tune)
    book, title = (m.group("book").strip(), m.group("rest").strip()) if m else ("", tune)
    if composer and title.lower().startswith(composer.lower()):
        title = title[len(composer):].strip()
    if m and not title:
        title = f"Page {m.group('page')}" if m.group("page") else tune
    return {"player": composer or row.get("performer", ""), "title": title or tune, "book": book,
            "played_by": row.get("performer", "")}


ENSEMBLE = re.compile(r"\s+(quartet|quintet|sextet|trio|orchestra|big band|band|group)$", re.I)


def player_name(name: str) -> str:
    """"Stan Getz, Oscar Peterson Trio" -> "Stan Getz"; "Stan Getz Quartet" -> "Stan Getz"."""
    first = (name or "").split(",")[0].strip()
    return ENSEMBLE.sub("", first).strip() or (name or "").strip()


def horn_from_name(path: str) -> str:
    m = re.search(r"\b(alto|tenor|soprano|baritone|bari)\b", Path(path or "").name, re.I)
    word = m.group(1).lower() if m else ""
    return "baritone" if word == "bari" else HORNS.get(word, "")


def key_item(row: dict, tags: dict, report: dict) -> dict:
    cid = row.get("chart_id", "")
    tag = tags.get(cid) or {}
    rep = report.get(cid) or {}
    kind = row.get("kind", "")
    item = {"id": cid, "source": "key", "kind": kind, "kind_name": KINDS.get(kind, kind.replace("_", " ")),
            "title": row.get("tune", "") or cid, "player": tag.get("player") or player_name(row.get("performer", "")),
            "played_by": "", "book": "", "record": row.get("recording", "") or tag.get("album") or "",
            "horn": HORNS.get((row.get("horn") or "").lower()) or HORNS.get((tag.get("horn") or "").lower(), "")
            or horn_from_name(row.get("pdf", "")),
            "year": tag.get("year") or year_of(cid), "style": tag.get("style") or "",
            "heard": fraction(row.get("heard_agree")), "coverage": fraction(row.get("coverage")),
            "audit": row.get("audit", ""), "href": None}
    if kind == "youtube_etude":
        item.update(etude(row))
    if tag.get("title") and kind != "youtube_etude":
        item["title"] = tag["title"]
    item["decade"] = f"{item['year'] // 10 * 10}s" if item["year"] else ""
    if rep.get("in_training"):
        item["use"] = "training"
    elif cid in tags or rep.get("benchmark"):
        item["use"] = "benchmark"
    else:
        item["use"] = None
    return item


def take_item(job: dict) -> dict:
    added = job.get("added") or ""
    return {"id": job["id"], "source": "saxscribe", "kind": "take",
            "kind_name": "Band record" if job.get("mix") else "Solo take",
            "title": job.get("title") or job["id"], "player": job.get("artist") or "", "played_by": "", "book": "",
            "record": "", "horn": job.get("horn", ""), "year": int(added[:4]) if added[:4].isdigit() else None,
            "decade": "", "style": "", "heard": None, "coverage": None, "audit": "", "use": None,
            "added": added, "href": f"/take/{job['id']}"}


AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".aif", ".aiff", ".ogg"}


def etude_links(runs: str | Path | None) -> dict:
    """keys/etudes/links.csv by take: where each etude recording and its lined-up key live."""
    path = runs_dir(runs) / "keys" / "etudes" / "links.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {r["take"]: r for r in csv.DictReader(f) if r.get("take")}


def files(runs: str | Path | None, row: dict, rep: dict | None, etudes: dict) -> dict:
    """This song's files on the Mac: pdf, audio (the recording the match used), key (its answer key
    lined up with that recording) and stem (a sax-only stem in the song's folder, when one was made).
    Audio that the links file fingerprints is checked like the PDF; a changed recording is left out."""
    out = {"pdf": local_path(runs, row.get("pdf", "")), "audio": None, "key": None, "stem": None}
    if rep:
        out["audio"] = review.resolve(runs, rep.get("audio"))
        out["key"] = review.resolve(runs, rep.get("key_json"))
    if out["audio"] is None and row.get("chart_id") in etudes:
        link = etudes[row["chart_id"]]
        audio = local_path(runs, link.get("audio_mac", ""))
        want = (link.get("audio_sha256") or "").strip().lower()
        if audio is not None and audio.is_file() and (not want or sha256(audio) == want):
            out["audio"] = audio
        key = runs_dir(runs) / "keys" / "etudes" / (link.get("aligned_key") or "")
        out["key"] = key if link.get("aligned_key") and key.is_file() else None
    a = out["audio"]
    if a is not None and (not a.is_file() or a.suffix.lower() not in AUDIO):
        out["audio"] = a = None
    if out["key"] is not None and out["key"].suffix.lower() != ".json":
        out["key"] = None
    if a is not None and a.parent.name == row.get("chart_id"):  # only a song's own folder, never a shared one
        stems = sorted(a.parent.glob("extras/**/stem.wav"))
        out["stem"] = stems[0] if stems else None
    return out


def _matched(runs: str | Path | None):
    """(rows, about, hidden): the matched ledger rows whose PDF is unchanged, one per chart."""
    found = ledger.full_rows(runs)
    rows, about = found if found else ([], None)
    ok, seen, hidden = [], set(), {"missing": 0, "changed": 0}
    matched = [r for r in rows if r.get("status") == "matched"]
    for row in matched:
        if row.get("chart_id") in seen:
            continue  # a second copy of the same chart (e.g. a book split twice)
        state = fingerprint_ok(runs, row)
        if state != "ok":
            hidden[state] += 1
            continue
        seen.add(row.get("chart_id"))
        ok.append(row)
    return ok, about, hidden, rows, len({r.get("chart_id") for r in matched})


def load(runs: str | Path | None = None, takes: list[dict] | None = None) -> dict:
    """{songs: [...], counts: {...}, ledger: {generated, from} or None}."""
    ok, about, hidden, rows, n_matched = _matched(runs)
    tags = benchmark_tags()
    report = {e["id"]: e for e in review.load(runs)["entries"]}
    etudes = etude_links(runs)
    with_cover = covers.have()
    songs = []
    for row in ok:
        item = key_item(row, tags, report)
        f = files(runs, row, report.get(row.get("chart_id")), etudes)
        item.update(href=f"/library/{item['id']}", has_audio=f["audio"] is not None,
                    cover=f"/api/library/{item['id']}/cover" if item["id"] in with_cover else None)
        songs.append(item)
    done = [take_item(j) for j in (takes or []) if j.get("state") == "done"]
    charts = (about or {}).get("charts") or sum(1 for r in rows if r.get("status") != "excluded")
    return {"songs": songs + done,
            "counts": {"keys": len(songs), "takes": len(done), "matched": n_matched, "charts": charts,
                       "hidden_missing": hidden["missing"], "hidden_changed": hidden["changed"]},
            "ledger": about}


def song(runs: str | Path | None, song_id: str) -> tuple[dict, dict]:
    """(the song's page fields, its files on the Mac) for one matched chart; KeyError otherwise."""
    ok, _, _, _, _ = _matched(runs)
    row = next((r for r in ok if r.get("chart_id") == song_id), None)
    if row is None:
        raise KeyError(song_id)
    report = {e["id"]: e for e in review.load(runs)["entries"]}
    rep = report.get(song_id)
    item = key_item(row, benchmark_tags(), report)
    f = files(runs, row, rep, etude_links(runs))
    rep = rep or {}
    item.update(href=f"/library/{song_id}", has_audio=f["audio"] is not None, has_stem=f["stem"] is not None,
                has_key=f["key"] is not None, clip=solo_clip(f["key"]) if f["audio"] is not None else None,
                match={"verdict": rep.get("verdict"), "reason": rep.get("reason") or row.get("reason", ""),
                       "length_s": rep.get("length_s"), "tempo_jumps": rep.get("tempo_jumps"),
                       "checked": rep.get("checked"), "austin": rep.get("austin_verdict") or None})
    return item, f


CLIP_PAD = 3.0  # seconds of the record kept before the solo's first note and after its last


def solo_clip(key: Path | None, pad: float = CLIP_PAD) -> dict | None:
    """Where the transcribed solo sits in the record: {start, end} in seconds, padded, from the key's
    own note times (the line-up check put them on the record's clock). None without a key."""
    try:
        notes = review.notes_in(key)
    except (OSError, ValueError):
        return None
    if not notes:
        return None
    first = min(n["onset"] for n in notes)
    last = max(n.get("offset") or n["onset"] for n in notes)
    return {"start": round(max(0.0, first - pad), 2), "end": round(last + pad, 2),
            "first_note": round(first, 2), "last_note": round(last, 2)}


def bars_file(runs: str | Path | None, song_id: str, key: Path | None) -> Path | None:
    """The page reading (score reader's bars, written pitch) that goes with a key, if any."""
    cands = []
    if key is not None:
        cands.append(key.parent / f"{song_id}_bars.txt")
    m = re.match(r"(ferling|luft)(\d+)_", song_id)
    if m:
        etude_keys = runs_dir(runs) / "keys" / "etudes" / "keys"
        cands.append(etude_keys / (f"study{int(m.group(2)):02d}_bars.txt" if m.group(1) == "ferling"
                                   else f"luft{int(m.group(2)):02d}_bars.txt"))
    return next((c for c in cands if c.is_file()), None)


def masks(runs: str | Path | None, song_id: str) -> str:
    """Bars the newest answer-key audit says to mask for this song ("9-17 35-38"), or ""."""
    audits = sorted((runs_dir(runs) / "keys" / "_audit").glob("*/masks_suggested.csv"))
    for path in reversed(audits):
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                if row.get("id") == song_id:
                    return row.get("bars_to_mask", "")
    return ""


def play_take(runs: str | Path | None, song_id: str, library_root: Path):
    """(the key as a take folder, a job dict for the player) for one matched song.
    KeyError when the song isn't in the Library; LookupError when it has no key or recording."""
    from . import key_take
    item, f = song(runs, song_id)
    if f["key"] is None or f["audio"] is None:
        raise LookupError("This song has no answer key or recording to play along with on this Mac.")
    take = key_take.build(f["key"], bars_file(runs, song_id, f["key"]), item["horn"],
                          Path(library_root) / "_keys" / song_id / "take", masks(runs, song_id),
                          item["title"], item["player"])
    job = {"id": song_id, "title": item["title"], "artist": item["player"], "horn": item["horn"] or "concert",
           "mix": item.get("has_stem", False), "engine": "answer_key", "state": "done", "library": True,
           "pdf": f"/api/library/{song_id}/pdf", "credit": "Answer key from the chart",
           "clip": item.get("clip")}
    return take, job, f
