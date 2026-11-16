"""Where Lift keeps things on the Mac, and the Saxscribe names it used before.

Lift was called Saxscribe until 2026-11-16 (ADR-0047). Its folders were renamed
(~/saxscribe-runs -> ~/lift-runs and so on) and a link was left at each old
name. Until that move has run on a machine, only the old folder exists, so each
default here takes the new folder when it exists and the old one otherwise.

Settings work the same way: LIFT_<NAME> wins, then the old SAXSCRIBE_<NAME>.
"""
from __future__ import annotations

import os
from pathlib import Path

OLD = "saxscribe"
NEW = "lift"

# Folder name pairs under the home folder: (new, old).
RUNS = ("lift-runs", "saxscribe-runs")
LIBRARY = ("lift-library", "saxscribe-library")
CACHE = (".cache/lift", ".cache/saxscribe")
DESKTOP = "~/Desktop/Lift Sheets"       # the app's copies of finished sheet music
TAKE_SUFFIX = ".lift"                   # song.wav -> song.lift/
OLD_TAKE_SUFFIX = ".saxscribe"


def home() -> Path:
    return Path.home()


def pick(new: Path, old: Path) -> Path:
    """The new folder, unless only the old one exists yet."""
    if new.exists() or not old.exists():
        return new
    return old


def _home_pair(pair: tuple[str, str]) -> Path:
    return pick(home() / pair[0], home() / pair[1])


def runs() -> Path:
    """Scorecards, keys, the catalog, the ledger, and saved Mac scripts."""
    return _home_pair(RUNS)


def library() -> Path:
    """The app's uploads and their takes."""
    return _home_pair(LIBRARY)


def cache() -> Path:
    """Downloaded model weights and page images."""
    return _home_pair(CACHE)


def env(name: str, default: str | None = None) -> str | None:
    """A setting from the environment: LIFT_<name>, else SAXSCRIBE_<name>, else default.
    An empty value counts as unset, as it always has."""
    return os.environ.get(f"LIFT_{name}") or os.environ.get(f"SAXSCRIBE_{name}") or default


def runs_prefixes() -> tuple[str, ...]:
    """How stored paths (ledger rows, links.csv) may spell the runs folder, old and new."""
    out = []
    for name in RUNS:
        out += [f"~/{name}/", str(home() / name) + "/"]
    return tuple(out)
