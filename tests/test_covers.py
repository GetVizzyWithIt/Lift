"""Album covers for the Library cards: where they come from, what is trusted, and the logo fallback."""
from __future__ import annotations

import io
import json
import shutil
import subprocess

import pytest

from lift.app import covers

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def test_only_jpeg_or_png_is_kept(tmp_path):
    assert covers.save("a", b"<html>not a picture</html>", tmp_path) is None
    assert covers.save("a", PNG, tmp_path).name == "a.png"
    assert covers.save("a", JPG, tmp_path).name == "a.jpg"            # a new cover replaces the old one
    assert not (tmp_path / "a.png").exists()
    assert covers.cached("a", tmp_path).name == "a.jpg" and covers.have(tmp_path) == {"a"}


def test_an_image_beside_the_recording_is_used(tmp_path):
    audio = tmp_path / "Parker - Confirmation.mp3"
    audio.write_bytes(b"")
    assert covers.nearby(audio) is None
    (tmp_path / "Folder.JPG").write_bytes(JPG)
    assert covers.nearby(audio) == JPG
    (tmp_path / "Parker - Confirmation.png").write_bytes(PNG)        # its own image wins over folder.jpg
    assert covers.nearby(audio) == PNG


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_art_inside_the_audio_file_is_pulled_out(tmp_path):
    pic, song = tmp_path / "pic.png", tmp_path / "song.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=orange:s=32x32", "-frames:v", "1",
                    str(pic)], check=True)
    made = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=0.5", "-i", str(pic),
                           "-map", "0:a", "-map", "1:v", "-c:v", "copy", "-disposition:v", "attached_pic",
                           "-id3v2_version", "3", str(song)])
    if made.returncode:
        pytest.skip("this ffmpeg can't write MP3")
    data = covers.embedded(song)
    assert data and data[:3] == b"\xff\xd8\xff"
    plain = tmp_path / "plain.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=0.5", str(plain)], check=True)
    assert covers.embedded(plain) is None


def fake_mb(score, artist, kind="release"):
    def get(url):
        if "coverartarchive" in url:
            return JPG
        rel = {"id": "mbid-1", "title": "Bird Symbols", "score": score,
               "artist-credit": [{"name": artist}]}
        if kind == "release":
            return json.dumps({"releases": [rel]}).encode()
        return json.dumps({"recordings": [{"score": score, "releases": [rel]}]}).encode()
    return get


def test_a_lookup_is_trusted_only_with_a_high_score_and_the_right_player():
    sure = covers.lookup("Charlie Parker", "Bird Symbols", "Confirmation", get=fake_mb(100, "Charlie Parker"))
    assert sure["sure"] and sure["url"].endswith("/mbid-1/front-250")
    assert not covers.lookup("Charlie Parker", "Bird Symbols", "x", get=fake_mb(70, "Charlie Parker"))["sure"]
    assert not covers.lookup("Charlie Parker", "Bird Symbols", "x", get=fake_mb(100, "Sonny Stitt"))["sure"]
    # with no record name, a tune match could be any compilation: never trusted without a look
    assert not covers.lookup("Charlie Parker", "", "Confirmation", get=fake_mb(100, "Charlie Parker", "recording"))["sure"]
    assert covers.lookup("", "Bird Symbols", "x", get=fake_mb(100, "x")) is None


