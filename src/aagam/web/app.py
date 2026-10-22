"""The AAGAM web interface: a JSON API, the built interface, and two background helpers.

It listens on 127.0.0.1 only. Two guards stop other websites open in her
browser from using it: the Host header must be this computer (against DNS
rebinding), and every change needs a custom header that a cross-site form or
script can't send without permission this server never gives.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from csdesk.documents.intake import DOC_TYPES, ingest_inbox, render_page
from csdesk.duedates import upcoming
from csdesk.errors import Blocked, CsDeskError, Invalid, NotFound
from csdesk.vault import ENTITIES, Source, mask

from .. import (
    __version__,
    ai,
    analysis,
    checks,
    editing,
    entities,
    everything,
    finance,
    library,
    precedents,
    review,
    workbook,
)
from ..config import AagamSettings
from ..db import open_db
from . import folders_api, system_api, trash_api

log = logging.getLogger("aagam.web")
STATIC = Path(__file__).parent / "static"
CHANGE_HEADER = "x-aagam"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class DocumentChanges(BaseModel):
    title: str | None = None
    doc_type: str | None = None
    company: str | None = None
    note: str | None = None
    company_name: str | None = None
    meeting_kind: str | None = None
    meeting_date: str | None = None
    doc_date: str | None = None


class PageTextIn(BaseModel):
    text: str


class ClauseChanges(BaseModel):
    title: str | None = None
    resolution_kind: str | None = None
    business: str | None = None
    sections: list[str] | None = None
    topics: list[str] | None = None
    max_amount: int | None = None
    body: str | None = None
    statement: str | None = None


class FactHide(BaseModel):
    kind: str
    value: str
    document_id: int | None = None


class NameIn(BaseModel):
    name: str | None = None


class StatementHeader(BaseModel):
    company_name: str | None = None
    basis: str | None = None
    period_end: str | None = None
    prior_period_end: str | None = None
    unit: str | None = None


class RecordIn(BaseModel):
    data: dict[str, Any]


class TagChanges(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)


class LoanFigures(BaseModel):
    paid_up_capital: int = Field(ge=0)
    free_reserves: int
    securities_premium: int = Field(0, ge=0)
    proposed_loans_investments: int = Field(0, ge=0)
    outstanding_loans_investments: int = Field(0, ge=0)
    proposed_borrowing: int = Field(0, ge=0)
    outstanding_borrowing: int = Field(0, ge=0)
    company: str | None = None
    to_wholly_owned_subsidiary: bool = False
    include_director_loans: bool = True


class LineFigures(BaseModel):
    current: int | None = None
    previous: int | None = None


class StatementFacts(BaseModel):
    company_class: str | None = None
    listed: bool | None = None
    holding_or_subsidiary: bool | None = None
    bank_borrowings: int | None = None
    deposits: int | None = None
    principal_repaid: int | None = None


class CompanyLink(BaseModel):
    company: str | None = None


class NoteIn(BaseModel):
    text: str
    target_kind: str = "general"
    target: str = ""
    pinned: bool = False


class NoteChange(BaseModel):
    text: str | None = None
    pinned: bool | None = None


class WorkIn(BaseModel):
    title: str
    kind: str
    company: str | None = None
    due_on: str | None = None
    meeting_date: str | None = None
    fy: str | None = None


class WorkChange(BaseModel):
    title: str | None = None
    status: str | None = None
    due_on: str | None = None
    meeting_date: str | None = None
    fy: str | None = None
    company: str | None = None


class ChecklistIn(BaseModel):
    checklist: list[dict[str, Any]]


def _spec(entity: str) -> Any:
    if entity not in ENTITIES:
        raise NotFound(f"Unknown record type {entity!r}.")
    return ENTITIES[entity]


def _fields(spec: Any) -> list[dict[str, Any]]:
    """The fields of a company-file record, for the interface to build its form from."""
    schema = spec.model.model_json_schema()
    out = []
    for name, prop in schema["properties"].items():
        options = prop.get("anyOf", [prop])
        kind = next((o for o in options if o.get("type") != "null"), {})
        out.append({
            "name": name,
            "type": kind.get("type", "string"),
            "enum": kind.get("enum"),
            "description": prop.get("description"),
            "required": name in spec.required,
            "sensitive": name in spec.sensitive,
        })
    return out


def _clean_record(data: dict[str, Any]) -> dict[str, Any]:
    """Empty boxes clear a field; a masked value sent back unchanged is left alone."""
    out = {}
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("XXXX"):
            continue
        out[key] = None if value == "" else value
    return out


def _entity_value(vault: Any, kind: str, key: str) -> str | None:
    for r in vault._rows("SELECT DISTINCT value FROM mentions WHERE kind = ?", (kind,)):
        if entities.key_of(kind, r["value"]) == key:
            return r["value"]
    if kind == "person":
        for r in vault._rows("SELECT DISTINCT detail FROM mentions WHERE kind = 'din' AND detail IS NOT NULL"):
            if entities.key_of("person", r["detail"]) == key:
                return r["detail"]
    return None


class OcrWorker(threading.Thread):
    """Reads long scanned documents in the background with Windows OCR."""

    def __init__(self, settings: AagamSettings, interval: float = 10) -> None:
        super().__init__(name="aagam-ocr", daemon=True)
        self.settings, self.interval = settings, interval
        self.stopping = threading.Event()

    def run(self) -> None:
        while not self.stopping.wait(self.interval):
            try:
                library.run_ocr_queue(self.settings.core.db_path, self.settings.core.home)
            except Exception:
                log.exception("OCR worker")

    def stop(self) -> None:
        self.stopping.set()


class InboxWatcher(threading.Thread):
    """Brings in files dropped into the inbox folder, once each has stopped growing."""

    def __init__(self, settings: AagamSettings, interval: float = 5) -> None:
        super().__init__(name="aagam-inbox", daemon=True)
        self.settings, self.interval = settings, interval
        self.stopping = threading.Event()
        self.sizes: dict[str, int] = {}

    def run(self) -> None:
        while not self.stopping.wait(self.interval):
            try:
                self.poll()
            except Exception:
                log.exception("inbox watcher")

    def poll(self) -> list[dict[str, Any]]:
        inbox = self.settings.core.inbox_dir
        inbox.mkdir(parents=True, exist_ok=True)
        files = {p.name: p.stat().st_size for p in inbox.iterdir() if p.is_file() and not p.name.startswith((".", "~$"))}
        steady = [name for name, size in files.items() if self.sizes.get(name) == size]
        self.sizes = files
        if not steady:
            return []
        with open_db(self.settings.core.db_path, actor="inbox") as vault:
            results = ingest_inbox(vault, self.settings.core)
            for result in results:
                if result.get("document_id") and not result.get("already_on_file"):
                    library.index_new(vault, self.settings.core, result["document_id"])
                    library.file_under_client(vault, result["document_id"])
        return results

    def stop(self) -> None:
        self.stopping.set()


def create_app(settings: AagamSettings, background: bool = True) -> FastAPI:
    core = settings.core
    core.ensure_dirs()
    helpers: list[Any] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        with open_db(core.db_path):
            pass  # create AAGAM's tables before anything else touches them
        if background:
            ai.reset_stuck_jobs(settings)
            if settings.local_ai:
                helpers.append(ai.Worker(settings))
            helpers.append(InboxWatcher(settings))
            helpers.append(OcrWorker(settings))
            helpers.extend(folders_api.helpers(settings))
            helpers.extend(system_api.helpers(settings))
            for helper in helpers:
                helper.start()
        yield
        for helper in helpers:
            helper.stop()

    app = FastAPI(title="AAGAM", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.helpers = helpers

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "AAGAM only answers on this computer."}, status_code=403)
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/") and request.headers.get(CHANGE_HEADER) != "1":
            return JSONResponse({"detail": "Changes must come from the AAGAM window."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(CsDeskError)
    async def plain_errors(_: Request, exc: CsDeskError) -> JSONResponse:
        status = 404 if isinstance(exc, NotFound) else 403 if isinstance(exc, Blocked) else 400
        return JSONResponse({"detail": str(exc)}, status_code=status)

    def db(actor: str = "her") -> Any:
        return open_db(core.db_path, actor=actor)

    def company_id_of(vault: Any, company: str | None) -> int | None:
        return vault.resolve_company(company) if company else None

    # Folders, the Trash, and this computer (health, updates, repairs): each in its own module.
    for module in (folders_api, trash_api, system_api):
        app.include_router(module.router(settings, db))

    # ---------------------------------------------------------- overview

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        from ..updates import app_folder, running_commit

        return {"ok": True, "version": __version__, "commit": running_commit(app_folder())}

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {"version": __version__, "doc_types": DOC_TYPES, "data_folder": str(core.home), "inbox": str(core.inbox_dir),
                "file_kinds": {key: label for key, (label, _) in library.FILE_KINDS.items()}}

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        today = date.today()
        with db() as vault:
            stats = library.stats(vault)
            due = [item.as_dict(today) for item in upcoming(vault, today, None, 30)]
            recent = library.list_documents(vault, limit=8)["documents"]
            works = [w for w in workbook.list_works(vault) if w["status"] in ("open", "waiting")]
            pinned = vault._rows("SELECT * FROM notes WHERE pinned = 1 ORDER BY updated_at DESC LIMIT 6")
            stats["financials"] = vault.conn.execute("SELECT COUNT(*) FROM financials").fetchone()[0]
        return {"stats": stats, "due": due[:12], "due_count": len(due), "recent": recent, "ai": ai_status(),
                "works": works[:8], "works_open": len(works), "pinned": pinned}

    @app.get("/api/ai/status")
    def ai_status() -> dict[str, Any]:
        status = ai.LocalAI.from_settings(settings).status() if settings.local_ai else {"running": False, "message": "Local AI is turned off."}
        with db() as vault:
            counts = {r["status"]: r["n"] for r in vault._rows("SELECT status, COUNT(*) AS n FROM ai_jobs GROUP BY status")}
        return {**status, "jobs": counts, "enabled": settings.local_ai}

    @app.get("/api/companies")
    def companies(q: str = "") -> dict[str, Any]:
        with db() as vault:
            return {"companies": vault.find_companies(q)}

    @app.get("/api/due")
    def due_dates(company: str | None = None, days: int = 60) -> dict[str, Any]:
        today = date.today()
        with db() as vault:
            items = upcoming(vault, today, company_id_of(vault, company), days)
        return {"today": today.isoformat(), "items": [item.as_dict(today) for item in items]}

    # --------------------------------------------------------- documents

    def library_filters(vault: Any, company: str | None, filters: dict[str, Any]) -> dict[str, Any]:
        """The query's filters as library.Filters fields. company "none" means documents without a client."""
        out = {k: v for k, v in filters.items() if v not in (None, "")}
        if company == "none":
            out["no_client"] = True
        elif company:
            out["company_id"] = company_id_of(vault, company)
        return out

    @app.get("/api/documents")
    def documents(
        company: str | None = None, doc_type: str | None = None, tag: str | None = None, limit: int = 100, offset: int = 0,
        name: str = "", year: str | None = None, fy: str | None = None, date_from: str | None = None, date_to: str | None = None,
        folder: int | None = None, within: str | None = None, kind: str | None = None, scanned: bool | None = None,
        sort: str = "added",
    ) -> dict[str, Any]:
        with db() as vault:
            given = library_filters(vault, company, {"doc_type": doc_type, "tag": tag, "name": name, "year": year, "fy": fy,
                                                     "date_from": date_from, "date_to": date_to, "folder_id": folder,
                                                     "within": within, "kind": kind, "scanned": scanned})
            return library.list_documents(vault, limit=min(limit, 500), offset=offset, sort=sort, **given)

    @app.get("/api/documents/facets")
    def document_facets(
        company: str | None = None, doc_type: str | None = None, tag: str | None = None, name: str = "", year: str | None = None,
        fy: str | None = None, date_from: str | None = None, date_to: str | None = None, folder: int | None = None,
        within: str | None = None, kind: str | None = None, scanned: bool | None = None,
    ) -> dict[str, Any]:
        with db() as vault:
            given = library_filters(vault, company, {"doc_type": doc_type, "tag": tag, "name": name, "year": year, "fy": fy,
                                                     "date_from": date_from, "date_to": date_to, "folder_id": folder,
                                                     "within": within, "kind": kind, "scanned": scanned})
            return library.facets(vault, library.Filters(**given))

    @app.post("/api/documents")
    async def upload(
        files: list[UploadFile] = File(...),
        company: str | None = Form(None),
        doc_type: str | None = Form(None),
        tags: str | None = Form(None),
        note: str | None = Form(None),
        paths: list[str] | None = Form(None),
        modified: list[str] | None = Form(None),
    ) -> dict[str, Any]:
        """Files from her computer. `company` "auto" files each under the client it points to. `paths` and `modified`, one
        per file when given, are where each sat in a folder she dropped ("Acme/2024-25/notice.pdf") and when it last changed."""
        if doc_type and doc_type not in DOC_TYPES:
            raise Invalid(f"Unknown document type {doc_type!r}.")
        tag_list = [t for t in (tags or "").split(",") if t.strip()]
        auto = company == "auto"
        results = []
        with tempfile.TemporaryDirectory() as tmp:
            for index, upload_file in enumerate(files):
                name = Path(upload_file.filename or "upload").name
                folder = Path(tmp) / str(index)
                folder.mkdir()
                path = folder / name
                with path.open("wb") as out:
                    shutil.copyfileobj(upload_file.file, out)
                relative = (paths[index] if paths and index < len(paths) else "").replace("\\", "/").strip("/")
                when = modified[index] if modified and index < len(modified) and modified[index] else None
                inside = "/".join(relative.split("/")[:-1]) if "/" in relative else None
                origin = library.Origin(folder=inside, modified=when) if inside or when else None
                try:
                    with db() as vault:
                        company_id = None if auto else company_id_of(vault, company)
                        results.append(library.add_document(vault, core, path, company_id, doc_type or None, tag_list, note,
                                                            origin=origin, work_out_client=auto))
                except CsDeskError as exc:
                    results.append({"file": relative or name, "error": str(exc)})
        return {"results": results}

    @app.get("/api/documents/{document_id}")
    def get_document(document_id: int) -> dict[str, Any]:
        with db() as vault:
            out = library.document(vault, document_id)
            out["works"] = workbook.works_of_document(vault, document_id)
            out["notes"] = workbook.notes_on(vault, "document", str(document_id))
            return out

    @app.patch("/api/documents/{document_id}")
    def change_document(document_id: int, changes: DocumentChanges) -> dict[str, Any]:
        with db() as vault:
            library.document(vault, document_id, brief=True)
            if changes.doc_type is not None:
                if changes.doc_type not in DOC_TYPES:
                    raise Invalid(f"Unknown document type {changes.doc_type!r}.")
                vault.conn.execute("UPDATE documents SET doc_type = ? WHERE id = ?", (changes.doc_type, document_id))
            if changes.company is not None:
                vault.conn.execute("UPDATE documents SET company_id = ? WHERE id = ?", (company_id_of(vault, changes.company) if changes.company else None, document_id))
                editing._set_meta(vault, document_id, "client_why", "set by her")
            if changes.note is not None:
                vault.conn.execute("UPDATE documents SET note = ? WHERE id = ?", (changes.note or None, document_id))
            if changes.title is not None:
                vault.conn.execute(
                    "INSERT INTO doc_meta (document_id, title) VALUES (?, ?) ON CONFLICT(document_id) DO UPDATE SET title = excluded.title",
                    (document_id, changes.title.strip() or None),
                )
            details = {k: v for k, v in changes.model_dump(exclude_unset=True).items() if k in editing.DOC_OVERRIDES}
            if details:
                editing.set_document_details(vault, document_id, details)
            vault.log("change document", {"id": document_id, **changes.model_dump(exclude_none=True)})
            if changes.doc_type is not None:
                library.index_document(vault, document_id, keep_type=True, home=core.home)
            return library.document(vault, document_id)

    @app.get("/api/documents/{document_id}/pages/{page_no}")
    def page(document_id: int, page_no: int) -> dict[str, Any]:
        with db() as vault:
            return library.page_text(vault, document_id, page_no)

    @app.put("/api/documents/{document_id}/pages/{page_no}")
    def edit_page(document_id: int, page_no: int, body: PageTextIn) -> dict[str, Any]:
        with db() as vault:
            return editing.edit_page(vault, core.home, document_id, page_no, body.text)

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: int) -> dict[str, Any]:
        with db() as vault:
            return editing.delete_document(vault, core.home, document_id)

    @app.get("/api/documents/{document_id}/pages/{page_no}/image")
    def page_image(document_id: int, page_no: int) -> Response:
        # Rendered once, then served from the cache folder: documents never change once stored.
        cached = core.home / "cache" / "pages" / str(document_id) / f"{page_no}.jpg"
        headers = {"Cache-Control": "private, max-age=86400"}
        if cached.is_file():
            return FileResponse(cached, media_type="image/jpeg", headers=headers)
        with db() as vault:
            doc = library.document(vault, document_id)
        if not 1 <= page_no <= doc["pages"]:
            raise NotFound(f"Document {document_id} has no page {page_no}.")
        image, _ = render_page(core.home / doc["stored_path"], page_no)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(image)
        return Response(image, media_type="image/jpeg", headers=headers)

    @app.get("/api/documents/{document_id}/file")
    def original(document_id: int, download: bool = False) -> FileResponse:
        with db() as vault:
            doc = library.document(vault, document_id)
        path = (core.home / doc["stored_path"]).resolve()
        if not path.is_relative_to(core.home.resolve()) or not path.is_file():
            raise NotFound("The stored file is missing from the data folder.")
        return FileResponse(
            path,
            media_type=doc["media_type"] or "application/octet-stream",
            filename=doc["original_name"],
            content_disposition_type="attachment" if download else "inline",
        )

    @app.get("/api/documents/{document_id}/search")
    def search_document(document_id: int, q: str) -> dict[str, Any]:
        with db() as vault:
            return library.search_in_document(vault, document_id, q)

    @app.post("/api/documents/{document_id}/tags")
    def tags(document_id: int, changes: TagChanges) -> dict[str, Any]:
        with db() as vault:
            for name in changes.add:
                library.add_tag(vault, document_id, name, by="her")
            for name in changes.remove:
                library.remove_tag(vault, document_id, name)
            return library.document(vault, document_id)

    @app.put("/api/documents/{document_id}/summary")
    def write_summary(document_id: int, summary: Summary) -> dict[str, Any]:
        if not summary.summary.strip():
            raise Invalid("Write a summary first.")
        with db() as vault:
            library.save_summary(vault, document_id, summary.summary, "her", summary.key_points)
            return library.document(vault, document_id)

    @app.post("/api/documents/{document_id}/summarise")
    def summarise(document_id: int) -> dict[str, Any]:
        with db() as vault:
            library.document(vault, document_id, brief=True)
            library.queue(vault, document_id, "summary")
            return {"queued": True, "ai": ai_status()}

    @app.post("/api/documents/{document_id}/reindex")
    def reindex(document_id: int) -> dict[str, Any]:
        with db() as vault:
            library.index_document(vault, document_id, keep_type=True, home=core.home)
            return library.document(vault, document_id)

    @app.post("/api/inbox")
    def inbox_now() -> dict[str, Any]:
        watcher = InboxWatcher(settings)
        watcher.sizes = {p.name: p.stat().st_size for p in core.inbox_dir.iterdir() if p.is_file()}
        return {"results": watcher.poll()}

    # ------------------------------------------------------------ search

    @app.get("/api/search")
    def search(q: str, company: str | None = None, doc_type: str | None = None, tag: str | None = None, limit: int = 30) -> dict[str, Any]:
        with db() as vault:
            return library.search(vault, q, company_id_of(vault, company), doc_type, tag, min(limit, 100))

    @app.get("/api/tags")
    def all_tags() -> dict[str, Any]:
        with db() as vault:
            return {"tags": library.all_tags(vault)}

    # -------------------------------------------------------- precedents

    @app.get("/api/precedents")
    def precedent_search(
        q: str = "",
        section: str | None = None,
        topic: str | None = None,
        kind: str | None = None,
        min_crore: float | None = None,
        max_crore: float | None = None,
        with_statement: bool = False,
        limit: int = 40,
    ) -> dict[str, Any]:
        with db() as vault:
            return precedents.search(
                vault, q, section or None, topic or None, kind or None,
                round(min_crore * 10_000_000) if min_crore is not None else None,
                round(max_crore * 10_000_000) if max_crore is not None else None,
                with_statement, min(limit, 200),
            )

    @app.get("/api/precedents/topics")
    def precedent_topics() -> dict[str, Any]:
        with db() as vault:
            return {"topics": precedents.topics(vault)}

    @app.get("/api/precedents/{clause_id}")
    def precedent(clause_id: int) -> dict[str, Any]:
        with db() as vault:
            return precedents.get(vault, clause_id)

    # ------------------------------------------------------------ checks

    @app.patch("/api/precedents/{clause_id}")
    def edit_precedent(clause_id: int, changes: ClauseChanges) -> dict[str, Any]:
        with db() as vault:
            return editing.edit_clause(vault, clause_id, changes.model_dump(exclude_unset=True))

    @app.delete("/api/precedents/{clause_id}")
    def delete_precedent(clause_id: int) -> dict[str, Any]:
        with db() as vault:
            return editing.delete_clause(vault, clause_id)

    @app.put("/api/tags/{name}")
    def rename_tag(name: str, body: NameIn) -> dict[str, Any]:
        with db() as vault:
            return editing.rename_tag(vault, name, body.name or "")

    @app.delete("/api/tags/{name}")
    def delete_tag(name: str) -> dict[str, Any]:
        with db() as vault:
            return editing.delete_tag(vault, name)

    @app.post("/api/checks/loan-limits")
    def loan_limits(figures: LoanFigures) -> dict[str, Any]:
        company_class = None
        if figures.company:
            with db() as vault:
                company_class = vault.company_row(vault.resolve_company(figures.company))["company_class"]
        data = figures.model_dump(exclude={"company"})
        return checks.loans_and_borrowing(**data, company_class=company_class)

    # ----------------------------------------- everything, entities, money

    @app.get("/api/everything")
    def everything_search(q: str) -> dict[str, Any]:
        with db() as vault:
            return everything.search_all(vault, q)

    @app.get("/api/entities")
    def entity_list(kind: str | None = None, q: str = "", limit: int = 200) -> dict[str, Any]:
        with db() as vault:
            return entities.browse(vault, kind or None, q, min(limit, 1000))

    @app.get("/api/entities/{kind}/{key}")
    def entity_dossier(kind: str, key: str) -> dict[str, Any]:
        with db() as vault:
            return entities.dossier(vault, kind, key)

    @app.put("/api/entities/{kind}/{key}")
    def entity_name(kind: str, key: str, body: NameIn) -> dict[str, Any]:
        with db() as vault:
            return editing.rename_entity(vault, kind, key, body.name)

    @app.delete("/api/entities/{kind}/{key}")
    def entity_hide(kind: str, key: str) -> dict[str, Any]:
        with db() as vault:
            return editing.hide_key(vault, kind, key, _entity_value(vault, kind, key))

    @app.post("/api/facts/hide")
    def fact_hide(body: FactHide) -> dict[str, Any]:
        with db() as vault:
            return editing.hide_fact(vault, body.kind, body.value, body.document_id)

    @app.get("/api/facts/hidden")
    def facts_hidden() -> dict[str, Any]:
        with db() as vault:
            return {"hidden": editing.hidden_list(vault)}

    @app.delete("/api/facts/hidden/{hidden_id}")
    def fact_unhide(hidden_id: int) -> dict[str, Any]:
        with db() as vault:
            return editing.unhide(vault, hidden_id, core.home)

    @app.get("/api/gstin/{gstin}")
    def gstin(gstin: str) -> dict[str, Any]:
        return entities.gstin_info(gstin)

    @app.get("/api/financials")
    def financial_list(company: str | None = None) -> dict[str, Any]:
        with db() as vault:
            return {"statements": finance.listing(vault, company_id_of(vault, company))}

    @app.get("/api/financials/{financial_id}")
    def financial_analysis(financial_id: int) -> dict[str, Any]:
        with db() as vault:
            return finance.analysis(vault, financial_id)

    @app.put("/api/financials/{financial_id}/lines/{key}")
    def financial_line(financial_id: int, key: str, figures: LineFigures) -> dict[str, Any]:
        with db() as vault:
            return finance.correct(vault, financial_id, key, figures.current, figures.previous)

    @app.put("/api/financials/{financial_id}/facts")
    def financial_facts(financial_id: int, facts: StatementFacts) -> dict[str, Any]:
        with db() as vault:
            return finance.set_facts(vault, financial_id, facts.model_dump(exclude_unset=True))

    @app.patch("/api/financials/{financial_id}")
    def financial_header(financial_id: int, body: StatementHeader) -> dict[str, Any]:
        with db() as vault:
            return finance.edit_header(vault, financial_id, body.model_dump(exclude_unset=True))

    @app.delete("/api/financials/{financial_id}")
    def financial_delete(financial_id: int) -> dict[str, Any]:
        with db() as vault:
            return finance.delete(vault, financial_id)

    @app.put("/api/financials/{financial_id}/company")
    def financial_company(financial_id: int, link: CompanyLink) -> dict[str, Any]:
        with db() as vault:
            return finance.link_company(vault, financial_id, company_id_of(vault, link.company))

    @app.get("/api/financials/{financial_id}/s186")
    def financial_s186(financial_id: int) -> dict[str, Any]:
        with db() as vault:
            return finance.s186_inputs(vault, financial_id)

    @app.post("/api/documents/{document_id}/financials")
    def read_financials(document_id: int) -> dict[str, Any]:
        with db() as vault:
            library.document(vault, document_id, brief=True)
            ids = finance.extract(vault, document_id, core.home)
            if not ids:
                raise Invalid("No balance sheet or statement of profit and loss was found in this document.")
            return {"statements": ids}

    # ------------------------------------------------ work, notes, checks

    @app.get("/api/work/kinds")
    def work_kinds() -> dict[str, Any]:
        return {"kinds": workbook.kinds()}

    @app.get("/api/work")
    def work_list(status: str | None = None, company: str | None = None, q: str = "") -> dict[str, Any]:
        with db() as vault:
            return {"works": workbook.list_works(vault, status or None, company_id_of(vault, company), q)}

    @app.post("/api/work")
    def work_create(body: WorkIn) -> dict[str, Any]:
        with db() as vault:
            return workbook.create_work(vault, body.title, body.kind, company_id_of(vault, body.company), body.due_on, body.meeting_date, body.fy)

    @app.get("/api/work/{work_id}")
    def work_get(work_id: int) -> dict[str, Any]:
        with db() as vault:
            return workbook.work(vault, work_id)

    @app.patch("/api/work/{work_id}")
    def work_change(work_id: int, body: WorkChange) -> dict[str, Any]:
        with db() as vault:
            fields = body.model_dump(exclude_unset=True)
            if "company" in fields:
                fields["company_id"] = company_id_of(vault, fields.pop("company"))
            return workbook.change_work(vault, work_id, **fields)

    @app.delete("/api/work/{work_id}")
    def work_delete(work_id: int) -> dict[str, Any]:
        with db() as vault:
            return workbook.delete_work(vault, work_id)

    @app.put("/api/work/{work_id}/checklist")
    def work_checklist(work_id: int, body: ChecklistIn) -> dict[str, Any]:
        with db() as vault:
            return workbook.set_checklist(vault, work_id, body.checklist)

    @app.post("/api/work/{work_id}/documents/{document_id}")
    def work_attach(work_id: int, document_id: int) -> dict[str, Any]:
        with db() as vault:
            return workbook.attach(vault, work_id, document_id)

    @app.delete("/api/work/{work_id}/documents/{document_id}")
    def work_detach(work_id: int, document_id: int) -> dict[str, Any]:
        with db() as vault:
            return workbook.detach(vault, work_id, document_id)

    @app.get("/api/notes")
    def note_list(target_kind: str | None = None, target: str | None = None, q: str = "") -> dict[str, Any]:
        with db() as vault:
            if target_kind:
                return {"notes": workbook.notes_on(vault, target_kind, target or "")}
            return {"notes": workbook.search_notes(vault, q)}

    @app.post("/api/notes")
    def note_add(body: NoteIn) -> dict[str, Any]:
        with db() as vault:
            return workbook.add_note(vault, body.text, body.target_kind, body.target, body.pinned)

    @app.patch("/api/notes/{note_id}")
    def note_change(note_id: int, body: NoteChange) -> dict[str, Any]:
        with db() as vault:
            return workbook.change_note(vault, note_id, body.text, body.pinned)

    @app.delete("/api/notes/{note_id}")
    def note_delete(note_id: int) -> dict[str, Any]:
        with db() as vault:
            workbook.delete_note(vault, note_id)
            return {"deleted": note_id}

    @app.get("/api/documents/{document_id}/analysis")
    def document_analysis(document_id: int) -> dict[str, Any]:
        with db() as vault:
            library.document(vault, document_id, brief=True)
            return {"analyses": analysis.for_document(vault, document_id)}

    @app.post("/api/documents/{document_id}/analyse")
    def document_analyse(document_id: int) -> dict[str, Any]:
        with db() as vault:
            library.document(vault, document_id, brief=True)
            return {"analyses": analysis.run_all(vault, document_id)}

    @app.get("/api/insights")
    def insights() -> dict[str, Any]:
        with db() as vault:
            return {"purposes": analysis.overview(vault)}

    @app.get("/api/insights/{kind}")
    def insight_register(kind: str, q: str = "", company: str | None = None, format: str = "json") -> Any:
        with db() as vault:
            out = analysis.register(vault, kind, q, company_id_of(vault, company))
        if format == "csv":
            import csv
            import io

            buffer = io.StringIO()
            keys = [c["key"] for c in out["columns"]] + ["document", "page", "context"]
            writer = csv.writer(buffer)
            writer.writerow([c["label"] for c in out["columns"]] + ["Document", "Page", "Words around it"])
            for item in out["items"]:
                writer.writerow(["; ".join(map(str, v)) if isinstance(v := item.get(k), list) else ("" if v is None else v) for k in keys])
            return Response(buffer.getvalue().encode("utf-8-sig"), media_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="aagam-{kind}.csv"'})
        return out

    @app.get("/api/documents/{document_id}/check")
    def notice_check(document_id: int) -> dict[str, Any]:
        with db() as vault:
            return review.check_notice(vault, document_id)

    # ---------------------------------------------------- the company file

    @app.get("/api/records/schema")
    def record_schema() -> dict[str, Any]:
        return {"entities": {name: _fields(spec) for name, spec in ENTITIES.items()}}

    @app.get("/api/companies/{company_id}/file")
    def company_file(company_id: int) -> dict[str, Any]:
        with db() as vault:
            out = vault.company_file(company_id, include_sources=True)
            count = lambda sql: vault.conn.execute(sql, (company_id,)).fetchone()[0]  # noqa: E731
            out["library"] = {
                "documents": count("SELECT COUNT(*) FROM documents WHERE company_id = ?"),
                "works": count("SELECT COUNT(*) FROM works WHERE company_id = ? AND status IN ('open', 'waiting')"),
                "financials": vault._rows("SELECT id, basis, period_end FROM financials WHERE company_id = ? ORDER BY period_end DESC", (company_id,)),
            }
            today = date.today()
            out["due"] = [item.as_dict(today) for item in upcoming(vault, today, company_id, 90)]
            return out

    @app.get("/api/parties")
    def party_list(q: str = "") -> dict[str, Any]:
        with db() as vault:
            if q.strip():
                return {"parties": vault.find_parties(q)}
            rows = vault._rows("SELECT id, kind, name, din, pan, org_type, frn, membership_no FROM parties ORDER BY name LIMIT 200")
            for r in rows:
                r["pan"] = mask(r["pan"])
            return {"parties": rows}

    @app.get("/api/records/{entity}/{record_id}")
    def record_get(entity: str, record_id: int) -> dict[str, Any]:
        spec = _spec(entity)
        with db() as vault:
            row = vault._get(spec.table, record_id)
            if row is None:
                raise NotFound(f"There is no {entity.replace('_', ' ')} with id {record_id}.")
            out = {k: (mask(v) if k in spec.sensitive else v) for k, v in dict(row).items()}
            out["sources"] = vault.latest_sources(entity, record_id)
            return out

    @app.post("/api/records/{entity}")
    def record_create(entity: str, body: RecordIn) -> dict[str, Any]:
        _spec(entity)
        with db() as vault:
            record_id = vault.save(entity, _clean_record(body.data), Source("user", "her", note="entered in the AAGAM window"))
        return record_get(entity, record_id)

    @app.patch("/api/records/{entity}/{record_id}")
    def record_change(entity: str, record_id: int, body: RecordIn) -> dict[str, Any]:
        _spec(entity)
        with db() as vault:
            vault.save(entity, _clean_record(body.data), Source("user", "her", note="changed in the AAGAM window"), record_id)
        return record_get(entity, record_id)

    @app.get("/api/records/{entity}/{record_id}/dependents")
    def record_dependents(entity: str, record_id: int) -> dict[str, Any]:
        _spec(entity)
        with db() as vault:
            return vault.dependents(entity, record_id)

    @app.delete("/api/records/{entity}/{record_id}")
    def record_delete(entity: str, record_id: int) -> dict[str, Any]:
        _spec(entity)
        with db() as vault:
            if entity == "company":
                editing.keep_notes_on_company(vault, record_id)
            return vault.delete(entity, record_id)

    # -------------------------------------------------------- interface

    @app.get("/{path:path}", include_in_schema=False)
    def interface(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404, "No such API.")
        target = (STATIC / path).resolve()
        if path and target.is_file() and target.is_relative_to(STATIC.resolve()):
            return FileResponse(target)
        index = STATIC / "index.html"
        if not index.is_file():
            return Response(
                "<h1>AAGAM</h1><p>The interface hasn't been built yet. Run <code>aagam build-ui</code>.</p>",
                media_type="text/html",
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def wait_until_up(port: int, timeout: float = 20) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False
