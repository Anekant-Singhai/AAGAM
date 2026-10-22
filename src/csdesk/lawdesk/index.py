"""Law desk: search the Acts, Rules, Secretarial Standards and circulars she keeps.

Files dropped into AAGAM_HOME/law (PDF, Word, text) are indexed on the next
search. Text with numbered sections ("137. Copy of financial statement ...")
is split by section, so a hit points to s.137 rather than to a whole Act.
The index is a separate file (law.db) and can be deleted and rebuilt at any time.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ..config import Settings
from ..documents.intake import IMAGE_SUFFIXES, MEDIA_TYPES, extract_pages
from ..errors import CsDeskError, Invalid

SECTION_START = re.compile(r"(?m)^[ \t]*(\d{1,3}[A-Z]{0,3})\.[ \t]+(?=\S)")
MAX_CHUNK = 4000
MIN_SECTION = 120
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its me my of on or the this to under "
    "what when where which who why will with".split()
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL, chunks INTEGER NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(title, locator, body, path UNINDEXED, tokenize = 'porter unicode61');
"""


def _connect(settings: Settings) -> sqlite3.Connection:
    settings.law_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.law_db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def refresh(settings: Settings) -> dict[str, Any]:
    """Index new or changed files in the law folder; drop files that were removed."""
    settings.law_dir.mkdir(parents=True, exist_ok=True)
    readable = {suffix for suffix in MEDIA_TYPES if suffix not in IMAGE_SUFFIXES}
    on_disk = {
        path.relative_to(settings.law_dir).as_posix(): path
        for path in settings.law_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in readable and not path.name.startswith("~$")
    }
    indexed, removed, problems = [], [], []
    with closing(_connect(settings)) as conn, conn:
        known = {row["path"]: row for row in conn.execute("SELECT * FROM files")}
        for rel in set(known) - set(on_disk):
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
            conn.execute("DELETE FROM files WHERE path = ?", (rel,))
            removed.append(rel)
        for rel, path in sorted(on_disk.items()):
            stat = path.stat()
            row = known.get(rel)
            if row and row["mtime"] == stat.st_mtime and row["size"] == stat.st_size:
                continue
            try:
                chunks = list(_chunks(path))
            except CsDeskError as exc:
                problems.append({"file": rel, "error": str(exc)})
                continue
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
            title = re.sub(r"[_-]+", " ", path.stem)
            conn.executemany(
                "INSERT INTO chunks (title, locator, body, path) VALUES (?, ?, ?, ?)",
                [(title, locator, body, rel) for locator, body in chunks],
            )
            conn.execute(
                "INSERT OR REPLACE INTO files (path, mtime, size, chunks) VALUES (?, ?, ?, ?)",
                (rel, stat.st_mtime, stat.st_size, len(chunks)),
            )
            indexed.append(rel)
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    return {"files": total, "indexed": indexed, "removed": removed, "problems": problems}


def search(settings: Settings, query: str, limit: int = 8) -> dict[str, Any]:
    """Passages matching every word first, then passages matching any of them."""
    status = refresh(settings)
    if status["files"] == 0:
        return {
            "results": [],
            "message": f"The law folder is empty. Put the Act, Rules, SS-1/SS-2 and circulars (PDF, Word or text) in {settings.law_dir}.",
        }
    limit = max(1, min(limit, 25))
    seen: set[int] = set()
    results: list[dict[str, Any]] = []
    with closing(_connect(settings)) as conn:
        for joiner in (" AND ", " OR "):
            rows = conn.execute(
                "SELECT rowid, title, locator, path, snippet(chunks, 2, '[', ']', ' … ', 40) AS passage"
                " FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
                (_match_expression(query, joiner), limit),
            ).fetchall()
            for row in rows:
                if row["rowid"] not in seen and len(results) < limit:
                    seen.add(row["rowid"])
                    results.append({key: row[key] for key in ("title", "locator", "passage", "path")})
            if len(results) >= limit:
                break
    return {"results": results, "files_indexed": status["files"]}


def _match_expression(query: str, joiner: str) -> str:
    terms = [t for t in re.findall(r"\w+(?:[-/.]\w+)*", query) if t.lower() not in STOPWORDS]
    if not terms:
        raise Invalid("Give some words to search for.")
    return joiner.join('"' + term.replace('"', "") + '"' for term in terms)


def _chunks(path: Path) -> list[tuple[str, str]]:
    """(locator, text) pieces: by numbered section when the text has them, else by page."""
    pages = extract_pages(path)
    marked = [(page.page_no, m) for page in pages for m in SECTION_START.finditer(page.text)]
    pieces: list[tuple[str, str]] = []
    if len(marked) >= 3:
        current_label, current_page, buffer = "opening text", pages[0].page_no if pages else 1, []
        for page in pages:
            position = 0
            for m in SECTION_START.finditer(page.text):
                buffer.append(page.text[position : m.start()])
                pieces += _split(f"{current_label} (p.{current_page})", "".join(buffer))
                current_label, current_page, buffer = f"s.{m.group(1)}", page.page_no, []
                position = m.start()
            buffer.append(page.text[position:] + "\n")
        pieces += _split(f"{current_label} (p.{current_page})", "".join(buffer))
        # One-line pieces are entries in an "Arrangement of Sections" list, not the sections themselves.
        pieces = [(locator, body) for locator, body in pieces if len(body.strip()) >= MIN_SECTION]
    else:
        for page in pages:
            pieces += _split(f"p.{page.page_no}", page.text)
    return [(locator, body) for locator, body in pieces if body.strip()]


def _split(locator: str, text: str) -> list[tuple[str, str]]:
    text = text.strip()
    if len(text) <= MAX_CHUNK:
        return [(locator, text)]
    parts, start = [], 0
    while start < len(text):
        end = min(start + MAX_CHUNK, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + MAX_CHUNK // 2, end)
            end = cut if cut > start else end
        parts.append((f"{locator}, part {len(parts) + 1}", text[start:end]))
        start = end
    return parts
