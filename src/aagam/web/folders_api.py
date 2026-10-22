"""Folders brought into the library: the web API and the background worker that reads them (folders.py)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from csdesk.errors import Invalid

from .. import folders
from ..config import AagamSettings
from ..db import open_db


class PathIn(BaseModel):
    path: str


class FolderIn(BaseModel):
    path: str
    company: str | None = "auto"  # "auto": worked out per file; "none": no client's; else a client's id, CIN or name
    doc_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    precedent: bool = False
    watch: bool = False


class FolderChange(BaseModel):
    watch: bool | None = None
    company: str | None = None
    doc_type: str | None = None
    tags: list[str] | None = None
    precedent: bool | None = None


def _client(vault: Any, company: str | None) -> tuple[str, int | None]:
    """The client choice as (client_mode, company_id)."""
    text = (company or "auto").strip()
    if text.lower() in ("auto", ""):
        return "auto", None
    if text.lower() == "none":
        return "none", None
    return "one", vault.resolve_company(text)


def router(settings: AagamSettings, db: Callable[..., Any]) -> APIRouter:
    core = settings.core
    api = APIRouter(prefix="/api/folders")

    @api.get("")
    def folder_list() -> dict[str, Any]:
        with db() as vault:
            return {"folders": folders.listing(vault)}

    @api.post("/preview")
    def folder_preview(body: PathIn) -> dict[str, Any]:
        with db() as vault:
            return folders.preview(vault, core.home, body.path)

    @api.post("/browse")
    def folder_browse() -> dict[str, Any]:
        return {"path": folders.choose_folder()}

    @api.post("")
    def folder_add(body: FolderIn) -> dict[str, Any]:
        with db() as vault:
            client_mode, company_id = _client(vault, body.company)
            return folders.add_folder(vault, core.home, body.path, client_mode, company_id, body.doc_type or None, body.tags,
                                      body.precedent, body.watch)

    @api.get("/{folder_id}")
    def folder_get(folder_id: int) -> dict[str, Any]:
        with db() as vault:
            return folders.get(vault, folder_id, details=True)

    @api.patch("/{folder_id}")
    def folder_change(folder_id: int, body: FolderChange) -> dict[str, Any]:
        given = body.model_dump(exclude_unset=True)
        with db() as vault:
            options: dict[str, Any] = {k: v for k, v in given.items() if k in ("watch", "tags", "precedent") and v is not None}
            if "doc_type" in given:
                options["doc_type"] = given["doc_type"] or None
            if given.get("company") is not None:
                options["client_mode"], options["company_id"] = _client(vault, given["company"])
            return folders.change(vault, folder_id, **options)

    @api.post("/{folder_id}/scan")
    def folder_scan(folder_id: int) -> dict[str, Any]:
        with db() as vault:
            return folders.queue_scan(vault, folder_id)

    @api.post("/{folder_id}/stop")
    def folder_stop(folder_id: int) -> dict[str, Any]:
        with db() as vault:
            return folders.stop(vault, folder_id)

    @api.delete("/{folder_id}")
    def folder_forget(folder_id: int, documents: str = "keep") -> dict[str, Any]:
        if documents not in ("keep", "trash"):
            raise Invalid('Say what happens to its documents: "keep" or "trash".')
        with db() as vault:
            return folders.forget(vault, core.home, folder_id, trash_documents=documents == "trash")

    return api


def helpers(settings: AagamSettings) -> list[threading.Thread]:
    """Background threads to start with the server: the folder reader. Passes a closed AAGAM left running are taken
    up again first."""
    with open_db(settings.core.db_path, actor="folders") as vault:
        folders.reset_dead(vault, "web:")
    return [folders.FolderWorker(settings)]
