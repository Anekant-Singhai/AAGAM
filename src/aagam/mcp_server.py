"""AAGAM for Claude Desktop: every CS Desk tool, plus the library, precedents and calculators.

Claude Desktop starts this as `aagam mcp`. It is the core's server with
AAGAM's tools added, and with document intake replaced by AAGAM's, which
also indexes each document (type, facts, resolutions, tags).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from csdesk.documents.intake import DOC_TYPES
from csdesk.server import INSTRUCTIONS as CORE_INSTRUCTIONS
from csdesk.server import build_server, tool_registrar

from . import (
    ai,
    analysis,
    checklists,
    checks,
    entities,
    everything,
    finance,
    folders,
    library,
    precedents,
    review,
    workbook,
)
from .config import AagamSettings
from .db import open_db

DocType = Literal[tuple(DOC_TYPES)]  # type: ignore[valid-type]
FileKind = Literal[tuple(library.FILE_KINDS)]  # type: ignore[valid-type]
FOLDER_SECONDS = 40  # how long ingest_folder reads before handing the rest to the background
EntityKind = Literal[tuple(entities.KINDS)]  # type: ignore[valid-type]
WorkKind = Literal[tuple(checklists.KINDS)]  # type: ignore[valid-type]

INSTRUCTIONS = (
    CORE_INSTRUCTIONS
    + """
AAGAM adds a document library and a precedent library on top of the company file:
- ingest_document / ingest_inbox bring documents in and index them: type, facts (CIN, DIN with the person,
  amounts, dates, sections), tags, and for notices each resolution with its explanatory statement.
- ingest_folder brings in a whole folder with the folders inside it, each document filed under the client its
  CIN, LLPIN, folder name or company name points to; folder_status follows a large one as it is read.
- library_search finds words across every page; library_document shows what is known about one document.
  Read the pages themselves with read_document before relying on a fact.
- precedent_search finds resolutions from notices on file by section, topic, kind, amount and words. Use it
  to start a draft; adapt the wording to her company and check it against the Act before suggesting it.
- loan_limits works out the s.186 limit (and s.180(1)(c), s.185 conditions) from balance-sheet figures.
- financial_statements / financial_analysis read a balance sheet and P&L into figures, the Schedule III ratios,
  and what applies to the company with the work it means for her. Check the figures against the pages before
  relying on them; correct a line with financial_correct and settle "check" items with financial_facts.
- search_everything searches all of it at once; entity_dossier gathers everything on one person or company.
- Her work register (work_*) keeps each job with its checklist, documents and notes; open work there when she
  starts a job, and link the documents you use. notice_check reviews a draft notice against the rules first.
- When you read a document she hasn't summarised, save a short summary with library_save_summary so the
  library shows it. Local AI may already have written one; yours replaces it, hers is never replaced.
- document_analysis gives what AAGAM's rules read in a document for six purposes (investments, legal matters,
  law cited, amendments, obligations, agreement terms); insights gives one purpose across the library. Both are
  rule-based readings with a confidence each: confirm anything important against the page before relying on it.
- LLPs are on the same footing: an LLPIN (AAB-1234) identifies one (entity_dossier with kind "llpin"); its due dates
  are Form 11 (30 May), Form 8 (30 October), Form 3 (the LLP agreement, within 30 days of incorporation or a change),
  Form 4 (partners, 30 days), Form 15 (registered office), Form 5 (name) and LLP BEN-2; work_create has LLP jobs.
"""
)


def _brief_item(item: dict[str, Any]) -> dict[str, Any]:
    """An analysis item for Claude: empty fields left out, the words around it cut to a useful length."""
    out = {k: v for k, v in item.items() if v not in (None, "", [], {})}
    if len(str(out.get("context", ""))) > 300:
        out["context"] = str(out["context"])[:300] + "…"
    return out


def _brief_analysis(found: dict[str, Any]) -> dict[str, Any]:
    return {"kind": found["kind"], "title": found["title"], "score": found["score"], "summary": found["summary"],
            "facts": found["facts"], "items": [_brief_item(i) for i in found["items"]],
            "key_sentences": [{"page": h["page"], "text": h["text"][:300]} for h in found["highlights"]]}


def build(settings: AagamSettings) -> MCPServer:
    core = settings.core
    server = build_server(core, name="aagam", instructions=INSTRUCTIONS)
    for replaced in ("ingest_document", "ingest_inbox"):
        server.remove_tool(replaced)
    tool = tool_registrar(server)

    def db() -> Any:
        return open_db(core.db_path, actor="claude")

    @tool()
    def ingest_document(
        path: str,
        company: str | None = None,
        doc_type: DocType | None = None,
        tags: list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Bring a file on this computer into the library (PDF, Word, Excel, email, web page, image or text) and
        index it. The original is copied, not moved. Leave doc_type empty to work it out from the text, and company
        empty to file it under the client its CIN, LLPIN or company name points to. Tag listed companies' notices
        "precedent" so their resolutions are easy to find as precedents."""
        origin = library.Origin.of_file(path) if Path(path).expanduser().is_file() else None
        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            return library.add_document(vault, core, path, company_id, doc_type, tags, note, origin=origin,
                                        work_out_client=company is None)

    @tool(description=f"Bring in every file in the inbox folder ({core.inbox_dir}) and index it, then move each to inbox/processed/<date>.")
    def ingest_inbox(company: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        from csdesk.documents.intake import ingest_inbox as core_inbox

        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            results = core_inbox(vault, core, company_id)
            for result in results:
                if result.get("document_id"):
                    if not result.get("already_on_file"):
                        library.index_new(vault, core, result["document_id"])
                    for tag in tags or []:
                        library.add_tag(vault, result["document_id"], tag)
            return {"files": results}

    @tool()
    def library_search(
        query: str, company: str | None = None, doc_type: DocType | None = None, tag: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Find documents by words on their pages. Every word must appear; "quoted words" must appear together.
        Each result lists the matching pages and up to three passages, with the matches in [[double brackets]]."""
        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            return library.search(vault, query, company_id, doc_type, tag, limit)

    @tool()
    def library_list(
        company: str | None = None,
        doc_type: DocType | None = None,
        tag: str | None = None,
        limit: int = 30,
        fy: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        folder_id: int | None = None,
        kind: FileKind | None = None,
        sort: Literal["added", "newest", "oldest", "name"] = "added",
    ) -> dict[str, Any]:
        """Documents in the library, last added first (or by their own date: newest, oldest; or by name), with type,
        date, tags and whether they have a summary. Narrow by client, type, tag, financial year ("2024-25"), dates
        (YYYY-MM-DD, by the document's own date), the folder they came from (ids from folder_status) or kind of file."""
        more = {k: v for k, v in {"fy": fy, "date_from": date_from, "date_to": date_to, "folder_id": folder_id, "kind": kind}.items()
                if v is not None}
        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            return library.list_documents(vault, company_id, doc_type, tag, limit, sort=sort, **more)

    @tool()
    def library_document(document_id: int) -> dict[str, Any]:
        """Everything known about one document: type and why, company and meeting, summary (and who wrote it),
        tags, facts found with their pages, and its resolutions. PANs are masked."""
        with db() as vault:
            return library.document(vault, document_id)

    @tool()
    def library_search_in_document(document_id: int, query: str) -> dict[str, Any]:
        """Which pages of one document contain these words, with a passage from each."""
        with db() as vault:
            return library.search_in_document(vault, document_id, query)

    @tool()
    def library_save_summary(document_id: int, summary: str, key_points: list[str] | None = None) -> dict[str, Any]:
        """Save your summary of a document (3 to 5 sentences, plus key points such as amounts, dates and sections),
        so the library shows it. It replaces a local AI summary; one she wrote herself is kept."""
        with db() as vault:
            library.save_summary(vault, document_id, summary, "claude", key_points)
            return library.document(vault, document_id, brief=True)

    @tool()
    def library_tag(document_id: int, add: list[str] | None = None, remove: list[str] | None = None) -> dict[str, Any]:
        """Add or remove tags on a document. Tags are short lowercase words or phrases, e.g. "precedent", "s.186"."""
        with db() as vault:
            for name in add or []:
                library.add_tag(vault, document_id, name, by="claude")
            for name in remove or []:
                library.remove_tag(vault, document_id, name)
            return {"tags": library.document(vault, document_id, brief=True)["tags"]}

    @tool()
    def precedent_search(
        query: str = "",
        section: str | None = None,
        topic: str | None = None,
        resolution_kind: Literal["special", "ordinary"] | None = None,
        min_crore: float | None = None,
        max_crore: float | None = None,
        with_statement: bool = False,
        limit: int = 15,
    ) -> dict[str, Any]:
        """Resolutions from every notice on file. Filter by section ("186"), topic ("loans-investments",
        "loans-to-directors", "borrowing-powers", "related-party", "auditors", "independent-director", ...),
        special or ordinary, the amount in the resolution (in crore), and words. Each result says which company's
        notice it is from; fetch the full text with precedent_get."""
        with db() as vault:
            return precedents.search(
                vault,
                query,
                section,
                topic,
                resolution_kind,
                round(min_crore * 10_000_000) if min_crore is not None else None,
                round(max_crore * 10_000_000) if max_crore is not None else None,
                with_statement,
                limit,
            )

    @tool()
    def precedent_get(resolution_id: int) -> dict[str, Any]:
        """One resolution in full: its heading, the resolution text, its explanatory statement, and the notice it
        came from (document, pages, company, meeting)."""
        with db() as vault:
            return precedents.get(vault, resolution_id)

    @tool()
    def loan_limits(
        paid_up_capital: int,
        free_reserves: int,
        securities_premium: int = 0,
        proposed_loans_investments: int = 0,
        outstanding_loans_investments: int = 0,
        proposed_borrowing: int = 0,
        outstanding_borrowing: int = 0,
        company: str | None = None,
        to_wholly_owned_subsidiary: bool = False,
        include_director_loans: bool = False,
    ) -> dict[str, Any]:
        """Work out the s.186 limit for loans, guarantees, security and investments (and the s.180(1)(c) borrowing
        limit when borrowing figures are given; s.185 conditions when asked), and whether the proposal needs a
        special resolution. Amounts in whole rupees, from the latest audited balance sheet. Give the company to
        apply its class (private companies have exemptions)."""
        company_class = None
        if company:
            with db() as vault:
                company_class = vault.company_row(vault.resolve_company(company))["company_class"]
        return checks.loans_and_borrowing(
            paid_up_capital, free_reserves, securities_premium, proposed_loans_investments, outstanding_loans_investments,
            proposed_borrowing, outstanding_borrowing, company_class, to_wholly_owned_subsidiary, include_director_loans,
        )

    @tool()
    def search_everything(query: str) -> dict[str, Any]:
        """One search across documents, resolutions, people and companies found in documents, the company file and
        financial statements. Says when the query looks like a CIN, GSTIN, DIN or PAN."""
        with db() as vault:
            return everything.search_all(vault, query)

    @tool()
    def entity_list(kind: EntityKind | None = None, query: str = "", limit: int = 50) -> dict[str, Any]:
        """People, companies and identifiers found across all documents, grouped however they were spelt, with how many
        documents mention each. Use the kind and key from here with entity_dossier."""
        with db() as vault:
            return entities.browse(vault, kind, query, limit)

    @tool()
    def entity_dossier(kind: EntityKind, name: str) -> dict[str, Any]:
        """Everything on one person, company or identifier: every document it appears in (pages and context), the
        company-file records it matches, its identifiers, who and what it appears with, and for a company its
        resolutions and financial statements. `name` can be written any way; it is matched by its key."""
        with db() as vault:
            return entities.dossier(vault, kind, entities.key_of(kind, name))

    @tool()
    def gstin_details(gstin: str) -> dict[str, Any]:
        """Decode a GSTIN: state, the PAN inside it (masked), which registration on that PAN it is, and where to verify it."""
        return entities.gstin_info(gstin)

    @tool()
    def financial_statements(document_id: int | None = None, company: str | None = None) -> dict[str, Any]:
        """Financial statements read from documents: list them for a company, or read them from a document now.
        Then use financial_analysis with the id."""
        with db() as vault:
            if document_id is not None:
                ids = finance.extract(vault, document_id, core.home)
                if not ids:
                    return {"statements": [], "message": "No balance sheet or statement of profit and loss was found in this document."}
                return {"statements": [r for r in finance.listing(vault) if r["id"] in ids]}
            return {"statements": finance.listing(vault, vault.resolve_company(company) if company else None)}

    @tool()
    def financial_analysis(financial_id: int) -> dict[str, Any]:
        """The figures read from a balance sheet and P&L (with pages), the eleven Schedule III ratios with the change
        from last year (changes over 25% need an explanation in the notes), the liability profile, warnings, and what
        applies to the company (small company, CSR, secretarial audit, internal audit, whole-time CS, independent
        directors, XBRL, CARO, tax audit, MSME-1, DPT-3), each with the work it means for her."""
        with db() as vault:
            return finance.analysis(vault, financial_id)

    @tool()
    def financial_correct(financial_id: int, line: str, current: int | None = None, previous: int | None = None) -> dict[str, Any]:
        """Correct or add one line of the statements (whole rupees), e.g. line "trade_receivables". Corrections are kept
        when the document is read again. Returns the analysis recomputed."""
        with db() as vault:
            return finance.correct(vault, financial_id, line, current, previous)

    @tool()
    def financial_facts(
        financial_id: int,
        company_class: Literal["private", "public", "opc"] | None = None,
        listed: bool | None = None,
        holding_or_subsidiary: bool | None = None,
        bank_borrowings: int | None = None,
        deposits: int | None = None,
        principal_repaid: int | None = None,
    ) -> dict[str, Any]:
        """Record facts the statements don't show, which settle the "check" items in the applicability list."""
        given = {k: v for k, v in {"company_class": company_class, "listed": listed, "holding_or_subsidiary": holding_or_subsidiary,
                                   "bank_borrowings": bank_borrowings, "deposits": deposits, "principal_repaid": principal_repaid}.items() if v is not None}
        with db() as vault:
            return finance.set_facts(vault, financial_id, given)

    @tool()
    def notice_check(document_id: int) -> dict[str, Any]:
        """Check a notice of a general meeting against the rules, without AI: meeting date and 21 clear days,
        explanatory statements for special business with interests disclosed (s.102), special resolutions where the
        Act needs them, s.185 particulars and s.186 amounts, proxies (s.105), route map (SS-2), e-voting (rule 20),
        signature, CIN. Each finding says ok, missing or check, with the rule and page."""
        with db() as vault:
            return review.check_notice(vault, document_id)

    @tool()
    def work_list(status: Literal["open", "waiting", "done", "dropped"] | None = None, company: str | None = None, query: str = "") -> dict[str, Any]:
        """Her work register: every job (AGM, board meeting, director appointment, allotment, charge, annual filing,
        due diligence, secretarial audit, LLP jobs...), open ones first, with checklist progress."""
        with db() as vault:
            return {"works": workbook.list_works(vault, status, vault.resolve_company(company) if company else None, query)}

    @tool()
    def work_create(
        title: str,
        kind: WorkKind,
        company: str | None = None,
        due_on: str | None = None,
        meeting_date: str | None = None,
    ) -> dict[str, Any]:
        """Open a piece of work with the standard checklist for its kind (each step with its legal basis). LLP jobs:
        llp_incorporation, llp_annual_filing (Form 8 and Form 11), llp_partner_change (Form 4), llp_agreement_change
        (Form 3), llp_office_change (Form 15), llp_name_change (Form 5), llp_strike_off (Form 24)."""
        with db() as vault:
            return workbook.create_work(vault, title, kind, vault.resolve_company(company) if company else None, due_on, meeting_date)

    @tool()
    def work_get(work_id: int) -> dict[str, Any]:
        """One piece of work: checklist with ticks, linked documents and notes."""
        with db() as vault:
            return workbook.work(vault, work_id)

    @tool()
    def work_update(
        work_id: int,
        tick_step: int | None = None,
        untick_step: int | None = None,
        step_note: str | None = None,
        status: Literal["open", "waiting", "done", "dropped"] | None = None,
        attach_document: int | None = None,
    ) -> dict[str, Any]:
        """Tick or untick a checklist step (numbered from 1), note on that step, change the status, or link a
        document. Tick only what she has confirmed is done."""
        with db() as vault:
            if tick_step is not None:
                workbook.tick(vault, work_id, tick_step - 1, True, step_note)
            if untick_step is not None:
                workbook.tick(vault, work_id, untick_step - 1, False, step_note)
            if attach_document is not None:
                workbook.attach(vault, work_id, attach_document)
            if status:
                workbook.change_work(vault, work_id, status=status)
            return workbook.work(vault, work_id)

    @tool()
    def document_analysis(document_id: int) -> dict[str, Any]:
        """What AAGAM's rules found in a document, purpose by purpose: investments (s.186), legal matters, law cited,
        amendments, obligations and deadlines, agreement terms. Each item has its page and the words around it."""
        with db() as vault:
            library.document(vault, document_id, brief=True)
            return {"analyses": [_brief_analysis(a) for a in analysis.for_document(vault, document_id)]}

    @tool()
    def insights(kind: Literal["investments", "legal", "law", "amendments", "obligations", "agreements"], query: str = "",
                 company: str | None = None) -> dict[str, Any]:
        """A register across the whole library: every investment, legal matter, provision cited, amendment, obligation
        or agreement term found, with its document and page. `query` narrows it (e.g. "186", "NCLT", "Acme")."""
        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            out = analysis.register(vault, kind, query, company_id, limit=300)
            return {"kind": out["kind"], "title": out["title"], "count": out["count"], "items": [_brief_item(i) for i in out["items"]]}

    @tool()
    def note_add(text: str, on: Literal["general", "document", "company", "entity", "work", "resolution", "financials"] = "general",
                 target: str = "", pinned: bool = False) -> dict[str, Any]:
        """Add a note: on a document (target = its id), company (id), entity ("person:asha rao"), work (id),
        resolution (id), financial statements (id), or a general note."""
        with db() as vault:
            return workbook.add_note(vault, text, on, target, pinned, by="claude")

    @tool()
    def notes_search(query: str = "") -> dict[str, Any]:
        """Her notes matching the words, or the latest ones."""
        with db() as vault:
            return {"notes": workbook.search_notes(vault, query)}

    @tool()
    def local_ai_status() -> dict[str, Any]:
        """Whether local AI (Ollama) is running with its model installed, and how many documents wait for a summary."""
        status = ai.LocalAI.from_settings(settings).status() if settings.local_ai else {"running": False, "message": "Local AI is turned off."}
        with db() as vault:
            status["queued"] = vault.conn.execute("SELECT COUNT(*) FROM ai_jobs WHERE status = 'queued'").fetchone()[0]
        return status

    @tool()
    def ingest_folder(
        path: str, company: str | None = None, tags: list[str] | None = None, precedent: bool = False, watch: bool = False
    ) -> dict[str, Any]:
        """Bring a whole folder on this computer into the library: every file AAGAM can read in it and in the folders
        inside it is copied in (her files stay where they are) and read like ingest_document. Each document is filed
        under the client its CIN, LLPIN, folder name or company name points to, unless `company` is given.
        `precedent`: other companies' documents, for the precedent library (no client). `watch`: new files are
        brought in while the AAGAM window is open. A large folder is read for about 40 seconds now and the rest in
        the background (or by calling this again); follow it with folder_status."""
        with db() as vault:
            company_id = vault.resolve_company(company) if company else None
            folder = folders.add_folder(vault, core.home, path, "one" if company_id else "auto", company_id, None, tags or [],
                                        precedent, watch)
        folders.run_queue(core, f"mcp:{os.getpid()}", folder_id=folder["id"], budget=FOLDER_SECONDS)
        with db() as vault:
            return folders.get(vault, folder["id"], details=True)

    @tool()
    def folder_status(folder_id: int | None = None) -> dict[str, Any]:
        """The folders brought into the library, with how far each has been read (found, done, added, already in
        the library, failed) and what was left out; with folder_id, that one with the files that couldn't be read."""
        with db() as vault:
            if folder_id is not None:
                return folders.get(vault, folder_id, details=True)
            return {"folders": folders.listing(vault)}

    return server
