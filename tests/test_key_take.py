"""An answer key as a take folder (app/key_take.py), and the Library's play-along routes."""
from __future__ import annotations

import json

import pytest

from saxscribe.app import key_take

from .test_library_page import make_runs

SONG = "ben-webster_the-touch-of-your-lips_1959"
# Written pitch (alto, +9): bar 1 eight eighths in 4/4, bar 2 in 3/4, bar 3 back in 4/4.
BARS = """# page reading
1 @4 C5/0.5 D5/0.5 E5/0.5 F5/0.5 G5/0.5 A5/0.5 B5/0.5 C6/0.5
2 @3 Bb4/1 r/2
3 @4 G5/4
"""
WRITTEN = [72, 74, 76, 77, 79, 81, 83, 84, 70, 79]
BEATS = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 7]


def key_notes(extra=True):
    """Concert pitch, global quarter-note positions, 120 bpm. With extra: a note at beat 5 the page lacks."""
    notes = [{"onset": b * 0.5, "offset": b * 0.5 + 0.2, "pitch": w - 9, "beat": b, "bar": 1} for w, b in zip(WRITTEN, BEATS)]
    if extra:
        notes.append({"onset": 2.5, "offset": 2.7, "pitch": 65, "beat": 5, "bar": 2})
    return notes


def build(tmp_path, notes, bars=BARS, masks="", horn="alto"):
    k = tmp_path / "key.json"
    k.write_text(json.dumps(notes))
    b = None
    if bars:
        b = tmp_path / "x_bars.txt"
        b.write_text(bars)
    return key_take.build(k, b, horn, tmp_path / "take", masks)


def test_page_rhythm_with_mixed_meter(tmp_path):
    take = build(tmp_path, key_notes(extra=False), masks="3")
    nota = json.loads(take.notation.read_text())
    assert nota["made_from"] == "page" and nota["sync"] == "notes"
    assert nota["bar_starts"] == ["0", "4", "7"] and nota["bar_numbers"] == [1, 2, 3] and nota["bar_end"] == "11"
    assert sorted(n["index"] for n in nota["notes"]) == list(range(10))
    assert [n["bar"] for n in sorted(nota["notes"], key=lambda n: n["index"])] == [1] * 8 + [2, 3]
    xml = take.written_musicxml("alto").read_text()
    assert "<beats>3</beats>" in xml and "<beats>4</beats>" in xml
    assert "misread on the page" in xml and key_take.GREY in xml  # masked bar shown in grey, not hidden
    assert "<step>B</step>" in xml and "<alter>-1</alter>" in xml  # page spelling Bb4 kept
    assert take.musicxml.exists()


def test_a_key_note_the_page_lacks_is_still_written(tmp_path):
    take = build(tmp_path, key_notes(extra=True))
    nota = json.loads(take.notation.read_text())
    assert nota["made_from"] == "page"
    assert sorted(n["index"] for n in nota["notes"]) == list(range(11))  # nothing left off
    bar2 = sorted((n for n in nota["notes"] if n["bar"] == 2), key=lambda n: n["beat"])
    assert [n["beat"] for n in bar2] == ["1", "2"]


def test_key_only_when_there_is_no_page_reading(tmp_path):
    take = build(tmp_path, key_notes(), bars=None)
    nota = json.loads(take.notation.read_text())
    assert nota["made_from"] == "key" and nota["bar_starts"] == ["0", "4"]
    assert sorted(n["index"] for n in nota["notes"]) == list(range(11))


def test_sync_runs_forward_and_rebuild_is_cached(tmp_path):
    from saxscribe.app import score_view
    take = build(tmp_path, key_notes())
    pairs = score_view.sync(take)
    assert len(pairs) >= 2
    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(pairs, pairs[1:]))
    assert pairs[0] == [0.0, 0.0]
    stamp = take.notation.stat().st_mtime_ns
    build(tmp_path, key_notes())
    assert take.notation.stat().st_mtime_ns == stamp
    build(tmp_path, key_notes(), masks="2")  # masks changed: rebuilt
    assert json.loads(take.notation.read_text())["masked_bars"] == [2]


