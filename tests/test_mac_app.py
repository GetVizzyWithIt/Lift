"""The Lift launcher (scripts/mac_app) and the app's quit-when-idle check."""
from __future__ import annotations

import plistlib
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

MAC_APP = Path(__file__).resolve().parents[1] / "scripts" / "mac_app"


def test_info_plist_names_the_launcher_and_icon():
    info = plistlib.loads((MAC_APP / "Info.plist").read_bytes())
    assert info["CFBundleName"] == "Lift"
    assert info["CFBundleExecutable"] == "launch"
    assert info["CFBundleIconFile"] == "AppIcon"
    assert info["LSUIElement"] is True
    assert info["NSDesktopFolderUsageDescription"]


def test_icon_is_a_1024_png():
    data = (MAC_APP / "AppIcon-1024.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (1024, 1024)


def test_launch_script_has_paths_to_fill_in():
    text = (MAC_APP / "launch.sh").read_text()
    assert '"@REPO@"' in text and '"@PYTHON@"' in text
    assert "--quit-when-idle" in text


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("name", ["launch.sh", "build_app.sh"])
def test_scripts_parse(name):
    subprocess.run(["bash", "-n", str(MAC_APP / name)], check=True)


def test_should_quit():
    pytest.importorskip("fastapi")
    from saxscribe.app.server import should_quit

    assert not should_quit(0, 60 * 29, 30, busy=False)      # a page checked in recently
    assert should_quit(0, 60 * 30, 30, busy=False)          # nobody for 30 minutes
    assert not should_quit(0, 60 * 90, 30, busy=True)       # never mid-transcription
    assert not should_quit(0, 60 * 90, 0, busy=False)       # 0 = never (started from Terminal)


def test_alive_route_and_busy(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from saxscribe.app.library import Library
    from saxscribe.app.server import create_app

    library = Library(tmp_path / "library")
    app = create_app(library)
    before = app.state.last_seen
    r = TestClient(app).post("/api/alive")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "busy": False}
    assert app.state.last_seen >= before
