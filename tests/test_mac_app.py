"""The Lift launcher (scripts/mac_app) and the app's quit-when-idle check."""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

MAC_APP = Path(__file__).resolve().parents[1] / "scripts" / "mac_app"


def test_build_makes_an_applescript_app_that_can_ask_for_the_desktop():
    # A shell-script app never gets macOS's Desktop permission question, so Lift
    # is an AppleScript app that runs launch.sh; its Info.plist says why it asks.
    text = (MAC_APP / "build_app.sh").read_text()
    assert "osacompile" in text and 'path to resource "launch.sh"' in text
    assert "NSDesktopFolderUsageDescription" in text
    assert "LSUIElement -bool YES" in text
    assert "lift-build.sha256" in text  # unchanged builds leave the app (and its permission) alone


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
    from lift.app.server import should_quit

    assert not should_quit(0, 60 * 29, 30, busy=False)      # a page checked in recently
    assert should_quit(0, 60 * 30, 30, busy=False)          # nobody for 30 minutes
    assert not should_quit(0, 60 * 90, 30, busy=True)       # never mid-transcription
    assert not should_quit(0, 60 * 90, 0, busy=False)       # 0 = never (started from Terminal)


def test_alive_route_and_busy(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from lift.app.library import Library
    from lift.app.server import create_app

    library = Library(tmp_path / "library")
    app = create_app(library)
    before = app.state.last_seen
    r = TestClient(app).post("/api/alive")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "busy": False}
    assert app.state.last_seen >= before


def test_quit_stops_the_server_but_not_mid_transcription(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from lift.app.library import Library
    from lift.app.server import create_app

    library = Library(tmp_path / "library")
    app = create_app(library)
    app.state.server = SimpleNamespace(should_exit=False)
    c = TestClient(app)
    monkeypatch.setattr(library, "busy", lambda: True)
    assert c.post("/api/quit").status_code == 409 and not app.state.server.should_exit
    assert c.post("/api/quit?force=true").status_code == 200 and app.state.server.should_exit
    monkeypatch.setattr(library, "busy", lambda: False)
    app.state.server.should_exit = False
    assert c.post("/api/quit").json() == {"quitting": True} and app.state.server.should_exit
    assert c.get("/api/version").json()["code"] == app.state.code


def test_launcher_restarts_a_server_running_old_code():
    text = (MAC_APP / "launch.sh").read_text()
    assert "api/version" in text and "rev-parse HEAD" in text and "api/quit" in text


def test_the_top_bar_has_a_quit_button():
    js = (Path(__file__).resolve().parents[1] / "lift" / "app" / "static" / "common.js").read_text()
    assert 'id="liftQuit"' in js and "/api/quit" in js
