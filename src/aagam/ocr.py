"""Reading scanned pages with Windows' own OCR engine.

Windows 10 and 11 include an OCR engine (Windows.Media.Ocr), so her laptop
needs nothing extra. A scanned page is rendered at about 180 dpi, read, and
its text stored with the page, which makes it searchable and lets facts,
types and resolutions be found in it. The page stays marked as a scan, so
Claude Desktop still gets the image itself to read, which is more reliable
than any OCR.

On other systems, or if the engine isn't available, this does nothing and
says so.
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("aagam.ocr")
OCR_SCALE = 2.5  # PDF points to pixels: about 180 dpi
INLINE_PAGES = 5  # documents with more scanned pages than this are read in the background


def available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.media.ocr import OcrEngine

        return OcrEngine.try_create_from_user_profile_languages() is not None
    except Exception:  # missing package, or no OCR language installed
        return False


async def _recognise(png: bytes) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def recognise(png: bytes) -> str:
    """Text in an image (PNG or JPEG bytes)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_recognise(png))
    # Called from inside an event loop (the web server): run on a fresh loop in a worker thread.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_recognise(png))).result()


def page_image(path: Path, page_no: int) -> bytes:
    """A page rendered for OCR, as PNG bytes. Images are passed through, scaled down if huge."""
    from PIL import Image

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        try:
            page = pdf[page_no - 1]
            image = page.render(scale=OCR_SCALE).to_pil()
            page.close()
        finally:
            pdf.close()
    else:
        image = Image.open(path)
        image.thumbnail((9000, 9000))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def ocr_document(vault: Any, home: Path, document_id: int, pages: list[int] | None = None) -> dict[str, Any]:
    """OCR the scanned pages of a document (or the given ones) and store their text."""
    if not available():
        return {"read": [], "skipped": "Windows OCR isn't available on this computer."}
    row = vault.conn.execute("SELECT stored_path FROM documents WHERE id = ?", (document_id,)).fetchone()
    path = home / row["stored_path"]
    wanted = pages or [
        r[0] for r in vault.conn.execute(
            "SELECT page_no FROM document_pages WHERE document_id = ? AND needs_vision = 1 AND length(text) < 25", (document_id,)
        )
    ]
    read = []
    for page_no in wanted:
        try:
            text = recognise(page_image(path, page_no)).strip()
        except Exception as exc:
            log.warning("OCR failed on document %s page %s: %s", document_id, page_no, exc)
            continue
        if text:
            vault.conn.execute(
                "UPDATE document_pages SET text = ? WHERE document_id = ? AND page_no = ?", (text, document_id, page_no)
            )
            read.append(page_no)
    if read:
        vault.conn.execute(
            """INSERT INTO doc_meta (document_id, ocr_pages) VALUES (?, ?)
               ON CONFLICT(document_id) DO UPDATE SET ocr_pages = excluded.ocr_pages""",
            (document_id, ",".join(str(p) for p in read)),
        )
    return {"read": read}
