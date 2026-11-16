from __future__ import annotations

import os
import tempfile

import pytest

# Settings exported in the shell (LIFT_* or the old SAXSCRIBE_*, e.g. LIFT_FINDER=original)
# would change what the tests see, so the tests start without any of them.
for _name in [n for n in os.environ if n.startswith(("LIFT_", "SAXSCRIBE_"))]:
    del os.environ[_name]

from lift.pipeline import transcribe  # noqa: E402

from . import fixture

# Tests never write to the real Desktop: the app's copy goes to a temp folder.
DESKTOP = os.environ["LIFT_DESKTOP"] = tempfile.mkdtemp(prefix="lift-desktop-")


@pytest.fixture(scope="session")
def fixture_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "phrase.wav"
    fixture.make(path)
    return path


@pytest.fixture(scope="session", params=["best", "light"])
def take(request, fixture_wav, tmp_path_factory):
    """The fixture run through every layer twice: with the best tools installed,
    and with the light fallbacks (pYIN contour, notes cut from it)."""
    out = tmp_path_factory.mktemp(f"take-{request.param}")
    if request.param == "best":
        return transcribe(fixture_wav, out)
    return transcribe(fixture_wav, out, contour_tool="pyin", notes_tool="contour")
