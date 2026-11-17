"""Songs cut from a book (app/catalog.chart_pages): the Library shows only that song's pages."""
from __future__ import annotations

import json
from fractions import Fraction

import pytest

from lift.app import catalog, key_take

from .test_library_page import make_runs

SONG = "ben-webster_the-touch-of-your-lips_1959"


def song_folder(runs, sid):
    d = runs / "keys" / "transcribed" / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_book_solo_pages_come_from_the_bars_note(tmp_path):
    runs = tmp_path / "runs"
    book = runs / "keys" / "transcribed" / "_books" / "dg" / "dg.pdf"
    book.parent.mkdir(parents=True)
    book.write_bytes(b"%PDF book")
    d = song_folder(runs, "dexter-gordon_fried-bananas_1969")
    key = d / "dexter-gordon_fried-bananas_1969_key.json"
    key.write_text("[]")
    (d / "dexter-gordon_fried-bananas_1969_bars.txt").write_text("# dexter-gordon_fried-bananas_1969 homr (pages 5-7)\n1 @4 r/4\n")
    assert catalog.chart_pages(runs, "dexter-gordon_fried-bananas_1969", book, key) == (book, [5, 6, 7])

    d2 = song_folder(runs, "dexter-gordon_valse-robin_1970")  # a retyped key's note, with more after it
    (d2 / "dexter-gordon_valse-robin_1970_bars.txt").write_text(
        "# dexter-gordon_valse-robin_1970 full retype (pages 63-65 of the book; tenor, written pitch, 3/4)\n")
    assert catalog.chart_pages(runs, "dexter-gordon_valse-robin_1970", book, None) == (book, [63, 64, 65])


def test_own_transcription_pdf_wins_over_a_book_without_a_page_note(tmp_path):
    runs = tmp_path / "runs"
    book = runs / "book.pdf"
    runs.mkdir()
    book.write_bytes(b"%PDF book")
    d = song_folder(runs, "john-coltrane_pursuance_1964")
    (d / "john-coltrane_pursuance_1964_bars.txt").write_text("# john-coltrane_pursuance_1964: homr OMR of its pdf\n")
    own = d / "john-coltrane_pursuance_1964_transcription.pdf"
    own.write_bytes(b"%PDF own")
    assert catalog.chart_pages(runs, "john-coltrane_pursuance_1964", book, None) == (own, None)
    assert catalog.chart_pages(runs, "nobody_nothing", book, None) == (book, None)  # no note: the whole PDF


def test_etude_pages(tmp_path):
    runs = tmp_path / "runs"
    keys = runs / "keys" / "etudes" / "keys"
    omr = runs / "keys" / "etudes" / "omr"
    keys.mkdir(parents=True)
    omr.mkdir(parents=True)
    for p in ("f-01", "f-02", "f-03", "l-02", "l-03"):
        (omr / f"{p}.musicxml").write_text("")
    ends = {1: "f-01", 2: "f-01", 3: "f-02", 4: "f-02", 5: "f-03"}
    for n, p in ends.items():
        (keys / f"study{n:02d}_bars.txt").write_text(f"# study {n}, OMR (homr) of IMSLP scan, ends on {p}.musicxml; written pitch\n")
    (keys / "luft02_bars.txt").write_text("# study 3, OMR (homr) of IMSLP scan, ends on l-03.musicxml; written pitch\n")
    book = runs / "ferling.pdf"
    book.write_bytes(b"%PDF")
    got = {sid: catalog.chart_pages(runs, sid, book, None)[1]
           for sid in ("ferling01_wonki", "ferling02_wonki", "ferling03_x", "ferling05_x", "luft02_voxman")}
    assert got == {"ferling01_wonki": [1], "ferling02_wonki": [1], "ferling03_x": [2], "ferling05_x": [3],
                   "luft02_voxman": [2, 3]}


def test_song_page_routes_show_only_the_songs_pages(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pdfium = pytest.importorskip("pypdfium2")
    from fastapi.testclient import TestClient

    from lift.app import pdf_pages
    from lift.app.library import Library
    from lift.app.server import create_app

    monkeypatch.setattr(pdf_pages, "CACHE", tmp_path / "pages")
    runs = make_runs(tmp_path)  # the chart there is a 2-page PDF outside the song's folder
    (runs / "keys" / "transcribed" / SONG / f"{SONG}_bars.txt").write_text(f"# {SONG} homr (pages 2-2)\n")
    c = TestClient(create_app(Library(tmp_path / "lib", inline=True), runs=runs))
    info = c.get(f"/api/library/{SONG}").json()
    assert info["pages"] == 1 and info["book_pages"] == [2]
    assert c.get(f"/api/library/{SONG}/page/1").status_code == 200
    assert c.get(f"/api/library/{SONG}/page/2").status_code == 404
    r = c.get(f"/api/library/{SONG}/pdf")
    out = tmp_path / "cut.pdf"
    out.write_bytes(r.content)
    assert len(pdfium.PdfDocument(str(out))) == 1


def test_rhythms_no_note_value_can_write_are_snapped(tmp_path):
    """A bar rebuilt from the key can put notes on spots like 123/740 of a beat; the score still writes."""
    pytest.importorskip("music21")
    notes = [{"onset": 0.5 * i, "offset": 0.5 * i + 0.2, "pitch": 60 + i, "beat": b, "bar": 1}
             for i, b in enumerate([0, 1, 1 + 123 / 740, 1 + 1603 / 740, 3.5])]
    k = tmp_path / "key.json"
    k.write_text(json.dumps(notes))
    bars = tmp_path / "bars.txt"
    bars.write_text("1 @9/2 r/1 C5/1 C5/0.2 E5/0.2 G5/0.1 C6/2\n")  # a 5-tuplet-ish reading that won't match
    take = key_take.build(k, bars, "tenor", tmp_path / "take")
    nota = json.loads(take.notation.read_text())
    assert sorted(n["index"] for n in nota["notes"]) == list(range(5))  # nothing dropped
    for n in nota["notes"]:
        assert (Fraction(n["beat"]) * 48).denominator == 1 and Fraction(n["length_beats"]) > 0
    assert take.written_musicxml("tenor").exists()


def test_perform_line_unrolls_repeats_and_gaps(tmp_path):
    b = tmp_path / "x_bars.txt"
    b.write_text("# x homr (pages 1-2)\n# perform: 0-2 1-1 r2 3-4\n0 @1 D5/1\n1 @3 F5/3\n2 @3 E5/2 r/1 # proofread note C5/1\n"
                 "3-4 @3 rest\n")
    bars = key_take.read_bars(b)
    assert [x["bar"] for x in bars] == [0, 1, 2, 1, 0, 0, 3, 4]
    assert [x["length"] for x in bars] == [1, 3, 3, 3, 4, 4, 3, 3]
    assert [t["name"] for t in bars[2]["tokens"]] == ["E5", "r"]  # the inline note isn't read as notes


def test_repeated_bars_are_found_at_their_first_pass():
    from lift.app.score_view import bar_q
    at = bar_q({"bar_starts": ["0", "1", "4", "7", "10"], "bar_numbers": [0, 1, 2, 1, 3], "bar_end": "13"})
    assert at(1) == 1 and at(3) == 10 and at(4) == 13
