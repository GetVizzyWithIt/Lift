"""The Review page (app/review_inbox.py): questions the Mac scripts couldn't settle, and Austin's answers."""
from __future__ import annotations

import json

import pytest

from saxscribe.app import review_inbox as rq
from tests.test_library_page import make_runs

CHECK = "x_check_1950"  # in the ledger at status "check", same two-page PDF as the Webster chart
WEBSTER = "ben-webster_the-touch-of-your-lips_1959"  # matched, in the match report


def key_with_bars(path):
    """Eight bars of quarter notes at 120 bpm (two seconds a bar), starting at 10 s."""
    notes = []
    for bar in range(1, 9):
        for beat in range(4):
            t = 10.0 + (bar - 1) * 2.0 + beat * 0.5
            notes.append({"onset": t, "offset": t + 0.45, "pitch": 60 + beat, "bar": bar,
                          "beat": (bar - 1) * 4 + beat, "written": None})
    path.write_text(json.dumps(notes))
    return path


def make(tmp_path):
    runs = make_runs(tmp_path)
    song = runs / "keys" / "transcribed" / CHECK
    song.mkdir(parents=True)
    key_with_bars(song / f"{CHECK}_key.json")
    (song / f"{CHECK}.mp3").write_bytes(b"ID3 check record")
    q = runs / "review" / "queues"
    for name, plugin, items in [
        ("match_check", "match_check", [
            {"id": "m1", "chart_id": CHECK, "question": "Do bars 3 to 5 match what you hear?",
             "listen_for": "the run into bar 4", "why": "aligner drifts at bar 4", "tried": ["v2 aligner", "octave check"],
             "bars": [3, 5], "focus_bar": 4, "key": f"keys/transcribed/{CHECK}/{CHECK}_key.json",
             "audio": f"keys/transcribed/{CHECK}/{CHECK}.mp3"},
            {"id": "m2", "chart_id": WEBSTER, "question": "Is this the same performance?"},
            {"id": "no-question"},  # not shown: every item needs a question
        ]),
        ("falkowski_page_start", "page_start", [
            {"id": "s1", "song": "Falkowski excerpt 12", "question": "Where does bar 1 begin?",
             "audio": f"keys/transcribed/{CHECK}/{CHECK}.mp3", "guesses": [{"label": "A", "time": 31}, {"label": "B", "time": 64}]},
        ]),
        ("weimar_listens", "yes_no_listen", [
            {"id": "l1", "song": "Mobley, Remember", "question": "Sax or trumpet in bar 42?",
             "choices": [{"value": "sax", "label": "Sax"}, {"value": "trumpet", "label": "Trumpet"}]},
        ]),
        ("note_ends", "tap_end", [{"id": "n1", "question": "Where does this note end?"}]),  # retired
    ]:
        (q / name).mkdir(parents=True)
        (q / name / "items.json").write_text(json.dumps({"queue": name, "plugin": plugin, "items": items}))
    return runs


def test_inbox_lists_questions_and_never_note_ends(tmp_path):
    runs = make(tmp_path)
    box = rq.inbox(runs)
    assert [(i["queue"], i["id"]) for i in box["items"]] == [
        ("falkowski_page_start", "s1"), ("match_check", "m1"), ("match_check", "m2"), ("weimar_listens", "l1")]
    assert box["left"] == 4 and box["minutes"] == 3 and box["done"] == 0
    kinds = {i["id"]: i["kind"] for i in box["items"]}
    assert kinds == {"s1": "Where it starts", "m1": "Match check", "m2": "Match check", "l1": "Quick listen"}
    assert {i["id"]: i["song"] for i in box["items"]}["m2"] == "The Touch of Your Lips, Ben Webster"


def test_detail_finds_the_bars_on_the_recording_and_the_page(tmp_path, monkeypatch):
    from saxscribe.app import pdf_pages
    monkeypatch.setattr(pdf_pages, "CACHE", tmp_path / "pages")
    d = rq.detail(make(tmp_path), "match_check", "m1")
    assert d["plugin"] == "match_check" and d["bars"] == [3, 5] and d["focus_bar"] == 4
    assert [b["bar"] for b in d["bar_times"]] == [3, 4, 5]
    assert d["bar_times"][0]["start"] == 14.0 and d["bar_times"][-1]["end"] == 19.95
    assert d["loop"] == {"start": 13.0, "end": 20.95}
    assert d["has_audio"] and d["has_key"] and d["can_draw"] and not d["has_stem"]
    assert d["pages"] == 2 and d["page"]["exact"] is False and d["page"]["page"] == 1  # bar 3 of 8, two pages
    assert [c["value"] for c in d["choices"]] == ["same", "different", "bar_wrong", "cant_tell"]
    assert d["tried"] == ["v2 aligner", "octave check"] and d["answered"] is None


