# Sax Transcription Tool (saxscribe)

## What this project is
A tool that transcribes saxophone performances to notes and readable
notation, for one user: Austin, a saxophone player on an Apple Silicon Mac
(M3 Pro). Two uses: review his own recordings, and learn other players' solos
from full-band recordings. The requirements doc ("Sax Transcription Tool —
Requirements and Project Instructions") is the source of truth; ask for it if
it is not attached. Alto first; check transfer to tenor once alto works.

## How to work
- Build in small, runnable steps. Every pull request leaves the CLI working:
  `python -m saxscribe transcribe file.wav` runs end to end.
- Measure before and after any model change. Report onset F1, note F1 and
  pitch accuracy with mir_eval on the fixed test set. A change with no
  scorecard is not done.
- Reuse before building. Start from Demucs, CREPE/torchcrepe, Basic Pitch,
  Beat This! and music21. Build only the pieces nothing provides: note
  segmentation under slurs, articulation tags, swing quantization, the editor.
- Keep the four layers separate on disk: stem, pitch contour, note events,
  notation. Never discard a lower layer to produce a higher one.
- Fidelity over playability. This tool is the opposite of the Songs in the Key
  of Life chart model: it must not learn to omit notes. If a shortcut from the
  game would do that, say so and don't take it.
- Separate from the game. `saxscribe/frontend.py` is a private copy of the
  game analyzer's front end. Never import from the game repo, and never bring
  over anything from its chart model.
- Explain choices in plain language. Austin is a strong analyst and a
  musician, not an ML researcher. Name the model and the metric, say what it
  does, skip the jargon.
- Mac first. Inference runs locally on MPS or Core ML. Anything that needs a
  real GPU goes in a Colab notebook with the weights brought back.
- Record every take and every edit. Edited transcriptions are training data;
  store them with the original model output as a diff.

- Bias checks: follow [docs/standards/bias-checks.md](docs/standards/bias-checks.md)
  (adopted 2026-11-10, ADR-0040). Big choices get options, a case against and
  outside review. After three experiments in a row that don't beat the current
  best, pause and measure the ceiling.

## Conventions
- Python 3.11, same venv layout as the game analyzer (own environment, see
  setup_mac.sh). Python version lives in .python-version. Add dependencies to
  requirements.txt with a one-line reason, then run `bash scripts/lock.sh` and
  commit requirements.lock with it (installs always use the lock).
- Concert pitch stored; display transposed (E-flat or B-flat) on request.
- Tests for every layer on the 10-second synthetic fixture (tests/fixture.py).
  Run `python -m pytest` before opening a PR.
- Branches named claude/<type>-<what>, one PR per change, with the scorecard in
  the PR description (see "Branches, pull requests and CI" below).
- No audio files or datasets in the repo. Paths to them live in a local
  config (config.local.*, ignored by git).

## When unsure
Draft the smallest version, run it on the fixture, and show the result. Ask
one question at a time. Prefer a working rough cut to a plan.

## Branches, pull requests and CI
- Nothing goes straight to main. Every change is a pull request from its own
  branch, and Austin merges it.
- Branch names: claude/<type>-<what>, e.g. claude/fix-numpy2-safe-loader.
  Types: feat, fix, exp (experiment), docs, chore (setup, deps), ci, refactor.
  If a session was handed a claude/project-thread-xxxx branch, make a
  claude/<type>-<what> branch for the PR anyway: this rule is Austin's standing
  permission to do so.
- CI (.github/workflows/tests.yml) runs the health check and `python -m pytest`
  on every PR. Don't ask Austin to merge a PR whose checks are red.
- Lasting choices get an ADR in docs/decisions/; new terms go in
  docs/glossary.md. The docs thread owns docs/, so tell it what you add.
- Secrets (API keys such as MVSep's) and machine files live outside the repo or
  in config.local.* (git-ignored). Never commit audio, datasets or weights.

## Current state (2026-11-15; update when it changes)
- Current priority: a clean dataset before any more training (Austin, 2026-11-14:
  "bad data in, bad data out"). Every PDF chart is matched confidently to its
  recording or excluded. The PDF ledger tracks it (Mac
  `~/saxscribe-runs/catalog/_tools/pdf_ledger.py`; snapshot in docs/data/ledger/),
  and the Results page's Dataset health tab shows it. E84 (held-out player swap,
  pre-registered) is on hold until then; no training run starts before the data
  is clean (ADR-0045).
- Main score: note F1 ignoring note ends (ADR-0044), because page-read keys get
  note ends wrong. The with-ends score is still reported. The band target (60)
  applies to the no-offset score.
- Standard path (CLI default, and the app's path for solo takes): Demucs (2
  shifts) -> Basic Pitch + CREPE pitch line -> per-horn range rules -> bleed
  hide -> held notes follow the pitch line -> sax-playing check -> bar lines ->
  swing. In the app, band records run setup D: the Filosax separator, our E77
  fine-tuned note finder (ADR-0041), and the vocal review mark from MVSep Mega's
  vocal stem (E82, ADR-0043; needs the Mega weights in ~/.cache/saxscribe/models).
  CLI equivalent: `--separator filosax --notes-tool filosax`. No model picker in
  the main UI. E83 (a second fine-tune) didn't beat E77.
- App pages: Library (`/library`: matched answer keys and finished takes, song
  pages, play-along on the engraved answer key, solo-only playback; PRs
  #181-#184), Results (`/results`: Progress, Songs, Lab, Log, Dataset health,
  Needs review), and the play-along with review flags (flags.json, ADR-0039).
  Library step 4 (Library as the home screen) waits on Austin's go.
- Audio for answer keys comes in this order: Internet Archive (Mac
  `catalog/_tools/archive_fetch.py`, then `archive_check.py`), then Austin's
  library CDs, then spotDL as a last resort that Austin runs himself (ADR-0046). The page
  reader (homr) runs in its own environment, `~/saxscribe-runs/.venv-omr`.
- Mac jobs: don't run two torch key jobs at once (the Mac crashed on
  2026-11-15 with two running); chain them in one caffeinate.
- Pipeline development is step by step: no change to the transcription
  pipeline without Austin's typed go in the build thread. `main` is protected
  (PR plus green pytest).
- Biggest open weaknesses: quiet low sax and other instruments (including
  vocals) leaking into the sax stem on band records, and answer keys that
  don't match their recordings. Scores per test set are in
  docs/evaluation/log.md; decisions in docs/decisions/.
