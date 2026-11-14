# PDF ledger (dataset health)

Script: Mac `~/saxscribe-runs/catalog/_tools/pdf_ledger.py` (copy here). Read-only. Run with plain `python3`.
Outputs: Mac `~/saxscribe-runs/catalog/ledger/`, with a copy synced here after each run.

## ledger_status.json (schema 1), for the dashboard
- `generated`: "YYYY-MM-DD HH:MM", Mac local time
- `total_pdfs`: every PDF row. `charts`: rows that aren't excluded.
- `healthy`: the matched count. `healthy_share`: matched / charts.
- `counts`: {status: n} for the 8 statuses, in this order: matched, check, wrong_audio, needs_audio, unreadable, not_started, unsorted, excluded
- `by_source`: {source kind: {status: n}}. The source kinds are transcribed, book_split, site_pdf, excerpt, youtube_etude, test_tune, loose, inbox, and "other instrument: <inst>".
- `top_reasons`: [{status, reason, n}], the 25 most common reasons for anything not matched

## ledger_history.csv
One row per run (generated plus the 8 counts), for a progress-over-time chart.

## pdf_ledger.csv
One row per PDF: pdf, source, kind, chart_id, performer, tune, horn, recording, sha256, status, reason, heard_agree, coverage, audit (the audit priority).

## needs_look.csv
The same columns, holding everything that isn't matched or excluded, sorted by status.

## Statuses
| status | meaning |
|---|---|
| matched | Lined up with its recording and passed every check: match pass, at least 80% of the chart placed, and no high-priority audit flag or misread lines. Usable. |
| check | Lined up, but at lower confidence: a match "check", an octave fix pending, few notes placed, or audit flags. |
| wrong_audio | The chart reads fine, but our recording is a different take or edit. |
| needs_audio | No recording yet. |
| unreadable | The page reader failed or misread it. Try another reader, otherwise exclude it. |
| not_started | Chart and recording are both here, but no key has been built yet. |
| unsorted | An inbox PDF that hasn't been identified yet. |
| excluded | Left out on purpose. The reason column says why. |
