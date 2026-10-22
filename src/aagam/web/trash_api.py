"""The Trash: the web API (trash.py does the work)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import trash
from ..config import AagamSettings


class LooseFile(BaseModel):
    name: str


class DocumentIds(BaseModel):
    ids: list[int]


def router(settings: AagamSettings, db: Callable[..., Any]) -> APIRouter:
    api = APIRouter()
    core = settings.core

    @api.get("/api/trash")
    def trash_list() -> dict[str, Any]:
        with db() as vault:
            return trash.list_trash(vault, core.home)

    @api.post("/api/trash/empty")
    def trash_empty() -> dict[str, Any]:
        with db() as vault:
            return trash.empty(vault, core.home)

    # The bin folder's files from before the Trash existed. These routes come before /api/trash/{trash_id}.
    @api.post("/api/trash/loose/restore")
    def loose_restore(body: LooseFile) -> dict[str, Any]:
        with db() as vault:
            return trash.restore_loose(vault, core, body.name)

    @api.delete("/api/trash/loose")
    def loose_delete(name: str) -> dict[str, Any]:
        with db() as vault:
            return trash.delete_loose(vault, core.home, name)

    @api.post("/api/trash/{trash_id}/restore")
    def trash_restore(trash_id: int) -> dict[str, Any]:
        with db() as vault:
            return trash.restore(vault, core, trash_id)

    @api.delete("/api/trash/{trash_id}")
    def trash_delete(trash_id: int) -> dict[str, Any]:
        with db() as vault:
            return trash.delete_forever(vault, core.home, trash_id)

    @api.post("/api/documents/trash")
    def documents_to_trash(body: DocumentIds) -> dict[str, Any]:
        with db() as vault:
            return trash.trash_documents(vault, core.home, body.ids)

    return api


def helpers(settings: AagamSettings) -> list[threading.Thread]:
    """Background threads to start with the server: none for the Trash."""
    return []