def test_a_run_saves_sure_covers_lists_unsure_ones_and_follows_overrides(tmp_path, capsys):
    where = tmp_path / "covers"
    songs = [{"id": "sure", "player": "Charlie Parker", "record": "Bird Symbols", "title": "Confirmation"},
             {"id": "unsure", "player": "Charlie Parker", "record": "", "title": "Confirmation"},
             {"id": "beside", "player": "X", "record": "", "title": "Y"},
             {"id": "dropped", "player": "Charlie Parker", "record": "Bird Symbols", "title": "Z"}]
    beside = tmp_path / "rec" / "y.mp3"
    beside.parent.mkdir()
    beside.write_bytes(b"")
    (beside.parent / "cover.jpg").write_bytes(JPG)
    where.mkdir()
    (where / "overrides.csv").write_text("id,source\ndropped,none\n")
    get = lambda url: (fake_mb(100, "Charlie Parker", "recording") if "recording/" in url  # noqa: E731
                       else fake_mb(100, "Charlie Parker"))(url)
    counts = covers.run(where=where, songs=songs, audio_of=lambda s: beside if s["id"] == "beside" else None,
                        get=get, pause=0)
    assert covers.cached("sure", where) and covers.cached("beside", where)
    assert not covers.cached("unsure", where) and not covers.cached("dropped", where)
    assert (counts["lookup"], counts["nearby"], counts["needs_a_look"], counts["logo"]) == (1, 1, 1, 2)
    assert "unsure" in (where / "needs_a_look.csv").read_text()
    assert "needs_a_look: 1" in (where / "_summary.txt").read_text()
    again = covers.run(where=where, songs=songs[:1], audio_of=lambda s: None, get=get, pause=0)
    assert again["already"] == 1                                       # found covers aren't looked up again


def test_offline_runs_never_touch_the_network(tmp_path):
    def boom(url):
        raise AssertionError("went online")
    counts = covers.run(where=tmp_path, songs=[{"id": "a", "player": "P", "record": "R", "title": "T"}],
                        audio_of=lambda s: None, get=boom, online=False, pause=0)
    assert counts["logo"] == 1


