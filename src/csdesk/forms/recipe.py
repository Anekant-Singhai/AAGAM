"""Form recipes: where each value goes on a portal page, recorded once and replayed.

The AI decides what goes into each field (from the company file); the recipe
decides where it goes. Each field is found by its label before anything is
typed into it. If the label isn't there, the portal page has changed and
filling stops. Every value is read back after typing. The only button a
recipe presses is its save button, and that click goes through the guard.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError

from .. import validators
from ..browser.guard import guarded_click
from ..errors import PageChanged
from ..vault import mask

SCREENSHOT_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class Field:
    key: str  # where the value comes from: "company.cin", "party.pan", "extra.date_of_appointment"
    label: str  # the field's label on the page, exactly as shown (for a radio group: the question)
    kind: Literal["text", "date", "select", "checkbox", "radio", "file"] = "text"
    selector: str | None = None  # CSS selector when the label can't find the field; a radio group always needs one
    required: bool = True
    sensitive: bool = False
    date_format: str = "%d/%m/%Y"


@dataclass(frozen=True)
class Recipe:
    code: str  # the form, e.g. "DIR-12"
    title: str
    url_contains: str  # part of the URL of the page the form is on
    page_marker: str  # text that must be on the page, e.g. the form's heading
    fields: tuple[Field, ...]
    save_button: str | None = None
    recorded_on: str | None = None  # when the recipe was last checked against the live portal
    hand_over: str = "Check every field against the fill log, then press Submit and sign with your DSC yourself."


@dataclass
class FillReport:
    recipe: str
    filled: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    saved: bool = False
    log_path: str | None = None
    screenshot_path: str | None = None
    notes: list[str] = field(default_factory=list)


async def fill(page: Any, recipe: Recipe, values: dict[str, Any], evidence_dir: Path) -> FillReport:
    """Fill one form page, save the draft if the recipe says so, and keep a log and screenshot as evidence."""
    if recipe.url_contains not in page.url:
        raise PageChanged(f"The tab is on {page.url}, not on the {recipe.code} form. Open the form first.")
    if await page.get_by_text(recipe.page_marker).count() == 0:
        raise PageChanged(
            f"This page doesn't show '{recipe.page_marker}', so it isn't the {recipe.code} form or the portal "
            "has changed it. Nothing was typed."
        )
    report = FillReport(recipe.code)
    for spec in recipe.fields:
        value = values.get(spec.key)
        if value in (None, ""):
            if spec.required:
                report.missing.append(f"{spec.label} ({spec.key})")
            continue
        target = page.locator(spec.selector) if spec.selector else page.get_by_label(spec.label, exact=True)
        count = await target.count()
        if count != 1 and not (spec.kind == "radio" and count > 1):
            done = ", ".join(item["label"] for item in report.filled) or "nothing"
            raise PageChanged(
                f"Expected one field labelled '{spec.label}' but found {count}, so the portal page may have changed. "
                f"Stopped before typing anything more (filled so far: {done})."
            )
        typed, shown = await _put(target, spec, value)
        ok = _same(typed, shown)
        report.filled.append(
            {"key": spec.key, "label": spec.label, "value": mask(typed) if spec.sensitive else typed, "read_back_ok": ok}
        )
        if not ok:
            seen = (mask(typed), mask(shown)) if spec.sensitive else (typed, shown)
            report.mismatches.append(f"{spec.label}: typed {seen[0]!r} but the page shows {seen[1]!r}")

    if recipe.save_button and not report.mismatches:
        await guarded_click(page.get_by_role("button", name=recipe.save_button, exact=True))
        report.saved = True
        await page.wait_for_timeout(800)  # let a "saved" message or a dialog appear before the screenshot

    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in recipe.code)
    shot = evidence_dir / f"{stamp}-{name}-filled.png"
    try:
        await page.screenshot(path=str(shot), full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
        report.screenshot_path = str(shot)
    except PlaywrightError:
        report.notes.append("No screenshot: the page may be showing a dialog box, which is left for her to answer.")
    log = evidence_dir / f"{stamp}-{name}-fill-log.json"
    report.log_path = str(log)
    log.write_text(
        json.dumps({"page": page.url, "recipe_checked_on": recipe.recorded_on, **asdict(report)}, indent=2),
        encoding="utf-8",
    )
    return report


async def _put(target: Any, spec: Field, value: Any) -> tuple[str, str]:
    """Enter one value; return (what was entered, what the page shows afterwards)."""
    if spec.kind == "date":
        day = date.fromisoformat(validators.iso_date(value))
        text = day.isoformat() if await target.get_attribute("type") == "date" else day.strftime(spec.date_format)
        await target.fill(text)
        return text, await target.input_value()
    if spec.kind == "select":
        await target.select_option(label=str(value))
        shown = await target.evaluate("el => el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ''")
        return str(value), shown
    if spec.kind == "checkbox":
        wanted = str(value).strip().lower() in ("1", "true", "yes", "y")
        await target.set_checked(wanted)
        return str(wanted), str(await target.is_checked())
    if spec.kind == "radio":
        # `target` is the whole group; pick the option whose own label matches the value.
        wanted = str(value)
        for index in range(await target.count()):
            option = target.nth(index)
            if _same(wanted, await option.evaluate(_OPTION_LABEL_JS)):
                await option.check()
                return wanted, wanted if await option.is_checked() else ""
        raise PageChanged(f"'{spec.label}' has no option '{wanted}'. Nothing was chosen there.")
    if spec.kind == "file":
        await target.set_input_files(str(value))
        shown = await target.evaluate("el => el.files.length ? el.files[0].name : ''")
        return Path(str(value)).name, shown
    text = str(value)
    await target.fill(text)
    return text, await target.input_value()


def _same(typed: str, shown: str) -> bool:
    return " ".join(typed.split()).casefold() == " ".join(str(shown).split()).casefold()


_OPTION_LABEL_JS = """el => {
  const labels = el.labels && el.labels.length ? [...el.labels].map(l => l.innerText || l.textContent).join(' ') : '';
  return (labels || el.getAttribute('aria-label') || el.value || '').replace(/\\s+/g, ' ').trim();
}"""
