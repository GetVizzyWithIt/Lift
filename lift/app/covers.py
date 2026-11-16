"""Album covers for the Library cards.

Each answer key's card shows its record's cover; a song with no cover (and every one of your own
takes) shows the Lift icon instead. Covers are found once, on the Mac, by `python -m lift covers`,
and saved in ~/.cache/lift/covers/<song id>.jpg (or .png). The app only reads that folder.

Where a cover comes from, first match wins:
  1. overrides.csv in the covers folder (id,source): a URL or file path to use, or "none" for the logo.
     This is how a cover from the "needs a look" list gets approved, or a wrong one gets dropped.
  2. Art embedded in the recording itself (MP3/M4A tags), pulled out with ffmpeg. Offline.
  3. An image saved next to the recording: same name as the audio file, or cover/folder/front.jpg.
     Internet Archive downloads often come with one (the 78's label).
  4. Cover Art Archive (the free cover library behind MusicBrainz), looked up by player and record
     (or tune). Only the names go out, never audio. A lookup is used only when MusicBrainz scores it
     90+ and the player's surname is in the release's artist; anything weaker goes on the
     "needs a look" list with its link, and the card keeps the logo.

Each run writes _summary.txt and needs_a_look.csv in the covers folder.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .. import paths

EXTS = (".jpg", ".png")
NEAR = ("cover", "folder", "front", "album")
USER_AGENT = "Lift/1.0 (personal sax transcription tool; https://github.com/GetVizzyWithIt/lift)"
MB = "https://musicbrainz.org/ws/2/"
CAA = "https://coverartarchive.org/release/{}/front-250"
SURE = 90  # MusicBrainz match score (0-100) needed to use a lookup without a look


def folder() -> Path:
    return paths.cache() / "covers"


def cached(song_id: str, where: Path | None = None) -> Path | None:
    where = where or folder()
    for ext in EXTS:
        p = where / f"{song_id}{ext}"
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def have(where: Path | None = None) -> set[str]:
    """Song ids with a saved cover, from one directory listing (the Library asks for every song)."""
    where = where or folder()
    if not where.is_dir():
        return set()
    return {p.stem for p in where.iterdir() if p.suffix in EXTS and p.stat().st_size > 0}


def _kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return None


def save(song_id: str, data: bytes, where: Path | None = None) -> Path | None:
    """Keep a cover (JPEG or PNG only); anything else is refused."""
    ext = _kind(data)
    if not ext:
        return None
    where = where or folder()
    where.mkdir(parents=True, exist_ok=True)
    for old in EXTS:
        (where / f"{song_id}{old}").unlink(missing_ok=True)
    out = where / f"{song_id}{ext}"
    out.write_bytes(data)
    return out


def embedded(audio: Path) -> bytes | None:
    """The picture stored inside the audio file's tags, if any."""
    if not shutil.which("ffmpeg") or not audio.is_file():
        return None
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(audio), "-an", "-map", "0:v:0", "-frames:v", "1",
                        "-c:v", "mjpeg", "-f", "image2pipe", "-"], capture_output=True)
    return r.stdout if r.returncode == 0 and _kind(r.stdout) else None


def nearby(audio: Path) -> bytes | None:
    """An image saved beside the recording: <audio name>.jpg/.png, or cover/folder/front/album."""
    if not audio.parent.is_dir():
        return None
    names = [audio.stem.lower()] + list(NEAR)
    files = {p.name.lower(): p for p in audio.parent.iterdir() if p.is_file()}
    for name in names:
        for ext in (".jpg", ".jpeg", ".png"):
            p = files.get(name + ext)
            if p:
                data = p.read_bytes()
                if _kind(data):
                    return data
    return None


