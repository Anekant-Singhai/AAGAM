"""Checking a notice of a general meeting before it goes out, without any AI.

Each check reads the notice as AAGAM has already split it (items, kinds,
statements, sections, amounts, pages) and its text, and reports one of:

  ok        the notice does what the rule asks
  missing   something the rule asks for isn't there
  check     AAGAM can't tell from the text; she should look

with the rule it rests on and the page to look at. This is what a second
pair of eyes does on a draft notice; it doesn't replace reading it.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from csdesk.errors import Invalid
from csdesk.vault import Vault

from . import library
from .extract import DATE_PATTERNS, parse_date

# Matters the Act requires a special resolution for, by section.
SPECIAL_REQUIRED = {
    "185": "s.185(2)", "186": "s.186(3) (when over the limit)", "180": "s.180(1)", "14": "s.14(1)", "13": "s.13(1)",
    "68": "s.68(2)(b)", "66": "s.66(1)", "62": "s.62(1)(c)", "42": "s.42(2)", "149": "s.149(10) (an independent director's second term)",
}
SIGNATURE = re.compile(r"(?i)by\s+order\s+of\s+the\s+board|on\s+behalf\s+of\s+the\s+board")


def check_notice(vault: Vault, document_id: int) -> dict[str, Any]:
    doc = library.document(vault, document_id)
    if doc["doc_type"] not in ("notice", "annual_report") and not doc["resolutions"]:
        raise Invalid("This isn't a notice of a meeting, so there's nothing to check here.")
    pages = library.pages_of(vault, document_id)
    text = "\n".join(t for _, t in pages)
    clauses = vault._rows("SELECT * FROM clauses WHERE document_id = ? ORDER BY item_no", (document_id,))
    findings: list[dict[str, Any]] = []

    def add(status: str, what: str, basis: str | None = None, page: int | None = None, item: int | None = None) -> None:
        findings.append({"status": status, "text": what, "basis": basis, "page": page, "item": item})

    def page_of(pattern: str) -> int | None:
        for page_no, page_text in pages:
            if re.search(pattern, page_text, re.IGNORECASE):
                return page_no
        return None

    kind = doc["meeting_kind"]
    physical = any("without" not in text[max(0, m.start() - 20): m.start()].lower()
                   for m in re.finditer(r"(?i)physical\s+presence", text))
    vc_only = bool(re.search(r"(?i)video\s+conferenc|\bOAVM\b|other\s+audio[\s-]?visual", text)) and not physical

    # The meeting itself.
    if doc["meeting_date"]:
        add("ok", f"Meeting date found: {doc['meeting_date']}.", "s.101(2)")
    else:
        add("check", "AAGAM couldn't find the meeting's date; check the notice states the day, date and time.", "s.101(2); SS-2 para 1.2")
    if doc["company_cin"] or doc["facts"].get("cin"):
        add("ok", "The CIN is printed.", "s.12(3)(c)")
    else:
        add("missing", "No CIN found. A company's notices must show its CIN, registered office, phone and email.", "s.12(3)(c)")

    # Notice period: clear days between the notice date and the meeting.
    notice_date = _notice_date(text)
    if doc["meeting_date"] and notice_date:
        meeting = date.fromisoformat(doc["meeting_date"])
        clear = (meeting - notice_date).days - 1
        if clear >= 21:
            add("ok", f"Notice dated {notice_date.isoformat()} gives {clear} clear days.", "s.101(1)")
        else:
            add("missing", f"Notice dated {notice_date.isoformat()} gives only {clear} clear days; 21 are needed unless members consent to shorter notice (95%).", "s.101(1)")
    elif doc["meeting_date"]:
        add("check", "The notice's own date wasn't found, so the 21 clear days can't be checked.", "s.101(1)")

    # Items: kinds, statements, amounts.
    if not clauses:
        add("check", "No numbered items were found; check the business is set out item by item.", "s.101(2)")
    special_business = [c for c in clauses if c["business"] == "special"]
    for c in special_business:
        if not c["statement"]:
            add("missing", f"Item {c['item_no']} is special business but has no explanatory statement.", "s.102(1)", c["page_from"], c["item_no"])
        elif not re.search(r"(?i)(?:concerned|interested)\s*(?:,|or|and|/)\s*(?:in\s+any\s+way\s+)?(?:concerned|interested)|interest(?:ed)?\s+(?:financially|in\s+the\s+resolution)", c["statement"]):
            add("check", f"Item {c['item_no']}'s statement doesn't say whether directors and KMP are concerned or interested.", "s.102(1)(a)", c["page_from"], c["item_no"])
    for c in clauses:
        sections = c["sections"].split()
        base = [s.split("(")[0] for s in sections]
        for section, rule in SPECIAL_REQUIRED.items():
            if section == "149" and not re.search(r"(?i)re-?appoint.*independent|independent.*second\s+term", c["title"]):
                continue  # only an independent director's second term needs a special resolution
            if section in base and c["resolution_kind"] != "special":
                add("check", f"Item {c['item_no']} relies on s.{section}, which needs a special resolution ({rule}), but it isn't proposed as one.", rule, c["page_from"], c["item_no"])
        if "186" in base:
            if c["max_amount"]:
                add("ok", f"Item {c['item_no']} (s.186) states the amount: ₹{c['max_amount'] / 10_000_000:,.2f} crore.", "s.186(3)", c["page_from"], c["item_no"])
            else:
                add("check", f"Item {c['item_no']} (s.186) doesn't state an amount; the special resolution should say how far the Board may go.", "s.186(3); rule 11", c["page_from"], c["item_no"])
        if "185" in base:
            statement = c["statement"] or ""
            wanted = [("the purpose", r"(?i)purpose|principal\s+business"), ("the amount", r"(?i)(?:₹|rs\.?|`|inr)\s*[\d,]|crore|lakh|per\s*cent"),
                      ("the borrower", r"(?i)subsidiar|associate|joint\s+venture|entit|body\s+corporate|company")]
            gaps = [name for name, pattern in wanted if not re.search(pattern, statement)]
            if gaps:
                add("check", f"Item {c['item_no']} (s.185): the statement should give full particulars; AAGAM didn't find {', '.join(gaps)}.", "s.185(2)(a)", c["page_from"], c["item_no"])
            else:
                add("ok", f"Item {c['item_no']} (s.185): the statement covers the purpose, amount and borrower.", "s.185(2)(a)", c["page_from"], c["item_no"])

    # The rest of the notice.
    if vc_only:
        add("ok", "A meeting held only by video conference: no proxy statement or route map is needed.", "MCA circulars on VC meetings")
    else:
        proxy = page_of(r"entitled\s+to\s+appoint\s+a\s+proxy")
        add("ok" if proxy else "missing", "Statement on appointing proxies" + (" is there." if proxy else " not found."), "s.105(2)", proxy)
        route = page_of(r"route\s+map")
        add("ok" if route else "check", "Route map" + (" is there." if route else " not found; SS-2 asks for one with the notice."), "SS-2 para 1.2.4", route)
    evoting = page_of(r"e-?voting")
    add("ok" if evoting else "check", "Remote e-voting" + (" is explained." if evoting else " isn't mentioned; it is required if the company is listed or has 1,000 or more members."), "s.108; rule 20", evoting)
    signed = page_of(SIGNATURE.pattern)
    add("ok" if signed else "missing", "Signed by order of the Board" + (" (and dated)." if signed else ": not found."), "SS-2 para 1.2", signed)
    if kind == "agm":
        has_accounts = any(re.search(r"(?i)financial\s+statements|balance\s+sheet|accounts", c["title"]) for c in clauses)
        add("ok" if has_accounts else "missing", "Adoption of the financial statements" + (" is an item." if has_accounts else " isn't among the items."), "s.102(2)(a)")
        rotation = any(re.search(r"(?i)retires?\s+by\s+rotation", c["title"] + (c["body"] or "")) for c in clauses)
        add("ok" if rotation else "check", "A director retiring by rotation" + (" is an item." if rotation else " isn't among the items; needed for a public company."), "s.152(6)")

    order = {"missing": 0, "check": 1, "ok": 2}
    findings.sort(key=lambda f: (order[f["status"]], f["item"] or 0))
    counts = {s: sum(1 for f in findings if f["status"] == s) for s in order}
    return {"document_id": document_id, "meeting_kind": kind, "notice_date": notice_date.isoformat() if notice_date else None,
            "findings": findings, "counts": counts}


def _notice_date(text: str) -> date | None:
    """The date under the signature ("By order of the Board ... Date: 13 August 2024")."""
    m = SIGNATURE.search(text)
    windows = [text[m.start(): m.start() + 500]] if m else []
    windows.append(text)
    for window in windows:
        dated = re.search(r"(?im)^\s*(?:date|dated)\s*[:\-]?\s*(.{6,40})$|(?:date|dated)\s*[:\-]\s*(.{6,30})", window)
        if dated:
            day = _first_date(dated.group(1) or dated.group(2))
            if day:
                return day
    # No "Date:" label: the first date after the signature ("Jaipur, July 05, 2022").
    return _first_date(windows[0]) if m else None


def _first_date(chunk: str) -> date | None:
    hits = []
    for index, pattern in enumerate(DATE_PATTERNS):
        for found in pattern.finditer(chunk):
            day = parse_date(found.groups(), index)
            if day:
                hits.append((found.start(), day))
    return min(hits)[1] if hits else None
