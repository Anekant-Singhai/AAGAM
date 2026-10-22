"""Record how she fills a form in the CS Desk browser, so a recipe can be written from it.

She fills the form as she normally would; the recorder watches from the side
over the same Chrome DevTools connection the form filler uses. It never clicks,
types or answers a dialog. It writes, into one folder per recording:

  meta.json      what is being recorded (form, company, person)
  events.jsonl   one line per thing that happened: page snapshots, field changes,
                 button presses, page changes, dialogs and the portal's requests
  screens/       a screenshot at each new step and after each button press
  flow.md        the readable account, and recipe_draft.py, written at the end

Values she types are reduced to their shape and the company-file field they
match before anything is written; passwords, OTPs and captchas are never read.
Requests are logged by method, address and status only: no headers, no bodies,
no query values. That is the part of a proxy like Burp Suite that recipes need,
without a certificate on her laptop or her session cookies in a log.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from playwright.async_api import Browser, Page, Request, async_playwright
from playwright.async_api import Error as PlaywrightError

from ..browser import chrome, session
from ..browser.guard import click_verdict
from ..config import Settings
from ..errors import NotFound
from ..vault import Vault
from .values import Matcher, describe_value

PAGE_SCRIPT = (Path(__file__).parent / "page_script.js").read_text(encoding="utf-8")
BINDING = "__csdeskRecord"
NETWORK_TYPES = frozenset({"document", "xhr", "fetch"})
HEARTBEAT_SECONDS = 2.0


def address(url: str) -> dict[str, Any]:
    """A URL without its query values: scheme, host and path, plus the names of the query parameters."""
    parsed = urlparse(url)
    if parsed.scheme in ("data", "about", "blob", "chrome", "devtools"):
        return {"url": f"{parsed.scheme}:", "query_keys": []}
    keys = sorted({key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    return {"url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "query_keys": keys}


class Recorder:
    def __init__(self, folder: Path, matcher: Matcher) -> None:
        self.folder = folder
        self.events_path = folder / "events.jsonl"
        self.screens = folder / "screens"
        self.screens.mkdir(parents=True, exist_ok=True)
        self.matcher = matcher
        self.seq = 0
        self.step = 0
        self.step_fields: set[str] = set()
        self.step_path: str | None = None
        self.tasks: set[asyncio.Task[Any]] = set()
        self.request_started: dict[Request, float] = {}
        self.shots = 0
        self.closing = False  # set while disconnecting, when Playwright reports every tab as closed

    # ----------------------------------------------------------------- writing

    def emit(self, kind: str, **data: Any) -> dict[str, Any]:
        self.seq += 1
        event = {"seq": self.seq, "t": datetime.now().isoformat(timespec="milliseconds"), "step": self.step, "type": kind, **data}
        with self.events_path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def later(self, coro: Any) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def screenshot(self, page: Page, label: str, delay: float = 1.2) -> None:
        await asyncio.sleep(delay)
        if page.is_closed() or self.closing:
            return
        self.shots += 1
        name = f"{self.shots:03d}-step{self.step}-{label}.png"
        try:
            await page.screenshot(path=str(self.screens / name), full_page=True, timeout=8000)
        except PlaywrightError:
            self.emit("note", text=f"No screenshot ({label}): the page may be showing a dialog box.")
            return
        self.emit("screenshot", file=f"screens/{name}", label=label, page_url=address(page.url)["url"])

    # --------------------------------------------------------------- steps

    def _new_step(self, reason: str, page: Page | None) -> None:
        self.step += 1
        self.step_fields = set()
        self.emit("step", reason=reason)
        if page is not None:
            self.later(self.screenshot(page, "step-start"))

    def on_navigation(self, page: Page, url: str) -> None:
        path = address(url)["url"]
        if path == self.step_path:
            return
        self.step_path = path
        self._new_step("new page", page)
        self.emit("navigate", **address(url))

    # ------------------------------------------------------- page reports

    def on_binding(self, source: dict[str, Any], payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        page: Page | None = source.get("page")
        page_url = address(page.url)["url"] if page is not None else ""
        kind = payload.get("type")
        frame = {"page_url": page_url, "in_frame": not payload.get("top", True), "frame_url": address(str(payload.get("url", "")))["url"]}
        if kind == "snapshot":
            fields = payload.get("fields") or []
            if not fields:
                return  # a page or frame with nothing to fill (a blank tab, a banner) says nothing about the form
            keys = {f"{frame['frame_url']}|{f.get('selector')}" for f in fields}
            if self.step_fields and len(keys & self.step_fields) < len(self.step_fields) / 2:
                self._new_step("the fields on the page changed", page)
            if self.step == 0:
                self._new_step("recording started", page)
            self.step_fields |= keys
            self.emit(
                "snapshot",
                reason=payload.get("reason"),
                heading=payload.get("heading", ""),
                title=payload.get("title", ""),
                fields=fields,
                buttons=payload.get("buttons") or [],
                **frame,
            )
        elif kind == "change":
            field = payload.get("field") or {}
            self.emit("change", field=field, value=describe_value(payload.get("value") or {}, self.matcher), **frame)
        elif kind == "click":
            verdict, decided_by = click_verdict(*(payload.get("names") or [payload.get("name")]))
            self.emit(
                "click",
                name=payload.get("name", ""),
                tag=payload.get("tag"),
                role=payload.get("role"),
                selector=payload.get("selector"),
                href=payload.get("href"),
                guard=verdict,
                decided_by=decided_by,
                **frame,
            )
            if page is not None:
                self.later(self.screenshot(page, "after-click", delay=1.5))

    # ---------------------------------------------------------- browser side

    def watch_page(self, page: Page) -> None:
        page.on("dialog", lambda dialog: self.emit("dialog", dialog_type=dialog.type, message=dialog.message[:300], page_url=address(page.url)["url"]))
        page.on("framenavigated", lambda frame: self.on_navigation(page, frame.url) if frame == page.main_frame else None)
        page.on("close", lambda _: None if self.closing else self.emit("tab_closed", page_url=address(page.url)["url"]))

    def on_request(self, request: Request) -> None:
        if request.resource_type in NETWORK_TYPES:
            self.request_started[request] = time.monotonic()

    async def on_request_done(self, request: Request, failed: bool = False) -> None:
        started = self.request_started.pop(request, None)
        if started is None:
            return
        status = None
        if not failed:
            with contextlib.suppress(PlaywrightError):
                response = await request.response()
                status = response.status if response else None
        self.emit(
            "request",
            method=request.method,
            resource_type=request.resource_type,
            status=status,
            failed=failed,
            ms=round((time.monotonic() - started) * 1000),
            **address(request.url),
        )


async def run(settings: Settings, folder: Path, stop: asyncio.Event | None = None) -> dict[str, Any]:
    """Record until `stop` is set, a STOP file appears in the folder, the browser closes, or time runs out."""
    from .draft import build

    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    if chrome.debug_info(settings.cdp_port) is None:
        raise NotFound("The CS Desk browser window isn't open. Open it and log in first, then start the recording.")
    with Vault.open(settings.db_path, actor="recorder") as vault:
        matcher = Matcher.from_vault(vault, meta.get("company_id"), meta.get("party_id"))
    recorder = Recorder(folder, matcher)
    deadline = time.monotonic() + 60 * float(meta.get("max_minutes", 120))
    stop_file = folder / "STOP"
    reason = "asked to stop"

    async with async_playwright() as playwright:
        browser: Browser = await session.connect(playwright, settings)
        context = browser.contexts[0]
        await context.expose_binding(BINDING, recorder.on_binding)
        await context.add_init_script(PAGE_SCRIPT)
        context.on("page", recorder.watch_page)
        context.on("request", recorder.on_request)
        context.on("requestfinished", lambda request: recorder.later(recorder.on_request_done(request)))
        context.on("requestfailed", lambda request: recorder.later(recorder.on_request_done(request, failed=True)))
        recorder.emit(
            "started",
            tabs=[{"tab": index, **address(page.url)} for index, page in enumerate(context.pages)],
        )
        for page in context.pages:
            recorder.watch_page(page)
            recorder.step_path = address(page.url)["url"]
            for frame in page.frames:
                with contextlib.suppress(PlaywrightError, TimeoutError):
                    await asyncio.wait_for(frame.evaluate(PAGE_SCRIPT), 5)
        (folder / "started.json").write_text(json.dumps({"pid": os.getpid(), "at": datetime.now().isoformat()}), encoding="utf-8")

        try:
            while True:
                (folder / "heartbeat").write_text(str(recorder.seq), encoding="utf-8")
                if (stop is not None and stop.is_set()) or stop_file.exists():
                    break
                if not browser.is_connected():
                    reason = "the browser was closed"
                    break
                if time.monotonic() > deadline:
                    reason = "time limit reached"
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait() if stop is not None else asyncio.sleep(HEARTBEAT_SECONDS), HEARTBEAT_SECONDS)
        finally:
            if recorder.tasks:
                await asyncio.wait(list(recorder.tasks), timeout=10)
            recorder.closing = True
            if browser.is_connected():
                for page in context.pages:
                    for frame in page.frames:
                        with contextlib.suppress(PlaywrightError, TimeoutError):
                            await asyncio.wait_for(
                                frame.evaluate("window.__csdeskRecorder && window.__csdeskRecorder.uninstall()"), 3
                            )
                recorder.emit("stopped", reason=reason)
                await browser.close()  # disconnects; her window stays open
            else:
                recorder.emit("stopped", reason=reason)

    summary = build(folder)
    (folder / "done.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
