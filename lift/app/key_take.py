"""An answer key as a take folder, so the play-along can show it.

The play-along (score_view.py, flags.py, play.js) reads a take folder: notes.json (what was
played, in seconds), notation.json (where each note sits in the bar) and score.musicxml. This
module writes those three files from an answer key, under <library>/_keys/<id>/take/:

  notes.json      the key's notes, in the key's order: onset and offset in the recording,
                  concert pitch. Nothing re-measured.
  notation.json   each note's bar and beat. Charts can change meter, so the start of every
                  bar is stored too ("bar_starts", quarter notes from the top), and "sync":
                  "notes" tells score_view to time the score from the key's notes alone.
  score.musicxml  the chart as sheet music, concert pitch; score-<horn>.musicxml written for
                  the chart's horn.

Rhythm and rests come from the chart's page reading (<id>_bars.txt, the score reader's bars,
written pitch), when there is one and it lines up with the key. Pitch always comes from the
key, because a proofread fix lands in the key and not in the page reading. A bar where the
key holds a note the page reading does not is written from the key alone, so no key note is
ever left off the page. Bars the audit marked as misread are written in grey with a note
above them: still shown, never hidden.

The folder is rebuilt when the key, its bars file, the masks or this module's version change.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from fractions import Fraction
from pathlib import Path

from ..horns import HORNS
from ..take import Take

VERSION = 2
GREY = "#8C877E"
TOKEN = re.compile(r"^(?P<grace>g)?(?P<name>r|[A-G][#b]*-?\d)(?:/(?P<dur>[\d.]+))?(?P<tie>~)?$")


def fr(x) -> Fraction:
    return Fraction(str(x)).limit_denominator(48)


def read_key(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    notes = data.get("notes", []) if isinstance(data, dict) else data
    return [n for n in notes if isinstance(n, dict) and n.get("beat") is not None and n.get("pitch") is not None
            and n.get("onset") is not None]


def read_bars(path: Path | None) -> list[dict]:
    """[{bar, length, tokens: [{q (from the bar's start), dur, rest, grace, name, tie}]}] from a bars.txt."""
    if path is None or not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].startswith("@"):
            continue
        length, q, tokens = fr(parts[1][1:]), Fraction(0), []
        for tok in parts[2:]:
            m = TOKEN.match(tok)
            if not m:
                continue
            if m.group("grace"):
                tokens.append({"q": q, "dur": Fraction(0), "rest": False, "grace": True, "name": m.group("name"), "tie": False})
                continue
            dur = fr(m.group("dur") or 1)
            tokens.append({"q": q, "dur": dur, "rest": m.group("name") == "r", "grace": False,
                           "name": m.group("name"), "tie": bool(m.group("tie"))})
            q += dur
        out.append({"bar": int(parts[0]), "length": length, "tokens": tokens})
    return out


def masked_bars(text: str) -> set[int]:
    """"9-17 35-38 86" -> {9..17, 35..38, 86}."""
    out: set[int] = set()
    for part in re.split(r"[\s,;]+", text or ""):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            out.update(range(a, b + 1))
    return out


def m21_name(name: str) -> str:
    """bars.txt spelling (Bb4, C#5) -> music21 (B-4, C#5)."""
    m = re.match(r"([A-G])([#b]*)(-?\d)$", name)
    if not m:
        return name
    return m.group(1) + m.group(2).replace("b", "-") + m.group(3)


def layout(key: list[dict], bars: list[dict]) -> tuple[list[dict], str]:
    """Each bar's events: [{bar, start, length, events: [{q, dur, rest, grace, key (index) or None,
    name (page spelling) or None, tie}]}], and how it was made ("page" or "key")."""
    order = sorted(range(len(key)), key=lambda i: (fr(key[i]["beat"]), i))
    if bars:
        starts, s = [], Fraction(0)
        for b in bars:
            starts.append(s)
            s += b["length"]
        page_q = {starts[k] + t["q"] for k, b in enumerate(bars) for t in b["tokens"] if not t["rest"] and not t["grace"]}
        plain = [i for i in order if not key[i].get("grace")]
        hit = sum(1 for i in plain if fr(key[i]["beat"]) in page_q)
        if plain and hit / len(plain) >= 0.9:
            return _from_page(key, order, bars, starts), "page"
    return _from_key(key, order), "key"


def _key_bar(key, idx, start, length, bar_no):
    """A bar written from the key alone: each note lasts until the next one (or the bar line)."""
    ev, q = [], start
    plain = [i for i in idx if not key[i].get("grace")]
    for i in idx:
        if key[i].get("grace"):
            ev.append({"q": fr(key[i]["beat"]) - start, "dur": Fraction(0), "rest": False, "grace": True,
                       "key": i, "name": None, "tie": False})
    for k, i in enumerate(plain):
        at = max(fr(key[i]["beat"]), q)
        if at > q:
            ev.append({"q": q - start, "dur": at - q, "rest": True, "grace": False, "key": None, "name": None, "tie": False})
        end = fr(key[plain[k + 1]]["beat"]) if k + 1 < len(plain) else start + length
        end = min(max(end, at + Fraction(1, 12)), start + length)
        if end <= at:  # two key notes on one spot: the later one still gets written, a 32nd on
            end = at + Fraction(1, 8)
        ev.append({"q": at - start, "dur": end - at, "rest": False, "grace": False, "key": i, "name": None, "tie": False})
        q = end
    if q < start + length:
        ev.append({"q": q - start, "dur": start + length - q, "rest": True, "grace": False, "key": None, "name": None, "tie": False})
    ev.sort(key=lambda e: (e["q"], not e["grace"]))
    return {"bar": bar_no, "start": start, "length": max(length, q - start), "events": ev}


def _from_key(key, order):
    by_bar: dict[int, list[int]] = {}
    for i in order:
        by_bar.setdefault(int(fr(key[i]["beat"]) // 4) + 1, []).append(i)
    last = max(by_bar, default=0)
    return [_key_bar(key, by_bar.get(b, []), Fraction(4 * (b - 1)), Fraction(4), b) for b in range(1, last + 1)]


def _from_page(key, order, bars, starts):
    at: dict[Fraction, list[int]] = {}
    for i in order:
        at.setdefault(fr(key[i]["beat"]), []).append(i)
    used: set[int] = set()
    out = []
    for k, b in enumerate(bars):
        s, ev = starts[k], []
        for t in b["tokens"]:
            e = {**t, "key": None}
            if not t["rest"]:
                pick = [i for i in at.get(s + t["q"], []) if i not in used and bool(key[i].get("grace")) == t["grace"]]
                if pick:
                    e["key"] = pick[0]
                    used.add(pick[0])
            ev.append(e)
        out.append({"bar": b["bar"], "start": s, "length": b["length"], "events": ev})
    # Key notes the page reading doesn't have: write those bars from the key alone.
    for i in order:
        if i in used:
            continue
        q = fr(key[i]["beat"])
        k = max((j for j, s in enumerate(starts) if s <= q), default=None)
        if k is None or q >= starts[k] + bars[k]["length"]:
            continue  # past the last bar: caught below
        idx = [j for j in order if starts[k] <= fr(key[j]["beat"]) < starts[k] + bars[k]["length"]]
        out[k] = _key_bar(key, idx, starts[k], bars[k]["length"], bars[k]["bar"])
        used.update(idx)
    rest = [i for i in order if i not in used]
    if rest:  # notes after the page's last bar
        end = starts[-1] + bars[-1]["length"]
        extra = _from_key(key, [i for i in rest if fr(key[i]["beat"]) >= end])
        n = bars[-1]["bar"]
        for b in extra:
            if b["start"] >= end:
                n += 1
                out.append({**b, "bar": n})
    return out


def time_signature(ql: Fraction) -> str | None:
    """A bar's length in quarter notes as a meter: 4 -> 4/4, 3 -> 3/4, 2.5 -> 5/8, 3.75 -> 15/16."""
    for unit in (4, 8, 16):
        n = ql * unit / 4
        if n.denominator == 1 and n > 0:
            return f"{n.numerator}/{unit}"
    return None


def _sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
        h.update(b"\0")
    return h.hexdigest()


def build(key_path: Path, bars_path: Path | None, horn: str, folder: Path, masks: str = "",
          title: str = "", player: str = "") -> Take:
    """Write (or reuse) the take folder for one answer key. horn "" = concert pitch only."""
    take = Take(folder)
    stamp = _sha(VERSION, key_path.read_bytes(), bars_path.read_bytes() if bars_path and bars_path.exists() else b"",
                 masks, horn)
    marker = folder / "key_source.json"
    if marker.exists() and json.loads(marker.read_text()).get("sha") == stamp and take.notation.exists():
        return take
    folder.mkdir(parents=True, exist_ok=True)
    key = read_key(key_path)
    bars, made_from = layout(key, read_bars(bars_path))
    mask = masked_bars(masks)
    h = HORNS.get(horn)
    shift = h.written_shift if h else 0

    from music21 import expressions, interval, meter, note, stream
    part = stream.Part()
    part.partName = f"{h.name.capitalize()} Sax in {h.key}" if h else "Concert pitch"
    nota, last_len = [], None
    for b in bars:
        m = stream.Measure(number=b["bar"])
        if b["length"] != last_len:
            ts = time_signature(b["length"])
            if ts:
                m.timeSignature = meter.TimeSignature(ts)
            last_len = b["length"]
        grey = b["bar"] in mask
        if grey and b["bar"] - 1 not in mask:  # one note per run of masked bars
            m.insert(0, expressions.TextExpression("misread on the page"))
        filled = Fraction(0)
        for e in b["events"]:
            if e["rest"]:
                if e["q"] < filled:
                    continue
                if e["q"] > filled:
                    r = note.Rest(quarterLength=e["q"] - filled)
                    m.append(r)
                r = note.Rest(quarterLength=min(e["dur"], b["length"] - e["q"]) or e["dur"])
                m.append(r)
                filled = e["q"] + r.quarterLength
                continue
            kn = key[e["key"]] if e["key"] is not None else None
            if kn is not None:
                midi = int(round(float(kn["pitch"]))) + shift
                n = note.Note(midi=midi)
                page = e.get("name") if e.get("name") not in (None, "r") else kn.get("written")
                if page:
                    try:
                        spelled = note.Note(m21_name(page))
                        if spelled.pitch.midi == midi:
                            n = note.Note(m21_name(page))
                    except Exception:
                        pass
            else:  # on the page but not in the key: written as the page has it
                n = note.Note(m21_name(e["name"]))
            if grey:
                n.style.color = GREY
            if e["grace"]:
                n = n.getGrace()
                m.append(n)
            else:
                if e["q"] > filled:
                    m.append(note.Rest(quarterLength=e["q"] - filled))
                n.quarterLength = e["dur"]
                if e.get("tie"):
                    from music21 import tie
                    n.tie = tie.Tie("start")
                m.append(n)
                filled = e["q"] + e["dur"]
            if kn is not None:
                nota.append({"index": e["key"], "bar": b["bar"], "beat": str(e["q"] + 1),
                             "pitch": int(round(float(kn["pitch"]))), "length_beats": str(e["dur"]),
                             "grace": bool(e["grace"])})
        if filled < b["length"]:
            m.append(note.Rest(quarterLength=b["length"] - filled))
        part.append(m)
    score = stream.Score()
    score.insert(0, part)
    if h:
        written = score
        written.write("musicxml", fp=str(take.written_musicxml(horn)))
        concert = score.transpose(interval.Interval(h.written_interval).reverse())
        for p in concert.parts:
            p.partName = "Concert pitch"
        concert.write("musicxml", fp=str(take.musicxml))
    else:
        score.write("musicxml", fp=str(take.musicxml))

    played = [{"onset": float(n["onset"]), "offset": float(n.get("offset", n["onset"])),
               "pitch": float(n["pitch"])} for n in key]
    take.notes.write_text(json.dumps({"notes": played, "beats": [], "source": "answer key"}) + "\n")
    take.notation.write_text(json.dumps({
        "notes": [x for x in nota if not x["grace"]], "grace_notes": [x for x in nota if x["grace"]],
        "bar_starts": [str(b["start"]) for b in bars], "bar_numbers": [b["bar"] for b in bars],
        "bar_end": str(bars[-1]["start"] + bars[-1]["length"]) if bars else "0",
        "sync": "notes", "masked_bars": sorted(mask), "made_from": made_from, "beat_shift": "0"}) + "\n")
    made = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(key_path.stat().st_mtime))
    take.manifest.write_text(json.dumps({"horn": horn, "layers": {"notes": {"made": made, "tool": "answer_key"},
                                                                  "notation": {"made": made, "tool": "answer_key"}}}) + "\n")
    # score-<horn>.musicxml must not look older than notation.json, or score_view remakes it from concert
    if h:
        take.written_musicxml(horn).touch()
    marker.write_text(json.dumps({"sha": stamp, "key": str(key_path), "bars": str(bars_path or ""),
                                  "made_from": made_from, "title": title, "player": player}) + "\n")
    return take
