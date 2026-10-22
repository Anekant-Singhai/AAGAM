"""The fill loop on the practice page, in a real (headless) Chrome or Edge."""

import json
from pathlib import Path

import pytest
from helpers import browser_or_skip, run
from playwright.async_api import async_playwright

from csdesk.browser.guard import guarded_click
from csdesk.browser.session import DEMO_FORM
from csdesk.errors import Blocked, PageChanged
from csdesk.forms import fill
from csdesk.forms.registry import DEMO

pytestmark = pytest.mark.browser

VALUES = {
    "company.cin": "U74999MH2015PTC123456",
    "company.name": "Acme Widgets Private Limited",
    "party.din": "01234567",
    "party.name": "Asha Rao",
    "party.pan": "ABCPE1234F",
    "extra.date_of_appointment": "2026-10-01",
    "extra.designation": "Additional Director",
}


async def _on_practice_page(executable, work):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=str(executable), headless=True)
        try:
            page = await browser.new_page()
            await page.goto(DEMO_FORM.as_uri())
            return await work(page)
        finally:
            await browser.close()


def test_the_recipe_fills_reads_back_saves_and_never_submits(tmp_path):
    executable = browser_or_skip()

    async def work(page):
        report = await fill(page, DEMO, VALUES, tmp_path / "evidence")
        state = {
            "pan": await page.input_value("#pan"),
            "date": await page.input_value("#doa"),
            "status": await page.text_content("#status"),
        }
        with pytest.raises(Blocked):
            await guarded_click(page.get_by_role("button", name="Submit"))
        state["submitted"] = await page.evaluate("document.body.dataset.submitted || 'no'")
        return report, state

    report, state = run(_on_practice_page(executable, work))
    assert (report.missing, report.mismatches, report.saved) == ([], [], True)
    assert state == {"pan": "ABCPE1234F", "date": "01/10/2026", "status": "Draft saved", "submitted": "no"}
    assert next(f for f in report.filled if f["key"] == "party.pan")["value"] == "XXXXXX234F"
    log = Path(report.log_path).read_text(encoding="utf-8")
    assert "ABCPE1234F" not in log and json.loads(log)["recipe"] == "DEMO-1"
    assert Path(report.screenshot_path).is_file()


def test_a_changed_label_stops_filling_at_that_field(tmp_path):
    executable = browser_or_skip()

    async def work(page):
        await page.evaluate("document.querySelector('label[for=din]').textContent = 'DIN of the director'")
        with pytest.raises(PageChanged, match="Director Identification Number") as stopped:
            await fill(page, DEMO, VALUES, tmp_path / "evidence")
        return str(stopped.value), await page.input_value("#cin"), await page.input_value("#dname")

    message, cin, director_name = run(_on_practice_page(executable, work))
    assert cin == VALUES["company.cin"]  # filled before the changed field
    assert director_name == ""  # nothing typed after it
    assert "filled so far" in message


def test_the_wrong_page_gets_nothing_typed(tmp_path):
    executable = browser_or_skip()

    async def work(page):
        await page.set_content("<h1>Some other page</h1><label for=x>Name of the company</label><input id=x>")
        with pytest.raises(PageChanged):
            await fill(page, DEMO, VALUES, tmp_path / "evidence")
        return await page.input_value("#x")

    assert run(_on_practice_page(executable, work)) == ""


def test_missing_values_are_reported_not_invented(tmp_path):
    executable = browser_or_skip()
    partial = {k: v for k, v in VALUES.items() if k != "extra.designation"}

    async def work(page):
        return await fill(page, DEMO, partial, tmp_path / "evidence")

    report = run(_on_practice_page(executable, work))
    assert report.missing == ["Designation (extra.designation)"]
