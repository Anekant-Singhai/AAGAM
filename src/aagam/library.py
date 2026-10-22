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
from dataclasses import replace
from pathlib import Path
from typing import Any

from csdesk.config import Settings
from csdesk.documents import ingest as core_ingest
from csdesk.documents.intake import DOC_TYPES
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import analysis, classify, editing, entities, extract, finance, notices, ocr
from .finance.statements import is_statement_page

TYPE_TAGS = {key: key.replace("_", "-") for key in DOC_TYPES}
SENSITIVE_KINDS = {"pan"}


# ------------------------------------------------------------------- intake


def add_document(
    vault: Vault,
    settings: Settings,
    path: str | Path,
    company_id: int | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    queue_ai: bool = True,
) -> dict[str, Any]:
    """Bring a file in and index it. `doc_type` None means "work it out from the text"."""
    info = core_ingest(vault, settings, path, company_id, doc_type or "other", note)
    document_id = info["document_id"]
    if not info.get("already_on_file") or not _indexed(vault, document_id):
        index_new(vault, settings, document_id, keep_type=doc_type is not None, queue_ai=queue_ai)
    for tag in tags or []:
        add_tag(vault, document_id, tag, by="her")
    return {**info, **document(vault, document_id, brief=True)}


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
    conn.execute(
        """INSERT INTO doc_meta (document_id, title, detected_type, detected_why, company_name, company_cin,
                                 meeting_kind, meeting_date, words, status, error, indexed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed', NULL, datetime('now'))
           ON CONFLICT(document_id) DO UPDATE SET
             title = COALESCE(doc_meta.title, excluded.title), detected_type = excluded.detected_type,
             detected_why = excluded.detected_why, company_name = excluded.company_name,
             company_cin = excluded.company_cin, meeting_kind = excluded.meeting_kind,
             meeting_date = excluded.meeting_date, words = excluded.words, status = 'indexed', error = NULL,
             indexed_at = excluded.indexed_at""",
        (document_id, detected.title, detected.doc_type, detected.why, detected.company_name, detected.company_cin,
         meeting_kind, detected.meeting_date, words),
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
                  m.suggested_tags, m.ocr_pages, m.edited_pages, m.overrides, m.words, m.status
           FROM documents d LEFT JOIN doc_meta m ON m.document_id = d.id LEFT JOIN companies c ON c.id = d.company_id
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
    if brief:
        return {k: out[k] for k in ("id", "doc_type", "title", "summary", "tags", "scanned_pages", "company_name", "meeting_kind")}
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


def list_documents(
    vault: Vault,
    company_id: int | None = None,
    doc_type: str | None = None,
    tag: str | None = None,
    limit: int = 100,
    offset: int = 0,
    name: str = "",
    year: str | None = None,
) -> dict[str, Any]:
    where, params = ["1 = 1"], []
    if name.strip():
        # Filters by what the document is called, not its text (that is search's job).
        where.append("(d.original_name LIKE ? OR d.id IN (SELECT document_id FROM doc_meta WHERE title LIKE ? OR company_name LIKE ?))")
        params += [f"%{name.strip()}%"] * 3
    if year:
        # The year of the meeting it is about, or else the year it came in.
        where.append("COALESCE((SELECT substr(meeting_date, 1, 4) FROM doc_meta WHERE document_id = d.id), substr(d.ingested_at, 1, 4)) = ?")
        params.append(str(year))
    if company_id is not None:
        where.append("d.company_id = ?")
        params.append(company_id)
    if doc_type:
        where.append("d.doc_type = ?")
        params.append(doc_type)
    if tag:
        where.append("d.id IN (SELECT dt.document_id FROM document_tags dt JOIN tags t ON t.id = dt.tag_id WHERE t.name = ?)")
        params.append(tag.lower())
    sql_where = " AND ".join(where)
    total = vault.conn.execute(f"SELECT COUNT(*) FROM documents d WHERE {sql_where}", params).fetchone()[0]
    rows = vault._rows(
        f"""SELECT d.id, d.doc_type, d.original_name, d.pages, d.ingested_at, d.company_id, c.name AS client,
                   m.title, m.company_name, m.meeting_kind, m.meeting_date, m.summary IS NOT NULL AS has_summary,
                   (SELECT COUNT(*) FROM clauses cl WHERE cl.document_id = d.id) AS resolutions,
                   (SELECT group_concat(t.name, ' ') FROM document_tags dt JOIN tags t ON t.id = dt.tag_id
                     WHERE dt.document_id = d.id) AS tags
            FROM documents d LEFT JOIN doc_meta m ON m.document_id = d.id LEFT JOIN companies c ON c.id = d.company_id
            WHERE {sql_where} ORDER BY d.id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    for r in rows:
        r["tags"] = sorted((r["tags"] or "").split())
    return {"total": total, "documents": rows}


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
