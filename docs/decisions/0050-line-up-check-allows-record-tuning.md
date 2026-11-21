# ADR-0050: The line-up check allows for each record's own tuning

- **Date**: 2026-11-20
- **Status**: Accepted
- **Decided by**: Austin (go on 11-20 in the Matching thread)
- **PR**: none for the code (Mac key tools: `keyalign_v2.py`, run by `tuning_regrade.py`); docs PR (this ADR)
- **Reviewed by**: the regrade itself (264 keys, below); no outside review

## Context
The line-up check (the "heard agreement" that grades each answer key as pass, check, or set aside) compares the chart's notes with the pitch heard on the sax stem, within a 0.6-semitone window. Many older records, and some newer ones, are not at A = 440. Old 78s ran at slightly wrong speeds, and some bands tuned to their piano. On such a record every note sits 15 to 50 cents off, so with that much offset a large share of correct notes fall outside the window. Good charts were landing at check or set aside for that reason alone.

## Decision
Before the heard-pitch check, the grader measures the record's **tuning offset** and subtracts it. The offset is the average pitch of the sax stem's pitch line against the nearest semitone, using only frames the pitch tracker is confident about (at least 200 of them; otherwise no correction). It is measured from the recording alone and never from the chart, so a wrong chart can't pull the offset toward itself. The 0.6-semitone window is unchanged.

The regrade (11-20 22:32 PT) reran every key that wasn't already a pass and whose record is 15 cents or more off. Passes were not touched, because done songs are never redone. Of 264 keys regraded, 35 now pass, 60 are at check, and 169 stay set aside. The ledger went from 280 to 285 matched charts of 739. Most new passes are early jazz and bebop records 16 to 50 cents off (for example Earl Bostic's Hurricane Blues at -42 cents, 69.6 to 93.3).

## Options considered
- **Widen the window to cover tuning.** Simpler, but a wider window also lets in wrong notes and wrong charts on records that are in tune. Rejected: it loosens the check exactly where it works now.
- **Measure the offset against the chart.** This finds the best shift between chart and recording. It is more precise, but a wrong chart can also find a shift that suits it, which defeats a check meant to catch wrong charts. Rejected.
- **Measure the offset from the recording alone (chosen).** It corrects only what the record itself shows and leaves the window as strict as before.

## Case against
The offset is one number per record. It breaks when tuning drifts during a record (a 78 slowing down, a tape splice, a medley at two speeds). It also breaks when the sax stem is mostly another instrument, because then the offset belongs to that instrument. An offset near 50 cents is ambiguous, since a record a quarter-tone sharp looks the same as one a quarter-tone flat a semitone up. A record pushed to the wrong side would then line up a semitone off, and the octave and clef checks don't catch that. Eight of the new passes have offsets of 44 cents or more and are worth a spot check.

## Consequences
- Charts that were good but mistuned now count as matched, without masking any bars (NO MASKING still holds).
- The regrade summary lists each new pass with its offset (`keycheck/better/tuning_regrade_2026-11-20_summary.txt` on the Mac).
- This ADR covers the line-up check only. Scoring the tool against these keys (mir_eval, 50-cent pitch tolerance) is a separate step; before benchmark v2 results (ADR-0049) are read on records far off pitch, check whether that scoring allows for tuning too.

## Look back
(to fill in after the 44-cent-and-over passes are spot-checked)