def test_the_app_serves_a_saved_cover_and_404s_otherwise(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from lift.app.library import Library
    from lift.app.server import create_app
    monkeypatch.setattr(covers, "folder", lambda: tmp_path / "covers")
    covers.save("parker_confirmation_1946", JPG)
    c = TestClient(create_app(Library(tmp_path / "lib", inline=True)))
    r = c.get("/api/library/parker_confirmation_1946/cover")
    assert r.status_code == 200 and io.BytesIO(r.content).read(3) == b"\xff\xd8\xff"
    assert c.get("/api/library/someone_else/cover").status_code == 404
    assert "app-icon.svg" in c.get("/static/library.js").text            # the fallback the cards use
    assert c.get("/static/brand/app-icon.svg").status_code == 200


def http_error(url, code):
    import urllib.error
    return urllib.error.HTTPError(url, code, "x", {}, None)


def test_a_release_with_no_scan_falls_back_to_its_album_cover(tmp_path):
    """Cover Art Archive often has no scan for one pressing; the album (release group) cover is used."""
    def get(url):
        if "coverartarchive.org/release/" in url:
            raise http_error(url, 404)
        if "musicbrainz.org/ws/2/release/" in url:
            return json.dumps({"release-group": {"id": "grp-1"}}).encode()
        if "release-group/grp-1/front-250" in url:
            return JPG
        raise AssertionError(url)
    rel = "0e0e0e0e-0000-0000-0000-000000000000"
    (tmp_path / "overrides.csv").write_text(f"id,source\na,https://coverartarchive.org/release/{rel}/front-250\n")
    counts = covers.run(where=tmp_path, songs=[{"id": "a", "player": "P", "record": "R", "title": "T"}],
                        audio_of=lambda s: None, get=get, pause=0)
    assert counts["override"] == 1 and counts["errors"] == 0 and covers.cached("a", tmp_path)


def test_errors_are_counted_by_reason(tmp_path):
    def get(url):
        raise http_error(url, 503)
    counts = covers.run(where=tmp_path, songs=[{"id": "a", "player": "P", "record": "R", "title": "T"}],
                        audio_of=lambda s: None, get=get, pause=0)
    assert counts["errors"] == 1 and counts["why"] == {"MusicBrainz busy": 1}
    assert "MusicBrainz busy" in (tmp_path / "_summary.txt").read_text()


def test_busy_answers_are_retried(monkeypatch):
    import urllib.request
    calls = []

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise http_error(req.full_url, 503)
        return R(JPG)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(covers.time, "sleep", lambda s: None)
    assert covers._get("https://musicbrainz.org/x") == JPG and len(calls) == 3


def test_record_notes_are_tidied_into_album_names():
    assert covers.tidy_record("Blue Train (Blue Note BST 81577)") == ("", "Blue Train")
    assert covers.tidy_record("Foreigner - 4 (Atlantic, 1981), 2008 remaster") == ("Foreigner", "4")
    assert covers.tidy_record("Kaleidoscope,") == ("", "Kaleidoscope")
    assert covers.tidy_record("") == ("", "")


def test_the_researched_album_names_are_read_and_name_real_songs():
    named = covers.albums()
    assert named["andrew-love_takin-it-to-the-streets_1976"] == ("The Doobie Brothers", "Takin' It to the Streets")
    assert all(album for _, album in named.values())


def test_a_sidemans_solo_matches_on_the_album_artist():
    """Andrew Love plays on a Doobie Brothers record: the release credits them, not him."""
    seen = []

    def get(url):
        seen.append(urllib.parse.unquote_plus(url))
        if "coverartarchive" in url:
            return JPG
        return fake_mb(100, "The Doobie Brothers")(url)
    import urllib.parse
    hit = covers.lookup("Andrew Love", "Takin' It to the Streets", "x", get=get, album_artist="The Doobie Brothers")
    assert hit["sure"] and 'artist:"The Doobie Brothers"' in seen[0]
    assert not covers.lookup("Andrew Love", "Takin' It to the Streets", "x", get=get)["sure"]


def test_an_album_musicbrainz_doesnt_know_falls_back_to_a_tune_suggestion():
    def get(url):
        if "release/?" in url:
            return json.dumps({"releases": []}).encode()
        return fake_mb(100, "Charlie Parker", "recording")(url)
    hit = covers.lookup("Charlie Parker", "Some Lost 78", "Confirmation", get=get)
    assert hit and not hit["sure"]


def test_candidates_without_a_picture_are_skipped(tmp_path):
    """MusicBrainz often lists a release with no scan first: the run walks on to one that has a cover."""
    import urllib.error

    def rel(i, artist="Michael Brecker"):
        return {"id": f"rel-{i}", "title": f"Press {i}", "score": 100, "artist-credit": [{"name": artist}],
                "release-group": {"id": f"grp-{i}"}}

    def get(url):
        if "musicbrainz.org/ws/2/release/?" in url:
            return json.dumps({"releases": [rel(1), rel(2)]}).encode()
        if "rel-2/" in url:
            return PNG
        if "coverartarchive" in url:
            raise urllib.error.HTTPError(url, 404, "x", {}, None)
        raise AssertionError(url)
    counts = covers.run(where=tmp_path, songs=[{"id": "a", "player": "Michael Brecker", "record": "Album", "title": "T"}],
                        audio_of=lambda s: None, get=get, pause=0)
    assert counts["lookup"] == 1 and covers.cached("a", tmp_path).suffix == ".png"


def test_an_override_with_no_picture_falls_back_to_a_lookup(tmp_path):
    import urllib.error

    def get(url):
        if "dead" in url:
            raise urllib.error.HTTPError(url, 404, "x", {}, None)
        return fake_mb(100, "Charlie Parker")(url)
    (tmp_path / "overrides.csv").write_text("id,source\na,https://example.org/dead.jpg\n")
    counts = covers.run(where=tmp_path, songs=[{"id": "a", "player": "Charlie Parker", "record": "Bird", "title": "T"}],
                        audio_of=lambda s: None, get=get, pause=0)
    assert counts["lookup"] == 1 and covers.cached("a", tmp_path)


def test_suggestions_only_list_covers_that_exist(tmp_path):
    import urllib.error

    def get(url):
        if "recording/?" in url:
            return json.dumps({"recordings": [{"score": 100, "releases": [
                {"id": "r1", "title": "No Scan", "artist-credit": [{"name": "P"}]},
                {"id": "r2", "title": "Has Scan", "artist-credit": [{"name": "P"}]}]}]}).encode()
        if "/r1/" in url:
            raise urllib.error.HTTPError(url, 404, "x", {}, None)
        return JPG
    covers.run(where=tmp_path, songs=[{"id": "a", "player": "P", "record": "", "title": "T"}],
               audio_of=lambda s: None, get=get, pause=0)
    text = (tmp_path / "needs_a_look.csv").read_text()
    assert "Has Scan" in text and "No Scan" not in text
