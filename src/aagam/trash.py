"""The Trash: deleted documents wait here, with what it takes to put them back as they were.

Deleting a document takes it out of the library at once: its pages leave search, its facts leave the dossiers
and its resolutions leave the precedents. As before, its file goes to the bin folder in AAGAM_HOME, her notes on
it (and on its statements and resolutions) become general notes, and the company file's quotes from it stay,
without their link. What she had added to it is kept here with it: her page corrections and summary, the details
and tags she set, her edits to its resolutions and statements, the work it was linked to, which notes and quotes
were about it, and the folder it came from.

Restoring puts all of that back and reads the document again, so it is as she left it. Deleting it forever, or
emptying the Trash, removes the file for good. Files deleted before the Trash existed are in the bin folder too:
the Trash lists them, and brings one back into the library or deletes it.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from csdesk.config import Settings
from csdesk.documents.intake import DOC_TYPES
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import editing, library

BIN = "bin"
# Bin files are named "<date> <time> <original name>" (editing.py did so before the Trash existed, too).
BIN_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{4} ")


# ------------------------------------------------------------------ deleting


def put_document(vault: Vault, home: Path, document_id: int) -> dict[str, Any]:
    """Delete a document into the Trash. Returns what went where, as deleting always has, with the Trash item's id."""
    doc = _one(vault, "SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise NotFound(f"There is no document {document_id}.")
    meta = _one(vault, "SELECT * FROM doc_meta WHERE document_id = ?", (document_id,))
    name = (meta or {}).get("title") or doc["original_name"]
    client = _one(vault, "SELECT name FROM companies WHERE id = ?", (doc["company_id"],)) if doc["company_id"] else None
    financials = vault._rows("SELECT * FROM financials WHERE document_id = ?", (document_id,))
    clauses = vault._rows("SELECT id, item_no, title FROM clauses WHERE document_id = ?", (document_id,))

    payload: dict[str, Any] = {
        "document": doc,
        "meta": meta,
        "pages": vault._rows("SELECT page_no, text, needs_vision FROM document_pages WHERE document_id = ? ORDER BY page_no", (document_id,)),
        # Automatic tags come back by themselves when the document is read again.
        "tags": vault._rows(
            """SELECT t.name, dt.added_by, dt.added_at FROM document_tags dt JOIN tags t ON t.id = dt.tag_id
               WHERE dt.document_id = ? AND dt.added_by != 'auto'""",
            (document_id,),
        ),
        "clause_edits": vault._rows("SELECT item_no, changes, deleted FROM clause_edits WHERE document_id = ?", (document_id,)),
        "hidden_facts": vault._rows("SELECT kind, key, shown, created_at FROM hidden_facts WHERE document_id = ?", (document_id,)),
        "financials": financials,
        "dismissed_financials": [r["basis"] for r in vault._rows("SELECT basis FROM dismissed_financials WHERE document_id = ?", (document_id,))],
        "works": [r["work_id"] for r in vault._rows("SELECT work_id FROM work_documents WHERE document_id = ?", (document_id,))],
        "notes": _note_ids(vault, "document", document_id),
        "note_prefix": f"On the deleted document “{name}”",
        "statement_notes": [],
        "resolution_notes": [],
        "sources": [r["id"] for r in vault._rows("SELECT id FROM field_sources WHERE document_id = ?", (document_id,))],
        "source_note": f"(source document deleted: {doc['original_name']})",
        "folder_files": vault._rows("SELECT folder_id, rel_path FROM folder_files WHERE document_id = ?", (document_id,)),
    }

    # Her notes on its statements and resolutions are kept as general notes, as when those are deleted one by one.
    for fin in financials:
        prefix = f"On the deleted statements of {fin['company_name'] or (client or {}).get('name') or 'a company'}"
        payload["statement_notes"] += [{"id": i, "financial_id": fin["id"], "prefix": prefix} for i in _note_ids(vault, "financials", fin["id"])]
        editing._keep_notes(vault, "financials", str(fin["id"]), prefix)
    for clause in clauses:
        prefix = f"On the deleted resolution “{clause['title']}”"
        payload["resolution_notes"] += [{"id": i, "item_no": clause["item_no"], "prefix": prefix} for i in _note_ids(vault, "resolution", clause["id"])]
        editing._keep_notes(vault, "resolution", str(clause["id"]), prefix)
    notes = editing._keep_notes(vault, "document", str(document_id), payload["note_prefix"])
    # The company file's quotes stay; they just no longer point at a document.
    sources = vault.conn.execute(
        "UPDATE field_sources SET document_id = NULL, note = trim(coalesce(note, '') || ' ' || ?) WHERE document_id = ?",
        (payload["source_note"], document_id),
    ).rowcount
    # Rows whose search index is kept by triggers go first, so the index is cleaned too.
    vault.conn.execute("DELETE FROM document_pages WHERE document_id = ?", (document_id,))
    vault.conn.execute("DELETE FROM clauses WHERE document_id = ?", (document_id,))
    vault.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    # The file moves last, once everything that can fail has been done, so a failure leaves it where it was.
    stored = home / doc["stored_path"]
    shared = vault.conn.execute("SELECT COUNT(*) FROM documents WHERE stored_path = ?", (doc["stored_path"],)).fetchone()[0]
    target = None
    if not shared and stored.is_file():
        target = _unique(home / BIN / f"{datetime.now():%Y-%m-%d %H%M} {doc['original_name']}")
    pages = doc["pages"]
    detail = " · ".join(part for part in (
        DOC_TYPES.get(doc["doc_type"], doc["doc_type"]), f"{pages} page{'' if pages == 1 else 's'}", (client or {}).get("name"),
    ) if part)
    trash_id = vault.conn.execute(
        "INSERT INTO trash (kind, item_id, name, detail, file, size, payload, deleted_by) VALUES ('document', ?, ?, ?, ?, ?, ?, ?)",
        (document_id, name, detail, target.relative_to(home).as_posix() if target else None,
         stored.stat().st_size if target else None, json.dumps(payload, ensure_ascii=False), vault.actor),
    ).lastrowid
    kept = str(target.relative_to(home)) if target else None
    vault.log("delete document", {"id": document_id, "name": doc["original_name"], "file_kept_in": kept, "trash": trash_id})
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stored), target)
    shutil.rmtree(home / "cache" / "pages" / str(document_id), ignore_errors=True)
    return {"deleted": document_id, "name": name, "file_kept_in": kept, "notes_kept": notes, "sources_unlinked": sources,
            "trash_id": trash_id}