def test_bar_q_follows_bar_starts():
    from saxscribe.app.score_view import bar_q
    at = bar_q({"bar_starts": ["0", "4", "7"], "bar_numbers": [1, 2, 3], "bar_end": "11"})
    assert [at(b) for b in (1, 2, 3, 4, 5)] == [0, 4, 7, 11, 15]
    assert bar_q({})(3) == 8


def test_masked_bars():
    assert key_take.masked_bars("9-11 35, 2") == {2, 9, 10, 11, 35}
    assert key_take.time_signature(key_take.fr(2.5)) == "5/8"


def test_library_play_routes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("verovio")
    from fastapi.testclient import TestClient

    from saxscribe.app.library import Library
    from saxscribe.app.server import create_app

    runs = make_runs(tmp_path)
    song = runs / "keys" / "transcribed" / SONG
    (song / "key.json").write_text(json.dumps(key_notes()))
    (song / f"{SONG}_bars.txt").write_text(BARS)
    c = TestClient(create_app(Library(tmp_path / "lib", inline=True), runs=runs))

    assert c.get(f"/library/{SONG}/play").status_code == 200
    job = c.get(f"/api/library/{SONG}/job").json()
    assert job["engine"] == "answer_key" and job["horn"] == "tenor" and job["mix"] and job["pdf"].endswith("/pdf")
    d = c.get(f"/api/library/{SONG}/score?view=tenor").json()
    assert "<svg" in d["svg"] and d["bar_starts"] == [0.0, 4.0, 7.0] and d["bar_end"] == 11.0 and len(d["sync"]) >= 2
    assert c.get(f"/api/library/{SONG}/audio/source").status_code == 200

    r = c.post(f"/api/library/{SONG}/flags", json={"bar": 2, "to": 2, "categories": ["pitch"], "scope": "bar",
                                                   "picked": [], "text": "", "view": "tenor"})
    assert r.status_code == 200, r.text
    flags = c.get(f"/api/library/{SONG}/flags").json()
    assert [f["bar"] for f in flags["flags"]] == [2] and flags["run"]["label"].startswith("Answer key")
    assert (tmp_path / "lib" / "_keys" / SONG / "flags.json").exists()
    assert c.post(f"/api/library/{SONG}/heard", json={"bars": [1, 3]}).status_code == 200

    assert c.get("/api/library/nope/job").status_code == 404
    (song / "key.json").unlink()
    assert c.get(f"/api/library/{SONG}/job").status_code in (404, 409)


def test_solo_clip_pads_the_key_notes(tmp_path):
    from saxscribe.app import catalog
    k = tmp_path / "k.json"
    k.write_text(json.dumps([{"onset": 95.0, "offset": 95.5, "pitch": 60}, {"onset": 140.2, "offset": 141.0, "pitch": 62}]))
    assert catalog.solo_clip(k) == {"start": 92.0, "end": 144.0, "first_note": 95.0, "last_note": 141.0}
    k.write_text(json.dumps([{"onset": 1.0, "offset": 2.0, "pitch": 60}]))
    assert catalog.solo_clip(k)["start"] == 0.0  # never before the record starts
    k.write_text("[]")
    assert catalog.solo_clip(k) is None and catalog.solo_clip(None) is None


def test_song_and_play_along_carry_the_solo_clip(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from saxscribe.app.library import Library
    from saxscribe.app.server import create_app

    runs = make_runs(tmp_path)
    song = runs / "keys" / "transcribed" / SONG
    notes = [{**n, "onset": n["onset"] + 60, "offset": n["offset"] + 60} for n in key_notes()]
    (song / "key.json").write_text(json.dumps(notes))
    c = TestClient(create_app(Library(tmp_path / "lib", inline=True), runs=runs))
    clip = c.get(f"/api/library/{SONG}").json()["clip"]
    assert clip["start"] == 57.0 and clip["first_note"] == 60.0 and clip["end"] == round(max(n["offset"] for n in notes) + 3, 2)
    assert c.get(f"/api/library/{SONG}/job").json()["clip"] == clip
