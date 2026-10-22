"""What kind of document this is, from its own words.

Rules look at the first pages, where a document announces itself ("NOTICE is
hereby given", "CERTIFIED TRUE COPY", "Balance Sheet as at"). Each rule says
which words decided it, so she can see why a document was filed where it was.
Local AI is only asked when no rule fits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .extract import CIN, COMPANY, DATE_PATTERNS, LLPIN, MARKET_BODIES, company_name, parse_date

Rule = tuple[str, list[re.Pattern[str]], list[re.Pattern[str]]]  # (type, all of, none of)


def _r(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


LLP_WORDS = _r(r"limited\s+liability\s+partnership|\bLLP\b")
PARTNERS_MEETING = _r(
    r"meeting\s+of\s+the\s+(?:designated\s+)?partners|(?:passed|approved)\s+by\s+(?:all\s+)?the\s+(?:designated\s+)?partners"
    r"|partners'?\s+resolution"
)
# What may follow "... Agreement" in a heading: the end of the line, "of XYZ LLP", "is made", "dated", "(the Agreement)".
AGREEMENT_HEADING_END = r"(?=[ \t]*$|[ \t]+(?:of|is|was|made|dated|between|executed|entered|to|for)\b|[ \t]*\()"

# Order matters: the first rule whose patterns all match wins.
RULES: list[Rule] = [
    ("mca_challan", [_r(r"\bchallan\b"), _r(r"\bSRN\b")], []),
    ("mca_form", [_r(r"\bform\s+(?:no\.?\s*)?(?:LLP\s+)?(?:DIR|MGT|AOC|ADT|PAS|SH|CHG|INC|DPT|MSME|BEN|CRA|LLP|MBP|GNL|CSR|STK|NDH|IEPF|"
                     r"FC|URC|MR|CG|RD|NFRA)[-\s]?\d+[A-Z]?\b"),
                  _r(r"\[?pursuant\s+to\s+(?:section|rule)")], []),
    # LLP forms are numbered without a prefix ("FORM 11 [Pursuant to section 35 of the Limited Liability Partnership Act...]").
    # The \b after the number keeps out income-tax forms such as Form 3CD.
    ("mca_form", [_r(r"\bform\s*(?:no\.?\s*)?(?:LLP[-\s]*)?(?:3|4|5|8|11|15|17|18|24|27|28|31)\b"), LLP_WORDS,
                  _r(r"\[?pursuant\s+to\s+(?:section|rule)")], []),
    ("mca_form", [_r(r"\bFiLLiP\b|form\s+for\s+incorporation\s+of\s+limited\s+liability\s+partnership|\bRUN[-\s]?LLP\b"), LLP_WORDS], []),
    # An LLP agreement names itself in a heading line ("LIMITED LIABILITY PARTNERSHIP AGREEMENT", "THIS LLP AGREEMENT is
    # made..."); minutes or letters that mention "the LLP Agreement, ..." in passing don't count. It comes before the
    # certificate of incorporation and consents, which its recitals often mention.
    ("llp_agreement", [_r(r"^[ \t]*(?:this\s+)?(?:supplementary\s+)?(?:limited\s+liability\s+partnership|LLP)\s+(?:\w+\s+)?agreement\b"
                          + AGREEMENT_HEADING_END)],
     [_r(r"notice\s+is\s+hereby\s+given")]),
    ("llp_agreement", [_r(r"^[ \t]*(?:this\s+)?supplementary\s+(?:limited\s+liability\s+partnership\s+|LLP\s+)?(?:agreement|deed)\b"
                          + AGREEMENT_HEADING_END), LLP_WORDS], []),
    ("partner_consent", [_r(r"\bconsent\s+to\s+(?:act|be(?:come)?)\s+(?:as\s+)?(?:an?\s+)?(?:designated\s+)?partner\b")], []),
    ("consent_dir2", [_r(r"\bDIR[-\s]?2\b"), _r(r"\bconsent\b")], []),
    ("declaration_dir8", [_r(r"\bDIR[-\s]?8\b")], []),
    ("disclosure_mbp1", [_r(r"\bMBP[-\s]?1\b")], []),
    ("certificate_of_incorporation", [_r(r"certificate\s+of\s+incorporation")], [_r(r"memorandum\s+of\s+association")]),
    ("moa", [_r(r"memorandum\s+of\s+association")], []),
    ("aoa", [_r(r"articles\s+of\s+association")], [_r(r"notice\s+is\s+hereby\s+given")]),
    ("partners_resolution", [_r(r"certified\s+(?:true\s+)?copy\s+of\s+(?:the\s+)?resolutions?"), PARTNERS_MEETING], []),
    ("board_resolution", [_r(r"certified\s+(?:true\s+)?copy\s+of\s+(?:the\s+)?resolutions?")], []),
    ("minutes", [_r(r"\bminutes\s+of\s+(?:the\s+)?(?:\w+\s+){0,5}meeting")], []),
    ("annual_report", [_r(r"\bannual\s+report\b"), _r(r"board'?s\s+report|directors'?\s+report"),
                       _r(r"balance\s+sheet")], []),
    ("notice", [_r(r"notice\s+is\s+hereby\s+given|notice\s+of\s+(?:the\s+)?(?:\w+\s+){0,3}(?:general|board)\s+meeting")], []),
    ("auditor_report", [_r(r"independent\s+auditor'?s'?\s+report")], []),
    ("board_report", [_r(r"(?:board'?s|directors'?)\s+report")], []),
    ("financial_statements", [_r(r"balance\s+sheet\s+as\s+(?:at|on)"), _r(r"profit\s+(?:and|&)\s+loss")], []),
    ("sanction_letter", [_r(r"\bsanction(?:ed)?\b"), _r(r"\b(?:facility|facilities|loan|limit)\b"), _r(r"\bbank\b")], []),
    ("charge_document", [_r(r"\b(?:hypothecation|mortgage|deed\s+of\s+charge)\b")], []),
    ("share_certificate", [_r(r"share\s+certificate"), _r(r"distinctive\s+nos?")], []),
    ("register_extract", [_r(r"register\s+of\s+(?:members|directors|charges|contracts|loans)")], []),
    ("master_data", [_r(r"company\s+master\s+data|llp\s+master\s+data")], []),
    ("appointment_letter", [_r(r"letter\s+of\s+appointment|appointment\s+letter")], []),
    ("resignation_letter", [_r(r"\bresign(?:ation)?\b"), _r(r"\b(?:director|board)\b"), _r(r"\bdear\b|\bto\s*,")], []),
    ("auditor_consent", [_r(r"\bconsent\b"), _r(r"section\s+139|section\s+141"), _r(r"\bauditor")], []),
    ("law", [_r(r"ministry\s+of\s+corporate\s+affairs|securities\s+and\s+exchange\s+board"),
             _r(r"\b(?:notification|general\s+circular|circular\s+no\.?|G\.S\.R\.|gazette)\b")], []),
    ("law", [_r(r"arrangement\s+of\s+sections")], []),
    ("agreement", [_r(r"\bthis\s+(?:agreement|deed)\b"), _r(r"\bwitness(?:eth)?\b|\bparties\b")], []),
    ("correspondence", [_r(r"^\s*(?:from|subject)\s*:"), _r(r"^\s*(?:to|date)\s*:")], []),
]

MEETING = re.compile(
    r"(?i)\b(\d{1,3})?(?:st|nd|rd|th|®|™)?\s*(annual|extra[\s-]?ordinary)\s+general\s+meeting|\b(board)\s+meeting\b"
)
HELD_ON = re.compile(r"(?i)(?:will\s+be|is\s+scheduled\s+to\s+be|was|shall\s+be)\s+held\b")


@dataclass(frozen=True)
class Detected:
    doc_type: str | None
    why: str | None
    company_name: str | None
    company_cin: str | None
    meeting_kind: str | None
    meeting_date: str | None
    title: str | None


def detect(pages: list[tuple[int, str]], filename: str = "") -> Detected:
    head = "\n".join(text for _, text in pages[:3])
    doc_type, why = None, None
    for kind, needed, excluded in RULES:
        found = [pattern.search(head) for pattern in needed]
        if all(found) and not any(pattern.search(head) for pattern in excluded):
            doc_type = kind
            why = "; ".join(f"“{' '.join(m.group(0).split())}”" for m in found if m)
            break

    cin = CIN.search(head)
    llpin = None if cin else LLPIN.search(head)
    company = _company(head)

    meeting_kind = meeting_date = None
    meeting = MEETING.search(head)
    if meeting and doc_type in ("notice", "minutes", None):
        word = (meeting.group(2) or meeting.group(3) or "").lower()
        meeting_kind = "agm" if word == "annual" else "board" if word == "board" else "egm"
        # "will be held on Monday, 21st August, 2023" or "will be held through ... on Monday, September 30th 2024".
        # The first "held" may be in a cover letter with a garbled date, so try each in turn.
        for held in HELD_ON.finditer(head, meeting.end()):
            hits = []
            for index, pattern in enumerate(DATE_PATTERNS):
                for when in pattern.finditer(head, held.end(), held.end() + 220):
                    day = parse_date(when.groups(), index)
                    if day:
                        hits.append((when.start(), day))
            if hits:
                meeting_date = min(hits)[1].isoformat()
                break

    company_cin = cin.group(0) if cin else llpin.group(1) if llpin else None
    return Detected(doc_type, why, company, company_cin, meeting_kind, meeting_date, _title(head, filename))


# ------------------------------------------------------------------ its date

# A line that gives the document's own date: "Date: 15.04.2024", "Dated this 5th day of June, 2024", "Place & Date: ...".
DATE_LABEL = _r(
    r"^\s*(?:date[d]?(?:\s+this)?|dt\.?|place\s*(?:and|&)\s*date|service\s+request\s+date|"
    r"date\s+of\s+(?:filing|issue|signing|execution|order|letter|agreement|payment|submission|report))\s*[:\-–.]?\s*"
)
ACCOUNTS_AT = _r(r"\b(?:as\s+(?:at|on)|for\s+the\s+(?:year|period|half[\s-]?year|quarter)\s+ended(?:\s+on)?)\s+")
ACCOUNTS = ("financial_statements", "annual_report", "auditor_report", "board_report")


def dated(pages: list[tuple[int, str]], detected: Detected, doc_type: str | None) -> tuple[str | None, str | None]:
    """The date a document is of, and how it was found: its meeting, its accounts' date, a "Date:" line on its first
    or last page, or else the first date on its first page. (None, None) when its words give none."""
    if detected.meeting_date:
        return detected.meeting_date, "the meeting date"
    if not pages:
        return None, None
    if doc_type in ACCOUNTS:
        found = _date_after(ACCOUNTS_AT, "\n".join(text for _, text in pages[:3]))
        if found:
            return found[0], f"the accounts' date, “{found[1]}”"
    for _, text in (pages[0], pages[-1]) if len(pages) > 1 else (pages[0],):
        found = _date_after(DATE_LABEL, text)
        if found:
            return found[0], f"“{found[1]}”"
    found = _first_date(pages[0][1])
    if found:
        return found[0], f"the first date on page 1, “{found[1]}”"
    return None, None


def _plausible(day: date) -> bool:
    return 1950 <= day.year <= date.today().year + 2


def _date_after(label: re.Pattern[str], text: str) -> tuple[str, str] | None:
    """The first plausible date that directly follows the label."""
    for m in label.finditer(text):
        for index, pattern in enumerate(DATE_PATTERNS):
            when = pattern.match(text, m.end())
            if when:
                day = parse_date(when.groups(), index)
                if day and _plausible(day):
                    return day.isoformat(), " ".join(text[m.start() : when.end()].split())
    return None


def _first_date(text: str) -> tuple[str, str] | None:
    hits = []
    for index, pattern in enumerate(DATE_PATTERNS):
        for when in pattern.finditer(text):
            day = parse_date(when.groups(), index)
            if day and _plausible(day):
                hits.append((when.start(), day, " ".join(when.group(0).split())))
                break  # the first of each pattern is enough
    if not hits:
        return None
    _, day, shown = min(hits)
    return day.isoformat(), shown


MEMBERS_OF = re.compile(r"(?i)(?:members|shareholders)\s+of\s+(?:the\s+company\s*,?\s*)?")
SIGNED_FOR = re.compile(r"(?im)^\s*for\s*,?\s+")


def _company(head: str) -> str | None:
    """The company the document is about: named after "Members of", signing "For ...", or most often; never an exchange."""
    scores: dict[str, float] = {}
    shown: dict[str, str] = {}
    for m in COMPANY.finditer(head):
        name = company_name(m.group(1))
        if not name or len(name) <= 6 or name.startswith("&") or MARKET_BODIES.match(name):
            continue
        before = head[max(0, m.start() - 40) : m.start()]
        weight = 1.0 + (6 if MEMBERS_OF.search(before[-30:]) else 0) + (3 if SIGNED_FOR.search(before[-12:]) else 0)
        key = name.lower()
        scores[key] = scores.get(key, 0) + weight
        shown.setdefault(key, name)
    return shown[max(scores, key=lambda k: scores[k])] if scores else None


# A superscript ordinal often comes out of a PDF or a scan as a symbol: "NOTICE OF 8™ ANNUAL GENERAL MEETING".
ORDINAL_GLYPH = re.compile(r"\b(\d{1,3})\s?[™®]\s?(?=[A-Za-z])")


def _ordinal(m: re.Match[str]) -> str:
    n = int(m.group(1))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{m.group(1)}{suffix} "


def _title(head: str, filename: str) -> str | None:
    lines = [ORDINAL_GLYPH.sub(_ordinal, " ".join(line.split())) for line in head.split("\n")[:60]]
    for line in lines:
        if 12 <= len(line) <= 120 and re.match(r"(?i)notice\s+of\b|minutes\s+of\b|certified\s+true\s+copy", line):
            return line.strip(" .:")
    for line in lines:
        if 12 <= len(line) <= 120 and re.search(r"(?i)notice|minutes|resolution|report|agreement|certificate|statement|form|letter|circular|memorandum|articles", line):
            return line.strip(" .:")
    stem = re.sub(r"[_\-]+", " ", filename.rsplit(".", 1)[0]).strip()
    return stem or None
