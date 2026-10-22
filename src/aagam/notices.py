"""Splitting a notice of a general meeting into its resolutions and explanatory statements.

Notices follow a common shape (Ordinary Business, Special Business, numbered
items, "to pass the following resolution as a Special Resolution", "RESOLVED
THAT ...", then Notes and the Explanatory Statement under section 102), but
every company lays it out differently. The splitter works from that shape, and
on real notices from listed companies:

- headers and footers repeated on every page are removed first;
- items are numbered lines, accepted only when the numbering runs in order,
  so a numbered list inside a resolution isn't mistaken for a new item;
- special business numbered from 1 again is renumbered to follow on;
- explanatory statements are matched to their items by number, or by order
  when the statement numbers its items from 1 again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import largest_amount, sections_of
from .text import Joined, join_pages, reflow, strip_running_lines

START = re.compile(r"(?i)notice\s+is\s+hereby\s+given|^\s*(?:\d+\.|[IVX]+\.|[A-Z]\.)?\s*ordinary\s+business", re.MULTILINE)
BUSINESS = re.compile(r"(?im)^[ \t]*(?:\d+\.|[IVX]+\.|[A-Z]\.|\(?[a-z]\))?[ \t]*(ORDINARY|SPECIAL)[ \t]+BUSINESS\b")
ITEM = re.compile(r"(?m)^[ \t]*(?:item\s+no\.?\s*)?(\d{1,2})[ \t]*[.):][ \t]*(?=\S)", re.IGNORECASE)
ITEMS_END = re.compile(
    r"(?im)^[ \t]*(?:by\s+order\s+of\s+the\s+board|on\s+behalf\s+of\s+the\s+board|notes?[ \t]*:?[ \t]*$|notes?[ \t]*:)"
)
STATEMENT = re.compile(
    r"(?im)^[ \t]*(?:\d+\.\s*)?(?:explanatory\s+statement|statement\s+(?:pursuant|under)\s+(?:to\s+)?section\s+102|"
    r"annexure\s+to\s+(?:the\s+)?notice)[^\n]{0,150}$"
)
STATEMENT_ITEM = re.compile(
    r"(?im)^[ \t]*items?[ \t]*(?:nos?\.?|numbers?)?[ \t]*[:.\-–]?[ \t]*0?(\d{1,2})\b(?:[ \t]*(?:&|and|,|to)[ \t]*0?(\d{1,2}))?"
)
STATEMENT_END = re.compile(
    r"(?im)^[ \t]*(?:annexure|details\s+of\s+(?:the\s+)?directors?\s+(?:seeking|proposed)|"
    r"(?:additional\s+)?information\s+(?:as\s+)?(?:required|pursuant)|profile\s+of\s+(?:the\s+)?directors?|"
    r"route\s+map|attendance\s+slip|proxy\s+form|form\s+no\.?\s*mgt-11)"
)
KIND = re.compile(r"(?i)as\s+(?:an?\s+)?(special|ordinary)\s+resolution")
RESOLVED = re.compile(r"[“\"'‘]?\s*(?:RESOLVED\s*THAT|Resolved\s+that)")
TITLE_END = re.compile(
    r"(?i)(?:\s*,?\s*(?:and\s*)?,?\s*(?:if\s+thought\s+fit|to\s+consider\s+and)|\s+in\s+this\s+regard\b|\s*[“\"]?RESOLVED\b)"
)
MEETING = re.compile(r"(?i)\b(annual|extra[\s-]?ordinary)\s+general\s+meeting")

# Topics a precedent can be found by, from the sections it relies on and its wording.
SECTION_TOPICS = {
    "185": "loans-to-directors", "186": "loans-investments", "180": "borrowing-powers", "188": "related-party",
    "139": "auditors", "140": "auditors", "141": "auditors", "142": "auditors", "148": "cost-audit",
    "149": "directors", "152": "directors", "160": "directors", "161": "directors",
    "196": "managerial-remuneration", "197": "managerial-remuneration", "198": "managerial-remuneration", "203": "kmp",
    "13": "memorandum-alteration", "14": "articles-alteration", "61": "share-capital", "64": "share-capital",
    "42": "share-issue", "62": "share-issue", "68": "buy-back", "71": "debentures", "123": "dividend",
    "94": "registers", "230": "scheme", "232": "scheme", "135": "csr", "117": "resolutions",
}
WORD_TOPICS = [
    (re.compile(r"(?i)independent\s+director"), "independent-director"),
    (re.compile(r"(?i)\bdividend"), "dividend"),
    (re.compile(r"(?i)remuneration"), "remuneration"),
    (re.compile(r"(?i)financial\s+statements?|balance\s+sheet"), "accounts"),
    (re.compile(r"(?i)retires?\s+by\s+rotation"), "rotation"),
    (re.compile(r"(?i)borrowing\s+(?:powers?|limits?)|\bto\s+borrow\b"), "borrowing-powers"),
    (re.compile(r"(?i)related\s+part(?:y|ies)"), "related-party"),
    (re.compile(r"(?i)authori[sz]ed\s+(?:share\s+)?capital"), "share-capital"),
]


@dataclass
class Item:
    number: int
    business: str | None
    title: str
    resolution_kind: str | None
    body: str
    page_from: int
    page_to: int
    statement: str | None = None
    sections: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    max_amount: int | None = None


@dataclass
class Notice:
    meeting_kind: str | None
    items: list[Item]
    statement_found: bool


def split_notice(pages: list[tuple[int, str]]) -> Notice:
    joined = join_pages(strip_running_lines(pages))
    text = joined.text
    start_match = START.search(text)
    start = start_match.start() if start_match else 0
    statement_match = next((m for m in STATEMENT.finditer(text, start) if STATEMENT_ITEM.search(text, m.end(), m.end() + 4000)), None)
    region_end = statement_match.start() if statement_match else len(text)

    items = _items(joined, start, region_end)
    if statement_match and items:
        _attach_statements(items, text, statement_match.end())
    for item in items:
        words = f"{item.title}\n{item.body}"
        item.sections = sections_of(words)
        topics = [SECTION_TOPICS[s] for s in item.sections if s in SECTION_TOPICS]
        topics += [topic for pattern, topic in WORD_TOPICS if pattern.search(words)]
        item.topics = list(dict.fromkeys(topics))
        item.max_amount = largest_amount(item.body)
    meeting = MEETING.search(text[: start + 3000] if start_match else text[:3000])
    kind = None if not meeting else "agm" if meeting.group(1).lower() == "annual" else "egm"
    return Notice(kind, items, statement_match is not None)


def _items(joined: Joined, start: int, region_end: int) -> list[Item]:
    text = joined.text
    headings = [(m.start(), m.group(1).lower()) for m in BUSINESS.finditer(text, start, region_end)]
    ends = [m.start() for m in ITEMS_END.finditer(text, start, region_end)]
    accepted: list[tuple[int, int, str | None]] = []  # (offset, global number, business)
    expected, local_expected, business, last_heading_seen = 1, 1, None, -1
    for m in ITEM.finditer(text, start, region_end):
        if accepted and any(accepted[-1][0] < end < m.start() for end in ends):
            break  # past the signature or the Notes: what follows are numbered notes, not business
        line = text[m.end() : text.find("\n", m.end())].strip()
        if re.match(r"(?i)(ordinary|special)\s+business", line):
            continue  # "1. ORDINARY BUSINESS:" is a heading, not an item
        number = int(m.group(1))
        heading = next(((pos, kind) for pos, kind in reversed(headings) if pos < m.start()), None)
        new_section = heading is not None and heading[0] > last_heading_seen
        if new_section and accepted:
            # The first item under a new heading may carry on the numbering or start again from 1.
            if number == expected:
                pass
            elif number == 1:
                local_expected = 1
            else:
                continue
        elif number == local_expected or (not accepted and number == 1):
            pass
        else:
            continue
        if heading is not None:
            business, last_heading_seen = heading[1], heading[0]
        accepted.append((m.start(), expected, business))
        expected += 1
        local_expected = number + 1

    if accepted:
        end_match = ITEMS_END.search(text, accepted[-1][0], region_end)
        region_end = end_match.start() if end_match else region_end
    items = []
    for index, (offset, number, business) in enumerate(accepted):
        end = accepted[index + 1][0] if index + 1 < len(accepted) else region_end
        raw = re.sub(r"^[ \t]*(?:item\s+no\.?\s*)?\d{1,2}[ \t]*[.):][ \t]*", "", text[offset:end], flags=re.IGNORECASE)
        resolved = RESOLVED.search(raw)
        head = raw[: resolved.start()] if resolved else raw
        title_end = TITLE_END.search(head, 10)
        title = reflow(head[: title_end.start()] if title_end else head).replace("\n", " ").strip(" .:,")
        kind_match = KIND.search(raw)
        kind = kind_match.group(1).lower() if kind_match else ("ordinary" if business == "ordinary" else None)
        body = reflow(raw[resolved.start() :]) if resolved else ""
        body = body.strip().strip("“”\"'").strip()
        items.append(
            Item(
                number=number,
                business=business,
                title=title[:400] or f"Item {number}",
                resolution_kind=kind,
                body=body,
                page_from=joined.page_at(offset),
                page_to=joined.page_at(max(offset, end - 1)),
            )
        )
    return items


def _attach_statements(items: list[Item], text: str, statement_start: int) -> None:
    end_match = None
    entries: list[tuple[list[int], int]] = []
    for m in STATEMENT_ITEM.finditer(text, statement_start):
        numbers = [int(m.group(1))] + ([int(m.group(2))] if m.group(2) else [])
        if entries and numbers[0] <= entries[-1][0][-1]:
            end_match = m.start()  # numbering went backwards: an annexure reusing "Item No."
            break
        entries.append((numbers, m.start()))
    if not entries:
        return
    stop = STATEMENT_END.search(text, entries[-1][1] + 10)
    last_end = min(x for x in (end_match, stop.start() if stop else None, len(text)) if x is not None)

    pieces: list[tuple[list[int], str]] = []
    for index, (numbers, offset) in enumerate(entries):
        end = entries[index + 1][1] if index + 1 < len(entries) else last_end
        body = re.sub(STATEMENT_ITEM.pattern, "", text[offset:end], count=1).strip(" :.\n\t-–")
        pieces.append((numbers, reflow(body)))

    by_number = {item.number: item for item in items}
    stated = [n for numbers, _ in pieces for n in numbers]
    special = [item for item in items if item.business == "special"]
    # Ordinary business rarely has a statement, so a statement that starts at "Item 1" while item 1 is
    # ordinary business has numbered the special business from 1 again: match it to those items in order.
    local = bool(special) and stated[0] == 1 and items[0].business == "ordinary" and special[0].number != 1
    for numbers, body in pieces:
        for n in numbers:
            if local:
                if n - 1 < len(special):
                    special[n - 1].statement = body
            elif n in by_number:
                by_number[n].statement = body
