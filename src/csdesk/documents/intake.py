"""Bringing documents in: keep a copy, pull out the text, flag pages that need eyes.

Text-layer PDFs, Word files, spreadsheets and plain text are read here.
Scanned pages and photos have no text layer: they are flagged `needs_vision`,
and read_pages hands them to Claude as page images instead.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import CsDeskError, Invalid, NotFound
from ..vault import Vault

MAX_BYTES = 60 * 1024 * 1024
MAX_PAGES_PER_READ = 10
MAX_CHARS_PER_READ = 60_000
SCAN_THRESHOLD = 25  # a page with less text than this is treated as a scan
IMAGE_LONG_SIDE = 1568  # Claude reads images at up to about this many pixels on the long side
# PDFium can't be used from two threads at once, not even on different files, and the web server, OCR and folder
# readers each have threads: every use of it holds this lock.
PDFIUM = threading.RLock()

DOC_TYPES: dict[str, str] = {
    "certificate_of_incorporation": "Certificate of Incorporation",
    "moa": "Memorandum of Association",
    "aoa": "Articles of Association",
    "llp_agreement": "LLP agreement (or supplementary agreement)",
    "board_resolution": "Board resolution (certified true copy)",
    "partners_resolution": "Partners' resolution (certified true copy)",
    "minutes": "Minutes of a meeting",
    "notice": "Notice or agenda of a meeting",
    "attendance": "Attendance record of a meeting",
    "financial_statements": "Audited financial statements",
    "auditor_report": "Auditor's report",
    "board_report": "Board's report",
    "consent_dir2": "Director's consent (DIR-2)",
    "partner_consent": "Consent to act as a partner or designated partner",
    "declaration_dir8": "Director's declaration of non-disqualification (DIR-8)",
    "disclosure_mbp1": "Disclosure of interest (MBP-1)",
    "auditor_consent": "Auditor's consent and eligibility certificate",
    "appointment_letter": "Appointment letter",
    "resignation_letter": "Resignation letter",
    "sanction_letter": "Bank sanction letter",
    "charge_document": "Charge, hypothecation or mortgage deed",
    "share_certificate": "Share certificate",
    "register_extract": "Extract of a statutory register",
    "pan_card": "PAN card",
    "aadhaar": "Aadhaar",
    "passport": "Passport",
    "address_proof": "Address proof",
    "mca_form": "Filed MCA form",
    "mca_challan": "MCA challan or SRN receipt",
    "master_data": "MCA master data printout",
    "annual_report": "Annual report",
    "agreement": "Agreement or deed",
    "correspondence": "Letter or email",
    "law": "Act, rules, circular or notification",
    "other": "Anything else",
}

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".html": "text/html",
    ".htm": "text/html",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".rtf": "application/rtf",
    ".xml": "application/xml",
    ".json": "application/json",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


@dataclass(frozen=True)
class PageText:
    page_no: int
    text: str
    needs_vision: bool


@dataclass(frozen=True)
class PagePart:
    """One page as handed to Claude: its text, or an image when it is a scan."""

    page_no: int
    text: str | None = None
    image: bytes | None = None
    image_format: str | None = None


# ---------------------------------------------------------------- extraction


def extract_pages(path: Path) -> list[PageText]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_pages(path)
    if suffix in IMAGE_SUFFIXES:
        return [PageText(1, "", True)]
    if suffix == ".docx":
        return [PageText(1, _docx_text(path), False)]
    if suffix == ".xlsx":
        return _xlsx_pages(path)
    if suffix in (".txt", ".md", ".csv"):
        return [PageText(1, _tidy(path.read_text(encoding="utf-8", errors="replace")), False)]
    if suffix == ".eml":
        return [PageText(1, _email_text(path), False)]
    if suffix == ".msg":
        return [PageText(1, _outlook_text(path), False)]
    if suffix in (".html", ".htm"):
        return [PageText(1, _html_text(path.read_text(encoding="utf-8", errors="replace")), False)]
    if suffix == ".pptx":
        return _pptx_pages(path)
    if suffix == ".xls":
        return _xls_pages(path)
    if suffix == ".rtf":
        from striprtf.striprtf import rtf_to_text

        return [PageText(1, _tidy(rtf_to_text(path.read_text(encoding="utf-8", errors="replace"))), False)]
    if suffix in (".xml", ".json"):
        return [PageText(1, _tidy(path.read_text(encoding="utf-8", errors="replace")), False)]
    raise Invalid(_unsupported(suffix))


def _pptx_pages(path: Path) -> list[PageText]:
    """One page per slide: its text boxes, tables and speaker notes."""
    from pptx import Presentation

    pages = []
    for index, slide in enumerate(Presentation(str(path)).slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines += [p.text for p in shape.text_frame.paragraphs if p.text.strip()]
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(cell.text.strip() for cell in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines += ["", f"Notes: {notes}"]
        pages.append(PageText(index, _tidy("\n".join(lines)), False))
    return pages or [PageText(1, "", False)]


def _xls_pages(path: Path) -> list[PageText]:
    import xlrd

    book = xlrd.open_workbook(str(path), on_demand=True)
    try:
        pages = []
        for index in range(book.nsheets):
            sheet = book.sheet_by_index(index)
            lines = [f"Sheet: {sheet.name}"]
            for r in range(sheet.nrows):
                row = sheet.row_values(r)
                if any(str(cell).strip() for cell in row):
                    lines.append("\t".join(_cell(cell) for cell in row))
            pages.append(PageText(index + 1, "\n".join(lines), False))
        return pages
    finally:
        book.release_resources()


def _cell(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _outlook_text(path: Path) -> str:
    import extract_msg

    message = extract_msg.openMsg(str(path))
    try:
        lines = [f"{name}: {value}" for name, value in (("From", message.sender), ("To", message.to), ("Cc", message.cc),
                                                        ("Date", message.date), ("Subject", message.subject)) if value]
        body = message.body or (_html_text(message.htmlBody.decode(errors="replace")) if message.htmlBody else "")
        lines += ["", body or ""]
        names = [a.longFilename or a.shortFilename for a in message.attachments if (a.longFilename or a.shortFilename)]
        if names:
            lines += ["", "Attachments: " + ", ".join(names)]
        return _tidy("\n".join(str(line) for line in lines))
    finally:
        message.close()


def _email_text(path: Path) -> str:
    """Headers that matter, then the plain-text body (or the HTML body as text). Attachments are listed by name."""
    from email import policy
    from email.parser import BytesParser

    with path.open("rb") as handle:
        message = BytesParser(policy=policy.default).parse(handle)
    lines = [f"{name}: {message[name]}" for name in ("From", "To", "Cc", "Date", "Subject") if message[name]]
    body = message.get_body(preferencelist=("plain", "html"))
    if body is not None:
        content = body.get_content()
        lines += ["", _html_text(content) if body.get_content_type() == "text/html" else content]
    attachments = [part.get_filename() for part in message.iter_attachments() if part.get_filename()]
    if attachments:
        lines += ["", "Attachments: " + ", ".join(attachments)]
    return _tidy("\n".join(lines))


def _html_text(markup: str) -> str:
    from html.parser import HTMLParser

    class Text(HTMLParser):
        BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article"}

        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            if tag in ("script", "style", "head"):
                self.skip += 1
            elif tag in self.BLOCK:
                self.parts.append("\n")
            elif tag in ("td", "th"):
                self.parts.append(" | ")

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style", "head") and self.skip:
                self.skip -= 1
            elif tag in self.BLOCK:
                self.parts.append("\n")

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.parts.append(data)

    parser = Text()
    parser.feed(markup)
    text = "".join(parser.parts)
    return _tidy("\n".join(" ".join(line.split()) for line in text.split("\n")))


def _pdf_pages(path: Path) -> list[PageText]:
    import pypdfium2 as pdfium

    with PDFIUM:
        try:
            pdf = pdfium.PdfDocument(path)
        except pdfium.PdfiumError as exc:
            raise Invalid(f"Couldn't open {path.name}: it may be password-protected or damaged ({exc}).") from exc
        try:
            pages = []
            for index in range(len(pdf)):
                page = pdf[index]
                textpage = page.get_textpage()
                text = _tidy(textpage.get_text_range())
                textpage.close()
                page.close()
                pages.append(PageText(index + 1, text, len(text.strip()) < SCAN_THRESHOLD))
            return pages
        finally:
            pdf.close()


def _docx_text(path: Path) -> str:
    import docx
    from docx.table import Table

    document = docx.Document(str(path))
    parts: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            for row in block.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        else:
            parts.append(block.text)
    return _tidy("\n".join(parts))


def _xlsx_pages(path: Path) -> list[PageText]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        pages = []
        for index, sheet in enumerate(workbook.worksheets, start=1):
            lines = [f"Sheet: {sheet.title}"]
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    lines.append("\t".join("" if cell is None else str(cell) for cell in row))
            pages.append(PageText(index, "\n".join(lines), False))
        return pages
    finally:
        workbook.close()


def render_page(path: Path, page_no: int) -> tuple[bytes, str]:
    """A page as a JPEG sized for Claude to read."""
    from PIL import Image

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdfium2 as pdfium

        with PDFIUM:
            pdf = pdfium.PdfDocument(path)
            try:
                page = pdf[page_no - 1]
                width, height = page.get_size()
                image = page.render(scale=IMAGE_LONG_SIDE / max(width, height)).to_pil()
                page.close()
            finally:
                pdf.close()
    elif suffix in IMAGE_SUFFIXES:
        image = Image.open(path)
        image.thumbnail((IMAGE_LONG_SIDE, IMAGE_LONG_SIDE))
    else:
        raise Invalid(f"{path.name} has no page images; its text is already readable.")
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return buffer.getvalue(), "jpeg"


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _unsupported(suffix: str) -> str:
    return (
        f"AAGAM can't read {suffix or 'files without an extension'} yet. "
        "Save it as PDF, Word (.docx), Excel, PowerPoint (.pptx), an image, an email, a web page or text."
    )


# -------------------------------------------------------------------- intake


@dataclass(frozen=True)
class Prepared:
    """A file read ahead of filing it: its fingerprint, and its pages when they could be read away from the filer."""

    sha256: str
    size: int
    pages: list[PageText] | None = None  # None: read when it is filed (always so for a PDF)


def prepare(source_path: str | Path) -> Prepared:
    """Fingerprint a file and read its text without touching the database, so it can run on another thread while
    other files are filed (PDFium itself still reads one PDF at a time, under PDFIUM)."""
    src = Path(source_path).expanduser()
    size = src.stat().st_size
    digest = _sha256(src)
    pages = None if size > MAX_BYTES else extract_pages(src)
    return Prepared(digest, size, pages)


def ingest(
    vault: Vault,
    settings: Settings,
    source_path: str | Path,
    company_id: int | None = None,
    doc_type: str = "other",
    note: str | None = None,
    prepared: Prepared | None = None,
) -> dict[str, Any]:
    """Copy a file into the company's documents folder and index its text. `prepared` is the same file already
    fingerprinted (and perhaps read) by prepare()."""
    src = Path(source_path).expanduser()
    if not src.is_file():
        raise NotFound(f"There is no file at {src}.")
    suffix = src.suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise Invalid(_unsupported(suffix))
    if doc_type not in DOC_TYPES:
        raise Invalid(f"Unknown document type {doc_type!r}; use one of: {', '.join(DOC_TYPES)}.")
    if src.stat().st_size > MAX_BYTES:
        raise Invalid(f"{src.name} is larger than {MAX_BYTES // (1024 * 1024)} MB; split it into parts first.")

    digest = prepared.sha256 if prepared else _sha256(src)
    existing = vault.conn.execute(
        "SELECT id, stored_path, pages FROM documents WHERE sha256 = ? AND company_id IS ?", (digest, company_id)
    ).fetchone()
    if existing:
        return {
            "document_id": existing["id"],
            "stored_path": existing["stored_path"],
            "pages": existing["pages"],
            "already_on_file": True,
        }

    folder_name = vault.company_folder(company_id) if company_id is not None else "_general"
    folder = settings.clients_dir / folder_name / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    dest = _unique(folder / f"{date.today():%Y%m%d}-{doc_type}-{_slug(src.stem)}{suffix}")
    shutil.copy2(src, dest)
    try:
        pages = prepared.pages if prepared and prepared.pages is not None else extract_pages(dest)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise

    stored = dest.relative_to(settings.home).as_posix()
    document_id = vault.conn.execute(
        "INSERT INTO documents (company_id, doc_type, original_name, stored_path, sha256, media_type, pages, note)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (company_id, doc_type, src.name, stored, digest, MEDIA_TYPES[suffix], len(pages), note),
    ).lastrowid
    vault.conn.executemany(
        "INSERT INTO document_pages (document_id, page_no, text, needs_vision) VALUES (?, ?, ?, ?)",
        [(document_id, p.page_no, p.text, int(p.needs_vision)) for p in pages],
    )
    vault.log("ingest document", {"id": document_id, "company_id": company_id, "doc_type": doc_type, "pages": len(pages)})
    return {
        "document_id": document_id,
        "stored_path": stored,
        "pages": len(pages),
        "scanned_pages": [p.page_no for p in pages if p.needs_vision],
        "characters": sum(len(p.text) for p in pages),
        "already_on_file": False,
    }


def ingest_inbox(
    vault: Vault, settings: Settings, company_id: int | None = None, doc_type: str = "other"
) -> list[dict[str, Any]]:
    """Ingest every file in the inbox folder, then move it to inbox/processed/<date>/."""
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    done = settings.inbox_dir / "processed" / date.today().isoformat()
    results = []
    for path in sorted(settings.inbox_dir.iterdir()):
        if not path.is_file() or path.name.startswith((".", "~$")) or path.name.lower() == "desktop.ini":
            continue
        try:
            info = ingest(vault, settings, path, company_id, doc_type)
        except CsDeskError as exc:
            results.append({"file": path.name, "error": str(exc)})
            continue
        done.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(_unique(done / path.name)))
        results.append({"file": path.name, **info})
    return results


def read_pages(
    vault: Vault, settings: Settings, document_id: int, pages: str = "1-5"
) -> tuple[dict[str, Any], list[PagePart], list[int]]:
    """The requested pages as text, or as images for scans. Returns (document, parts, pages not returned)."""
    row = vault.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise NotFound(f"There is no document {document_id}.")
    document = dict(row)
    wanted = parse_page_spec(pages, document["pages"])
    page_rows = {
        r["page_no"]: r
        for r in vault.conn.execute("SELECT * FROM document_pages WHERE document_id = ?", (document_id,))
    }
    path = settings.home / document["stored_path"]
    parts: list[PagePart] = []
    chars = 0
    for page_no in wanted:
        if len(parts) >= MAX_PAGES_PER_READ:
            break
        page = page_rows[page_no]
        if page["needs_vision"]:
            image, fmt = render_page(path, page_no)
            parts.append(PagePart(page_no, image=image, image_format=fmt))
            continue
        text = page["text"]
        if chars + len(text) > MAX_CHARS_PER_READ and parts:
            break
        parts.append(PagePart(page_no, text=text))
        chars += len(text)
    returned = {p.page_no for p in parts}
    return document, parts, [n for n in wanted if n not in returned]


def parse_page_spec(spec: str, total: int) -> list[int]:
    """A page list such as "1-3,5,8-" or "all", as the page numbers that exist, in order."""
    if total < 1:
        raise Invalid("That document has no pages.")
    text = spec.strip().lower()
    if text in ("", "all"):
        return list(range(1, total + 1))
    pages: set[int] = set()
    for part in text.split(","):
        m = re.fullmatch(r"\s*(\d+)?\s*(-)?\s*(\d+)?\s*", part)
        if not m or not (m.group(1) or m.group(3)):
            raise Invalid(f"Can't read the page list {spec!r}; use something like 1-3,5,8-.")
        start = int(m.group(1) or 1)
        end = int(m.group(3) or total) if m.group(2) else start
        pages.update(range(max(start, 1), min(end, total) + 1))
    if not pages:
        raise Invalid(f"None of the pages {spec!r} exist; the document has {total}.")
    return sorted(pages)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or "document"


def _unique(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate
