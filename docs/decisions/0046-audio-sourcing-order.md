# ADR-0046: Where audio for answer keys comes from, in order

- **Date**: 2026-11-15
- **Status**: Accepted
- **Decided by**: Austin (02:47Z 11-15)
- **PR**: docs sweep 2026-11-15 (this ADR)
- **Reviewed by**: the first Internet Archive passes (202 charts searched, 47 downloaded)

## Context
The ledger has about 139 sax charts with no recording and more with the wrong one. Many charts are of 1940s and 1950s records, which the Internet Archive holds as 78 rpm transfers (the Great 78 Project). Other sources need purchases or a download tool Austin runs.

## Decision
Find audio in this order:
1. Internet Archive: `catalog/_tools/archive_fetch.py`, then `archive_check.py` to line each download up with its chart.
2. Austin's library CDs.
3. spotDL, as a last resort that Austin runs himself on the short list left over. Threads build no tooling for it.

Every download still passes the match check (ADR-0042) before it is filed. Austin's own audio stays on the Mac.

## Options considered
- **Archive first (chosen):** free, legal, scriptable, and strong on exactly the older records the charts come from.
- **Buy recordings first:** right takes more often, but costs money per track and needs Austin each time.
- **spotDL first:** covers almost everything, but it matches by search on YouTube, so the take is often wrong, and it's a tool Austin prefers to run himself.

## Case against
- 78 rpm transfers run 20 to 50 cents off pitch and carry surface noise; a pitch correction was tried and didn't help (log, 2026-11-15), so a noisy transfer may line up worse than a CD.
- Archive items are often a different take or a later re-recording under the same title (6 of 47 were clearly wrong). This breaks if most Archive downloads fail the match check.

## Consequences
- The leftover list shrinks before Austin spends time or money.
- Watch the match-check pass rate of Archive downloads against CD rips.

## Look back
Filled in later.
