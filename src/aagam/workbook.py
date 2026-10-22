"""The work register and notes: how past and present work is kept and found again."""

from __future__ import annotations

import json
from typing import Any

from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import checklists
from .library import fts_query

NOTE_KINDS = ("general", "document", "company", "entity", "work", "resolution", "financials")
STATUSES = ("open", "waiting", "done", "dropped")


# ------------------------------------------------------------------ notes


def add_note(vault: Vault, text: str, target_kind: str = "general", target: str = "", pinned: bool = False, by: str = "her") -> dict[str, Any]:
    if target_kind not in NOTE_KINDS:
        raise Invalid(f"Notes go on: {', '.join(NOTE_KINDS)}.")
    if not text.strip():
        raise Invalid("Write the note first.")
    note_id = vault.conn.execute(
        "INSERT INTO notes (target_kind, target, text, pinned, by) VALUES (?, ?, ?, ?, ?)",
        (target_kind, str(target), text.strip(), int(pinned), by),
    ).lastrowid
    vault.log("add note", {"id": note_id, "on": f"{target_kind}:{target}"})
    return note(vault, note_id)


def note(vault: Vault, note_id: int) -> dict[str, Any]:
    row = vault.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        raise NotFound(f"There is no note {note_id}.")
    return dict(row)


def change_note(vault: Vault, note_id: int, text: str | None = None, pinned: bool | None = None) -> dict[str, Any]:
    note(vault, note_id)
    if text is not None:
        if not text.strip():
            raise Invalid("A note can't be empty; delete it instead.")
        vault.conn.execute("UPDATE notes SET text = ?, updated_at = datetime('now') WHERE id = ?", (text.strip(), note_id))
    if pinned is not None:
        vault.conn.execute("UPDATE notes SET pinned = ?, updated_at = datetime('now') WHERE id = ?", (int(pinned), note_id))
    return note(vault, note_id)


def delete_note(vault: Vault, note_id: int) -> None:
    note(vault, note_id)
    vault.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def notes_on(vault: Vault, target_kind: str, target: str) -> list[dict[str, Any]]:
    return vault._rows(
        "SELECT * FROM notes WHERE target_kind = ? AND target = ? ORDER BY pinned DESC, updated_at DESC", (target_kind, str(target))
    )


