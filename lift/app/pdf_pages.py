"""Chart PDF pages as PNG images, for the Library song page.

iPad Safari shows only the first page of a PDF inside a page, so each page is drawn
to an image once (pypdfium2, the PDF engine Chrome uses) and kept in a cache keyed by
the PDF's fingerprint: ~/.cache/lift/pages/<sha256>/<n>.png. The PDF itself is
never changed.
"""
from __future__ import annotations

from pathlib import Path
from .. import paths

CACHE = paths.cache() / "pages"
WIDTH = 1700  # pixels across: sharp on an iPad held upright, about 200 dpi for a letter page


def count(pdf: Path) -> int:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        return len(doc)
    finally:
        doc.close()


def png(pdf: Path, sha: str, n: int, cache: Path | None = None) -> Path:
    """Page n (from 1) as a PNG, drawn once and then read from the cache. IndexError past the last page."""
    out = (cache or CACHE) / sha / f"{n}.png"
    if out.exists():
        return out
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        if not 1 <= n <= len(doc):
            raise IndexError(n)
        page = doc[n - 1]
        width_pt = page.get_width() or 612
        image = page.render(scale=WIDTH / width_pt).to_pil()
        page.close()
    finally:
        doc.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.png")
    image.save(tmp, optimize=True)
    tmp.replace(out)
    return out


def cut(pdf: Path, sha: str, pages: list[int], cache: Path | None = None) -> Path:
    """A PDF of just these pages (from 1) of a book, made once and kept next to the page images.
    The book itself is never changed."""
    out = (cache or CACHE) / sha / f"pages-{pages[0]}-{pages[-1]}.pdf"
    if out.exists():
        return out
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    try:
        keep = [n - 1 for n in pages if 1 <= n <= len(doc)]
        if not keep:
            raise IndexError(pages[0])
        new = pdfium.PdfDocument.new()
        new.import_pages(doc, keep)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.pdf")
        new.save(str(tmp))
        new.close()
    finally:
        doc.close()
    tmp.replace(out)
    return out
