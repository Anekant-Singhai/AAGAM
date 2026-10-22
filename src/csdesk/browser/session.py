"""Working inside her logged-in browser window.

Each function attaches to the CS Desk window over CDP, does one thing, and
detaches, leaving the window and her login as they were. Nothing here clicks;
the form filler's clicks go through guard.guarded_click.

Two Playwright defaults would interfere with her window, so attaching turns
them off. Playwright dismisses (presses Cancel on) every dialog the page opens
unless someone listens for it, so every attachment listens and leaves dialogs
for her. Playwright also redirects downloads into a temporary folder that it
deletes on disconnect; no_defaults=True keeps the browser's own download
settings.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from playwright.async_api import (
    Browser,
    BrowserContext,
    Dialog,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..config import Settings
from ..errors import Blocked, Invalid, NotFound
from . import chrome
from .guard import check_url

# Sites the tools may open. Anything else she opens herself.
ALLOWED_HOSTS = ("mca.gov.in", "gst.gov.in", "incometax.gov.in", "icsi.edu")
DEMO_FORM = (Path(__file__).resolve().parent.parent / "forms" / "demo" / "demo_form.html").resolve()

# A tab showing a dialog can't be attached to, read or captured until she answers it.
CONNECT_TIMEOUT_MS = 20_000
SCREENSHOT_TIMEOUT_MS = 10_000
DIALOG_HINT = "the page may be showing a dialog box. Ask her to answer it, then try again."


@asynccontextmanager
async def attached(settings: Settings, dialogs: list[dict[str, str]] | None = None) -> AsyncIterator[Browser]:
    """Attach to the CS Desk window. Dialogs that open meanwhile are left for her and noted in `dialogs`."""
    if chrome.debug_info(settings.cdp_port) is None:
        raise NotFound(
            "The CS Desk browser window isn't open. Start it with browser_start (or `csdesk browser`), "
            "then ask her to log in."
        )
    async with async_playwright() as playwright:
        browser = await connect(playwright, settings)
        for context in browser.contexts:
            leave_dialogs_for_her(context, dialogs if dialogs is not None else [])
        try:
            yield browser
        finally:
            # On a CDP connection this only disconnects; her window and session stay open.
            await browser.close()


async def connect(playwright: Playwright, settings: Settings) -> Browser:
    """Attach to the CS Desk window. Attaching waits for every tab to respond, which a tab can't do while a
    dialog box is open in it, so a timeout here almost always means a dialog is waiting for her."""
    try:
        return await playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{settings.cdp_port}", no_defaults=True, timeout=CONNECT_TIMEOUT_MS
        )
    except PlaywrightTimeoutError as exc:
        raise Blocked(f"The CS Desk browser isn't responding: {DIALOG_HINT}") from exc


def leave_dialogs_for_her(context: BrowserContext, sink: list[dict[str, str]]) -> None:
    """Listen for dialogs so Playwright doesn't dismiss them, and note each one without answering it."""

    def note(dialog: Dialog) -> None:
        sink.append({"type": dialog.type, "message": dialog.message[:500], "url": dialog.page.url if dialog.page else ""})

    context.on("dialog", note)


def tabs(browser: Browser) -> list[Page]:
    return [page for context in browser.contexts for page in context.pages]


async def pick_tab(browser: Browser, tab: int | None = None, url_contains: str | None = None) -> Page:
    """The tab to work in: the one asked for, else the one she has in front (on the form's page, or on MCA)."""
    pages = tabs(browser)
    if not pages:
        raise NotFound("The CS Desk browser has no open tabs.")
    if tab is not None:
        if not 0 <= tab < len(pages):
            raise Invalid(f"There is no tab {tab}; browser_status lists the open tabs.")
        return pages[tab]
    if url_contains:
        pages = [page for page in pages if url_contains in page.url]
        if not pages:
            raise NotFound(f"No open tab is on {url_contains}. Open the form in the CS Desk browser first.")
    else:
        pages = [page for page in pages if _host(page.url).endswith("mca.gov.in")] or pages
    # The order of tabs over CDP isn't the order she opened them in, so go by which one she can see.
    for page in pages:
        if await in_front(page):
            return page
    return pages[0]


async def in_front(page: Page) -> bool:
    try:
        return await asyncio.wait_for(page.evaluate("document.visibilityState"), 3) == "visible"
    except (PlaywrightError, TimeoutError):
        return False


async def status(settings: Settings) -> dict[str, Any]:
    info = chrome.debug_info(settings.cdp_port)
    if info is None:
        return {"open": False, "message": "The CS Desk browser window isn't open. Use browser_start."}
    dialogs: list[dict[str, str]] = []
    async with attached(settings, dialogs) as browser:
        listed = [
            {
                "tab": index,
                "title": await _title(page),
                "url": page.url,
                "in_front": await in_front(page),
                "logged_in": await looks_logged_in(page),
            }
            for index, page in enumerate(tabs(browser))
        ]
    result: dict[str, Any] = {"open": True, "browser": info.get("Browser"), "tabs": listed}
    if dialogs:
        result["dialogs"] = dialogs
    return result


async def looks_logged_in(page: Page) -> bool | None:
    """Best guess for MCA: a visible Logout / Sign out control. None when the tab isn't on MCA or can't be read."""
    if not _host(page.url).endswith("mca.gov.in"):
        return None

    async def look() -> bool:
        controls = page.get_by_text(re.compile(r"^\s*(log\s?out|sign\s?out)\s*$", re.IGNORECASE))
        for index in range(min(await controls.count(), 5)):
            if await controls.nth(index).is_visible():
                return True
        return False

    try:
        return await asyncio.wait_for(look(), 5)
    except (PlaywrightError, TimeoutError):
        return None


def check_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        if Path(url2pathname(parsed.path)).resolve() == DEMO_FORM:
            return
        raise Blocked("The only local page CS Desk opens is its practice form.")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise Blocked(f"CS Desk only opens https pages on {', '.join(ALLOWED_HOSTS)}. She can open other sites herself.")
    check_url(url)


async def open_url(settings: Settings, url: str) -> dict[str, Any]:
    check_allowed(url)
    async with attached(settings) as browser:
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.bring_to_front()
        return {"tab": tabs(browser).index(page), "title": await _title(page), "url": page.url}


async def screenshot(settings: Settings, folder: Path, tab: int | None = None, label: str = "screen") -> tuple[Path, bytes]:
    """Save a full-page screenshot as evidence; return its path and a viewport-sized image for Claude to read."""
    folder.mkdir(parents=True, exist_ok=True)
    async with attached(settings) as browser:
        page = await pick_tab(browser, tab)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{label}.png"
        try:
            await page.screenshot(path=str(path), full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
            view = await page.screenshot(type="jpeg", quality=80, timeout=SCREENSHOT_TIMEOUT_MS)
        except PlaywrightError as exc:
            raise Blocked(f"Couldn't take a screenshot: {DIALOG_HINT}") from exc
    return path, view


async def _title(page: Page) -> str:
    try:
        return await asyncio.wait_for(page.title(), 3)
    except (PlaywrightError, TimeoutError):
        return ""


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
