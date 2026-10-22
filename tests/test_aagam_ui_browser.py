"""The built interface, driven in a real (headless) browser against a real server."""

import asyncio
import contextlib
import socket
import threading
import time

import pytest
import uvicorn
from helpers import browser_or_skip, run, write_financials_pdf, write_notice_pdf
from playwright.async_api import async_playwright

from aagam import library
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.web.app import STATIC, create_app

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not (STATIC / "index.html").exists(), reason="run `aagam build-ui` first")]


@contextlib.contextmanager
def serving(settings):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(create_app(AagamSettings(core=settings, local_ai=False), background=False), host="127.0.0.1", port=port, log_level="error")
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not instance.started and time.monotonic() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    instance.should_exit = True
    thread.join(5)


@pytest.fixture
def server(settings, tmp_path):
    with open_db(settings.db_path) as vault:
        library.add_document(vault, settings, write_notice_pdf(tmp_path / "Acme AGM notice.pdf"), tags=["precedent"], queue_ai=False)
    with serving(settings) as url:
        yield url


@pytest.fixture
def desk(settings, tmp_path):
    """The notice and a set of audited statements on file."""
    with open_db(settings.db_path) as vault:
        library.add_document(vault, settings, write_notice_pdf(tmp_path / "Acme AGM notice.pdf"), tags=["precedent"], queue_ai=False)
        statements = library.add_document(vault, settings, write_financials_pdf(tmp_path / "Acme accounts 2026.pdf"), queue_ai=False)
        library.index_new(vault, settings, statements["document_id"], queue_ai=False)
    with serving(settings) as url:
        yield url


def test_her_path_through_the_interface(server):
    executable = browser_or_skip()

    async def steps():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(executable), headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            await page.goto(server)
            await page.get_by_text("Resolutions on file").wait_for()

            # Search from the top bar, open the hit on its page.
            await page.get_by_label("Search documents").click()
            await page.get_by_label("What to find").fill('"working capital"')
            await page.keyboard.press("Enter")
            await page.get_by_text("1 document match.").wait_for()
            await page.locator("a", has_text="NOTICE OF 10TH ANNUAL GENERAL MEETING").first.click()
            await page.get_by_text("Page 4 of 4").wait_for()
            assert await page.locator("article mark").first.inner_text() == "working"

            # Tag it, then find the s.186 precedent and read its explanatory statement.
            await page.get_by_role("button", name="Add tag").click()
            await page.get_by_placeholder("Type a tag…").fill("group loans")
            await page.keyboard.press("Enter")
            await page.locator('span[title="Added by you"]', has_text="group loans").wait_for()
            await page.get_by_role("link", name="Precedents").click()
            await page.get_by_role("button", name="s.186", exact=True).click()  # the filter, not the sidebar tag "s.186 1"
            await page.get_by_text("Approval for making investments").first.click()
            await page.get_by_text("Explanatory statement").wait_for()
            statement = await page.locator(".legal").nth(1).inner_text()

            # The calculator.
            await page.get_by_role("link", name="Calculators").click()
            boxes = page.locator("form input[inputmode=decimal]")
            for index, value in enumerate(["10", "50", "20", "0", "100"]):
                await boxes.nth(index).fill(value)
            await page.get_by_role("button", name="Work it out").click()
            await page.get_by_text("Over the limit by ₹30,00,00,000").wait_for()
            await browser.close()
            return errors, statement

    errors, statement = run(asyncio.wait_for(steps(), 90))
    assert errors == []
    assert "exceed the limit under section 186(2)" in statement


