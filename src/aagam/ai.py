"""Local AI through Ollama, for the routine reading: a summary and suggested tags for each document.

It runs on her laptop, so documents don't leave it. Small local models are
good at summarising and poor at legal judgment, so this is all they do here.
Drafting, checking and legal reading go to Claude Desktop, which uses the
same library through the MCP tools.

Nothing depends on it. If Ollama isn't installed or running, jobs wait in the
queue and everything else works. Whatever it writes is labelled with the
model's name, and it never replaces a summary she wrote.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any

from csdesk.documents.intake import DOC_TYPES
from csdesk.errors import Invalid

from . import library
from .config import AagamSettings
from .db import open_db

log = logging.getLogger("aagam.ai")
MAX_CHARS = 20_000

SYSTEM = (
    "You read documents for a Company Secretary in India and write short, accurate notes about them. "
    "Use only what the document says. Never invent names, amounts, dates or section numbers; if something "
    "isn't in the text, leave it out. Write in plain English. For a notice or minutes, say what business is "
    "transacted (each resolution, and whether it is special or ordinary, with its amounts and sections), "
    "not the voting or attendance procedure."
)
SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3 to 5 sentences: what the document is, who it concerns, what it decides or records"},
        "key_points": {"type": "array", "items": {"type": "string"}, "description": "up to 6 facts worth noting: amounts, dates, sections, approvals"},
        "document_type": {"type": "string", "enum": list(DOC_TYPES)},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "up to 5 short lowercase topic tags"},
    },
    "required": ["summary", "key_points", "document_type", "tags"],
}


class LocalAI:
    def __init__(self, url: str, model: str, context: int = 8192, timeout: float = 600) -> None:
        self.url, self.model, self.context, self.timeout = url.rstrip("/"), model, context, timeout

    @classmethod
    def from_settings(cls, settings: AagamSettings) -> LocalAI:
        return cls(settings.local_ai_url, settings.local_ai_model, settings.local_ai_context)

    def _request(self, path: str, body: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.url}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
        )
        with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
            return json.load(response)

    def status(self) -> dict[str, Any]:
        try:
            models = [m["name"] for m in self._request("/api/tags", timeout=3).get("models", [])]
        except (OSError, ValueError):
            return {
                "running": False,
                "model": self.model,
                "model_installed": False,
                "message": "Local AI isn't running. Install Ollama from ollama.com and start it; summaries wait until then.",
            }
        installed = self.model in models or f"{self.model}:latest" in models
        return {
            "running": True,
            "model": self.model,
            "model_installed": installed,
            "models": models,
            "message": "Ready." if installed else f"Ollama is running but the model isn't installed: run `ollama pull {self.model}`.",
        }

    def chat_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            "think": False,
            "options": {"temperature": 0.1, "num_ctx": self.context},
            "keep_alive": "10m",
        }
        try:
            reply = self._request("/api/chat", body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if "think" in detail.lower():
                body.pop("think")  # a model without a thinking switch
                reply = self._request("/api/chat", body)
            else:
                raise Invalid(f"Local AI refused the request ({exc.code}): {detail[:200]}") from exc
        content = reply.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise Invalid(f"Local AI didn't answer in the expected form: {content[:200]!r}") from exc


def prompt_for(vault: Any, document_id: int) -> str:
    doc = library.document(vault, document_id, brief=True)
    name = vault.conn.execute("SELECT original_name FROM documents WHERE id = ?", (document_id,)).fetchone()[0]
    parts, used = [], 0
    for page_no, text in library.pages_of(vault, document_id):
        if not text.strip():
            continue
        chunk = f"\n--- page {page_no} ---\n{text}"
        if used + len(chunk) > MAX_CHARS:
            parts.append(f"\n--- page {page_no} (rest of the document not shown) ---\n{text[: max(0, MAX_CHARS - used)]}")
            break
        parts.append(chunk)
        used += len(chunk)
    return (
        f"File name: {name}\nType so far: {DOC_TYPES.get(doc['doc_type'], doc['doc_type'])}\n\n"
        f"Write the notes for this document.\n{''.join(parts)}"
    )


def summarise(vault: Any, ai: LocalAI, document_id: int) -> dict[str, Any]:
    if not any(text.strip() for _, text in library.pages_of(vault, document_id)):
        return {"skipped": "No text to read (a scan): ask Claude Desktop to read it."}
    answer = ai.chat_json(SYSTEM, prompt_for(vault, document_id), SUMMARY_SCHEMA)
    summary = str(answer.get("summary", "")).strip()
    if not summary:
        raise Invalid("Local AI returned an empty summary.")
    points = [str(p).strip() for p in answer.get("key_points", []) if str(p).strip()][:6]
    by = f"local:{ai.model}"
    library.save_summary(vault, document_id, summary, by, points)
    suggestions = [" ".join(str(tag).lower().split())[:40] for tag in answer.get("tags", [])[:5]]
    library.suggest_tags(vault, document_id, [s for s in suggestions if s])
    current = vault.conn.execute("SELECT doc_type FROM documents WHERE id = ?", (document_id,)).fetchone()[0]
    suggested = answer.get("document_type")
    if current == "other" and suggested in DOC_TYPES and suggested != "other":
        vault.conn.execute("UPDATE documents SET doc_type = ? WHERE id = ?", (suggested, document_id))
    return {"summary": summary, "key_points": points, "by": by}


def run_queue(settings: AagamSettings, ai: LocalAI, limit: int | None = None) -> int:
    """Work through queued jobs, one at a time; returns how many were done."""
    done = 0
    while limit is None or done < limit:
        with open_db(settings.core.db_path, actor="local-ai") as vault:
            job = vault.conn.execute("SELECT * FROM ai_jobs WHERE status = 'queued' AND task = 'summary' ORDER BY id LIMIT 1").fetchone()
            if job is None:
                return done
            vault.conn.execute(
                "UPDATE ai_jobs SET status = 'running', started_at = datetime('now'), provider = 'ollama', model = ? WHERE id = ?",
                (ai.model, job["id"]),
            )
        status, note = "done", None
        try:
            with open_db(settings.core.db_path, actor="local-ai") as vault:
                result = summarise(vault, ai, job["document_id"]) if job["task"] == "summary" else {"skipped": "unknown task"}
            if "skipped" in result:
                status, note = "skipped", result["skipped"]
        except Exception as exc:  # one bad document mustn't stop the queue
            log.warning("AI job %s failed: %s", job["id"], exc)
            status, note = "failed", str(exc)[:500]
        with open_db(settings.core.db_path, actor="local-ai") as vault:
            vault.conn.execute(
                "UPDATE ai_jobs SET status = ?, note = ?, finished_at = datetime('now') WHERE id = ?", (status, note, job["id"])
            )
        done += 1
    return done


class Worker(threading.Thread):
    """Runs queued AI jobs in the background while the AAGAM window is open."""

    def __init__(self, settings: AagamSettings, interval: float = 15) -> None:
        super().__init__(name="aagam-local-ai", daemon=True)
        self.settings, self.interval = settings, interval
        self.ai = LocalAI.from_settings(settings)
        self.stopping = threading.Event()
        self.last_status: dict[str, Any] = {}

    def run(self) -> None:
        while not self.stopping.is_set():
            self.last_status = self.ai.status()
            if self.last_status.get("model_installed"):
                try:
                    run_queue(self.settings, self.ai, limit=1)
                    if self._pending():
                        continue
                except Exception:  # keep the worker alive whatever happens
                    log.exception("local AI worker")
            self.stopping.wait(self.interval)

    def _pending(self) -> bool:
        with open_db(self.settings.core.db_path, actor="local-ai") as vault:
            return vault.conn.execute("SELECT 1 FROM ai_jobs WHERE status = 'queued' AND task = 'summary' LIMIT 1").fetchone() is not None

    def stop(self) -> None:
        self.stopping.set()


def reset_stuck_jobs(settings: AagamSettings) -> None:
    """Jobs left 'running' when AAGAM was closed go back in the queue."""
    with open_db(settings.core.db_path, actor="local-ai") as vault:
        vault.conn.execute("UPDATE ai_jobs SET status = 'queued', started_at = NULL WHERE status = 'running'")
