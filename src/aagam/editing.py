"""Her corrections and deletions, and how they survive re-reading a document.

What AAGAM reads from a document (its facts, resolutions, statements, tags) is
rebuilt whenever the document is read again. Her corrections are kept apart,
in their own tables, and applied after every reading:

- a page's text she corrected (an OCR misreading) is kept as hers;
- the company, meeting and date she set for a document win over what was read;
- a resolution she edited keeps her wording; one she deleted stays deleted;
- a fact that isn't one (a table heading taken for a company) stays hidden, in
  that document or everywhere; a person or company can be shown under her name;
- a tag she renamed or deleted is renamed or left off by automatic tagging too,
  and an automatic tag she took off a document isn't put back;
- statements she deleted aren't read again.

Deleting a document puts it in the Trash (trash.py): the file waits in the bin
folder, her notes on it become general notes, the company file's quotes stay
(without the link), and all she had added to it is kept, so restoring it puts
it back as it was.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import entities

# ---------------------------------------------------------------- documents

DOC_OVERRIDES = ("company_name", "meeting_kind", "meeting_date", "doc_date")
MEETING_KINDS = ("agm", "egm", "board", "committee", "postal_ballot")


def _meta(vault: Vault, document_id: int, column: str) -> Any:
    row = vault.conn.execute(f"SELECT {column} FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()
    return row[0] if row else None


def _set_meta(vault: Vault, document_id: int, column: str, value: Any) -> None:
    vault.conn.execute(
        f"INSERT INTO doc_meta (document_id, {column}) VALUES (?, ?) ON CONFLICT(document_id) DO UPDATE SET {column} = excluded.{column}",
        (document_id, value),
    )


def set_document_details(vault: Vault, document_id: int, details: dict[str, Any]) -> None:
    """The company it is about, the meeting kind and date, the document's own date: hers from now on, whatever
    re-reading finds."""
    unknown = set(details) - set(DOC_OVERRIDES)
    if unknown:
        raise Invalid(f"Unknown detail: {', '.join(sorted(unknown))}.")
    if details.get("meeting_kind") and details["meeting_kind"] not in MEETING_KINDS:
        raise Invalid(f"The meeting is one of: {', '.join(MEETING_KINDS)}.")
    for key, what in (("meeting_date", "the meeting date"), ("doc_date", "the document's date")):
        if details.get(key):
            try:
                datetime.strptime(details[key], "%Y-%m-%d")
            except ValueError as exc:
                raise Invalid(f"Give {what} as YYYY-MM-DD.") from exc
    current = json.loads(_meta(vault, document_id, "overrides") or "{}")
    current.update({k: (v.strip() if isinstance(v, str) else v) or None for k, v in details.items()})
    _set_meta(vault, document_id, "overrides", json.dumps(current))
    apply_document_overrides(vault, document_id)
    if "doc_date" in details and not details["doc_date"]:
        from . import library  # she cleared her date: work it out again

        row = vault.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is not None:
            library.date_document(vault, row)


def apply_document_overrides(vault: Vault, document_id: int) -> None:
    overrides = json.loads(_meta(vault, document_id, "overrides") or "{}")
    for key, value in overrides.items():
        if key == "doc_date":
            if value:  # her date wins; cleared, the next reading works it out again
                vault.conn.execute("UPDATE doc_meta SET doc_date = ?, doc_date_basis = 'set by her' WHERE document_id = ?", (value, document_id))
        elif key in DOC_OVERRIDES:
            vault.conn.execute(f"UPDATE doc_meta SET {key} = ? WHERE document_id = ?", (value, document_id))
    if "company_name" in overrides or "meeting_kind" in overrides or "meeting_date" in overrides:
        # The precedent library carries the company and meeting of each resolution; keep it in step.
        for key in ("company_name", "meeting_kind", "meeting_date"):
            if key in overrides:
                vault.conn.execute(f"UPDATE clauses SET {key} = ? WHERE document_id = ?", (overrides[key], document_id))


def edited_pages(vault: Vault, document_id: int) -> set[int]:
    value = _meta(vault, document_id, "edited_pages")
    return {int(p) for p in value.split(",")} if value else set()


def edit_page(vault: Vault, home: Path | None, document_id: int, page_no: int, text: str) -> dict[str, Any]:
    """She corrects a page's text (usually an OCR misreading). Everything is read again from her text."""
    from . import library

    library.page_text(vault, document_id, page_no)
    vault.conn.execute("UPDATE document_pages SET text = ? WHERE document_id = ? AND page_no = ?", (text.strip(), document_id, page_no))
    pages = edited_pages(vault, document_id) | {page_no}
    _set_meta(vault, document_id, "edited_pages", ",".join(str(p) for p in sorted(pages)))
    vault.log("edit page", {"document": document_id, "page": page_no})
    library.index_document(vault, document_id, keep_type=True, home=home)
    return library.page_text(vault, document_id, page_no)