def _get(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _clean(s: str) -> str:
    return re.sub(r'[\\+\-!(){}\[\]^"~*?:/]|&&|\|\|', " ", s or "").strip()


def surname(player: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", player or "")
    return words[-1].lower() if words else ""


def lookup(player: str, record: str, title: str, get=_get) -> dict | None:
    """The best Cover Art Archive candidate: {url, score, release, artist, sure} or None.
    Searches releases by record name when there is one, else recordings by tune; MusicBrainz asks
    for at most one request a second, so callers wait between songs."""
    if not player or not (record or title):
        return None
    if record:
        q = f'release:"{_clean(record)}" AND artist:"{_clean(player)}"'
        data = json.loads(get(MB + "release/?" + urllib.parse.urlencode({"query": q, "fmt": "json", "limit": 5})))
        releases = [(r.get("score", 0), r) for r in data.get("releases", [])]
    else:
        q = f'recording:"{_clean(title)}" AND artist:"{_clean(player)}"'
        data = json.loads(get(MB + "recording/?" + urllib.parse.urlencode({"query": q, "fmt": "json", "limit": 5})))
        releases = [(rec.get("score", 0), rel) for rec in data.get("recordings", []) for rel in rec.get("releases", [])]
    want = surname(player)
    for score, rel in releases:
        artist = " ".join(c.get("name", "") for c in rel.get("artist-credit", []) if isinstance(c, dict))
        if not rel.get("id"):
            continue
        sure = bool(record) and score >= SURE and bool(want) and want in artist.lower()
        return {"url": CAA.format(rel["id"]), "score": score, "release": rel.get("title", ""), "artist": artist,
                "sure": sure}
    return None


def overrides(where: Path) -> dict[str, str]:
    p = where / "overrides.csv"
    if not p.is_file():
        return {}
    with p.open(newline="") as f:
        return {r["id"].strip(): (r.get("source") or "").strip() for r in csv.DictReader(f) if r.get("id")}


def _bar(i: int, n: int, label: str) -> None:
    width = 30
    done = int(width * i / n) if n else width
    sys.stdout.write(f"\r[{'#' * done}{'.' * (width - done)}] {i}/{n} {label[:40]:<40}")
    sys.stdout.flush()


def run(runs: str | Path | None = None, online: bool = True, redo: bool = False, where: Path | None = None,
        songs: list[dict] | None = None, audio_of=None, get=_get, pause: float = 1.1) -> dict:
    """Find a cover for every Library answer key that has none yet. Returns the counts it wrote to
    _summary.txt; unsure lookups go to needs_a_look.csv for a check."""
    from . import catalog
    where = where or folder()
    where.mkdir(parents=True, exist_ok=True)
    if songs is None:
        songs = [s for s in catalog.load(runs)["songs"] if s.get("source") == "key"]
    if audio_of is None:
        def audio_of(song):
            try:
                return catalog.song(runs, song["id"])[1].get("audio")
            except KeyError:
                return None
    over = overrides(where)
    counts = {"songs": len(songs), "already": 0, "override": 0, "embedded": 0, "nearby": 0, "lookup": 0,
              "logo": 0, "needs_a_look": 0, "errors": 0}
    look, log = [], []
    for i, s in enumerate(songs, 1):
        sid = s["id"]
        _bar(i, len(songs), s.get("title", sid))
        src = over.get(sid)
        if src is not None:
            data = None
            if src.lower() != "none":
                try:
                    data = get(src) if src.startswith("http") else Path(src).expanduser().read_bytes()
                except Exception as e:  # noqa: BLE001 - one bad override shouldn't stop the run
                    counts["errors"] += 1
                    log.append(f"{sid}\toverride failed: {e}")
            for ext in EXTS:
                (where / f"{sid}{ext}").unlink(missing_ok=True)
            if data and save(sid, data, where):
                counts["override"] += 1
                log.append(f"{sid}\toverride")
            else:
                counts["logo"] += 1
            continue
        if not redo and cached(sid, where):
            counts["already"] += 1
            continue
        audio = audio_of(s)
        audio = Path(audio) if audio else None
        found = None
        if audio:
            for how, fn in (("embedded", embedded), ("nearby", nearby)):
                data = fn(audio)
                if data and save(sid, data, where):
                    found = how
                    break
        if not found and online:
            try:
                hit = lookup(s.get("player", ""), s.get("record", ""), s.get("title", ""), get=get)
                time.sleep(pause)
                if hit and hit["sure"]:
                    if save(sid, get(hit["url"]), where):
                        found = "lookup"
                elif hit:
                    look.append({"id": sid, "title": s.get("title", ""), "player": s.get("player", ""),
                                 "record": s.get("record", ""), "found_release": hit["release"],
                                 "found_artist": hit["artist"], "score": hit["score"], "url": hit["url"]})
            except Exception as e:  # noqa: BLE001 - a 404 (no art) or a network blip: try the rest
                counts["errors"] += 1
                log.append(f"{sid}\tlookup failed: {e}")
        if found:
            counts[found] += 1
            log.append(f"{sid}\t{found}")
        else:
            counts["logo"] += 1
    sys.stdout.write("\n")
    counts["needs_a_look"] = len(look)
    with (where / "needs_a_look.csv").open("w", newline="") as f:
        cols = ["id", "title", "player", "record", "found_release", "found_artist", "score", "url"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(look)
    lines = [f"Covers run {time.strftime('%Y-%m-%d %H:%M')}"] + [f"{k}: {v}" for k, v in counts.items()]
    lines += ["", "To use a cover from needs_a_look.csv, or to drop a wrong one, add a row to overrides.csv",
              "(columns id,source; source is a URL, a file path, or none) and run again.", ""] + log
    (where / "_summary.txt").write_text("\n".join(lines) + "\n")
    return counts
