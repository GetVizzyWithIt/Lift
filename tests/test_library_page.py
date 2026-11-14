"""The Library (app/catalog.py): matched answer keys from the ledger, checked against their fingerprints."""
from __future__ import annotations

import csv
import hashlib
import json

import pytest

from saxscribe.app import catalog
from saxscribe.score import ledger

COLS = ["pdf", "source", "kind", "chart_id", "performer", "tune", "horn", "recording", "sha256", "status",
        "reason", "heard_agree", "coverage", "audit"]


def make_runs(tmp_path):
    runs = tmp_path / "runs"
    charts = runs / "keys" / "transcribed"
    charts.mkdir(parents=True)

    def pdf(name, body=b"%PDF-1.4 chart"):
        p = charts / name
        p.write_bytes(body)
        return f"~/saxscribe-runs/keys/transcribed/{name}", hashlib.sha256(body).hexdigest()

    ok_path, ok_sha = pdf("webster.pdf")
    et_path, et_sha = pdf("ferling.pdf", b"%PDF etude")
    ch_path, _ = pdf("changed.pdf", b"%PDF edited after matching")
    rows = [
        dict(pdf=ok_path, kind="transcribed", chart_id="ben-webster_the-touch-of-your-lips_1959", performer="Ben Webster",
             tune="The Touch of Your Lips", horn="ts", recording="Ben Webster Meets Oscar Peterson (Verve, 1959)",
             sha256=ok_sha, status="matched", heard_agree="85.0", coverage="1.0", audit="low"),
        dict(pdf=et_path, kind="youtube_etude", chart_id="ferling08_voxman", performer="Joey Resendez",
             tune="Selected Studies for Saxophone (ed. Voxman, Rubank) p.13 Ferling Etude No. 8", horn="alto",
             sha256=et_sha, status="matched", heard_agree="0.9"),
        dict(pdf=ch_path, kind="transcribed", chart_id="x_changed_1950", performer="X", tune="Changed",
             sha256="0" * 64, status="matched"),
        dict(pdf="~/saxscribe-runs/keys/transcribed/gone.pdf", kind="transcribed", chart_id="x_gone_1950",
             performer="X", tune="Gone", sha256="1" * 64, status="matched"),
        dict(pdf=ok_path, kind="transcribed", chart_id="x_check_1950", performer="X", tune="Not yet",
             sha256=ok_sha, status="check"),
        dict(pdf=ok_path, kind="excerpt", chart_id="x_copy", performer="X", tune="Copy", sha256=ok_sha, status="excluded"),
    ]
    folder = runs / "catalog" / "ledger"
    folder.mkdir(parents=True)
    with (folder / "pdf_ledger.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLS} for r in rows)
    (folder / "ledger_status.json").write_text(json.dumps(
        {"generated": "2999-01-01 00:00", "schema": 1, "total_pdfs": 6, "charts": 5,
         "counts": {s: 0 for s in ledger.STATUSES}, "by_source": {}, "top_reasons": []}))
    (runs / "keys" / "match_report.jsonl").write_text(json.dumps(
        {"id": "ferling08_voxman", "verdict": "pass", "in_training": True}) + "\n")
    return runs


def test_only_matched_charts_whose_pdf_is_unchanged(tmp_path):
    d = catalog.load(make_runs(tmp_path))
    assert {s["id"] for s in d["songs"]} == {"ben-webster_the-touch-of-your-lips_1959", "ferling08_voxman"}
    assert d["counts"] == {"keys": 2, "takes": 0, "matched": 4, "charts": 5, "hidden_missing": 1, "hidden_changed": 1}
    assert d["ledger"]["from"] == "this Mac"
    for s in d["songs"]:  # paths and fingerprints stay on the Mac
        assert "pdf" not in s and "sha256" not in s


def test_song_fields(tmp_path):
    songs = {s["id"]: s for s in catalog.load(make_runs(tmp_path))["songs"]}
    w = songs["ben-webster_the-touch-of-your-lips_1959"]
    assert (w["source"], w["horn"], w["year"], w["decade"], w["heard"]) == ("key", "tenor", 1959, "1950s", 0.85)
    assert w["use"] == "benchmark"  # in docs/evaluation/benchmark_tags.json
    e = songs["ferling08_voxman"]  # etudes group under their composer; the YouTube player is the recording
    assert (e["player"], e["title"], e["played_by"], e["book"]) == (
        "Ferling", "Etude No. 8", "Joey Resendez", "Selected Studies for Saxophone")
    assert e["use"] == "training" and e["heard"] == 0.9


@pytest.mark.parametrize("name,want", [("Stan Getz Quartet", "Stan Getz"), ("Stan Getz, Oscar Peterson Trio", "Stan Getz"),
                                       ("The Hornheads", "The Hornheads")])
def test_player_name(name, want):
    assert catalog.player_name(name) == want


def test_library_route_lists_keys_and_finished_takes(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from saxscribe.app.library import Library
    from saxscribe.app.server import create_app

    lib = Library(tmp_path / "lib", inline=True)
    c = TestClient(create_app(lib, runs=make_runs(tmp_path)))
    assert "Library" in c.get("/library").text
    d = c.get("/api/library").json()
    assert d["counts"]["keys"] == 2 and d["counts"]["takes"] == 0
    done = {"id": "20261114-120000-take", "state": "done", "title": "My take", "horn": "alto", "mix": False,
            "added": "2026-11-14T12:00:00"}
    item = catalog.load(make_runs(tmp_path / "again"), [done, {**done, "state": "running"}])["songs"][-1]
    assert (item["source"], item["href"], item["kind_name"]) == ("saxscribe", "/take/20261114-120000-take", "Solo take")
