"""The document library: bring documents in, work out what they are, find things in them.

A document comes in through the core's intake (a copy is kept and its text is
read page by page). Indexing then:

1. works out its type, the company it is about, and for meeting papers the
   kind and date of the meeting (classify.py);
2. finds the facts in it: CINs, DINs with their people, PANs (masked),
   amounts, dates, section references, firms, members (extract.py);
3. splits notices into their resolutions and explanatory statements, which
   become the precedent library (notices.py);
4. tags it from all of that, and queues a summary for local AI.

Search runs on SQLite's full-text index over every page.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from csdesk.config import Settings
from csdesk.documents import ingest as core_ingest
from csdesk.documents.intake import DOC_TYPES, MEDIA_TYPES
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import analysis, classify, editing, entities, extract, finance, notices, ocr
from .finance.statements import is_statement_page

TYPE_TAGS = {key: key.replace("_", "-") for key in DOC_TYPES}
SENSITIVE_KINDS = {"pan"}
# Kinds of file, for the library's filter.
FILE_KINDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "pdf": ("PDF", (".pdf",)),
    "word": ("Word", (".docx", ".rtf")),
    "excel": ("Excel", (".xlsx", ".xls", ".csv")),
    "email": ("Email", (".eml", ".msg")),
    "slides": ("PowerPoint", (".pptx",)),
    "image": ("Image", (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")),
    "web": ("Web page or data", (".html", ".htm", ".xml", ".json")),
    "text": ("Text", (".txt", ".md")),
}
KIND_OF_MEDIA = {MEDIA_TYPES[suffix]: kind for kind, (_, suffixes) in FILE_KINDS.items() for suffix in suffixes}


# ------------------------------------------------------------------- intake


@dataclass(frozen=True)
class Origin:
    """Where a document came from on her computer, so the library can be sorted by folder and by date."""

    path: str | None = None  # the file as she had it
    folder_id: int | None = None  # the folder it was brought in with (folders.py)
    folder: str | None = None  # the folder it sat in, inside that one: "Acme/2024-25/AGM" ('' at the top)
    modified: str | None = None  # when the file last changed (ISO)

    @classmethod
    def of_file(cls, path: str | Path, **more: Any) -> Origin:
        path = Path(path).expanduser().resolve()
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        return cls(str(path), modified=modified, **more)


def add_document(
    vault: Vault,
    settings: Settings,
    path: str | Path,
    company_id: int | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    queue_ai: bool = True,
    origin: Origin | None = None,
    work_out_client: bool = False,
    prepared: Any = None,
) -> dict[str, Any]:
    """Bring a file in and index it. `doc_type` None means "work it out from the text". With `work_out_client`, a
    document that came without a client is filed under the one it points to (file_under_client); another
    company's document (tagged "precedent") never is. `prepared` is the file already read by intake.prepare()."""
    info = core_ingest(vault, settings, path, company_id, doc_type or "other", note, prepared=prepared)
    document_id = info["document_id"]
    fresh = not info.get("already_on_file") or not _indexed(vault, document_id)
    if fresh and origin:
        record_origin(vault, document_id, origin)
    if fresh:
        index_new(vault, settings, document_id, keep_type=doc_type is not None, queue_ai=queue_ai)
    for tag in tags or []:
        add_tag(vault, document_id, tag, by="her")
    if fresh and work_out_client and company_id is None and "precedent" not in {t.strip().lower() for t in tags or []}:
        file_under_client(vault, document_id, Path(origin.folder).parts if origin and origin.folder else ())
    return {**info, **document(vault, document_id, brief=True)}


def record_origin(vault: Vault, document_id: int, origin: Origin) -> None:
    values = {"source_path": origin.path, "folder_id": origin.folder_id, "source_folder": origin.folder, "file_modified": origin.modified}
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        return
    columns = ", ".join(values)
    vault.conn.execute(
        f"INSERT INTO doc_meta (document_id, {columns}) VALUES (?, {', '.join('?' * len(values))}) "
        f"ON CONFLICT(document_id) DO UPDATE SET {', '.join(f'{k} = excluded.{k}' for k in values)}",
        (document_id, *values.values()),
    )


def _short_name(name: str) -> str:
    """A company's name without its legal form, to match a folder called "Acme Widgets" to Acme Widgets Private Limited."""
    key = entities.key_of("company", name)
    return re.sub(r"\s*\b(?:(?:opc\s+)?private\s+limited|limited|llp|limited\s+liability\s+partnership)$", "", key).strip()


def client_for(vault: Vault, document_id: int, folders: tuple[str, ...] | list[str] = ()) -> tuple[int, str] | None:
    """The client a document belongs to, and why: the one whose CIN or LLPIN heads it, else the one a folder it sat in
    is named after (nearest folder first), else the one whose name it carries. None unless exactly one client fits."""
    clients = vault._rows("SELECT id, name, cin FROM companies")
    if not clients:
        return None
    meta = vault.conn.execute("SELECT company_name, company_cin FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()
    if meta and meta["company_cin"]:
        same = [c for c in clients if c["cin"] == meta["company_cin"]]
        if len(same) == 1:
            label = "LLPIN" if "-" in meta["company_cin"] else "CIN"
            return same[0]["id"], f"its {label} {meta['company_cin']}"
    for part in reversed(list(folders)):
        short = _short_name(part)
        if len(short) < 4 and not re.search(r"[A-Z]{3}-\d{4}|[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", part.upper()):
            continue
        same = [c for c in clients if _short_name(c["name"]) == short or (c["cin"] and c["cin"] in part.upper())]
        if len(same) == 1:
            return same[0]["id"], f"the folder “{part}”"
    if meta and meta["company_name"]:
        key = entities.key_of("company", meta["company_name"])
        same = [c for c in clients if entities.key_of("company", c["name"]) == key]
        if len(same) == 1:
            return same[0]["id"], f"its company name, “{meta['company_name']}”"
    return None


def file_under_client(vault: Vault, document_id: int, folders: tuple[str, ...] | list[str] = (), wait_for_ocr: bool = True) -> int | None:
    """Give a document without a client the client it points to (client_for). One still waiting to be read by OCR is
    looked at again once it has been read (run_ocr_queue). Returns the client's id, or None."""
    row = vault.conn.execute("SELECT company_id FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None or row["company_id"] is not None:
        return None
    found = client_for(vault, document_id, folders)
    if found is None:
        waiting = wait_for_ocr and vault.conn.execute(
            "SELECT 1 FROM ai_jobs WHERE document_id = ? AND task = 'ocr' AND status IN ('queued', 'running')", (document_id,)
        ).fetchone()
        if waiting:
            editing._set_meta(vault, document_id, "client_why", "pending: " + json.dumps(list(folders), ensure_ascii=False))
        return None
    company_id, why = found
    vault.conn.execute("UPDATE documents SET company_id = ? WHERE id = ?", (company_id, document_id))
    vault.conn.execute("UPDATE financials SET company_id = ? WHERE document_id = ? AND company_id IS NULL", (company_id, document_id))
    editing._set_meta(vault, document_id, "client_why", why)
    vault.log("file under client", {"document": document_id, "company_id": company_id, "why": why})
    return company_id


def index_new(vault: Vault, settings: Settings, document_id: int, keep_type: bool = False, queue_ai: bool = True) -> None:
    """Everything that happens to a document that has just arrived, however it arrived."""
    waiting_for_ocr = read_scans(vault, settings, document_id)
    index_document(vault, document_id, keep_type=keep_type, home=settings.home)
    if queue_ai and not waiting_for_ocr:
        queue(vault, document_id, "summary")


def read_scans(vault: Vault, settings: Settings, document_id: int) -> bool:
    """OCR a document's scanned pages: now if there are few, in the background if many. True if left for the background."""
    scanned = vault.conn.execute(
        "SELECT COUNT(*) FROM document_pages WHERE document_id = ? AND needs_vision = 1 AND length(text) < 25", (document_id,)
    ).fetchone()[0]
    if not scanned or not ocr.available():
        return False
    if scanned <= ocr.INLINE_PAGES:
        ocr.ocr_document(vault, settings.home, document_id)
        return False
    queue(vault, document_id, "ocr")
    return True


def run_ocr_queue(db_path: Path, home: Path, limit: int | None = None) -> int:
    """Background OCR for long scanned documents; each is re-read and queued for a summary afterwards."""
    from .db import open_db

    done = 0
    while limit is None or done < limit:
        with open_db(db_path, actor="ocr") as vault:
            job = vault.conn.execute("SELECT * FROM ai_jobs WHERE status = 'queued' AND task = 'ocr' ORDER BY id LIMIT 1").fetchone()
            if job is None:
                return done
            vault.conn.execute("UPDATE ai_jobs SET status = 'running', started_at = datetime('now'), provider = 'windows-ocr' WHERE id = ?", (job["id"],))
        status, note = "done", None
        try:
            with open_db(db_path, actor="ocr") as vault:
                result = ocr.ocr_document(vault, home, job["document_id"])
                note = result.get("skipped") or f"read {len(result['read'])} page(s)"
                index_document(vault, job["document_id"], home=home)  # the type can only now be seen
                queue(vault, job["document_id"], "summary")
            with open_db(db_path, actor="ocr") as vault:
                pending = editing._meta(vault, job["document_id"], "client_why") or ""
                if pending.startswith("pending: "):
                    # It came without a client; now that it can be read, see which client it is.
                    vault.conn.execute("UPDATE doc_meta SET client_why = NULL WHERE document_id = ?", (job["document_id"],))
                    file_under_client(vault, job["document_id"], json.loads(pending.removeprefix("pending: ")), wait_for_ocr=False)
        except Exception as exc:  # one bad scan mustn't stop the queue
            status, note = "failed", str(exc)[:500]
        with open_db(db_path, actor="ocr") as vault:
            vault.conn.execute("UPDATE ai_jobs SET status = ?, note = ?, finished_at = datetime('now') WHERE id = ?", (status, note, job["id"]))
        done += 1
    return done


def _indexed(vault: Vault, document_id: int) -> bool:
    row = vault.conn.execute("SELECT status FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()
    return bool(row and row["status"] == "indexed")


def pages_of(vault: Vault, document_id: int) -> list[tuple[int, str]]:
    return [
        (r["page_no"], r["text"])
        for r in vault.conn.execute(
            "SELECT page_no, text FROM document_pages WHERE document_id = ? ORDER BY page_no", (document_id,)
        )
    ]


def index_document(vault: Vault, document_id: int, keep_type: bool = False, home: Path | None = None) -> dict[str, Any]:
    """(Re)build everything AAGAM knows about a document from its page text. `home` lets statements be read by layout."""
    row = vault.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise NotFound(f"There is no document {document_id}.")
    pages = pages_of(vault, document_id)
    detected = classify.detect(pages, row["original_name"])
    conn = vault.conn
    conn.execute("DELETE FROM mentions WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM clauses WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM document_tags WHERE document_id = ? AND added_by = 'auto'", (document_id,))

    found = extract.find_mentions(pages)
    # Facts she hid (here or everywhere) stay hidden; so does a hidden person's name beside a DIN.
    hidden = editing.hidden_keys(vault, document_id)
    if hidden:
        found = [m for m in found if (m.kind, entities.key_of(m.kind, m.value)) not in hidden]
        found = [replace(m, detail=None) if m.kind == "din" and m.detail and ("person", entities.key_of("person", m.detail)) in hidden else m
                 for m in found]
    conn.executemany(
        "INSERT INTO mentions (document_id, page_no, kind, value, shown, detail, context) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (document_id, m.page_no, m.kind, m.shown if m.kind in SENSITIVE_KINDS else m.value, m.shown, m.detail, m.context)
            for m in found
        ],
    )

    doc_type = row["doc_type"] if keep_type or row["doc_type"] != "other" else (detected.doc_type or "other")
    if doc_type != row["doc_type"]:
        conn.execute("UPDATE documents SET doc_type = ? WHERE id = ?", (doc_type, document_id))

    clauses: list[notices.Item] = []
    meeting_kind = detected.meeting_kind
    if doc_type in ("notice", "annual_report"):
        notice = notices.split_notice(pages)
        clauses = notice.items
        meeting_kind = meeting_kind or notice.meeting_kind
        conn.executemany(
            """INSERT INTO clauses (document_id, kind, item_no, business, resolution_kind, title, body, statement,
                                    sections, topics, max_amount, page_from, page_to, company_name, meeting_kind, meeting_date)
               VALUES (?, 'resolution', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (document_id, c.number, c.business, c.resolution_kind, c.title, c.body, c.statement,
                 _padded(c.sections), _padded(c.topics), c.max_amount, c.page_from, c.page_to,
                 detected.company_name, meeting_kind, detected.meeting_date)
                for c in clauses
            ],
        )
        editing.apply_clause_edits(vault, document_id)

    words = sum(len(text.split()) for _, text in pages)
    doc_date, doc_date_basis = classify.dated(pages, detected, doc_type)
    if doc_date is None:
        doc_date, doc_date_basis = _undated(vault, row)
    conn.execute(
        """INSERT INTO doc_meta (document_id, title, detected_type, detected_why, company_name, company_cin,
                                 meeting_kind, meeting_date, words, status, error, indexed_at, doc_date, doc_date_basis)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed', NULL, datetime('now'), ?, ?)
           ON CONFLICT(document_id) DO UPDATE SET
             title = COALESCE(doc_meta.title, excluded.title), detected_type = excluded.detected_type,
             detected_why = excluded.detected_why, company_name = excluded.company_name,
             company_cin = excluded.company_cin, meeting_kind = excluded.meeting_kind,
             meeting_date = excluded.meeting_date, words = excluded.words, status = 'indexed', error = NULL,
             indexed_at = excluded.indexed_at, doc_date = excluded.doc_date, doc_date_basis = excluded.doc_date_basis""",
        (document_id, detected.title, detected.doc_type, detected.why, detected.company_name, detected.company_cin,
         meeting_kind, detected.meeting_date, words, doc_date, doc_date_basis),
    )
    editing.apply_document_overrides(vault, document_id)
    meeting_kind = json.loads(editing._meta(vault, document_id, "overrides") or "{}").get("meeting_kind", meeting_kind)

    statements_found: list[int] = []
    if doc_type in ("financial_statements", "annual_report", "auditor_report") or any(is_statement_page(t) for _, t in pages):
        statements_found = finance.extract(vault, document_id, home)
        if statements_found and doc_type in ("auditor_report", "other") and not keep_type:
            # Audited accounts open with the auditor's report, but what matters is the statements behind it.
            doc_type = "financial_statements"
            vault.conn.execute("UPDATE documents SET doc_type = ? WHERE id = ?", (doc_type, document_id))

    auto = {TYPE_TAGS.get(doc_type, doc_type)}
    if statements_found:
        auto.add("financials")
    if meeting_kind:
        auto.add(meeting_kind)
    for clause in clauses:
        auto.update(f"s.{s}" for s in clause.sections if "(" not in s)
        auto.update(clause.topics)
        if clause.resolution_kind == "special":
            auto.add("special-resolution")
    if any(m.kind == "pan" for m in found):
        auto.add("has-pan")
    # What the document says, purpose by purpose; each purpose found tags it.
    analyses = analysis.run_all(vault, document_id)
    for found_analysis in analyses:
        auto.update(found_analysis["tags"])
    for tag in sorted(auto):
        add_tag(vault, document_id, tag, by="auto")
    vault.log("index document", {"id": document_id, "type": doc_type, "facts": len(found), "resolutions": len(clauses),
                                  "statements": len(statements_found)})
    return {"document_id": document_id, "doc_type": doc_type, "facts": len(found), "resolutions": len(clauses),
            "financials": statements_found, "analyses": [a["kind"] for a in analyses]}


def _undated(vault: Vault, row: Any) -> tuple[str, str]:
    """For a document whose words give no date: when the file last changed, else the day it was added."""
    modified = editing._meta(vault, row["id"], "file_modified")
    if modified:
        return modified[:10], "the day the file was last changed"
    return row["ingested_at"][:10], "the day it was added"


def backfill_dates(vault: Vault, limit: int = 200) -> int:
    """Date documents read before AAGAM worked dates out, a few at a time (the background worker calls this)."""
    rows = vault._rows(
        """SELECT d.* FROM documents d LEFT JOIN doc_meta m ON m.document_id = d.id
           WHERE m.doc_date IS NULL ORDER BY d.id LIMIT ?""",
        (limit,),
    )
    for row in rows:
        date_document(vault, row)
    return len(rows)


def date_document(vault: Vault, row: Any) -> None:
    """Work out a document's date again from its words (a date she set still wins)."""
    pages = pages_of(vault, row["id"])
    detected = classify.detect(pages, row["original_name"])
    doc_date, basis = classify.dated(pages, detected, row["doc_type"])
    if doc_date is None:
        doc_date, basis = _undated(vault, row)
    vault.conn.execute(
        """INSERT INTO doc_meta (document_id, doc_date, doc_date_basis) VALUES (?, ?, ?)
           ON CONFLICT(document_id) DO UPDATE SET doc_date = excluded.doc_date, doc_date_basis = excluded.doc_date_basis""",
        (row["id"], doc_date, basis),
    )
    editing.apply_document_overrides(vault, row["id"])


def reindex_all(vault: Vault, home: Path | None = None) -> int:
    ids = [r["id"] for r in vault.conn.execute("SELECT id FROM documents ORDER BY id")]
    for document_id in ids:
        index_document(vault, document_id, home=home)  # a type she set is kept; "other" is looked at again
    return len(ids)


def _padded(values: list[str]) -> str:
    return f" {' '.join(values)} " if values else ""


# --------------------------------------------------------------------- tags


def _tag_id(vault: Vault, name: str, kind: str = "topic") -> int:
    clean = " ".join(name.strip().split()).lower()
    if not clean or len(clean) > 60:
        raise Invalid("A tag is a word or short phrase, up to 60 characters.")
    row = vault.conn.execute("SELECT id FROM tags WHERE name = ?", (clean,)).fetchone()
    if row:
        return row["id"]
    if clean.startswith("s.") and re.fullmatch(r"s\.\d+[a-z]?", clean):
        kind = "section"
    return vault.conn.execute("INSERT INTO tags (name, kind) VALUES (?, ?)", (clean, kind)).lastrowid


def add_tag(vault: Vault, document_id: int, name: str, by: str = "her") -> None:
    clean = " ".join(name.strip().split()).lower()
    ruled, becomes = editing.tag_rule(vault, clean)
    if ruled and becomes is None:
        if by != "her":
            return  # she deleted this tag; automatic tagging leaves it off
        vault.conn.execute("DELETE FROM tag_rules WHERE name = ?", (clean,))  # she wants it again
    elif ruled:
        name = becomes or name  # she renamed it
    if by == "auto" and " ".join(name.strip().split()).lower() in editing.removed_tags(vault, document_id):
        return  # she took it off this document
    if by == "her":
        editing.remember_removed_tag(vault, document_id, " ".join(name.strip().split()).lower(), add=False)
    tag_id = _tag_id(vault, name)
    vault.conn.execute(
        """INSERT INTO document_tags (document_id, tag_id, added_by) VALUES (?, ?, ?)
           ON CONFLICT(document_id, tag_id) DO UPDATE SET
             added_by = CASE WHEN excluded.added_by = 'her' THEN 'her' ELSE document_tags.added_by END""",
        (document_id, tag_id, by),
    )
    row = vault.conn.execute("SELECT suggested_tags FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()
    if row and row["suggested_tags"]:
        clean = " ".join(name.strip().split()).lower()
        left = [t for t in json.loads(row["suggested_tags"]) if t != clean]
        vault.conn.execute("UPDATE doc_meta SET suggested_tags = ? WHERE document_id = ?", (json.dumps(left), document_id))


def suggest_tags(vault: Vault, document_id: int, names: list[str]) -> None:
    """Tags an AI proposes. They stay suggestions until she accepts one."""
    current = {t["name"] for t in document(vault, document_id, brief=True)["tags"]}
    fresh = [n for n in dict.fromkeys(names) if n and n not in current]
    vault.conn.execute(
        """INSERT INTO doc_meta (document_id, suggested_tags) VALUES (?, ?)
           ON CONFLICT(document_id) DO UPDATE SET suggested_tags = excluded.suggested_tags""",
        (document_id, json.dumps(fresh, ensure_ascii=False)),
    )


def remove_tag(vault: Vault, document_id: int, name: str) -> None:
    clean = " ".join(name.strip().split()).lower()
    row = vault.conn.execute(
        "SELECT dt.added_by FROM document_tags dt JOIN tags t ON t.id = dt.tag_id WHERE dt.document_id = ? AND t.name = ?", (document_id, clean)
    ).fetchone()
    vault.conn.execute(
        "DELETE FROM document_tags WHERE document_id = ? AND tag_id = (SELECT id FROM tags WHERE name = ?)", (document_id, clean)
    )
    if row and row["added_by"] != "her":
        editing.remember_removed_tag(vault, document_id, clean)  # re-reading won't put it back


def all_tags(vault: Vault) -> list[dict[str, Any]]:
    return vault._rows(
        """SELECT t.name, t.kind, COUNT(dt.document_id) AS documents FROM tags t
           LEFT JOIN document_tags dt ON dt.tag_id = t.id GROUP BY t.id HAVING documents > 0 ORDER BY documents DESC, t.name"""
    )


# ---------------------------------------------------------------- reading


def document(vault: Vault, document_id: int, brief: bool = False) -> dict[str, Any]:
    row = vault.conn.execute(
        """SELECT d.id, d.company_id, d.doc_type, d.original_name, d.stored_path, d.media_type, d.pages, d.note,
                  d.ingested_at, c.name AS client, m.title, m.detected_type, m.detected_why, m.company_name,
                  m.company_cin, m.meeting_kind, m.meeting_date, m.summary, m.summary_by, m.summary_at, m.key_points,
                  m.suggested_tags, m.ocr_pages, m.edited_pages, m.overrides, m.words, m.status,
                  m.doc_date, m.doc_date_basis, m.source_path, m.source_folder, m.folder_id, m.file_modified,
                  CASE WHEN m.client_why LIKE 'pending:%' THEN NULL ELSE m.client_why END AS client_why, f.path AS folder_path
           FROM documents d LEFT JOIN doc_meta m ON m.document_id = d.id LEFT JOIN companies c ON c.id = d.company_id
           LEFT JOIN folders f ON f.id = m.folder_id
           WHERE d.id = ?""",
        (document_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"There is no document {document_id}.")
    out = dict(row)
    out["key_points"] = json.loads(out["key_points"]) if out["key_points"] else []
    out["suggested_tags"] = json.loads(out["suggested_tags"]) if out["suggested_tags"] else []
    out["ocr_pages"] = [int(p) for p in out["ocr_pages"].split(",")] if out["ocr_pages"] else []
    out["edited_pages"] = [int(p) for p in out["edited_pages"].split(",")] if out["edited_pages"] else []
    out["overrides"] = json.loads(out["overrides"]) if out["overrides"] else {}
    out["tags"] = [
        dict(r)
        for r in vault.conn.execute(
            "SELECT t.name, dt.added_by FROM document_tags dt JOIN tags t ON t.id = dt.tag_id WHERE dt.document_id = ? ORDER BY t.name",
            (document_id,),
        )
    ]
    out["scanned_pages"] = [
        r[0] for r in vault.conn.execute("SELECT page_no FROM document_pages WHERE document_id = ? AND needs_vision = 1", (document_id,))
    ]
    out["doc_date"] = out["doc_date"] or out["meeting_date"] or out["ingested_at"][:10]
    out["fy"] = fy_of(out["doc_date"])
    if brief:
        return {k: out[k] for k in ("id", "doc_type", "title", "summary", "tags", "scanned_pages", "company_name", "meeting_kind",
                                    "doc_date", "company_id", "client")}
    out["facts"] = facts(vault, document_id)
    out["resolutions"] = vault._rows(
        """SELECT id, item_no, business, resolution_kind, title, sections, topics, max_amount, page_from, page_to,
                  statement IS NOT NULL AS has_statement FROM clauses WHERE document_id = ? ORDER BY item_no""",
        (document_id,),
    )
    for clause in out["resolutions"]:
        clause["sections"] = clause["sections"].split()
        clause["topics"] = clause["topics"].split()
    out["ai_jobs"] = vault._rows("SELECT task, status, model, note, finished_at FROM ai_jobs WHERE document_id = ? ORDER BY id DESC LIMIT 5", (document_id,))
    out["financials"] = vault._rows("SELECT id, basis, period_end, unit FROM financials WHERE document_id = ? ORDER BY basis DESC", (document_id,))
    return out


def facts(vault: Vault, document_id: int) -> dict[str, list[dict[str, Any]]]:
    """Facts grouped by kind, each value once, with the pages it appears on and one context."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for r in vault.conn.execute(
        "SELECT kind, value, shown, detail, page_no, context FROM mentions WHERE document_id = ? ORDER BY page_no, id", (document_id,)
    ):
        entry = grouped.setdefault(r["kind"], {}).setdefault(
            r["value"], {"value": r["value"], "shown": r["shown"], "detail": r["detail"], "pages": [], "context": r["context"]}
        )
        if r["page_no"] not in entry["pages"]:
            entry["pages"].append(r["page_no"])
        entry["detail"] = entry["detail"] or r["detail"]
    return {kind: list(values.values()) for kind, values in grouped.items()}


def page_text(vault: Vault, document_id: int, page_no: int) -> dict[str, Any]:
    row = vault.conn.execute(
        "SELECT page_no, text, needs_vision FROM document_pages WHERE document_id = ? AND page_no = ?", (document_id, page_no)
    ).fetchone()
    if row is None:
        raise NotFound(f"Document {document_id} has no page {page_no}.")
    return dict(row)


def fy_of(day: str | None) -> str | None:
    """The Indian financial year a date falls in: 2024-09-30 is in 2024-25, 2025-03-31 too."""
    if not day or not re.match(r"\d{4}-\d{2}", day):
        return None
    year, month = int(day[:4]), int(day[5:7])
    start = year if month >= 4 else year - 1
    return f"{start}-{(start + 1) % 100:02d}"


# The date the library sorts and filters by: the document's own, else its meeting's, else the day it came in.
DOC_DATE = "COALESCE(m.doc_date, m.meeting_date, substr(d.ingested_at, 1, 10))"
FY_START = f"(CAST(substr({DOC_DATE}, 1, 4) AS INTEGER) - (CAST(substr({DOC_DATE}, 6, 2) AS INTEGER) < 4))"
SORTS = {
    "added": "d.id DESC",
    "newest": f"{DOC_DATE} DESC, d.id DESC",
    "oldest": f"{DOC_DATE} ASC, d.id ASC",
    "name": "lower(COALESCE(m.title, d.original_name)) ASC, d.id ASC",
}
LIBRARY_FROM = "documents d LEFT JOIN doc_meta m ON m.document_id = d.id LEFT JOIN companies c ON c.id = d.company_id"


@dataclass(frozen=True)
class Filters:
    """What the library is narrowed to. Every field is optional; dates are YYYY-MM-DD."""

    company_id: int | None = None
    no_client: bool = False  # only documents not filed under a client
    doc_type: str | None = None
    tag: str | None = None
    name: str = ""
    year: str | None = None  # calendar year of the document's date
    fy: str | None = None  # "2024-25": 1 April 2024 to 31 March 2025
    date_from: str | None = None
    date_to: str | None = None
    folder_id: int | None = None  # brought in with this folder
    within: str | None = None  # and inside this folder of it: "Acme/2024-25"
    kind: str | None = None  # a FILE_KINDS key
    scanned: bool | None = None  # has (or has no) scanned pages

    def where(self, skip: frozenset[str] | set[str] = frozenset()) -> tuple[str, list[Any]]:
        """The SQL condition over LIBRARY_FROM, leaving out the filters named in `skip` (for counting a filter's choices)."""
        where, params = ["1 = 1"], []
        on = lambda key: key not in skip and getattr(self, key) not in (None, "", False)  # noqa: E731
        if on("name") and self.name.strip():
            # Filters by what the document is called, not its text (that is search's job).
            where.append("(d.original_name LIKE ? OR m.title LIKE ? OR m.company_name LIKE ? OR m.source_folder LIKE ?)")
            params += [f"%{self.name.strip()}%"] * 4
        if on("company_id"):
            where.append("d.company_id = ?")
            params.append(self.company_id)
        if on("no_client"):
            where.append("d.company_id IS NULL")
        if on("doc_type"):
            where.append("d.doc_type = ?")
            params.append(self.doc_type)
        if on("tag"):
            where.append("d.id IN (SELECT dt.document_id FROM document_tags dt JOIN tags t ON t.id = dt.tag_id WHERE t.name = ?)")
            params.append(self.tag.lower())
        if on("year"):
            if not re.fullmatch(r"\d{4}", str(self.year)):
                raise Invalid("Give the year as four digits, e.g. 2024.")
            where.append(f"substr({DOC_DATE}, 1, 4) = ?")
            params.append(str(self.year))
        if on("fy"):
            m = re.fullmatch(r"(\d{4})-(\d{2})", str(self.fy))
            if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
                raise Invalid("Give the financial year as e.g. 2024-25.")
            start = int(m.group(1))
            where.append(f"{DOC_DATE} BETWEEN ? AND ?")
            params += [f"{start}-04-01", f"{start + 1}-03-31"]
        for key, op in (("date_from", ">="), ("date_to", "<=")):
            if on(key):
                value = str(getattr(self, key))
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise Invalid("Give dates as YYYY-MM-DD.") from exc
                where.append(f"{DOC_DATE} {op} ?")
                params.append(value)
        if on("folder_id"):
            where.append("m.folder_id = ?")
            params.append(self.folder_id)
        if on("within"):
            inside = self.within.strip("/\\").replace("\\", "/")
            if inside:
                where.append("(m.source_folder = ? OR substr(m.source_folder, 1, ?) = ?)")
                params += [inside, len(inside) + 1, inside + "/"]
        if on("kind"):
            if self.kind not in FILE_KINDS:
                raise Invalid(f"Kinds of file: {', '.join(FILE_KINDS)}.")
            media = sorted({MEDIA_TYPES[s] for s in FILE_KINDS[self.kind][1]})
            where.append(f"d.media_type IN ({', '.join('?' * len(media))})")
            params += media
        if "scanned" not in skip and self.scanned is not None:
            where.append(("" if self.scanned else "NOT ") + "EXISTS (SELECT 1 FROM document_pages p WHERE p.document_id = d.id AND p.needs_vision = 1)")
        return " AND ".join(where), params


def list_documents(
    vault: Vault,
    company_id: int | None = None,
    doc_type: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
    name: str = "",
    year: str | None = None,
    sort: str = "added",
    **more: Any,
) -> dict[str, Any]:
    """Documents, newest added first (or by `sort`: newest, oldest, name), narrowed by any of the Filters."""
    if sort not in SORTS:
        raise Invalid(f"Sort by one of: {', '.join(SORTS)}.")
    known = {f.name for f in fields(Filters)}
    unknown = set(more) - known
    if unknown:
        raise Invalid(f"Unknown filter: {', '.join(sorted(unknown))}.")
    filters = Filters(company_id=company_id, doc_type=doc_type, tag=tag, name=name or "", year=year, **more)
    sql_where, params = filters.where()
    total = vault.conn.execute(f"SELECT COUNT(*) FROM {LIBRARY_FROM} WHERE {sql_where}", params).fetchone()[0]
    rows = vault._rows(
        f"""SELECT d.id, d.doc_type, d.original_name, d.pages, d.ingested_at, d.company_id, d.media_type, c.name AS client,
                   m.title, m.company_name, m.meeting_kind, m.meeting_date, m.summary IS NOT NULL AS has_summary,
                   {DOC_DATE} AS doc_date, m.doc_date_basis, m.source_folder, m.folder_id,
                   CASE WHEN m.client_why LIKE 'pending:%' THEN NULL ELSE m.client_why END AS client_why,
                   (SELECT COUNT(*) FROM clauses cl WHERE cl.document_id = d.id) AS resolutions,
                   (SELECT group_concat(t.name, ' ') FROM document_tags dt JOIN tags t ON t.id = dt.tag_id
                     WHERE dt.document_id = d.id) AS tags
            FROM {LIBRARY_FROM}
            WHERE {sql_where} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    for r in rows:
        r["tags"] = sorted((r["tags"] or "").split())
        r["fy"] = fy_of(r["doc_date"])
        r["kind"] = KIND_OF_MEDIA.get(r["media_type"])
    return {"total": total, "documents": rows}


def facets(vault: Vault, filters: Filters) -> dict[str, Any]:
    """The choices each library filter offers, each counted with the other filters applied: types, clients, financial
    years, folders (and the folders inside the chosen one), kinds of file."""

    def counted(skip: set[str], select: str, group: str, joins: str = "") -> list[dict[str, Any]]:
        sql_where, params = filters.where(frozenset(skip))
        return vault._rows(
            f"SELECT {select}, COUNT(*) AS documents FROM {LIBRARY_FROM} {joins} WHERE {sql_where} GROUP BY {group} ORDER BY documents DESC",
            params,
        )

    types = [{"key": r["key"], "label": DOC_TYPES.get(r["key"], r["key"]), "documents": r["documents"]}
             for r in counted({"doc_type"}, "d.doc_type AS key", "d.doc_type")]
    clients = [{"key": r["key"], "label": r["label"] or "No client", "documents": r["documents"]}
               for r in counted({"company_id", "no_client"}, "d.company_id AS key, c.name AS label", "d.company_id")]
    years = sorted(counted({"fy", "year", "date_from", "date_to"}, f"{FY_START} AS start", FY_START), key=lambda r: -(r["start"] or 0))
    fys = [{"key": f"{r['start']}-{(r['start'] + 1) % 100:02d}", "documents": r["documents"]} for r in years if r["start"]]
    folder_rows = counted({"folder_id", "within"}, "m.folder_id AS key, f.path AS label", "m.folder_id",
                          "LEFT JOIN folders f ON f.id = m.folder_id")
    folder_list = [{"key": r["key"], "label": r["label"], "documents": r["documents"]} for r in folder_rows if r["key"] is not None]
    kinds: dict[str, int] = {}
    for r in counted({"kind"}, "d.media_type AS media", "d.media_type"):
        kind = KIND_OF_MEDIA.get(r["media"], "other")
        kinds[kind] = kinds.get(kind, 0) + r["documents"]
    inside: dict[str, int] = {}
    if filters.folder_id is not None:
        prefix = (filters.within or "").strip("/\\").replace("\\", "/")
        for r in counted({"within"}, "m.source_folder AS folder", "m.source_folder"):
            rest = (r["folder"] or "").removeprefix(prefix).strip("/") if not prefix or (r["folder"] or "").startswith(prefix) else None
            if rest:
                child = f"{prefix}/{rest.split('/')[0]}" if prefix else rest.split("/")[0]
                inside[child] = inside.get(child, 0) + r["documents"]
    return {
        "types": types,
        "clients": clients,
        "fys": fys,
        "folders": folder_list,
        "inside": [{"key": k, "label": k.split("/")[-1], "documents": n} for k, n in sorted(inside.items())],
        "kinds": [{"key": k, "label": FILE_KINDS[k][0] if k in FILE_KINDS else "Other", "documents": n}
                  for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])],
    }


# ----------------------------------------------------------------- search


def fts_query(text: str) -> str:
    """Her words as an FTS5 query: every word must appear; "quoted phrases" stay phrases; words of 3+ letters match as prefixes."""
    parts: list[str] = []
    for phrase, word in re.findall(r'"([^"]+)"|([\w.()/-]+)', text):
        if phrase:
            tokens = re.findall(r"\w+", phrase)
            if tokens:
                parts.append('"' + " ".join(tokens) + '"')
            continue
        for token in re.findall(r"\w+", word):
            parts.append(f'"{token}"*' if len(token) >= 3 and not token.isdigit() else f'"{token}"')
    if not parts:
        raise Invalid("Type a word or two to search for.")
    return " ".join(parts)


def search(
    vault: Vault,
    query: str,
    company_id: int | None = None,
    doc_type: str | None = None,
    tag: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Documents whose pages match, best first, each with its best passages and every matching page."""
    match = fts_query(query)
    where, params = ["pages_fts MATCH ?"], [match]
    if company_id is not None:
        where.append("d.company_id = ?")
        params.append(company_id)
    if doc_type:
        where.append("d.doc_type = ?")
        params.append(doc_type)
    if tag:
        where.append("d.id IN (SELECT dt.document_id FROM document_tags dt JOIN tags t ON t.id = dt.tag_id WHERE t.name = ?)")
        params.append(tag.lower())
    rows = vault._rows(
        f"""SELECT p.document_id, p.page_no, bm25(pages_fts) AS score,
                   snippet(pages_fts, 0, '[[', ']]', ' … ', 24) AS snippet
            FROM pages_fts JOIN document_pages p ON p.rowid = pages_fts.rowid JOIN documents d ON d.id = p.document_id
            WHERE {' AND '.join(where)} ORDER BY score LIMIT 500""",
        params,
    )
    by_doc: dict[int, dict[str, Any]] = {}
    for r in rows:
        hit = by_doc.setdefault(r["document_id"], {"document_id": r["document_id"], "score": r["score"], "pages": [], "passages": []})
        hit["pages"].append(r["page_no"])
        if len(hit["passages"]) < 3:
            hit["passages"].append({"page": r["page_no"], "text": " ".join(r["snippet"].split())})
    results = sorted(by_doc.values(), key=lambda h: h["score"])[:limit]
    for hit in results:
        hit["pages"].sort()
        hit.update(document(vault, hit["document_id"], brief=True))
        hit["original_name"] = vault.conn.execute("SELECT original_name FROM documents WHERE id = ?", (hit["document_id"],)).fetchone()[0]
        del hit["score"]
    return {"query": query, "documents": results, "matching_documents": len(by_doc)}


def search_in_document(vault: Vault, document_id: int, query: str) -> dict[str, Any]:
    match = fts_query(query)
    rows = vault._rows(
        """SELECT p.page_no, snippet(pages_fts, 0, '[[', ']]', ' … ', 32) AS snippet
           FROM pages_fts JOIN document_pages p ON p.rowid = pages_fts.rowid
           WHERE pages_fts MATCH ? AND p.document_id = ? ORDER BY p.page_no""",
        (match, document_id),
    )
    return {"document_id": document_id, "query": query, "pages": [{"page": r["page_no"], "text": " ".join(r["snippet"].split())} for r in rows]}


# --------------------------------------------------------------- AI queue


def queue(vault: Vault, document_id: int, task: str) -> None:
    pending = vault.conn.execute(
        "SELECT 1 FROM ai_jobs WHERE document_id = ? AND task = ? AND status IN ('queued', 'running')", (document_id, task)
    ).fetchone()
    if not pending:
        vault.conn.execute("INSERT INTO ai_jobs (document_id, task) VALUES (?, ?)", (document_id, task))


def save_summary(vault: Vault, document_id: int, summary: str, by: str, key_points: list[str] | None = None) -> None:
    """Store a summary. One she wrote is never replaced by an AI's."""
    document(vault, document_id, brief=True)
    current = vault.conn.execute("SELECT summary_by FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()
    if current and current["summary_by"] == "her" and by != "her":
        raise Invalid("She wrote this document's summary herself; it isn't replaced automatically.")
    vault.conn.execute(
        """INSERT INTO doc_meta (document_id, summary, summary_by, summary_at, key_points) VALUES (?, ?, ?, datetime('now'), ?)
           ON CONFLICT(document_id) DO UPDATE SET summary = excluded.summary, summary_by = excluded.summary_by,
             summary_at = excluded.summary_at, key_points = excluded.key_points""",
        (document_id, summary.strip(), by, json.dumps(key_points or [], ensure_ascii=False)),
    )
    vault.log("save summary", {"id": document_id, "by": by})


def stats(vault: Vault) -> dict[str, Any]:
    one = lambda sql: vault.conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "documents": one("SELECT COUNT(*) FROM documents"),
        "pages": one("SELECT COUNT(*) FROM document_pages"),
        "resolutions": one("SELECT COUNT(*) FROM clauses"),
        "companies": one("SELECT COUNT(*) FROM companies"),
        "summaries": one("SELECT COUNT(*) FROM doc_meta WHERE summary IS NOT NULL"),
        "ai_queue": one("SELECT COUNT(*) FROM ai_jobs WHERE status IN ('queued', 'running')"),
        "by_type": vault._rows("SELECT doc_type, COUNT(*) AS documents FROM documents GROUP BY doc_type ORDER BY documents DESC"),
    }
