"""The Lift look: every main page gets the shared top bar, the Lift icons, and says Lift, not Saxscribe."""
from __future__ import annotations

import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from lift.app.library import Library  # noqa: E402
from lift.app.server import create_app  # noqa: E402

PAGES = {"/": "transcribe", "/library": "library", "/results": "results", "/review": "review"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(create_app(Library(tmp_path_factory.mktemp("library"), inline=True)))


@pytest.mark.parametrize("path,page", PAGES.items())
def test_main_pages_ask_for_the_top_bar_and_carry_the_icons(client, path, page):
    html = client.get(path).text
    assert f'<body data-page="{page}">' in html
    assert 'href="/static/brand/favicon.svg"' in html and 'href="/static/brand/apple-touch-icon.png"' in html
    assert "/static/common.js" in html          # liftBar() lives there
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert "Lift" in title and "Saxscribe" not in title


def test_the_brand_files_are_served(client):
    for name in ("favicon.svg", "logo-dark.svg", "apple-touch-icon.png"):
        assert client.get(f"/static/brand/{name}").status_code == 200


def test_the_bar_links_every_main_page_and_counts_review_questions(client):
    js = client.get("/static/common.js").text
    for path in PAGES:
        assert f"'{path}'" in js
    assert "/api/review/inbox" in js and "liftReviewCount" in js


def test_no_page_says_saxscribe_to_the_user(client):
    """Only internal ids (the take source id and saved-settings keys) may still say saxscribe."""
    for name in ("index.html", "library.html", "song.html", "results.html", "review.html", "play.html",
                 "print.html", "library.js", "song.js", "play.js", "review.js", "results.js"):
        text = client.get(f"/static/{name}").text
        assert "Saxscribe" not in text, name
