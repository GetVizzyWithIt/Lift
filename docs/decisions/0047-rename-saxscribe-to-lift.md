# ADR-0047: Rename Saxscribe to Lift, keeping every old name working

- **Date**: 2026-11-16
- **Status**: Accepted
- **Decided by**: Austin (16:28Z and 16:37Z 11-16: "It should say lift - and we should update all our folder structures to align too"; "Go"; "yes rename the repo please")
- **PR**: claude/refactor-rename-to-lift (code and Mac script), claude/docs-rename-to-lift (this ADR and the docs)
- **Reviewed by**: a fresh second-pass reviewer, before the Mac script ran

## Context
Austin named the tool Lift, with the record-and-tone-arm logo. The name
Saxscribe was everywhere: the Python package and command, the GitHub repo, and
the folders on the Mac. Those Mac folders are ~/saxscribe-runs (353 GB:
scripts, keys, the ledger, the catalog, the review hub), ~/saxscribe-library,
~/.cache/saxscribe, the Python environment in Application Support, the code
checkout on the Desktop, and the downloads folder. About 2,200 data files, about
2,600 catalog rows, five Python environments, seven old code copies, and about
120 saved Mac scripts have the old paths written into them.

## Decision
Rename everything to Lift and leave a link (a macOS symlink) at every old
folder name.

| Before | After |
| --- | --- |
| package `saxscribe/`, `python -m saxscribe` | `lift/`, `python -m lift`; `saxscribe/` is a small alias that hands back the same modules |
| settings `SAXSCRIBE_<NAME>` | `LIFT_<NAME>`, with the old name still read (`lift/paths.py: env`) |
| take folders `song.saxscribe/` | `song.lift/` for new takes; an existing `song.saxscribe/` is reused |
| ~/Desktop/saxscribe (code) | ~/dev/lift |
| ~/Desktop/Saxscribe (the app's sheet-music copies) | ~/Desktop/Lift Sheets |
| ~/Desktop/Saxscribe_Recent_Downloads | ~/Desktop/Lift_Recent_Downloads |
| ~/saxscribe-runs, ~/saxscribe-library | ~/lift-runs, ~/lift-library |
| ~/.cache/saxscribe | ~/.cache/lift |
| ~/Library/Application Support/saxscribe/python | ~/Library/Application Support/Lift/python |
| catalog/saxscribe_catalog.db | catalog/lift_catalog.db |
| GitHub GetVizzyWithIt/Saxscribe | GetVizzyWithIt/lift (GitHub forwards the old address) |

The code reads the new folder when it exists and the old one otherwise, so it
works before and after the move. `scripts/rename_to_lift.sh` does the Mac move.
By default it does a dry run. With --apply, it waits for running jobs to finish.
It then asks the running app for every page, song, and take, and counts how
many catalog paths resolve. Next it renames each folder and leaves the link. It
asks the same questions again and needs the same answers. Last, it runs the full
test suite, both health checks, and each side environment. --undo puts
everything back.

The code moves off the Desktop because macOS treats upper and lower case as the
same name. ~/Desktop/lift would collide with the Lift launcher shortcut, just as
~/Desktop/saxscribe and ~/Desktop/Saxscribe were already one folder.

Left as it was, on purpose:
- Stored paths inside data files and the catalog. They resolve through the links.
- Historical records: past entries in docs/evaluation/log.md, ADRs 0001 to 0046,
  results.jsonl, experiments.jsonl, the E84 pre-registration, and the ledger snapshot.
- The E77 weights file name `saxscribe_finder_e77.pt`, which is fixed by its fingerprint.
- The catalog's internal source id "saxscribe" for app-made takes, and the
  browser's saved-setting keys, so saved settings survive.

## Options considered
- **Rename everything and link the old names (chosen):** one name everywhere,
  nothing stored needs rewriting, and undo is one command.
- **Rename and rewrite every stored path:** the cleanest end state, but it
  touches about 2,200 files and 2,600 catalog rows, means rebuilding five Python
  environments, and is the hardest option to undo.
- **Rename only what Austin sees:** the least risk, but two names would live on.

## Case against
- Links are invisible. A tool that resolves real paths could write a mix of old
  and new names into new records.
- "lift" is a common word. A downloaded package with the same name could clash
  someday, though nothing installs one today.
- This breaks if a saved script checks that a folder is a real directory and not
  a link. None was found in the scan.

## Consequences
- New commands, docs, and scripts use the Lift names. Old ones keep working.
- A saved script that says saxscribe gets patched when a thread next edits it,
  not all at once.
- The update command becomes `cd ~/dev/lift && ...`. `cd ~/Desktop/saxscribe`
  still works through its link.

## Look back
Filled in later: after a month, list anything that broke because of a link.
