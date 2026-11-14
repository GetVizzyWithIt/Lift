# ADR-0044: Judge models mainly on note F1 without note ends

- **Date**: 2026-11-14
- **Status**: Accepted
- **Decided by**: Austin (decision card, 23:30Z: skip the rest of the note-end tapping; the Weimar result answers it)
- **PR**: docs #179 (this ADR, with the step 2 finding)
- **Reviewed by**: the step 2 note-end check (log, 2026-11-14) and the first 7 hand-tapped clips

## Context
Note F1 counts a note right only if its start, pitch and end all match the answer key. On the 33-song benchmark, note ends cost about 16 points (E81: setup D 50.9 with ends, 66.9 without). The step 2 check measured the keys themselves. On Weimar (127 solos, 63,341 notes), page-style key ends, placed at the next note's start, run late 91% of the time: median 17.4 ms, worst tenth over 120 ms. Our E77 note finder's ends are as close as the best key ends (median 12.9 ms). Of the first 7 hand-tapped clips, our end was closer than the key's on 5. So much of the "note end" loss is error in the keys, not in the transcription.

## Decision
- Answer keys read from a page (transcribed charts and Weimar) have unreliable note ends.
- Models are judged mainly on **note F1 without note ends** (onset and pitch must match).
- Note F1 with note ends is still measured and reported beside it.
- The band-record target of 60 note F1 applies to the no-offset score.
- Pre-registered rules already in force (E83, E84) keep their stated tests, which already include "no-offset not lower".

## Options considered
- **No-offset as the main score (chosen):** measures what the keys can support. Ends stay visible as a second number.
- **Keep with-offset as the main score:** stricter, but it would grade the model against end times the keys get wrong, so a better model could score worse.
- **Finish the hand tapping first (about 90 clips):** a firmer number, at Austin's time. Weimar's 63,341 notes already answer the question.

## Case against
- Note length matters for reading music: a model that writes every note too short or too long would no longer be caught by the main score.
- The keys' error was measured on Weimar; transcribed charts may differ.
- Past results were headlined with offsets, so comparisons across the switch need care.
- This breaks if a model's no-offset score rises while its with-offset score falls sharply; then the ends need a separate check.

## Consequences
- Reports lead with no-offset note F1 and give the with-offset score next to it.
- The dashboard's headline and target line should follow (a separate change).
- Step 2 tapping is closed. The tap clips stay on the Mac.

## Look back
After E84 and the dataset-health clean-up: do no-offset and with-offset scores still move together, and do the cleaned keys' ends agree better with the audio?
