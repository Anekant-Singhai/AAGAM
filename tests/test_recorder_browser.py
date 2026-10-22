"""Recording her filling the practice form, writing a recipe from it, and replaying that recipe."""

import asyncio
import contextlib
import json
from pathlib import Path

import pytest
from helpers import ACME, USER, browser_or_skip, close_browser, run
from mcp import Client
from playwright.async_api import async_playwright

from csdesk import recorder
from csdesk.browser import chrome, session
from csdesk.browser.session import DEMO_FORM
from csdesk.errors import Blocked
from csdesk.forms import fill
from csdesk.server import build_server
from csdesk.vault import Vault

pytestmark = pytest.mark.browser
PAN = "ABCPE1234F"


@contextlib.asynccontextmanager
async def as_her(settings):
    """Her own hands on the CS Desk window: a second connection that types and clicks, and answers dialogs."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{settings.cdp_port}", no_defaults=True)
        page = next(p for p in browser.contexts[0].pages if "demo_form.html" in p.url)
        page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
        try:
            yield page
        finally:
            await browser.close()


async def fill_by_hand(page, with_dialog: bool = False):
    for selector, value in (
        ("#cin", ACME["cin"]),
        ("#cname", ACME["name"]),
        ("#din", "01234567"),
        ("#dname", "Asha Rao"),
        ("#pan", PAN),
        ("#doa", "01/10/2026"),
    ):
        await page.fill(selector, value)
        await page.locator(selector).blur()
    await page.select_option("#desig", label="Additional Director")
    await page.check('input[name="shareholder"][value="Y"]')
    if with_dialog:
        await page.evaluate("setTimeout(() => { window.answer = confirm('Save the draft now?') }, 0)")
        await asyncio.sleep(0.5)
    await page.click("#save")
    await page.click("#submit")  # she may press Submit on the practice page; the recording notes it as hers
    await asyncio.sleep(2)  # the recorder takes its after-click screenshots


def on_file(settings):
    with Vault.open(settings.db_path) as vault:
        company_id = vault.save("company", ACME, USER)
        party_id = vault.save("party", {"kind": "individual", "name": "Asha Rao", "din": "01234567", "pan": PAN}, USER)
    return company_id, party_id


def test_record_her_filling_then_replay_the_draft_recipe(settings, tmp_path):
    browser_or_skip()
    company_id, party_id = on_file(settings)
    chrome.launch(settings, url="about:blank", headless=True)
    try:
        run(session.open_url(settings, DEMO_FORM.as_uri()))
        folder = recorder.new_recording(settings, "DEMO-1", str(company_id), party_id)

        async def record_and_fill():
            stop = asyncio.Event()
            task = asyncio.create_task(recorder.run(settings, folder, stop))
            while not (folder / "started.json").exists():
                assert not task.done(), task.result()
                await asyncio.sleep(0.2)
            async with as_her(settings) as page:
                await fill_by_hand(page, with_dialog=True)
                answer = await page.evaluate("String(window.answer)")
            stop.set()
            return await task, answer

        summary, answer = run(record_and_fill())
        assert answer == "true"  # she answered the dialog; the recorder didn't dismiss it
        assert (summary["fields_filled"], summary["matched"]) == (8, 5)

        events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        clicks = {e["name"]: e["guard"] for e in events if e["type"] == "click"}
        assert clicks == {"Save as draft": "allowed", "Submit": "hers"}
        assert any(e["type"] == "dialog" and e["dialog_type"] == "confirm" for e in events)
        assert any(e["type"] == "screenshot" for e in events)

        # Nothing she typed is written down, only its shape and match.
        for path in folder.rglob("*"):
            if path.suffix in (".jsonl", ".json", ".md", ".py"):
                text = path.read_text(encoding="utf-8")
                assert PAN not in text and "01/10/2026" not in text, path.name

        flow = (folder / "flow.md").read_text(encoding="utf-8")
        assert "| Income-tax PAN of the director | text | PAN | party.pan |" in flow
        assert "pressed **Submit** (hers; CS Desk never presses it)" in flow

        namespace: dict = {}
        exec((folder / "recipe_draft.py").read_text(encoding="utf-8"), namespace)
        draft = namespace["DEMO_1"]
        assert draft.save_button == "Save as draft"
        by_key = {f.key: f for f in draft.fields}
        assert by_key["party.pan"].sensitive and by_key["extra.date_of_appointment"].kind == "date"
        assert by_key["extra.is_the_director_also_a_shareholder"].kind == "radio"

        # The recorded recipe fills a fresh copy of the form on its own.
        values = {
            "company.cin": ACME["cin"], "company.name": ACME["name"], "party.din": "01234567", "party.name": "Asha Rao",
            "party.pan": PAN, "extra.date_of_appointment": "2026-10-01", "extra.designation": "Additional Director",
            "extra.is_the_director_also_a_shareholder": "Yes",
        }

        async def replay():
            async with session.attached(settings) as browser:
                page = await browser.contexts[0].new_page()
                await page.goto(DEMO_FORM.as_uri())
                report = await fill(page, draft, values, tmp_path / "evidence")
                checked = await page.is_checked('input[name="shareholder"][value="Y"]')
                return report, checked, await page.text_content("#status")

        report, checked, status = run(replay())
        assert (report.missing, report.mismatches, report.saved) == ([], [], True)
        assert checked and status == "Draft saved"
    finally:
        run(close_browser(settings.cdp_port))


def test_record_from_claude_with_the_tools(settings):
    browser_or_skip()
    _, party_id = on_file(settings)
    chrome.launch(settings, url="about:blank", headless=True)
    try:
        run(session.open_url(settings, DEMO_FORM.as_uri()))

        async def steps():
            async with Client(build_server(settings)) as client:
                started = await client.call_tool("record_start", {"form": "DEMO-1", "company": "Acme", "party_id": party_id})
                assert not started.is_error, started.content
                again = await client.call_tool("record_start", {"form": "DEMO-1"})
                async with as_her(settings) as page:
                    await fill_by_hand(page)
                status = await client.call_tool("record_status", {})
                stopped = await client.call_tool("record_stop", {})
                return started, again, status, stopped

        started, again, status, stopped = run(steps())
        assert again.is_error and "still running" in again.content[0].text
        assert status.structured_content["running"] and status.structured_content["captured"]["change"] >= 8
        assert not stopped.is_error, stopped.content
        result = stopped.structured_content
        assert (result["fields_filled"], result["matched"]) == (8, 5)
        assert "| Corporate Identification Number (CIN) | text | CIN | company.cin |" in result["flow_markdown"]
        assert Path(result["recipe_draft"]).is_file()
        assert recorder.active(settings) is None
        assert chrome.debug_info(settings.cdp_port) is not None  # her window is still open
    finally:
        run(close_browser(settings.cdp_port))


def test_tools_leave_dialogs_for_her_and_say_so_while_one_is_open(settings, monkeypatch):
    browser_or_skip()
    chrome.launch(settings, url="about:blank", headless=True)
    monkeypatch.setattr(session, "CONNECT_TIMEOUT_MS", 3000)
    try:

        async def steps():
            dialogs: list = []
            async with session.attached(settings, dialogs) as browser:
                page = browser.contexts[0].pages[0]
                await page.evaluate("setTimeout(() => { window.answer = confirm('Discard the draft?') }, 0)")
                await asyncio.sleep(1)
                # Still waiting for her: the page can't run anything until she answers.
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(page.evaluate("String(window.answer)"), 1.5)
            return dialogs

        dialogs = run(steps())
        assert dialogs[0]["type"] == "confirm" and dialogs[0]["message"] == "Discard the draft?"
        with pytest.raises(Blocked, match="dialog box"):
            run(session.status(settings))
    finally:
        run(close_browser(settings.cdp_port))


def test_recording_needs_the_browser_open(settings):
    folder = recorder.new_recording(settings, "DIR-12")
    with pytest.raises(Exception, match="isn't open"):
        run(recorder.run(settings, folder))
