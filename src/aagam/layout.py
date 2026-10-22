"""Rows of a page as they look, rebuilt from where the text sits.

Many PDFs store a table's captions as one block of text and its figures as
another, so reading the text layer in order puts every figure far from its
caption. Financial statements need each caption on the same line as its
figures, so for those pages the text is rebuilt row by row from positions:
segments whose vertical centres line up form a row, read left to right.

Scanned statements get the same treatment from the OCR engine's word boxes.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median


def _rows(segments: list[tuple[float, float, float, str]], top_down: bool) -> str:
    """segments: (vertical centre, left, height, text). Returns one line per row."""
    if not segments:
        return ""
    tolerance = max(2.0, median(s[2] for s in segments) * 0.5)
    ordered = sorted(segments, key=lambda s: ((s[0] if top_down else -s[0]), s[1]))
    rows: list[list[tuple[float, float, float, str]]] = []
    for seg in ordered:
        if rows and abs(rows[-1][0][0] - seg[0]) <= tolerance:
            rows[-1].append(seg)
        else:
            rows.append([seg])
    return "\n".join("  ".join(s[3] for s in sorted(row, key=lambda s: s[1])) for row in rows)


def pdf_rows(path: Path, page_no: int) -> str:
    import pypdfium2 as pdfium

    from csdesk.documents.intake import PDFIUM

    with PDFIUM:
        pdf = pdfium.PdfDocument(path)
        try:
            page = pdf[page_no - 1]
            textpage = page.get_textpage()
            segments = []
            for index in range(textpage.count_rects()):
                left, bottom, right, top = textpage.get_rect(index)
                text = " ".join(textpage.get_text_bounded(left, bottom, right, top).split())
                if text:
                    segments.append(((bottom + top) / 2, left, top - bottom, text))
            textpage.close()
            page.close()
        finally:
            pdf.close()
    return _rows(segments, top_down=False)  # PDF y grows upwards


def ocr_rows(png: bytes) -> str:
    """OCR an image and return its words grouped into visual rows."""
    import asyncio

    async def recognise() -> list[tuple[float, float, float, str]]:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(png)
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
        result = await OcrEngine.try_create_from_user_profile_languages().recognize_async(bitmap)
        words = []
        for line in result.lines:
            for word in line.words:
                box = word.bounding_rect
                words.append((box.y + box.height / 2, box.x, box.height, word.text))
        return words

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        words = pool.submit(lambda: asyncio.run(recognise())).result()
    return _rows(words, top_down=True)  # image y grows downwards
