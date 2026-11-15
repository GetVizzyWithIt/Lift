# ADR-0045: A clean dataset before any more training

- **Date**: 2026-11-14
- **Status**: Accepted
- **Decided by**: Austin (20:39Z: "bad data in, bad data out"; 21:25Z: one goal, every PDF matched confidently or excluded)
- **PR**: docs sweep 2026-11-15 (this ADR); Dataset health tab PR #177
- **Reviewed by**: the key audit (329 charts) and the step 1 diagnosis, which found keys that don't match their recordings among the biggest open weaknesses

## Context
Every model since E77 learns from, and is scored against, answer keys made from PDF charts lined up with recordings. The key audit and the first ledger run showed many charts with the wrong recording, no recording, or sections the page reader misread. E83 found more of the same data doesn't move the note finder. Training on mismatched pairs would teach the model wrong notes, and scoring on them would hide real progress.

## Decision
- No training run (E84 or later) starts until the dataset is clean.
- Clean means every PDF chart has one status in the PDF ledger and ends either **matched** (passes the match check, ADR-0042) or **excluded** (unreadable, not sax, or no recording to be had). A chart that doesn't match gets the right recording found.
- The ledger (`~/saxscribe-runs/catalog/_tools/pdf_ledger.py`, snapshot in docs/data/ledger/) is the record, and the Results page's Dataset health tab shows it.
- Non-sax charts are re-scored only and never train anything.

## Options considered
- **Clean first (chosen):** slower to the next model, but every later score means what it says.
- **Run E84 on the matched charts only:** possible now, but the held-out players and benchmark depend on charts still in "check", and a second run would follow anyway.
- **Train on everything and let the model average out errors:** cheapest, and the opposite of the fidelity rule; wrong keys teach wrong notes.

## Case against
- The matching work could take long enough that the model stalls for weeks.
- "Confident" is a threshold; a ledger that calls too much matched gives a false sense of a clean set. This breaks if a re-check of matched charts finds more than a few wrong pairs.
- Excluding hard charts may remove exactly the quiet, low, or busy passages the model is weakest on.

## Consequences
- E84 stays pre-registered and on hold; it is rebuilt on the cleaned data.
- The Library shows only matched charts, so it grows as the work finishes.
- Watch the share of charts excluded per player: heavy exclusion of one player skews the held-out swap.

## Look back
Filled in later.
