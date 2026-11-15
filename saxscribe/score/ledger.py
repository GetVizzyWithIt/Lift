"""The PDF ledger behind the dashboard's Dataset health tab.

Every PDF transcription we hold gets one status on the way to a confident match
with its recording: matched, check, wrong_audio, needs_audio, unreadable,
not_started, unsorted or excluded (meanings in docs/data/ledger/README.md).
The Mac script `~/saxscribe-runs/catalog/_tools/pdf_ledger.py` writes three
files to `<runs>/catalog/ledger/`:

  ledger_status.json   the counts (schema 1): totals, counts by status,
                       by_source, top_reasons
  ledger_history.csv   one row per run: generated, then the 8 counts
  pdf_ledger.csv       one row per PDF

A snapshot of the same files lives in docs/data/ledger/ so the published
dashboard can show them. The newer of the two copies wins.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_LEDGER = Path(__file__).resolve().parents[2] / "docs" / "data" / "ledger"
STATUSES = ["matched", "check", "wrong_audio", "needs_audio", "unreadable", "not_started", "unsorted", "excluded"]
# columns the dashboard's table needs (the full path and fingerprint stay on the Mac)
PDF_COLS = ["chart_id", "performer", "tune", "horn", "kind", "source", "recording", "status", "reason",
            "heard_agree", "coverage", "audit"]


def _read(folder: Path) -> dict | None:
    status = folder / "ledger_status.json"
    if not status.exists():
        return None
    out = {"status": json.loads(status.read_text()), "history": [], "pdfs": []}
    hist = folder / "ledger_history.csv"
    if hist.exists():
        with hist.open(newline="") as f:
            for row in csv.DictReader(f):
                out["history"].append({"generated": row.get("generated", ""),
                                       "counts": {s: int(row.get(s) or 0) for s in STATUSES}})
    pdfs = folder / "pdf_ledger.csv"
    if pdfs.exists():
        with pdfs.open(newline="") as f:
            out["pdfs"] = [{k: row.get(k, "") for k in PDF_COLS} for row in csv.DictReader(f)]
    return out


def _newest(runs: str | Path | None) -> tuple[dict, str, Path] | None:
    local = (Path(runs).expanduser() if runs else Path.home() / "saxscribe-runs") / "catalog" / "ledger"
    found = [(d, src, folder) for folder, src in ((local, "this Mac"), (REPO_LEDGER, "the repo snapshot"))
             if (d := _read(folder))]
    if not found:
        return None
    return max(found, key=lambda x: x[0]["status"].get("generated", ""))


def load(runs: str | Path | None = None) -> dict | None:
    """The newest ledger: this machine's (<runs>/catalog/ledger) or the repo snapshot; None when neither exists."""
    found = _newest(runs)
    if not found:
        return None
    data, src, _ = found
    data["from"] = src
    return data


def full_rows(runs: str | Path | None = None) -> tuple[list[dict], dict] | None:
    """Every column of pdf_ledger.csv (PDF path and fingerprint included) from the same copy load() picks,
    plus {generated, from}. For the app's Library, which runs on the Mac; never sent to a page as is."""
    found = _newest(runs)
    if not found:
        return None
    data, src, folder = found
    path = folder / "pdf_ledger.csv"
    rows = list(csv.DictReader(path.open(newline=""))) if path.exists() else []
    return rows, {"generated": data["status"].get("generated", ""), "from": src,
                  "charts": data["status"].get("charts")}