def test_an_items_own_page_and_crop_win_over_the_guess():
    g = rq.page_guess({"page": 2, "top": 0.4, "bottom": 0.6}, 3, (1, 2), 40)
    assert g == {"page": 2, "exact": True, "crop": {"top": 0.4, "bottom": 0.6}}
    assert rq.page_guess({}, 3, (30, 32), 40)["page"] == 3
    assert rq.page_guess({}, 0, (30, 32), 40) is None


def test_answers_save_undo_and_reach_the_match_review(tmp_path):
    runs = make(tmp_path)
    with pytest.raises(ValueError):
        rq.save(runs, "match_check", "m2", "maybe")
    with pytest.raises(ValueError):
        rq.save(runs, "match_check", "m2", "bar_wrong")  # which bar?
    rq.save(runs, "match_check", "m2", "bar_wrong", "the turnaround", {"bar": 12, "ignored": 1})
    got = rq.answers(runs)[("match_check", "m2")]
    assert got["answer"] == "bar_wrong" and got["bar"] == 12 and "ignored" not in got and got["chart_id"] == WEBSTER
    from saxscribe.score import review
    mine = {e["id"]: e for e in review.load(runs)["entries"]}[WEBSTER]
    assert mine["austin_verdict"] == "good" and mine["austin_note"] == "bar 12 wrong on the chart: the turnaround"
    assert rq.inbox(runs)["left"] == 3
    rq.save(runs, "match_check", "m2", "undo")
    assert ("match_check", "m2") not in rq.answers(runs) and rq.inbox(runs)["left"] == 4
    assert {e["id"]: e for e in review.load(runs)["entries"]}[WEBSTER]["austin_verdict"] is None
    # a chart that isn't in the match report only goes to answers.jsonl
    rq.save(runs, "match_check", "m1", "different")
    assert CHECK not in {e["id"] for e in review.load(runs)["entries"]}


def test_start_point_and_listen_answers(tmp_path):
    runs = make(tmp_path)
    with pytest.raises(ValueError):
        rq.save(runs, "falkowski_page_start", "s1", "tap")  # no time
    rq.save(runs, "falkowski_page_start", "s1", "guess", extra={"time": 64, "choice": "B"})
    a = rq.answers(runs)[("falkowski_page_start", "s1")]
    assert a["time"] == 64.0 and a["choice"] == "B" and a["plugin"] == "start_point"
    with pytest.raises(ValueError):
        rq.save(runs, "weimar_listens", "l1", "other")  # this item asks sax or trumpet
    rq.save(runs, "weimar_listens", "l1", "trumpet")
    with pytest.raises(KeyError):
        rq.save(runs, "note_ends", "n1", "anything")


def test_review_routes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("pypdfium2")
    from fastapi.testclient import TestClient

    from saxscribe.app import pdf_pages
    from saxscribe.app.library import Library
    from saxscribe.app.server import create_app

    monkeypatch.setattr(pdf_pages, "CACHE", tmp_path / "pages")
    c = TestClient(create_app(Library(tmp_path / "lib", inline=True), runs=make(tmp_path)))
    assert "review.js" in c.get("/review").text
    assert c.get("/api/review/inbox").json()["left"] == 4
    base = "/api/review/item/match_check/m1"
    assert c.get(base).json()["bars"] == [3, 5]
    assert c.get("/api/review/item/match_check/nope").status_code == 404
    assert c.get("/api/review/item/note_ends/n1").status_code == 404
    assert c.get(f"{base}/audio/record").content == b"ID3 check record"
    assert c.get(f"{base}/audio/stem").status_code == 404
    assert len(c.get(f"{base}/key").json()["notes"]) == 32
    whole = c.get(f"{base}/page/1")
    strip = c.get(f"{base}/page/1?top=0.25&bottom=0.5")
    assert whole.content[:4] == strip.content[:4] == b"\x89PNG" and len(strip.content) < len(whole.content)
    assert c.get(f"{base}/page/9").status_code == 404
    assert c.get(f"{base}/pdf").headers["content-type"] == "application/pdf"
    r = c.post(f"{base}/answer", json={"answer": "same", "note": ""})
    assert r.status_code == 200 and r.json()["inbox"]["left"] == 3
    assert c.post(f"{base}/answer", json={"answer": "nonsense"}).status_code == 400
    assert c.get(base).json()["answered"]["answer"] == "same"


def test_the_bars_in_question_are_engraved_from_the_key(tmp_path):
    pytest.importorskip("verovio")
    pytest.importorskip("music21")
    runs = make(tmp_path)
    out = rq.engraved(runs, "match_check", "m1", tmp_path / "lib")
    assert out["bars"] == [3, 4, 5] and out["svg"].count('class="measure') == 3
    with pytest.raises(LookupError):
        rq.engraved(runs, "weimar_listens", "l1", tmp_path / "lib")  # no key, no bars
