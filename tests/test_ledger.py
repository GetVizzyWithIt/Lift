"""The PDF ledger the Dataset health tab reads (score/ledger.py)."""
import json

from lift.score import history, ledger


def test_repo_snapshot_loads_and_adds_up(tmp_path):
    d = ledger.load(tmp_path)  # an empty runs folder: the repo snapshot
    assert d and d["from"] == "the repo snapshot"
    s = d["status"]
    assert list(s["counts"]) == ledger.STATUSES
    assert sum(s["counts"].values()) == s["total_pdfs"] == len(d["pdfs"])
    assert s["charts"] == s["total_pdfs"] - s["counts"]["excluded"]
    for src in s["by_source"].values():
        assert set(src) <= set(ledger.STATUSES)
    assert all(set(r["counts"]) == set(ledger.STATUSES) for r in d["history"])
    assert "sha256" not in d["pdfs"][0]  # fingerprints and Mac paths stay out of the page


def test_newer_mac_ledger_wins(tmp_path):
    folder = tmp_path / "catalog" / "ledger"
    folder.mkdir(parents=True)
    (folder / "ledger_status.json").write_text(json.dumps(
        {"generated": "2999-01-01 00:00", "schema": 1, "total_pdfs": 1, "charts": 1, "healthy": 1, "healthy_share": 1.0,
         "counts": {s: int(s == "matched") for s in ledger.STATUSES}, "by_source": {}, "top_reasons": []}))
    d = ledger.load(tmp_path)
    assert d["from"] == "this Mac" and d["status"]["total_pdfs"] == 1 and d["pdfs"] == []


def test_dashboard_data_carries_the_ledger(tmp_path):
    assert history.dashboard_data(tmp_path)["ledger"]["status"]["schema"] == 1
