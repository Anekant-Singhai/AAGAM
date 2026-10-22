"""Automatic analysis: what each document says, purpose by purpose, read with rules (no AI needed).

Every document is analysed when it comes in and whenever it is read again. Each analyser looks for one
purpose a CS reads documents for, scores how much the document is about it (keywords weighted by how
telling they are, counted against the document's length), and extracts what it can, each item with its
page and the sentence it came from:

- investments: loans, investments, guarantees and security given (s.186), investee, instrument, amount;
- legal: litigation and proceedings: forum, case number, parties, sections, status, amounts at stake;
- law: the law a document relies on: Acts, sections, rules, regulations, notifications, circulars, cases;
- amendments: what an amending instrument changes: what is substituted, inserted or omitted, from when;
- obligations: what must be done by when: "within 30 days", "on or before", with the duty and its basis;
- agreements: the terms of a contract: parties, date, term, consideration, governing law, termination.

Results are kept in `analyses` (one row per document and purpose) and brought together across the
library as registers: every investment, every legal matter, every provision cited, every amendment.
"""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from csdesk.vault import Vault

log = logging.getLogger(__name__)

# Purposes, in the order they are shown. Each is a module here with KIND, TITLE, COLUMNS and analyse(doc).
PURPOSES = ("investments", "legal", "law", "amendments", "obligations", "agreements")


@dataclass
class Doc:
    """What an analyser is given: the document's pages and what is already known about it."""

    id: int
    doc_type: str
    title: str | None
    company_name: str | None
    meeting_date: str | None
    pages: list[tuple[int, str]]
    mentions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(t for _, t in self.pages)


def result(kind: str, title: str, columns: list[dict[str, str]], items: list[dict[str, Any]], score: float,
           summary: str, tags: list[str] | None = None, highlights: list[dict[str, Any]] | None = None,
           facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """The shape every analyser returns. Column types: text, money, date, number, list, long."""
    return {"kind": kind, "title": title, "columns": columns, "items": items, "score": round(score, 3), "summary": summary,
            "tags": tags or [], "highlights": highlights or [], "facts": facts or {}}


def _modules() -> list[Any]:
    return [importlib.import_module(f".{name}", __name__) for name in PURPOSES]


def analysers() -> dict[str, Callable[[Doc], dict[str, Any] | None]]:
    return {m.KIND: m.analyse for m in _modules()}


def catalogue() -> list[dict[str, Any]]:
    return [{"kind": m.KIND, "title": m.TITLE, "columns": m.COLUMNS, "about": (m.__doc__ or "").strip().split("\n")[0]} for m in _modules()]


def load(vault: Vault, document_id: int) -> Doc:
    row = vault.conn.execute(
        """SELECT d.id, d.doc_type, m.title, m.company_name, m.meeting_date, d.original_name FROM documents d
           LEFT JOIN doc_meta m ON m.document_id = d.id WHERE d.id = ?""",
        (document_id,),
    ).fetchone()
    pages = [(r[0], r[1]) for r in vault.conn.execute("SELECT page_no, text FROM document_pages WHERE document_id = ? ORDER BY page_no", (document_id,))]
    mentions = vault._rows("SELECT kind, value, shown, detail, page_no, context FROM mentions WHERE document_id = ?", (document_id,))
    return Doc(row["id"], row["doc_type"], row["title"] or row["original_name"], row["company_name"], row["meeting_date"], pages, mentions)


def run_all(vault: Vault, document_id: int) -> list[dict[str, Any]]:
    """Analyse a document for every purpose and keep what was found. A failing analyser never stops the others."""
    doc = load(vault, document_id)
    vault.conn.execute("DELETE FROM analyses WHERE document_id = ?", (document_id,))
    found = []
    for kind, analyse in analysers().items():
        try:
            out = analyse(doc)
        except Exception:  # one analyser's bug mustn't cost the document its other analyses
            log.exception("analyser %s failed on document %s", kind, document_id)
            continue
        if not out or not (out["items"] or out["highlights"]):
            continue
        vault.conn.execute(
            "INSERT INTO analyses (document_id, kind, score, summary, result) VALUES (?, ?, ?, ?, ?)",
            (document_id, kind, out["score"], out["summary"], json.dumps(out, ensure_ascii=False, default=str)),
        )
        found.append(out)
    return found


def for_document(vault: Vault, document_id: int) -> list[dict[str, Any]]:
    rows = vault._rows("SELECT kind, result FROM analyses WHERE document_id = ?", (document_id,))
    order = {k: i for i, k in enumerate(PURPOSES)}
    return sorted((json.loads(r["result"]) for r in rows), key=lambda r: order.get(r["kind"], 99))


def overview(vault: Vault) -> list[dict[str, Any]]:
    """Per purpose: how many documents and items, for the Insights page."""
    counts = {r["kind"]: r for r in vault._rows(
        "SELECT kind, COUNT(*) AS documents, SUM(json_array_length(json_extract(result, '$.items'))) AS items FROM analyses GROUP BY kind"
    )}
    return [{**c, "documents": counts.get(c["kind"], {}).get("documents", 0), "items": counts.get(c["kind"], {}).get("items", 0) or 0}
            for c in catalogue()]


def register(vault: Vault, kind: str, query: str = "", company_id: int | None = None, limit: int = 2000) -> dict[str, Any]:
    """Every item of one purpose across the library, each with its document: the investments register, the matters list…"""
    module = next((m for m in _modules() if kind == m.KIND), None)
    if module is None:
        from csdesk.errors import NotFound

        raise NotFound(f"Unknown analysis {kind!r}; use one of: {', '.join(PURPOSES)}.")
    sql = """SELECT a.document_id, a.result, coalesce(m.title, d.original_name) AS document, d.doc_type, d.company_id,
                    c.name AS client, m.company_name, m.meeting_date, d.ingested_at
             FROM analyses a JOIN documents d ON d.id = a.document_id LEFT JOIN doc_meta m ON m.document_id = d.id
             LEFT JOIN companies c ON c.id = d.company_id WHERE a.kind = ?"""
    params: list[Any] = [kind]
    if company_id is not None:
        sql += " AND d.company_id = ?"
        params.append(company_id)
    items = []
    q = query.strip().lower()
    for row in vault._rows(sql + " ORDER BY coalesce(m.meeting_date, d.ingested_at) DESC", params):
        for item in json.loads(row["result"])["items"]:
            if q and q not in json.dumps(item, ensure_ascii=False).lower() and q not in (row["document"] or "").lower():
                continue
            items.append({**item, "document_id": row["document_id"], "document": row["document"], "doc_type": row["doc_type"],
                          "company": row["client"] or row["company_name"]})
            if len(items) >= limit:
                break
    return {"kind": kind, "title": module.TITLE, "columns": module.COLUMNS, "items": items, "count": len(items)}