def trash_documents(vault: Vault, home: Path, ids: list[int]) -> dict[str, Any]:
    """Delete several documents into the Trash. One that can't be deleted doesn't stop the others."""
    trashed: list[int] = []
    failed: list[dict[str, Any]] = []
    for document_id in dict.fromkeys(ids):
        vault.conn.execute("SAVEPOINT trash_one")
        try:
            put_document(vault, home, document_id)
        except Exception as exc:  # one bad document mustn't undo the rest
            vault.conn.execute("ROLLBACK TO SAVEPOINT trash_one")
            failed.append({"id": document_id, "error": str(exc)})
        else:
            trashed.append(document_id)
        vault.conn.execute("RELEASE SAVEPOINT trash_one")
    return {"trashed": trashed, "failed": failed}


# ------------------------------------------------------------------- the list


def list_trash(vault: Vault, home: Path) -> dict[str, Any]:
    """What is in the Trash, newest first, and the files in the bin folder from before the Trash existed."""
    items = []
    referenced = set()
    for row in vault._rows("SELECT id, kind, item_id, name, detail, file, size, deleted_at, deleted_by FROM trash ORDER BY deleted_at DESC, id DESC"):
        if row["file"]:
            referenced.add(Path(row["file"]).name.lower())
        items.append({
            "id": row["id"], "kind": row["kind"], "item_id": row["item_id"], "name": row["name"], "detail": row["detail"],
            "deleted_at": row["deleted_at"], "deleted_by": row["deleted_by"], "size": row["size"],
            "file_missing": not _held_file(vault, home, row).is_file(),
        })
    loose = []
    bin_dir = home / BIN
    if bin_dir.is_dir():
        for path in sorted(bin_dir.iterdir(), key=lambda p: p.name.lower()):
            if path.is_file() and path.name.lower() not in referenced and not path.name.startswith(".") and path.name.lower() != "desktop.ini":
                stat = path.stat()
                loose.append({"name": path.name, "size": stat.st_size,
                              "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
    size = sum(i["size"] or 0 for i in items) + sum(f["size"] for f in loose)
    return {"items": items, "loose": loose, "bytes": size, "count": len(items) + len(loose)}


# ------------------------------------------------------------------ restoring


def restore(vault: Vault, settings: Settings, trash_id: int) -> dict[str, Any]:
    """Put a document back as she left it, under its old id if that is free, and read it again."""
    home = settings.home
    row = _trash_row(vault, trash_id)
    if row["kind"] != "document":
        raise Invalid(f"AAGAM can't restore a {row['kind']} yet.")
    payload = json.loads(row["payload"])
    doc, meta = payload["document"], payload["meta"]
    held = _held_file(vault, home, row, payload)
    if not held.is_file():
        raise Invalid(f"The file of “{row['name']}” is no longer in the bin folder, so it can't be put back. Delete it forever instead.")

    # Where the file goes back to: its old place, or beside it if something else is there now.
    stored = doc["stored_path"]
    target = None
    if row["file"]:
        target = home / stored
        if target.exists():
            target = _unique(target)
            stored = target.relative_to(home).as_posix()

    company_id = doc["company_id"] if doc["company_id"] and _exists(vault, "companies", doc["company_id"]) else None
    values = {**doc, "stored_path": stored, "company_id": company_id}
    if _exists(vault, "documents", doc["id"]):
        values.pop("id")  # a document added since has taken its number
    new_id = _insert(vault, "documents", values)
    vault.conn.executemany(
        "INSERT INTO document_pages (document_id, page_no, text, needs_vision) VALUES (?, ?, ?, ?)",
        [(new_id, p["page_no"], p["text"], p["needs_vision"]) for p in payload["pages"]],
    )
    if meta:
        folder_id = meta.get("folder_id")
        _insert(vault, "doc_meta", {**meta, "document_id": new_id,
                                    "folder_id": folder_id if folder_id and _exists(vault, "folders", folder_id) else None})
    for tag in payload["tags"]:
        tag_id = library._tag_id(vault, tag["name"])
        vault.conn.execute("INSERT OR IGNORE INTO document_tags (document_id, tag_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                           (new_id, tag_id, tag["added_by"], tag["added_at"]))
    vault.conn.executemany(
        "INSERT OR REPLACE INTO clause_edits (document_id, item_no, changes, deleted) VALUES (?, ?, ?, ?)",
        [(new_id, e["item_no"], e["changes"], e["deleted"]) for e in payload["clause_edits"]],
    )
    vault.conn.executemany(
        "INSERT INTO hidden_facts (kind, key, shown, document_id, created_at) VALUES (?, ?, ?, ?, ?)",
        [(h["kind"], h["key"], h["shown"], new_id, h["created_at"]) for h in payload["hidden_facts"]],
    )
    statements: dict[int, int] = {}
    for fin in payload["financials"]:
        values = {**fin, "document_id": new_id,
                  "company_id": fin["company_id"] if fin["company_id"] and _exists(vault, "companies", fin["company_id"]) else None}
        if _exists(vault, "financials", fin["id"]):
            values.pop("id")
        statements[fin["id"]] = _insert(vault, "financials", values)
    vault.conn.executemany("INSERT OR IGNORE INTO dismissed_financials (document_id, basis) VALUES (?, ?)",
                           [(new_id, basis) for basis in payload["dismissed_financials"]])
    for work_id in payload["works"]:
        if _exists(vault, "works", work_id):
            vault.conn.execute("INSERT OR IGNORE INTO work_documents (work_id, document_id) VALUES (?, ?)", (work_id, new_id))
    notes = _return_notes(vault, payload["notes"], payload["note_prefix"], "document", new_id)
    for note in payload["statement_notes"]:
        if note["financial_id"] in statements:
            _return_notes(vault, [note["id"]], note["prefix"], "financials", statements[note["financial_id"]])
    sources = 0
    for source_id in payload["sources"]:
        source = _one(vault, "SELECT note FROM field_sources WHERE id = ? AND document_id IS NULL", (source_id,))
        if source is not None:
            vault.conn.execute("UPDATE field_sources SET document_id = ?, note = ? WHERE id = ?",
                               (new_id, _without(source["note"], payload["source_note"]), source_id))
            sources += 1
    for link in payload["folder_files"]:
        vault.conn.execute("UPDATE folder_files SET document_id = ? WHERE folder_id = ? AND rel_path = ? AND document_id IS NULL",
                           (new_id, link["folder_id"], link["rel_path"]))

    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(held), target)
    try:
        library.index_new(vault, settings, new_id, keep_type=True, queue_ai=not (meta or {}).get("summary"))
        # Its resolutions have new numbers after reading; her notes on them follow their item numbers.
        for note in payload["resolution_notes"]:
            clause = _one(vault, "SELECT id FROM clauses WHERE document_id = ? AND item_no = ? ORDER BY id LIMIT 1", (new_id, note["item_no"]))
            if clause:
                _return_notes(vault, [note["id"]], note["prefix"], "resolution", clause["id"])
    except BaseException:
        if target and target.is_file():
            shutil.move(str(target), held)  # the database rolls back; the file goes back to the bin with it
        raise
    vault.conn.execute("DELETE FROM trash WHERE id = ?", (trash_id,))
    vault.log("restore document", {"id": new_id, "was": doc["id"], "name": doc["original_name"], "notes": notes, "sources": sources})
    return {"document_id": new_id, "name": row["name"]}


# ----------------------------------------------------------- deleting forever


def delete_forever(vault: Vault, home: Path, trash_id: int) -> dict[str, Any]:
    row = _trash_row(vault, trash_id)
    _remove_held(home, row)
    vault.conn.execute("DELETE FROM trash WHERE id = ?", (trash_id,))
    vault.log("delete forever", {"trash": trash_id, "name": row["name"]})
    return {"deleted": trash_id}


def empty(vault: Vault, home: Path) -> dict[str, Any]:
    """Everything in the Trash, and the bin folder's older files, deleted for good."""
    rows = vault._rows("SELECT id, name, file FROM trash")
    files = sum(_remove_held(home, row) for row in rows)
    vault.conn.execute("DELETE FROM trash")
    loose = list_trash(vault, home)["loose"]
    for item in loose:
        _loose_path(home, item["name"]).unlink(missing_ok=True)
    vault.log("empty trash", {"items": len(rows), "older_files": len(loose)})
    return {"deleted": len(rows) + len(loose), "files": files + len(loose)}


# --------------------------------------------- files from before the Trash existed


def restore_loose(vault: Vault, settings: Settings, name: str) -> dict[str, Any]:
    """Bring a file from the bin folder back into the library as a new document, and take it out of the bin."""
    path = _loose_path(settings.home, name, vault)
    original = BIN_STAMP.sub("", path.name) or path.name
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / original
        shutil.copy2(path, copy)
        info = library.add_document(vault, settings, copy, origin=library.Origin(modified=library.Origin.of_file(path).modified),
                                    work_out_client=True)
    path.unlink()
    vault.log("restore older bin file", {"file": path.name, "document": info["document_id"]})
    return {"document_id": info["document_id"]}


def delete_loose(vault: Vault, home: Path, name: str) -> dict[str, Any]:
    path = _loose_path(home, name, vault)
    path.unlink()
    vault.log("delete older bin file", {"file": path.name})
    return {"deleted": path.name}


# ------------------------------------------------------------------- helpers


def _one(vault: Vault, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = vault.conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _exists(vault: Vault, table: str, row_id: int) -> bool:
    return vault.conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is not None


def _insert(vault: Vault, table: str, values: dict[str, Any]) -> int:
    """A row as it was, keeping only the columns the table has now (it may have gained or lost some since)."""
    columns = {r[1] for r in vault.conn.execute(f"PRAGMA table_info({table})")}
    row = {k: v for k, v in values.items() if k in columns}
    sql = f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})"
    return vault.conn.execute(sql, list(row.values())).lastrowid


def _note_ids(vault: Vault, kind: str, target: int) -> list[int]:
    return [r["id"] for r in vault._rows("SELECT id FROM notes WHERE target_kind = ? AND target = ?", (kind, str(target)))]


def _return_notes(vault: Vault, ids: list[int], prefix: str, kind: str, target: int) -> int:
    """Notes that became general notes go back on what they were about, without the line saying it was deleted."""
    head = f"{prefix}:\n"
    moved = 0
    for note_id in ids:
        note = _one(vault, "SELECT text FROM notes WHERE id = ? AND target_kind = 'general'", (note_id,))
        if note is None:
            continue  # she has deleted it or put it somewhere else since
        text = note["text"][len(head):] if note["text"].startswith(head) else note["text"]
        vault.conn.execute("UPDATE notes SET target_kind = ?, target = ?, text = ?, updated_at = datetime('now') WHERE id = ?",
                           (kind, str(target), text, note_id))
        moved += 1
    return moved


def _without(note: str | None, marker: str) -> str | None:
    text = (note or "").replace(f" {marker}", "").replace(marker, "").strip()
    return text or None


def _trash_row(vault: Vault, trash_id: int) -> dict[str, Any]:
    row = _one(vault, "SELECT * FROM trash WHERE id = ?", (trash_id,))
    if row is None:
        raise NotFound(f"There is nothing in the Trash with id {trash_id}.")
    return row


def _held_file(vault: Vault, home: Path, row: dict[str, Any], payload: dict[str, Any] | None = None) -> Path:
    """Where a Trash item's file is: in the bin folder, or still in place when another document shares it."""
    if row["file"]:
        return home / row["file"]
    if payload is None:
        payload = json.loads(_one(vault, "SELECT payload FROM trash WHERE id = ?", (row["id"],))["payload"])
    return home / payload["document"]["stored_path"]


def _remove_held(home: Path, row: dict[str, Any]) -> int:
    """Delete a Trash item's file from the bin folder. A file another document still uses is left alone."""
    if not row["file"]:
        return 0
    path = (home / row["file"]).resolve()
    if not path.is_relative_to((home / BIN).resolve()) or not path.is_file():
        return 0
    path.unlink()
    return 1


def _loose_path(home: Path, name: str, vault: Vault | None = None) -> Path:
    """A file in the bin folder by its name, and nothing outside it."""
    bin_dir = (home / BIN).resolve()
    if not name or name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name or ":" in name:
        raise Invalid("That isn't a file in the bin folder.")
    path = (bin_dir / name).resolve()
    if path.parent != bin_dir:
        raise Invalid("That isn't a file in the bin folder.")
    if not path.is_file():
        raise NotFound(f"There is no {name} in the bin folder.")
    if vault is not None and any(Path(r["file"]).name.lower() == name.lower() for r in vault._rows("SELECT file FROM trash WHERE file IS NOT NULL")):
        raise Invalid(f"{name} belongs to a document in the Trash; restore or delete that instead.")
    return path


def _unique(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate
