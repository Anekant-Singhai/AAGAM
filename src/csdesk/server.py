"""CS Desk as an MCP server: the tools Claude uses on her behalf.

Claude Desktop (or Claude Code) starts it as `csdesk serve`. Each tool opens
the company file for one call only. Errors meant for her come back as plain
sentences; anything unexpected is logged to AAGAM_HOME/logs.
"""

from __future__ import annotations

import functools
import inspect
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from playwright.async_api import Error as PlaywrightError

from . import __version__, documents, dossier, drafting, lawdesk, recorder
from .browser import chrome, session
from .config import Settings
from .documents.intake import DOC_TYPES
from .duedates import upcoming
from .errors import CsDeskError
from .forms import RECIPES, build_values, fill, recipe_for
from .vault import Source, Vault
from .vault.models import (
    AppointmentIn,
    AuditorAppointmentIn,
    ChargeIn,
    CompanyIn,
    EventIn,
    FilingStatus,
    MeetingIn,
    PartyIn,
    RegistrationIn,
    ResolutionIn,
    SourceIn,
)

DocType = Literal[tuple(DOC_TYPES)]  # type: ignore[valid-type]
EntityName = Literal[
    "company", "party", "appointment", "meeting", "resolution", "auditor_appointment", "charge", "event",
    "registration", "filing",
]

INSTRUCTIONS = """\
CS Desk works for a Company Secretary in India. It keeps a company file (companies, LLPs, directors, KMP,
meetings, resolutions, charges, filings), reads her documents, works out due dates, drafts from her Word
templates, searches her law folder, writes company dossiers, and fills portal forms in her own logged-in
browser window.

Rules that always apply:
- Never submit, sign, pay or file on any portal. The tools stop before those steps; tell her what is ready
  and let her do them.
- She logs in to portals herself (captcha and OTP). Check browser_status before filling a form; if MCA isn't
  logged in, ask her to log in in the CS Desk window.
- Every save needs a source. For a value from a document, read it with read_document first and give
  document_id, page and the exact words as the quote. For something she tells you, use kind "user".
- To build a recipe for a form that has none, record her filling it once on a draft (record_start, then
  record_stop) and review the draft recipe it writes. Recording only watches; it never clicks or types.
- PAN, Aadhaar and passport numbers come back masked. Don't ask her to paste them into the chat; she can type
  them locally with `csdesk set-sensitive`.
- Dates are YYYY-MM-DD and amounts are whole rupees.
- Due dates come from rules with a stated legal basis. Point out items marked "check", and don't present a
  date as certain when the file lacks the facts it depends on.
- For legal questions, search her law folder with law_search and cite what it returns. If it has nothing on
  the point, say so, and mark anything you add from general knowledge as such.
"""


def tool_registrar(server: MCPServer) -> Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """A decorator that registers tools on `server`, passing CS Desk errors to Claude as their own message."""

    def tool(structured: bool | None = None, description: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def wrapper(*args: Any, **kwargs: Any) -> Any:
                    try:
                        return await fn(*args, **kwargs)
                    except CsDeskError as exc:
                        raise ToolError(str(exc)) from exc

            else:

                @functools.wraps(fn)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    try:
                        return fn(*args, **kwargs)
                    except CsDeskError as exc:
                        raise ToolError(str(exc)) from exc

            server.add_tool(wrapper, description=description, structured_output=structured)
            return fn

        return register

    return tool


def build_server(settings: Settings, name: str = "csdesk", instructions: str = INSTRUCTIONS) -> MCPServer:
    settings.ensure_dirs()
    server = MCPServer(name, instructions=instructions, version=__version__)
    tool = tool_registrar(server)

    def open_vault() -> Any:
        return Vault.open(settings.db_path, actor="claude")

    def save(entity: str, fields: Any, source: SourceIn, record_id: int | None) -> dict[str, Any]:
        with open_vault() as vault:
            saved_id = vault.save(entity, fields, Source.from_input(source, "claude"), record_id)
            return {"record_id": saved_id, "changed": sorted(fields.model_dump(exclude_unset=True))}

    # ----------------------------------------------------------- company file

    @tool()
    def find_companies(query: str = "") -> dict[str, Any]:
        """List the companies and LLPs on file. `query` matches part of a name, or a whole CIN/LLPIN."""
        with open_vault() as vault:
            return {"companies": vault.find_companies(query)}

    @tool()
    def get_company(company: str, include_sources: bool = False) -> dict[str, Any]:
        """Everything on file for one company: details, directors and KMP, auditors, meetings, resolutions,
        charges, events, registrations, filings and documents. `company` is an id, CIN/LLPIN or name.
        PANs come back masked. With include_sources, each company field also says where it came from."""
        with open_vault() as vault:
            return vault.company_file(vault.resolve_company(company), include_sources)

    @tool()
    def save_company(fields: CompanyIn, source: SourceIn, company: str | None = None) -> dict[str, Any]:
        """Add a company or LLP (leave `company` empty), or change one (`company` = id, CIN or name).
        Only the fields you pass change. A CIN also fills in class, listing, section 8 status and NIC code."""
        with open_vault() as vault:
            record_id = vault.resolve_company(company) if company else None
            company_id = vault.save("company", fields, Source.from_input(source, "claude"), record_id)
            return {"company_id": company_id, "company": vault.company_row(company_id)}

    @tool()
    def find_parties(query: str) -> dict[str, Any]:
        """Find people and organisations (directors, KMP, auditors, banks) by part of the name, or by DIN or PAN."""
        with open_vault() as vault:
            return {"parties": vault.find_parties(query)}

    @tool()
    def save_party(fields: PartyIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Add a person or organisation (leave record_id empty), or change one. PAN and Aadhaar are stored
        but always come back masked; better that she types them locally with `csdesk set-sensitive` than
        pastes them into the chat."""
        with open_vault() as vault:
            party_id = vault.save("party", fields, Source.from_input(source, "claude"), record_id)
            return {"party_id": party_id, "party": vault.party(party_id)}

    @tool()
    def save_appointment(fields: AppointmentIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record that a person holds a position in a company (director, KMP) or LLP (designated partner).
        For a resignation, pass the appointment's record_id with date_of_cessation and cessation_reason.
        Appointments and cessations get DIR-12 (LLP: Form 4) due dates."""
        return save("appointment", fields, source, record_id)

    @tool()
    def save_meeting(fields: MeetingIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record a board meeting, AGM, EGM, committee meeting or postal ballot. AGM dates drive the
        AOC-4 and MGT-7 due dates; board meeting dates drive the next-meeting date."""
        return save("meeting", fields, source, record_id)

    @tool()
    def save_resolution(fields: ResolutionIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record a resolution. Special resolutions, and any marked mgt14_required, get an MGT-14 due date."""
        return save("resolution", fields, source, record_id)

    @tool()
    def save_auditor_appointment(
        fields: AuditorAppointmentIn, source: SourceIn, record_id: int | None = None
    ) -> dict[str, Any]:
        """Record an auditor's appointment (statutory ones get an ADT-1 due date). Add the audit firm first
        with save_party (kind organisation, org_type audit_firm, frn)."""
        return save("auditor_appointment", fields, source, record_id)

    @tool()
    def save_charge(fields: ChargeIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record a charge and later its modification or satisfaction (CHG-1 / CHG-4 due dates). Add the
        charge holder first with save_party (kind organisation, org_type bank)."""
        return save("charge", fields, source, record_id)

    @tool()
    def save_event(fields: EventIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record an allotment (PAS-3), alteration of share capital (SH-7), change of registered office
        (INC-22; for an LLP Form 15), a BEN-1 declaration received (BEN-2; LLP BEN-2), and for an LLP a change of
        name (Form 5) or of its LLP agreement (Form 3), or another event that starts a filing clock."""
        return save("event", fields, source, record_id)

    @tool()
    def save_registration(fields: RegistrationIn, source: SourceIn, record_id: int | None = None) -> dict[str, Any]:
        """Record a GSTIN, IEC, Udyam or other registration the company holds. GSTINs are checked against
        their check character."""
        return save("registration", fields, source, record_id)

    @tool()
    def field_history(entity: EntityName, record_id: int, field: str | None = None) -> dict[str, Any]:
        """Where a record's values came from and how they changed: document, page and quote, or who said so."""
        with open_vault() as vault:
            return {"history": vault.field_history(entity, record_id, field)}

    # -------------------------------------------------------------- documents

    @tool()
    def ingest_document(
        path: str, company: str | None = None, doc_type: DocType = "other", note: str | None = None
    ) -> dict[str, Any]:
        """Bring a file on this computer into the company's document folder and index its text (PDF, Word
        .docx, Excel .xlsx, image or text). The original is copied, not moved. Scanned pages are flagged;
        read_document shows them to you as images."""
        with open_vault() as vault:
            company_id = vault.resolve_company(company) if company else None
            return documents.ingest(vault, settings, path, company_id, doc_type, note)

    @tool(
        description=(
            f"Ingest every file she has dropped into the inbox folder ({settings.inbox_dir}), then move each one "
            "to inbox/processed/<date>. Give the company when all the files belong to one."
        )
    )
    def ingest_inbox(company: str | None = None, doc_type: DocType = "other") -> dict[str, Any]:
        with open_vault() as vault:
            company_id = vault.resolve_company(company) if company else None
            return {"files": documents.ingest_inbox(vault, settings, company_id, doc_type)}

    @tool()
    def list_documents(company: str | None = None, doc_type: DocType | None = None) -> dict[str, Any]:
        """Documents on file, newest first."""
        with open_vault() as vault:
            company_id = vault.resolve_company(company) if company else None
            return {"documents": vault.documents(company_id, doc_type)}

    @tool(structured=False)
    def read_document(document_id: int, pages: str = "1-5") -> list[Any]:
        """Read pages of a stored document. Text pages come back as text, scanned pages as images. `pages`
        is like "1-3,7" or "all" (up to 10 pages per call). When you save what you read, cite document_id,
        page and the exact words."""
        with open_vault() as vault:
            document, parts, rest = documents.read_pages(vault, settings, document_id, pages)
        content: list[Any] = [
            f"Document {document_id}: {document['original_name']} ({document['doc_type']}, {document['pages']} pages)"
        ]
        for part in parts:
            if part.text is not None:
                content.append(f"--- page {part.page_no} ---\n{part.text}")
            else:
                content.append(f"--- page {part.page_no} (scanned; image follows) ---")
                content.append(Image(data=part.image, format=part.image_format))
        if rest:
            content.append(f"Not returned this time (size limit): pages {_ranges(rest)}. Ask for them next.")
        return content

    # ------------------------------------------------------ due dates, filings

    @tool()
    def due_dates(company: str | None = None, days_ahead: int = 60) -> dict[str, Any]:
        """What is overdue and what falls due in the next `days_ahead` days, for one company or all. Each
        item gives the date, how it was worked out and its legal basis; items marked "check" rest on a rule
        she should confirm. An item drops off once a filing with the same trigger is submitted or approved."""
        today = date.today()
        with open_vault() as vault:
            company_id = vault.resolve_company(company) if company else None
            items = upcoming(vault, today, company_id, days_ahead)
        return {"today": today.isoformat(), "items": [item.as_dict(today) for item in items]}

    @tool()
    def start_filing(
        company: str, form: str, trigger: str | None = None, due_on: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        """Open a filing record and its evidence folder. When it answers a due_dates item, pass that item's
        form and trigger so the item closes once the filing is submitted."""
        with open_vault() as vault:
            company_id = vault.resolve_company(company)
            filing_id = vault.save(
                "filing",
                {"company_id": company_id, "form": form, "trigger": trigger, "due_on": due_on, "status": "planned", "notes": note},
                Source("user", "claude"),
            )
            folder = Path("clients", vault.company_folder(company_id), "filings", f"{filing_id}-{_slug(form)}")
            (settings.home / folder).mkdir(parents=True, exist_ok=True)
            vault.save("filing", {"folder": folder.as_posix()}, Source("derived", "claude", note="evidence folder"), filing_id)
            return vault.filing(filing_id)

    @tool()
    def update_filing(
        filing_id: int,
        status: FilingStatus | None = None,
        srn: str | None = None,
        filed_on: str | None = None,
        fees: int | None = None,
        note: str | None = None,
        source_kind: Literal["user", "portal"] = "user",
    ) -> dict[str, Any]:
        """Record progress on a filing after she acts: submitted (with SRN and date), approved, sent back
        for resubmission, rejected or cancelled. Only the values you pass change."""
        changes = {
            name: value
            for name, value in {"status": status, "srn": srn, "filed_on": filed_on, "fees": fees, "notes": note}.items()
            if value is not None
        }
        if not changes:
            raise ToolError("Nothing to change: pass a status, SRN, date, fees or note.")
        with open_vault() as vault:
            vault.save("filing", changes, Source(source_kind, "claude"), filing_id)
            return vault.filing(filing_id)

    @tool()
    def list_filings(company: str | None = None, status: FilingStatus | None = None) -> dict[str, Any]:
        """Filings on record with status and SRN, earliest due first."""
        with open_vault() as vault:
            company_id = vault.resolve_company(company) if company else None
            return {"filings": vault.filings(company_id, status)}

    # ---------------------------------------------------------------- browser

    @tool()
    def browser_start() -> dict[str, Any]:
        """Open the CS Desk browser window on the MCA home page so she can log in; captcha and OTP are hers.
        If it is already open, says so. The window has its own profile, so she stays logged in between uses
        until MCA ends the session."""
        info = chrome.launch(settings)
        with open_vault() as vault:
            vault.log("browser start", info)
        return {**info, "next": "Ask her to log in to MCA in the CS Desk window, then check browser_status."}

    @tool()
    async def browser_status() -> dict[str, Any]:
        """Whether the CS Desk browser is open, its tabs (and which one she has in front), and whether each MCA
        tab looks logged in (a visible Logout link). Lists any dialog box waiting for her. Check this before
        filling a form."""
        return await session.status(settings)

    @tool()
    async def browser_open(url: str) -> dict[str, Any]:
        """Open a page in a new tab of the CS Desk browser. Allowed: https pages on mca.gov.in, gst.gov.in,
        incometax.gov.in and icsi.edu, never payment or signing pages. Pass "practice" to open the bundled
        practice form (DEMO-1), which is safe for trying the fill loop."""
        if url.strip().lower() in ("practice", "demo"):
            url = session.DEMO_FORM.as_uri()
        result = await session.open_url(settings, url)
        with open_vault() as vault:
            vault.log("browser open", {"url": url})
        return result

    @tool(structured=False)
    async def browser_screenshot(tab: int | None = None, filing_id: int | None = None) -> list[Any]:
        """See what a tab of the CS Desk browser shows right now. The full page is also saved, in the
        filing's evidence folder when filing_id is given, otherwise in screenshots/."""
        folder = "screenshots"
        if filing_id is not None:
            with open_vault() as vault:
                folder = vault.filing(filing_id)["folder"] or folder
        path, view = await session.screenshot(settings, settings.home / folder, tab)
        return [f"Full page saved to {path}", Image(data=view, format="jpeg")]

    @tool(structured=False)
    async def fill_form(
        filing_id: int,
        party_id: int | None = None,
        extra: dict[str, str] | None = None,
        tab: int | None = None,
        recipe: str | None = None,
    ) -> list[Any]:
        """Fill the open portal form for a filing from the company file, using the recorded recipe for its
        form. Types and reads back each field, saves a draft if the recipe has a save button, keeps a fill log
        and screenshot as evidence, then stops: she reviews, submits, signs with her DSC and pays. `party_id`
        is the person the form is about (e.g. the director being appointed); `extra` holds values the company
        file doesn't, e.g. {"date_of_appointment": "2026-10-01", "designation": "Additional Director"}.
        `recipe` picks one step of a form recorded in several steps, e.g. "DIR-12/step2". Dialog boxes the
        portal opens are left for her to answer and are listed in the result."""
        with open_vault() as vault:
            filing = vault.filing(filing_id)
            chosen = recipe_for(recipe or filing["form"])
            values = build_values(vault, filing, party_id, extra)
            evidence = settings.home / (filing["folder"] or f"clients/{vault.company_folder(filing['company_id'])}/filings/{filing_id}")
        dialogs: list[dict[str, str]] = []
        async with session.attached(settings, dialogs) as browser:
            page = await session.pick_tab(browser, tab, chosen.url_contains)
            report = await fill(page, chosen, values, evidence)
            try:
                view = await page.screenshot(type="jpeg", quality=80, timeout=session.SCREENSHOT_TIMEOUT_MS)
            except PlaywrightError:
                view = None
        with open_vault() as vault:
            status = "in_progress" if report.mismatches else "ready_for_review"
            vault.save("filing", {"status": status}, Source("derived", "claude", note=f"filled with recipe {chosen.code}"), filing_id)
            vault.log(
                "fill form",
                {"filing_id": filing_id, "recipe": chosen.code, "filled": len(report.filled), "missing": report.missing, "mismatches": report.mismatches},
            )
        summary = {
            "filing_id": filing_id,
            "form": chosen.code,
            "status": status,
            "filled": report.filled,
            "missing": report.missing,
            "mismatches": report.mismatches,
            "draft_saved": report.saved,
            "fill_log": report.log_path,
            "screenshot": report.screenshot_path,
            "notes": report.notes,
            "dialogs_waiting_for_her": dialogs,
            "for_her": chosen.hand_over,
        }
        content: list[Any] = [json.dumps(summary, indent=2)]
        if view is not None:
            content.append(Image(data=view, format="jpeg"))
        return content

    # ------------------------------------------------------------- recording

    @tool()
    async def record_start(
        form: str, company: str | None = None, party_id: int | None = None, max_minutes: int = 120
    ) -> dict[str, Any]:
        """Start recording how she fills a portal form in the CS Desk browser, to write its recipe from. She
        logs in and opens the form first, then fills it as usual on a draft she won't submit. The recorder only
        watches: it notes each page's fields, what she changes, the buttons she presses, dialogs and the portal's
        requests. Typed values are kept only as their shape and the company-file field they match, so give the
        company (and the person, e.g. the director being appointed) for the matching to work."""
        current = recorder.active(settings)
        if current is not None:
            raise ToolError(f"Recording {current.name} is still running; stop it with record_stop first.")
        if chrome.debug_info(settings.cdp_port) is None:
            raise ToolError("The CS Desk browser window isn't open. Use browser_start, let her log in, then start recording.")
        folder = recorder.new_recording(settings, form, company, party_id, max_minutes)
        pid = recorder.spawn(settings, folder)
        result = await recorder.wait_for(folder, ("started.json", "error.json"), 45)
        if result != "started.json":
            raise ToolError(recorder.read_error(folder) if result else "The recorder didn't start within 45 seconds; see recorder.log.")
        with open_vault() as vault:
            vault.log("record start", {"recording": folder.name, "form": form, "pid": pid})
        return {
            "recording": folder.name,
            "folder": str(folder),
            "for_her": "Recording has started. Fill the form as you normally would and save the draft. Don't submit. "
            "Tell me when you're done.",
        }

    @tool()
    def record_status() -> dict[str, Any]:
        """Whether a recording is running, and how much it has captured so far."""
        folder = recorder.active(settings)
        if folder is None:
            return {"running": False}
        return {"running": True, "recording": folder.name, "captured": recorder.counts(folder)}

    @tool()
    async def record_stop(recording: str | None = None) -> dict[str, Any]:
        """Stop the running recording and write up what it captured: flow.md (each step's fields, what she
        entered by shape, which company-file field matched, buttons, dialogs and the portal's requests) and
        recipe_draft.py, a draft recipe with TODOs to review. Returns the flow text and the review list."""
        folder = recorder.find(settings, recording)
        if not (folder / "done.json").exists():
            (folder / "STOP").touch()
            finished = await recorder.wait_for(folder, ("done.json", "error.json"), 60)
            if finished != "done.json":
                if recorder.is_running(folder):
                    raise ToolError("The recorder is still finishing; call record_stop again in a moment.")
                summary = recorder.build(folder)  # write up what was captured before it stopped
                summary["note"] = recorder.read_error(folder) if finished else "The recorder had stopped; this is what it captured."
            else:
                summary = json.loads((folder / "done.json").read_text(encoding="utf-8"))
        else:
            summary = json.loads((folder / "done.json").read_text(encoding="utf-8"))
        with open_vault() as vault:
            vault.log("record stop", {"recording": folder.name, "fields": summary.get("fields_filled")})
        summary["flow_markdown"] = Path(summary["flow"]).read_text(encoding="utf-8")
        return summary

    # --------------------------------------------------- drafting, law, dossier

    @tool()
    def list_templates() -> dict[str, Any]:
        """Her Word templates and the `extra` values each one needs."""
        drafting.ensure_sample(settings.templates_dir)
        return {"folder": str(settings.templates_dir), "templates": drafting.list_templates(settings.templates_dir)}

    @tool()
    def render_draft(company: str, template: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
        """Make a Word draft from one of her templates, filled from the company file plus `extra` (see
        list_templates for what each template needs). It is saved in the company's drafts folder for her to
        review and edit."""
        with open_vault() as vault:
            return drafting.render(vault, settings, vault.resolve_company(company), template, extra)

    @tool()
    def law_search(query: str, limit: int = 8) -> dict[str, Any]:
        """Search the Acts, Rules, Secretarial Standards and circulars in her law folder. Each result gives
        the file, the section or page, and a passage. Cite them when you answer."""
        return lawdesk.search(settings, query, limit)

    @tool()
    def build_dossier(company: str) -> dict[str, Any]:
        """Write a dossier on a company from the company file: snapshot, directors and their other companies on
        file, auditors, charges, meetings, overdue and upcoming filings, gaps, and where each fact came from.
        Saved as Markdown in the company's dossier folder; the text is returned too."""
        with open_vault() as vault:
            return dossier.build(vault, settings, vault.resolve_company(company), date.today())

    @tool()
    def csdesk_info() -> dict[str, Any]:
        """Where CS Desk keeps things on this computer, and which document types and form recipes it knows."""
        return {
            "version": __version__,
            "data_folder": str(settings.home),
            "inbox": str(settings.inbox_dir),
            "templates": str(settings.templates_dir),
            "law_folder": str(settings.law_dir),
            "form_recipes": {code: recipe.title for code, recipe in RECIPES.items()},
            "document_types": DOC_TYPES,
        }

    return server


def _ranges(pages: list[int]) -> str:
    spans: list[str] = []
    start = prev = pages[0]
    for page in pages[1:] + [None]:  # type: ignore[list-item]
        if page is not None and page == prev + 1:
            prev = page
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        if page is not None:
            start = prev = page
    return ", ".join(spans)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "form"
