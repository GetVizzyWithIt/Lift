# ADR-0048: Review questions come from queue files, machines first

- **Date**: 2026-11-16
- **Status**: Accepted
- **Decided by**: Austin ("human review last", 2026-11-14 23:00Z; the Review page, PR #191)
- **PR**: #191 (the Review page); docs PR (this ADR)
- **Reviewed by**: the review hub's first queues (note ends, Weimar listens, match checks)

## Context
Questions for Austin's ears were spread across the app's Needs review tab, the Mac's review hub (port 8770), and messages in threads. Austin's rule is that he should hear only what every automatic check has tried and still can't decide, one question at a time, with the chart and the right spot of the recording in front of him.

## Decision
- The Mac scripts decide what needs Austin. Each writes one queue file, `~/lift-runs/review/queues/<queue>/items.json`, in the hub format: `queue`, `plugin`, `title`, `why`, `items`.
- The app's Review page (`/review`, `lift/app/review_inbox.py`) only reads these files. It never makes questions itself. It shows one item at a time.
- Three kinds of question (plugins):
  - `match_check`: is this chart this recording?
  - `start_point`: where does the chart start?
  - `listen`: one short question about one spot.

  The hub's older names map onto these.
- An item needs only `id` and `question`. Its other fields (chart, bars, loop, guesses, choices and so on) are documented in the module docstring of `review_inbox.py`.
- Every answer is appended to `review/answers.jsonl`. Match-check answers also go to `keys/match_review.jsonl`, so the Library and the benchmark see them. The Results page's Match pairs tab keeps their history.
- Note-end tapping (`note_ends`) is retired (ADR-0044) and is never shown.

## Options considered
- **Queue files written by the scripts (chosen):** one format for every review type. The scripts keep the decision about what is still uncertain, and the app stays read-only on the questions.
- **The app finds uncertain items itself:** it would duplicate each script's logic in the app and blur "human review last".
- **Keep the separate review hub:** it works, but it is a second server on another port, and it lacks the chart and the answer-key tones.

## Case against
- A script that writes too many items turns the page into a chore. This fails if queues grow faster than Austin answers them.
- Two answer files (`answers.jsonl` and `match_review.jsonl`) can drift if one write fails.

## Consequences
- A new review type means a new plugin in `review_inbox.py` and a script that writes its queue.
- Watch queue sizes. Each item should show which automatic checks it already tried (`tried`).

## Look back
Filled in later.
