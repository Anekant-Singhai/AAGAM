"""The precedent library: resolutions from every notice on file, searchable by section, kind, amount and words.

This is the search she did by hand last night ("s.185 and s.186 resolutions
from listed companies' notices"), as one query.
"""

from __future__ import annotations

import re
from typing import Any

from csdesk.errors import NotFound
from csdesk.vault import Vault

from .library import fts_query


def search(
    vault: Vault,
    query: str = "",
    section: str | None = None,
    topic: str | None = None,
    resolution_kind: str | None = None,
    min_amount: int | None = None,
    max_amount: int | None = None,
    with_statement: bool = False,
    limit: int = 30,
) -> dict[str, Any]:
    where: list[str] = ["1 = 1"]
    params: list[Any] = []
    joins = ""
    order = "c.id DESC"
    if query.strip():
        joins = "JOIN clauses_fts f ON f.rowid = c.id"
        where.append("clauses_fts MATCH ?")
        params.append(fts_query(query))
        order = "bm25(clauses_fts, 4.0, 1.0, 0.5)"
    if section:
        number = re.sub(r"(?i)^(?:s\.|sec(?:tion)?\.?)\s*", "", section.strip())
        where.append("c.sections LIKE ?")
        params.append(f"% {number} %")
    if topic:
        where.append("c.topics LIKE ?")
        params.append(f"% {topic.strip().lower()} %")
    if resolution_kind:
        where.append("c.resolution_kind = ?")
        params.append(resolution_kind)
    if min_amount is not None:
        where.append("c.max_amount >= ?")
        params.append(min_amount)
    if max_amount is not None:
        where.append("c.max_amount <= ?")
        params.append(max_amount)
    if with_statement:
        where.append("c.statement IS NOT NULL")
    rows = vault._rows(
        f"""SELECT c.id, c.document_id, c.item_no, c.business, c.resolution_kind, c.title, c.sections, c.topics,
                   c.max_amount, c.page_from, c.company_name, c.meeting_kind, c.meeting_date,
                   c.statement IS NOT NULL AS has_statement, substr(c.body, 1, 280) AS opening,
                   d.original_name, d.company_id, co.name AS client
            FROM clauses c {joins} JOIN documents d ON d.id = c.document_id LEFT JOIN companies co ON co.id = d.company_id
            WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?""",
        [*params, limit],
    )
    for r in rows:
        r["sections"] = r["sections"].split()
        r["topics"] = r["topics"].split()
    return {"resolutions": rows, "count": len(rows)}


def get(vault: Vault, clause_id: int) -> dict[str, Any]:
    row = vault.conn.execute(
        """SELECT c.*, d.original_name, d.company_id, co.name AS client FROM clauses c
           JOIN documents d ON d.id = c.document_id LEFT JOIN companies co ON co.id = d.company_id WHERE c.id = ?""",
        (clause_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"There is no resolution {clause_id} in the precedent library.")
    out = dict(row)
    out["sections"] = out["sections"].split()
    out["topics"] = out["topics"].split()
    return out


def topics(vault: Vault) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for (value,) in vault.conn.execute("SELECT topics FROM clauses"):
        for topic in value.split():
            counts[topic] = counts.get(topic, 0) + 1
    return [{"topic": t, "resolutions": n} for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