def test_the_desk_work_notes_financials_and_themes(desk, tmp_path):
    executable = browser_or_skip()
    letter = tmp_path / "Consent letter.txt"
    letter.write_text("Consent to act as director under section 152(5), DIN 01234567.", encoding="utf-8")

    async def steps():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(executable), headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(desk)
            await page.get_by_text("Work in hand").first.wait_for()

            # Ctrl+K finds anything and goes anywhere: the statements, by the company's name.
            await page.keyboard.press("Control+k")
            await page.get_by_label("What to find").fill("Acme")
            await page.get_by_role("dialog").get_by_text("Financial statements", exact=True).wait_for()
            await page.get_by_label("What to find").fill("work register")
            await page.keyboard.press("Enter")
            await page.get_by_text("Every job in hand and done").wait_for()

            # Start an AGM: its checklist comes with the law behind each step. Tick the first.
            await page.get_by_role("button", name="New work").click()
            await page.get_by_role("button", name="Start this work").click()
            await page.get_by_text("s.134(1), s.173").wait_for()
            first = page.get_by_role("checkbox", name="Step 1", exact=True)
            await first.click()
            await page.wait_for_function("document.querySelector('[aria-label=\"Step 1\"]').getAttribute('aria-checked') === 'true'")
            await page.get_by_label("New note").fill("Shorter-notice consents from 96% of members.")
            await page.get_by_role("button", name="Save note").click()
            await page.get_by_text("Shorter-notice consents from 96% of members.").wait_for()

            # The statements: ratios, where the money comes from, what applies; correct a line.
            await page.get_by_role("link", name="Financials", exact=True).click()
            await page.get_by_text("Year to 31 Mar 2026").click()
            await page.get_by_text("Where the money comes from").wait_for()
            assert await page.get_by_text("Other liabilities and provisions").count() == 1
            await page.get_by_role("tab", name="Ratios").click()
            await page.get_by_text("Ratios (Schedule III)").wait_for()
            current_ratio = page.locator("tr", has_text="Current ratio").locator("td").nth(1)
            assert (await current_ratio.inner_text()).strip() == "1.35×"
            await page.get_by_role("tab", name="What applies").click()
            await page.get_by_text("What these figures make apply").wait_for()
            await page.get_by_role("tab", name="Figures").click()
            await page.locator("tr", has_text="Inventories").first.click()
            await page.get_by_label("This year").fill("1500")
            await page.keyboard.press("Enter")
            await page.locator("tr", has_text="Inventories").get_by_text("yours").wait_for()

            # The notes page finds the note; the theme menu switches to Night light and remembers it.
            await page.get_by_role("link", name="Notes", exact=True).click()
            await page.get_by_label("Search notes").fill("consents")
            await page.locator("mark", has_text="consents").first.wait_for()
            await page.get_by_label("Theme").click()
            await page.get_by_role("menuitemradio", name="Night light").click()
            assert await page.evaluate("document.documentElement.dataset.theme") == "night"
            await page.reload()
            assert await page.evaluate("document.documentElement.dataset.theme") == "night"

            # "?" opens help for the page; the guide lists what AAGAM does.
            await page.keyboard.press("?")
            await page.get_by_role("dialog", name="Help").get_by_text("Pinned notes show on Home.").wait_for()
            await page.get_by_role("link", name="Everything AAGAM does").click()
            await page.get_by_role("heading", name="What AAGAM does").wait_for()

            # Adding a document through the upload box opens it once it is read.
            await page.get_by_role("button", name="Add documents").first.click()
            await page.get_by_label("Choose files to add").set_input_files(str(letter))
            await page.get_by_role("button", name="Add 1 document").click()
            await page.get_by_text("Page 1 of 1").wait_for()

            # A person's dossier, from the director named in the notice.
            await page.get_by_role("link", name="People & companies", exact=True).click()
            await page.get_by_role("link", name="Asha Rao").first.click()
            await page.get_by_text("Where they appear").wait_for()
            await browser.close()
            return errors

    errors = run(asyncio.wait_for(steps(), 120))
    assert errors == []


def test_correcting_and_deleting_from_the_window(desk):
    executable = browser_or_skip()

    async def steps():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(executable), headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            # A new client in the company file, a field changed, a meeting added and deleted, then the client deleted.
            await page.goto(f"{desk}/companies?new=1")
            await page.get_by_label("Name").fill("Bharat Fasteners Private Limited")
            await page.get_by_role("button", name="Add client").click()
            await page.get_by_role("heading", name="Bharat Fasteners Private Limited").wait_for()
            await page.get_by_label("RoC").fill("RoC-Pune")
            await page.get_by_role("button", name="Save 1 change").click()
            await page.get_by_text("Saved.").first.wait_for()
            await page.get_by_role("tab", name="Meetings").click()
            await page.get_by_role("button", name="Add a meeting").click()
            await page.get_by_label("Kind").select_option("agm")
            await page.get_by_label("Date").fill("2026-09-26")
            await page.get_by_role("button", name="Add", exact=True).click()
            row = page.locator("tbody tr", has_text="26 Sep 2026")
            await row.wait_for()
            await row.hover()
            await row.get_by_role("button", name="Delete").click()
            await page.get_by_role("dialog").get_by_role("button", name="Delete").click()
            await page.get_by_text("No meetings on file.").wait_for()
            await page.get_by_label("More").click()
            await page.get_by_role("menuitem", name="Delete this client").click()
            await page.get_by_role("dialog").get_by_role("button", name="Delete client").click()
            await page.get_by_role("heading", name="Clients").wait_for()
            await page.locator("main li", has_text="Bharat Fasteners").wait_for(state="detached")

            # A page corrected by hand, a fact hidden, then the document deleted.
            await page.goto(f"{desk}/library?type=notice")
            await page.locator("a, button", has_text="NOTICE OF 10TH ANNUAL GENERAL MEETING").first.click()
            await page.get_by_text("Page 1 of 4").wait_for()
            await page.get_by_label("More about this document").click()
            await page.get_by_role("menuitem", name="Correct this page's text").click()
            await page.get_by_label("Page text").fill("Acme Widgets Limited\nCIN: L74999MH2015PLC123456\nA page she typed herself.")
            await page.get_by_role("button", name="Save page").click()
            await page.get_by_text("You corrected this page's text.").wait_for()
            await page.get_by_role("tab", name="Facts").click()
            fact = page.locator("li", has_text="01234567").first
            await fact.hover()
            await fact.get_by_title("Not a fact: hide it").click()
            await page.get_by_role("dialog").get_by_role("button", name="In this document").click()
            await page.get_by_text("Hidden in this document.").wait_for()
            assert await page.locator("li", has_text="01234567").count() == 0
            await page.get_by_label("More about this document").click()
            await page.get_by_role("menuitem", name="Delete this document").click()
            await page.get_by_role("dialog").get_by_role("button", name="Delete document").click()
            await page.get_by_role("heading", name="Library").wait_for()
            await page.get_by_text("1 document").wait_for()
            await browser.close()
            return errors

    errors = run(asyncio.wait_for(steps(), 120))
    assert errors == []