def delete_document(vault: Vault, home: Path, document_id: int) -> dict[str, Any]:
    """Delete a document into the Trash, from where it can be put back as it was (trash.py)."""
    from . import trash

    return trash.put_document(vault, home, document_id)


def _keep_notes(vault: Vault, kind: str, target: str, prefix: str) -> int:
    """Her notes on something being deleted become general notes, so her words aren't lost."""
    return vault.conn.execute(
        "UPDATE notes SET target_kind = 'general', target = '', text = ? || char(10) || text, updated_at = datetime('now') "
        "WHERE target_kind = ? AND target = ?",
        (f"{prefix}:", kind, target),
    ).rowcount


def keep_notes_on_company(vault: Vault, company_id: int) -> int:
    name = vault.company_row(company_id)["name"]
    return _keep_notes(vault, "company", str(company_id), f"On {name} (deleted from the company file)")


# --------------------------------------------------------------- resolutions

CLAUSE_FIELDS = {"title", "resolution_kind", "business", "sections", "topics", "max_amount", "body", "statement"}


def edit_clause(vault: Vault, clause_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    from . import precedents

    clause = precedents.get(vault, clause_id)
    unknown = set(changes) - CLAUSE_FIELDS
    if unknown:
        raise Invalid(f"Unknown field: {', '.join(sorted(unknown))}.")
    clean = _clean_clause(changes)
    row = vault.conn.execute("SELECT changes FROM clause_edits WHERE document_id = ? AND item_no = ?", (clause["document_id"], clause["item_no"])).fetchone()
    merged = {**(json.loads(row["changes"]) if row else {}), **clean}
    vault.conn.execute(
        """INSERT INTO clause_edits (document_id, item_no, changes) VALUES (?, ?, ?)
           ON CONFLICT(document_id, item_no) DO UPDATE SET changes = excluded.changes, deleted = 0""",
        (clause["document_id"], clause["item_no"], json.dumps(merged)),
    )
    _apply_clause(vault, clause_id, clean)
    vault.log("edit resolution", {"id": clause_id, "fields": sorted(clean)})
    return precedents.get(vault, clause_id)


def _clean_clause(changes: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if key in ("sections", "topics"):
            items = value.split() if isinstance(value, str) else list(value or [])
            out[key] = [str(i).strip().removeprefix("s.") for i in items if str(i).strip()] if key == "sections" else [str(i).strip().lower() for i in items if str(i).strip()]
        elif key == "resolution_kind":
            if value not in (None, "", "ordinary", "special", "board"):
                raise Invalid("A resolution is ordinary, special or board.")
            out[key] = value or None
        elif key == "business":
            if value not in (None, "", "ordinary", "special"):
                raise Invalid("Business is ordinary or special.")
            out[key] = value or None
        elif key == "max_amount":
            out[key] = int(value) if value not in (None, "") else None
        elif key == "title":
            if not str(value or "").strip():
                raise Invalid("A resolution needs a title.")
            out[key] = str(value).strip()
        elif key == "body":
            out[key] = str(value or "").strip()
        else:
            out[key] = (str(value).strip() or None) if value is not None else None
    return out


def _apply_clause(vault: Vault, clause_id: int, changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if key in ("sections", "topics"):
            value = f" {' '.join(value)} " if value else ""
        vault.conn.execute(f"UPDATE clauses SET {key} = ? WHERE id = ?", (value, clause_id))


def delete_clause(vault: Vault, clause_id: int) -> dict[str, Any]:
    from . import precedents

    clause = precedents.get(vault, clause_id)
    vault.conn.execute(
        """INSERT INTO clause_edits (document_id, item_no, deleted) VALUES (?, ?, 1)
           ON CONFLICT(document_id, item_no) DO UPDATE SET deleted = 1""",
        (clause["document_id"], clause["item_no"]),
    )
    _keep_notes(vault, "resolution", str(clause_id), f"On the deleted resolution “{clause['title']}”")
    vault.conn.execute("DELETE FROM clauses WHERE id = ?", (clause_id,))
    vault.log("delete resolution", {"id": clause_id, "document": clause["document_id"], "item": clause["item_no"]})
    return {"deleted": clause_id}


def apply_clause_edits(vault: Vault, document_id: int) -> None:
    for edit in vault._rows("SELECT item_no, changes, deleted FROM clause_edits WHERE document_id = ?", (document_id,)):
        ids = [r[0] for r in vault.conn.execute("SELECT id FROM clauses WHERE document_id = ? AND item_no = ?", (document_id, edit["item_no"]))]
        for clause_id in ids:
            if edit["deleted"]:
                vault.conn.execute("DELETE FROM clauses WHERE id = ?", (clause_id,))
            else:
                _apply_clause(vault, clause_id, json.loads(edit["changes"]))


# ------------------------------------------------------------ facts, entities


def hidden_keys(vault: Vault, document_id: int | None = None) -> set[tuple[str, str]]:
    """(kind, key) pairs hidden everywhere, plus those hidden in this document."""
    rows = vault._rows("SELECT kind, key FROM hidden_facts WHERE document_id IS NULL OR document_id = ?", (document_id,))
    return {(r["kind"], r["key"]) for r in rows}


def hide_fact(vault: Vault, kind: str, value: str, document_id: int | None = None) -> dict[str, Any]:
    """Hide a fact that isn't one: in one document, or (document_id None) everywhere."""
    return hide_key(vault, kind, entities.key_of(kind, value), value, document_id)


def hide_key(vault: Vault, kind: str, key: str, shown: str | None = None, document_id: int | None = None) -> dict[str, Any]:
    if not key:
        raise Invalid("Nothing to hide.")
    if document_id is not None and vault.conn.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
        raise NotFound(f"There is no document {document_id}.")
    exists = vault.conn.execute(
        "SELECT id FROM hidden_facts WHERE kind = ? AND key = ? AND document_id IS ?", (kind, key, document_id)
    ).fetchone()
    hidden_id = exists["id"] if exists else vault.conn.execute(
        "INSERT INTO hidden_facts (kind, key, shown, document_id) VALUES (?, ?, ?, ?)", (kind, key, shown or key, document_id)
    ).lastrowid
    removed = _remove_mentions(vault, kind, key, document_id)
    vault.log("hide fact", {"kind": kind, "key": key, "document": document_id, "mentions": removed})
    return {"id": hidden_id, "kind": kind, "key": key, "removed": removed}


def _remove_mentions(vault: Vault, kind: str, key: str, document_id: int | None) -> int:
    sql = "SELECT id, value FROM mentions WHERE kind = ?" + (" AND document_id = ?" if document_id is not None else "")
    params: tuple[Any, ...] = (kind, document_id) if document_id is not None else (kind,)
    ids = [r["id"] for r in vault._rows(sql, params) if entities.key_of(kind, r["value"]) == key]
    for mention_id in ids:
        vault.conn.execute("DELETE FROM mentions WHERE id = ?", (mention_id,))
    if kind == "person":
        # A person is also named beside a DIN; that name goes too.
        sql = "SELECT id, detail FROM mentions WHERE kind = 'din' AND detail IS NOT NULL" + (" AND document_id = ?" if document_id is not None else "")
        for r in vault._rows(sql, (document_id,) if document_id is not None else ()):
            if entities.key_of("person", r["detail"]) == key:
                vault.conn.execute("UPDATE mentions SET detail = NULL WHERE id = ?", (r["id"],))
    return len(ids)


def hidden_list(vault: Vault) -> list[dict[str, Any]]:
    return vault._rows(
        """SELECT h.id, h.kind, h.key, h.shown, h.document_id, h.created_at, coalesce(m.title, d.original_name) AS document
           FROM hidden_facts h LEFT JOIN documents d ON d.id = h.document_id LEFT JOIN doc_meta m ON m.document_id = h.document_id
           ORDER BY h.id DESC"""
    )


def unhide(vault: Vault, hidden_id: int, home: Path | None = None) -> dict[str, Any]:
    from . import library

    row = vault.conn.execute("SELECT * FROM hidden_facts WHERE id = ?", (hidden_id,)).fetchone()
    if row is None:
        raise NotFound(f"Nothing hidden with id {hidden_id}.")
    vault.conn.execute("DELETE FROM hidden_facts WHERE id = ?", (hidden_id,))
    # Read again the documents it can be in, so it comes back where it was.
    if row["document_id"] is not None:
        docs = [row["document_id"]]
    else:
        word = max((row["shown"] or row["key"]).split(), key=len)
        docs = [r[0] for r in vault.conn.execute("SELECT DISTINCT document_id FROM document_pages WHERE text LIKE ?", (f"%{word}%",))]
    for document_id in docs:
        library.index_document(vault, document_id, keep_type=True, home=home)
    return {"restored": hidden_id, "documents_read_again": len(docs)}


def rename_entity(vault: Vault, kind: str, key: str, name: str | None) -> dict[str, Any]:
    """The name she wants it shown under (None goes back to the fullest spelling found)."""
    if kind not in entities.KINDS:
        raise Invalid(f"Unknown kind {kind!r}.")
    if name and name.strip():
        vault.conn.execute(
            "INSERT INTO entity_names (kind, key, name) VALUES (?, ?, ?) ON CONFLICT(kind, key) DO UPDATE SET name = excluded.name",
            (kind, key, name.strip()),
        )
    else:
        vault.conn.execute("DELETE FROM entity_names WHERE kind = ? AND key = ?", (kind, key))
    return {"kind": kind, "key": key, "name": name}


def entity_names(vault: Vault) -> dict[tuple[str, str], str]:
    return {(r["kind"], r["key"]): r["name"] for r in vault._rows("SELECT kind, key, name FROM entity_names")}


# ---------------------------------------------------------------------- tags


def tag_rule(vault: Vault, name: str) -> tuple[bool, str | None]:
    """(has a rule, what it becomes). Becomes None: deleted."""
    row = vault.conn.execute("SELECT becomes FROM tag_rules WHERE name = ?", (name,)).fetchone()
    return (True, row["becomes"]) if row else (False, None)


def rename_tag(vault: Vault, old: str, new: str) -> dict[str, Any]:
    old_clean, new_clean = (" ".join(t.strip().split()).lower() for t in (old, new))
    if not new_clean or len(new_clean) > 60:
        raise Invalid("A tag is a word or short phrase, up to 60 characters.")
    source = vault.conn.execute("SELECT id FROM tags WHERE name = ?", (old_clean,)).fetchone()
    if source is None:
        raise NotFound(f"There is no tag {old!r}.")
    if old_clean == new_clean:
        return {"tag": new_clean, "merged": False}
    target = vault.conn.execute("SELECT id FROM tags WHERE name = ?", (new_clean,)).fetchone()
    if target:
        # Merging into a tag that exists: documents keep the strongest "added by" (hers wins).
        vault.conn.execute(
            """INSERT INTO document_tags (document_id, tag_id, added_by, added_at)
               SELECT document_id, ?, added_by, added_at FROM document_tags WHERE tag_id = ?
               ON CONFLICT(document_id, tag_id) DO UPDATE SET
                 added_by = CASE WHEN excluded.added_by = 'her' THEN 'her' ELSE document_tags.added_by END""",
            (target["id"], source["id"]),
        )
        vault.conn.execute("DELETE FROM tags WHERE id = ?", (source["id"],))
    else:
        vault.conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new_clean, source["id"]))
    vault.conn.execute(
        "INSERT INTO tag_rules (name, becomes) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET becomes = excluded.becomes",
        (old_clean, new_clean),
    )
    vault.conn.execute("DELETE FROM tag_rules WHERE name = ?", (new_clean,))  # in case the new name was once deleted
    vault.log("rename tag", {"from": old_clean, "to": new_clean, "merged": bool(target)})
    return {"tag": new_clean, "merged": bool(target)}


def delete_tag(vault: Vault, name: str) -> dict[str, Any]:
    clean = " ".join(name.strip().split()).lower()
    row = vault.conn.execute("SELECT id FROM tags WHERE name = ?", (clean,)).fetchone()
    if row is None:
        raise NotFound(f"There is no tag {name!r}.")
    count = vault.conn.execute("SELECT COUNT(*) FROM document_tags WHERE tag_id = ?", (row["id"],)).fetchone()[0]
    vault.conn.execute("DELETE FROM tags WHERE id = ?", (row["id"],))
    vault.conn.execute("INSERT INTO tag_rules (name, becomes) VALUES (?, NULL) ON CONFLICT(name) DO UPDATE SET becomes = NULL", (clean,))
    vault.log("delete tag", {"tag": clean, "documents": count})
    return {"deleted": clean, "documents": count}


def removed_tags(vault: Vault, document_id: int) -> set[str]:
    value = _meta(vault, document_id, "removed_tags")
    return set(json.loads(value)) if value else set()


def remember_removed_tag(vault: Vault, document_id: int, name: str, add: bool = True) -> None:
    current = removed_tags(vault, document_id)
    current = current | {name} if add else current - {name}
    _set_meta(vault, document_id, "removed_tags", json.dumps(sorted(current)))
