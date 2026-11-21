# ADR-0049: Benchmark v2 splits every matched chart into benchmark, held back, and training reserve

- **Date**: 2026-11-20
- **Status**: Accepted
- **Decided by**: Austin (extra_share 0.2 picked on the Build thread's card, 2026-11-20 09:41 PT)
- **PR**: #213 (`python -m lift benchmark split|score`, `lift/score/benchmark.py`), #214 (waits for heavy Mac jobs); docs PR (this ADR)
- **Reviewed by**: the Advisor's 11-14 review of held-out sets (session rule, a larger held-out set, alto players), which the E84 pre-registration took up

## Context
The PDF ledger now matches far more charts to their recordings than the 33 songs of the E81 benchmark (280 of 739 on 11-20). Data comes before training (ADR-0045), but a bigger, fixed benchmark can be set up now, scored with today's default, and kept apart from training before any new training run starts (E84 and later). The benchmark has to stay the same as the ledger grows, and nothing from the same recording session as a benchmark record may leak into training (the session rule, E84).

## Decision
`python -m lift benchmark split` puts every matched chart into one group, using the rules in [docs/evaluation/benchmark_split.json](../evaluation/benchmark_split.json):

| Group | What goes in it |
| --- | --- |
| test | Austin's own test tunes: scored and reported on their own, never trained on |
| benchmark | The E81 benchmark songs, every record by an E84 held-out player (Byas, Stitt, Marsh, Berg, Mobley, Sims, Bartz, and Charles Davis), and one in five (extra_share 0.2) of the other sessions |
| session hold | Records that share a session with a benchmark or test record (the same player and year, or the same album): kept out of training |
| seen | Records a model already trained on: scored for information only |
| training reserve | Everything else: saved for training later, scored now for the baseline |
| skip | No usable recording or key on the Mac (listed in needs_a_look.csv) |

The extra sessions are picked a whole session at a time, by a hash of the session's name, so a session's group never changes as charts are added. `python -m lift benchmark score` scores every group with the live default: setup D on band records, the standard path on etudes. The main score is note F1 without note ends (ADR-0044). Results go to `~/lift-runs/benchmark/v2/summary.md` and to experiments.jsonl as set `benchmark-v2`, entry B2.

## Options considered
- **extra_share 0 (about 37 benchmark records).** These would be only the E81 songs and the held-out players, as first agreed for E84. It keeps the most material for training, but a benchmark this small is dominated by a few players and moves a lot from one song to the next.
- **extra_share 0.2 (about 82 benchmark records, about 179 in the training reserve on 11-20).** Chosen. It roughly doubles the benchmark and still leaves most sessions for training.
- **extra_share about 0.33 (about 110 benchmark records).** This would give a steadier score, but it takes a third of the other sessions out of training while training data is the main shortage.

The pick is fit, not habit: the held-out players and the session rule come from the pre-registered E84 plan, and the share is a single number Austin can change in the rules file.

## Case against
The session rule works from player, year, and album, as the ledger records them. It breaks when a record has no year (it becomes its own session, so a real same-session record can slip into the training reserve) or when the same session was issued under two album names. A record without a year is listed in needs_a_look.csv for that reason. A hashed share can also come out lopsided by chance. If one era or style of playing ends up mostly in the benchmark, the benchmark score will say more about that style than about the tool.

## Consequences
- The benchmark grows with the ledger without being redrawn, so B2 and later scores compare.
- A session hold record is never trained on, even though it isn't scored as benchmark.
- Any later training run (E84 onward) takes its material from the training reserve only.
- Changing extra_share or the held-out players changes the benchmark, so it needs a new ADR and a fresh B row.

## Look back
(to fill in after the first training run that uses the training reserve)
