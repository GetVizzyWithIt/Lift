"""Saxscribe was renamed Lift (ADR-0047). Old imports, the old command, old
settings, old folders, and old take folders all keep working."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import lift
from lift import paths

ROOT = Path(__file__).resolve().parents[1]


def test_old_imports_are_the_same_modules():
    import saxscribe
    import saxscribe.score.card as old_card
    from saxscribe.take import default_folder as old_default_folder

    import lift.score.card as card
    from lift.take import default_folder

    assert old_card is card                      # one copy, not two
    assert old_default_folder is default_folder
    assert card.__spec__.name == "lift.score.card"
    assert saxscribe.LAYERS == lift.LAYERS


def test_old_command_still_runs():
    for pkg in ("lift", "saxscribe"):
        out = subprocess.run([sys.executable, "-m", pkg, "--help"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        assert "usage: lift" in out and "transcribe" in out


def test_settings_read_new_name_then_old(monkeypatch):
    monkeypatch.delenv("LIFT_TEST_SETTING", raising=False)
    monkeypatch.delenv("SAXSCRIBE_TEST_SETTING", raising=False)
    assert paths.env("TEST_SETTING", "default") == "default"
    monkeypatch.setenv("SAXSCRIBE_TEST_SETTING", "old")
    assert paths.env("TEST_SETTING") == "old"
    monkeypatch.setenv("LIFT_TEST_SETTING", "new")
    assert paths.env("TEST_SETTING") == "new"


def test_folders_prefer_new_and_fall_back_to_old(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "home", lambda: tmp_path)
    # Nothing there yet: the new names.
    assert paths.runs() == tmp_path / "lift-runs"
    assert paths.library() == tmp_path / "lift-library"
    assert paths.cache() == tmp_path / ".cache" / "lift"
    # Only the old folders (before the Mac move): the old names.
    (tmp_path / "saxscribe-runs").mkdir()
    (tmp_path / "saxscribe-library").mkdir()
    (tmp_path / ".cache" / "saxscribe").mkdir(parents=True)
    assert paths.runs() == tmp_path / "saxscribe-runs"
    assert paths.library() == tmp_path / "saxscribe-library"
    assert paths.cache() == tmp_path / ".cache" / "saxscribe"
    # After the move: the new names win.
    (tmp_path / "lift-runs").mkdir()
    assert paths.runs() == tmp_path / "lift-runs"


def test_new_takes_get_lift_folders_and_old_ones_are_reused(tmp_path):
    from lift.take import default_folder
    wav = tmp_path / "song.wav"
    assert default_folder(wav) == tmp_path / "song.lift"
    (tmp_path / "song.saxscribe").mkdir()            # a take made before the rename
    assert default_folder(wav) == tmp_path / "song.saxscribe"
    (tmp_path / "song.lift").mkdir()
    assert default_folder(wav) == tmp_path / "song.lift"


def test_stored_paths_with_either_runs_name_map_to_the_runs_folder(tmp_path):
    from lift.app.catalog import local_path
    for stored in ("~/saxscribe-runs/keys/a.pdf", "~/lift-runs/keys/a.pdf",
                   str(Path.home() / "saxscribe-runs" / "keys" / "a.pdf"),
                   str(Path.home() / "lift-runs" / "keys" / "a.pdf")):
        assert local_path(tmp_path, stored) == tmp_path / "keys" / "a.pdf"


def test_no_code_still_runs_the_old_command():
    # The launcher, setup, and CI start the app as lift; only the saxscribe/ alias says saxscribe.
    for rel in ("setup_mac.sh", "scripts/mac_app/launch.sh", "scripts/mac_app/build_app.sh",
                ".github/workflows/tests.yml"):
        assert "-m saxscribe" not in (ROOT / rel).read_text(), rel
