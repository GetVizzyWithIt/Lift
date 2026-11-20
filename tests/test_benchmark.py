"""The growing benchmark (score/benchmark.py): split rules, the session rule, and a resumable scoring run."""
from __future__ import annotations

import csv
import json

from lift.score import benchmark
from tests.test_library_page import make_runs

RULE = {"held_out_players": ["Hank Mobley", "Sonny Stitt"], "test_kinds": ["test_tune"]}


def item(cid, player, **kw):
    base = {"id": cid, "kind": "transcribed", "player": player, "tune": cid, "horn": "tenor", "year": None,
            "album": "", "mix": True, "audio": "a.mp3", "key": "k.json", "in_training": False, "e81": False}
    return {**base, **kw}


def tiers(rows):
    return {r["id"]: (r["tier"], r["why"]) for r in rows}


def test_split_groups():
    rows = benchmark.split([
        item("mobley_a_1960", "Hank Mobley", year=1960),
        item("stitt_b_1958", "Sonny  Stitt"),
        item("pfh", "Stan Getz", kind="test_tune"),
        item("coltrane_c_1957", "John Coltrane", year=1957, e81=True),
        item("trained", "Lester Young", in_training=True),
        item("free_1970", "Joe Henderson", year=1970),
        item("nofile", "Joe Henderson", audio=""),
        item("nokey", "Joe Henderson", key=""),
    ], RULE)
    t = tiers(rows)
    assert t["mobley_a_1960"] == ("benchmark", "held-out player")
    assert t["stitt_b_1958"][0] == "benchmark"           # spacing and case don't matter
    assert t["pfh"] == ("test", "Austin's test tune")
    assert t["coltrane_c_1957"] == ("benchmark", "E81 benchmark song")
    assert t["trained"][0] == "seen"
    assert t["free_1970"] == ("train_reserve", "")
    assert t["nofile"] == ("skip", "no recording on this Mac")
    assert t["nokey"] == ("skip", "no lined-up answer key")


def test_session_rule_keeps_same_session_out_of_training():
    rows = benchmark.split([
        item("coltrane_lazy-bird_1957", "John Coltrane", year=1957, e81=True, album="Blue Train"),
        item("coltrane_blue-train_1957", "John Coltrane", year=1957),
        item("coltrane_moment_1958", "John Coltrane", year=1958, album="Blue Train"),
        item("coltrane_giant_1959", "John Coltrane", year=1959),
        item("someone_unknown", "Someone"),
    ], RULE)
    t = tiers(rows)
    assert t["coltrane_blue-train_1957"] == ("session_hold", "same player and year as coltrane_lazy-bird_1957")
    assert t["coltrane_moment_1958"] == ("session_hold", "same album as coltrane_lazy-bird_1957")
    assert t["coltrane_giant_1959"] == ("train_reserve", "")
    assert t["someone_unknown"] == ("train_reserve", "no year on file: session rule could not be checked")


def test_charts_from_the_ledger(tmp_path):
    runs = make_runs(tmp_path)
    got = {c["id"]: c for c in benchmark.charts(runs)}
    web = got["ben-webster_the-touch-of-your-lips_1959"]
    assert web["mix"] is True and web["horn"] == "tenor" and web["e81"] is True and web["year"] == 1959
    assert web["audio"].endswith(".mp3") and web["key"].endswith("key.json")
    et = got["ferling08_voxman"]
    assert et["mix"] is False and et["in_training"] is True
    assert "x_changed_1950" not in got and "x_check_1950" not in got


def fake_score(item, folder):
    f1 = {"ben-webster_the-touch-of-your-lips_1959": 0.62}.get(item["id"], 0.1)
    return {"record": item["id"], "set": "benchmark-v2", "setup": benchmark.SETUP_D, "metrics":
            {"note_f1_no_offset": f1, "note_f1": f1 - 0.1, "onset_f1": f1, "pitch_accuracy": 0.9, "sax_found": 0.4},
            "note": item["tier"]}


def test_score_run_writes_summary_and_needs_a_look_and_resumes(tmp_path, monkeypatch):
    runs = make_runs(tmp_path)
    calls = []
    monkeypatch.setattr(benchmark, "heavy_jobs", lambda *a: [])
    monkeypatch.setattr(benchmark, "score_one", lambda it, folder: calls.append(it["id"]) or fake_score(it, folder))
    out = benchmark.run_score(runs)
    folder = runs / "benchmark" / "v2"
    assert out["scored"] == len(calls) == 2
    md = (folder / "summary.md").read_text()
    assert "| benchmark | 1 | 1 | 62.0 |" in md and "| seen | 1 | 1 | 10.0 |" in md
    look = {r["id"]: r["why"] for r in csv.DictReader((folder / "needs_a_look.csv").open())}
    assert "sax found only 40.0" in look["ferling08_voxman"] and "note F1 without ends only 10.0" in look["ferling08_voxman"]
    assert len((folder / "rows.jsonl").read_text().splitlines()) == 2
    assert len((runs / "experiments.jsonl").read_text().splitlines()) == 2
    calls.clear()
    benchmark.run_score(runs)                  # a second run carries on: nothing scored twice
    assert calls == []
    assert "BENCHMARK_DONE" in (folder / "run.log").read_text()


def test_refuses_to_start_beside_another_heavy_job(tmp_path, monkeypatch):
    runs = make_runs(tmp_path)
    monkeypatch.setattr(benchmark, "heavy_jobs", lambda *a: ["123 python run_keys.py"])
    try:
        benchmark.run_score(runs)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("should not start beside another heavy job")


def test_read_key_drops_grace_notes_and_keeps_heard(tmp_path):
    p = tmp_path / "k_key.json"
    p.write_text(json.dumps({"notes": [{"onset": 1.0, "offset": 1.2, "pitch": 60, "heard_ok": True},
                                       {"onset": 1.5, "offset": 1.55, "pitch": 61, "grace": True},
                                       {"onset": 2.0, "offset": 2.4, "pitch": 62, "heard_ok": False}]}))
    got = benchmark.read_key(p)
    assert [n["pitch"] for n in got] == [60, 62] and [n["heard_ok"] for n in got] == [True, False]


def test_extra_share_takes_whole_sessions_and_is_stable():
    items = [item(f"p{i}_t{j}_19{50 + i}", f"Player {i}", year=1950 + i) for i in range(40) for j in range(2)]
    rows = benchmark.split(items, {**RULE, "extra_share": 0.25})
    picked = {r["id"] for r in rows if r["tier"] == "benchmark"}
    assert 4 <= len(picked) // 2 <= 18                       # roughly a quarter of 40 sessions
    for i in range(40):                                      # both tunes of a session go the same way
        assert (f"p{i}_t0_19{50 + i}" in picked) == (f"p{i}_t1_19{50 + i}" in picked)
    again = benchmark.split(items + [item("new_1999", "Newcomer", year=1999)], {**RULE, "extra_share": 0.25})
    assert {r["id"] for r in again if r["tier"] == "benchmark"} - {"new_1999"} == picked
    assert not benchmark.split(items, RULE)[0]["why"].startswith("sampled")