def search_notes(vault: Vault, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    if not query.strip():
        return vault._rows("SELECT * FROM notes ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,))
    return vault._rows(
        """SELECT n.*, snippet(notes_fts, 0, '[[', ']]', ' … ', 20) AS snippet FROM notes_fts
           JOIN notes n ON n.id = notes_fts.rowid WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?""",
        (fts_query(query), limit),
    )


# ------------------------------------------------------------------- work


def kinds() -> dict[str, str]:
    return {key: value["label"] for key, value in checklists.KINDS.items()}


def create_work(
    vault: Vault,
    title: str,
    kind: str,
    company_id: int | None = None,
    due_on: str | None = None,
    meeting_date: str | None = None,
    fy: str | None = None,
) -> dict[str, Any]:
    if kind not in checklists.KINDS:
        raise Invalid(f"Unknown kind of work {kind!r}; use one of: {', '.join(checklists.KINDS)}.")
    if not title.strip():
        raise Invalid("Give the work a title, e.g. “AGM 2026, Acme Widgets”.")
    if company_id is not None:
        vault.company_row(company_id)
    work_id = vault.conn.execute(
        "INSERT INTO works (title, kind, company_id, due_on, meeting_date, fy, checklist) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title.strip(), kind, company_id, due_on, meeting_date, fy, json.dumps(checklists.steps_for(kind))),
    ).lastrowid
    vault.log("create work", {"id": work_id, "kind": kind})
    return work(vault, work_id)


def work(vault: Vault, work_id: int) -> dict[str, Any]:
    row = vault.conn.execute(
        "SELECT w.*, c.name AS company FROM works w LEFT JOIN companies c ON c.id = w.company_id WHERE w.id = ?", (work_id,)
    ).fetchone()
    if row is None:
        raise NotFound(f"There is no work {work_id}.")
    out = dict(row)
    out["checklist"] = json.loads(out["checklist"])
    out["kind_label"] = checklists.KINDS.get(out["kind"], checklists.KINDS["other"])["label"]
    out["progress"] = _progress(out["checklist"])
    out["documents"] = vault._rows(
        """SELECT d.id, d.original_name, d.doc_type, m.title, wd.added_at FROM work_documents wd JOIN documents d ON d.id = wd.document_id
           LEFT JOIN doc_meta m ON m.document_id = d.id WHERE wd.work_id = ? ORDER BY wd.added_at""",
        (work_id,),
    )
    out["notes"] = notes_on(vault, "work", str(work_id))
    return out


def _progress(checklist: list[dict[str, Any]]) -> dict[str, int]:
    return {"done": sum(1 for s in checklist if s.get("done")), "total": len(checklist)}


def list_works(vault: Vault, status: str | None = None, company_id: int | None = None, query: str = "") -> list[dict[str, Any]]:
    where, params = ["1 = 1"], []
    if status:
        where.append("w.status = ?")
        params.append(status)
    if company_id is not None:
        where.append("w.company_id = ?")
        params.append(company_id)
    if query.strip():
        where.append("(w.title LIKE ? OR c.name LIKE ?)")
        params += [f"%{query.strip()}%"] * 2
    rows = vault._rows(
        f"""SELECT w.id, w.title, w.kind, w.company_id, c.name AS company, w.status, w.due_on, w.meeting_date, w.fy, w.checklist,
                   w.updated_at, w.closed_at, (SELECT COUNT(*) FROM work_documents wd WHERE wd.work_id = w.id) AS documents
            FROM works w LEFT JOIN companies c ON c.id = w.company_id WHERE {' AND '.join(where)}
            ORDER BY w.status = 'done', w.status = 'dropped', COALESCE(w.due_on, '9999'), w.updated_at DESC""",
        params,
    )
    for r in rows:
        r["progress"] = _progress(json.loads(r.pop("checklist")))
        r["kind_label"] = checklists.KINDS.get(r["kind"], checklists.KINDS["other"])["label"]
    return rows


def change_work(vault: Vault, work_id: int, **fields: Any) -> dict[str, Any]:
    current = work(vault, work_id)
    allowed = {"title", "status", "due_on", "meeting_date", "fy", "company_id"}
    # A date or company passed as None (or "") clears it; a title or status passed as None is left alone.
    clearable = {"due_on", "meeting_date", "fy", "company_id"}
    changes = {k: (v if v != "" else None) for k, v in fields.items() if k in allowed and (v is not None or k in clearable)}
    if "status" in changes and changes["status"] not in STATUSES:
        raise Invalid(f"Status is one of: {', '.join(STATUSES)}.")
    for key, value in changes.items():
        vault.conn.execute(f"UPDATE works SET {key} = ?, updated_at = datetime('now') WHERE id = ?", (value, work_id))
    if changes.get("status") in ("done", "dropped") and current["status"] not in ("done", "dropped"):
        vault.conn.execute("UPDATE works SET closed_at = datetime('now') WHERE id = ?", (work_id,))
    if changes.get("status") in ("open", "waiting"):
        vault.conn.execute("UPDATE works SET closed_at = NULL WHERE id = ?", (work_id,))
    return work(vault, work_id)


def set_checklist(vault: Vault, work_id: int, checklist: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the checklist with her edited version (ticks, new steps, removed steps, notes on steps)."""
    work(vault, work_id)
    clean = []
    for step in checklist:
        text = str(step.get("text", "")).strip()
        if not text:
            continue
        done = bool(step.get("done"))
        clean.append({"text": text, "basis": step.get("basis"), "done": done,
                      "done_at": step.get("done_at") if done else None, "note": step.get("note") or None})
    vault.conn.execute("UPDATE works SET checklist = ?, updated_at = datetime('now') WHERE id = ?", (json.dumps(clean), work_id))
    return work(vault, work_id)


def tick(vault: Vault, work_id: int, index: int, done: bool = True, note: str | None = None) -> dict[str, Any]:
    from datetime import datetime

    current = work(vault, work_id)
    steps = current["checklist"]
    if not 0 <= index < len(steps):
        raise Invalid(f"Step {index + 1} doesn't exist; the checklist has {len(steps)}.")
    steps[index]["done"] = done
    steps[index]["done_at"] = datetime.now().isoformat(timespec="minutes") if done else None
    if note is not None:
        steps[index]["note"] = note or None
    return set_checklist(vault, work_id, steps)


def attach(vault: Vault, work_id: int, document_id: int) -> dict[str, Any]:
    work(vault, work_id)
    if vault.conn.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone() is None:
        raise NotFound(f"There is no document {document_id}.")
    vault.conn.execute("INSERT OR IGNORE INTO work_documents (work_id, document_id) VALUES (?, ?)", (work_id, document_id))
    return work(vault, work_id)


def detach(vault: Vault, work_id: int, document_id: int) -> dict[str, Any]:
    vault.conn.execute("DELETE FROM work_documents WHERE work_id = ? AND document_id = ?", (work_id, document_id))
    return work(vault, work_id)


def works_of_document(vault: Vault, document_id: int) -> list[dict[str, Any]]:
    return vault._rows(
        "SELECT w.id, w.title, w.status FROM work_documents wd JOIN works w ON w.id = wd.work_id WHERE wd.document_id = ?", (document_id,)
    )


def delete_work(vault: Vault, work_id: int) -> dict[str, Any]:
    """Delete a piece of work. Its documents stay in the library; her notes on it become general notes."""
    current = work(vault, work_id)
    vault.conn.execute(
        "UPDATE notes SET target_kind = 'general', target = '', text = ? || char(10) || text WHERE target_kind = 'work' AND target = ?",
        (f"On the deleted work “{current['title']}”:", str(work_id)),
    )
    vault.conn.execute("DELETE FROM works WHERE id = ?", (work_id,))
    vault.log("delete work", {"id": work_id, "title": current["title"]})
    return {"deleted": work_id}
