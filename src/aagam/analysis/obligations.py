"""What must be done, by whom and by when: within so many days, on or before a date, with its basis.

A duty counts only when a sentence both obliges someone (shall, must, is required to, is directed to, is
hereby authorised to…) and gives a time limit: "within thirty days of allotment", "on or before 31st March,
2026", "not later than", "at least 21 clear days before the meeting", "before the expiry of the term". A date
on its own is never a duty. Where the limit is an absolute date, or runs from a date given in the same
sentence (or from "the date of this order" when the document's own date is known), the due date is worked
out so she can sort her week by it.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from ..extract import COMPANY, REGULATION, SECTION, SECTION_MORE, company_name, normal_section
from . import Doc, result
from .text import dates, key_sentences, relevance, sentences

KIND = "obligations"
TITLE = "Obligations and deadlines"
COLUMNS = [
    {"key": "duty", "label": "What must be done", "type": "long"},
    {"key": "deadline", "label": "By", "type": "text"},
    {"key": "due", "label": "Due date", "type": "date"},
    {"key": "who", "label": "Who", "type": "text"},
    {"key": "basis", "label": "Basis", "type": "text"},
]

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_WORD = r"(?:" + "|".join(sorted([*_UNITS, *_TENS, "fourty", "hundred", "a", "an"], key=len, reverse=True)) + r")"
# "thirty", "forty-five", "one hundred and eighty", "30", "thirty (30)", "30 (thirty)".
WORDS = rf"{_WORD}(?:[\s-]+(?:and\s+)?{_WORD}){{0,3}}"
NUMBER = rf"(?:\d{{1,4}}|{WORDS})(?:\s*\(\s*(?:\d{{1,4}}|{WORDS})\s*\))?"
UNIT = r"(?:clear\s+|working\s+|business\s+|calendar\s+)?(?:days?|weeks?|months?|years?|hours?)(?:['’]s?)?(?:\s+time)?"


def number_value(raw: str) -> int | None:
    """30 for "30", "thirty", "thirty (30)" or "30 (thirty)"; 180 for "one hundred and eighty"; None if unreadable."""
    raw = raw.lower().split("(")[0].strip()
    if raw.isdigit():
        return int(raw)
    total, current = 0, 0
    for word in re.split(r"[\s-]+", raw):
        if word in ("and", ""):
            continue
        if word in ("a", "an"):
            current += 1
        elif word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS or word == "fourty":
            current += _TENS.get(word, 40)
        elif word == "hundred":
            current = (current or 1) * 100
        else:
            return None
    total += current
    return total or None


# A time limit that runs from or to an event: "within sixty days of receipt", "at least 21 clear days before".
RELATIVE = re.compile(
    rf"\b(?P<lead>within(?:\s+(?:a\s+)?(?:maximum\s+)?period\s+of)?|not\s+later\s+than|no\s+later\s+than|"
    rf"(?:before|prior\s+to)\s+the\s+expiry\s+of(?:\s+(?:a\s+)?period\s+of)?|at\s+least|not\s+less\s+than|"
    rf"a\s+minimum\s+of|(?<=\s))\s*(?P<num>{NUMBER})\s+(?P<unit>{UNIT})"
    r"(?P<rel>\s+(?:of|from|after|before|prior\s+to|following|since|in\s+advance\s+of|preceding|next)\b)?",
    re.IGNORECASE,
)
# A fixed date: "on or before 31st March, 2026", "not later than 30.09.2026", "by 15 November 2026".
ABSOLUTE = re.compile(r"\b(?:on\s+or\s+before|not\s+later\s+than|no\s+later\s+than|latest\s+by|by|before)\s+(?:the\s+)?",
                      re.IGNORECASE)
EXPIRY = re.compile(r"\b(?:before|prior\s+to)\s+the\s+(?:expiry|expiration|end)\s+of\s+(?:the\s+|its\s+|this\s+|such\s+)", re.IGNORECASE)

OBLIGE = re.compile(
    r"\b(?:shall|must|should|(?:is|are|be|stands?)\s+(?:hereby\s+)?(?:required|directed|requested|called\s+upon|obliged|obligated|liable)\s+to|"
    r"required\s+to|undertakes?\s+to|agrees?\s+to|covenants?\s+to|directed\s+to|authori[sz]ed\s+to|has\s+to|have\s+to|needs?\s+to|"
    r"(?:is|are)\s+to\s+be|to\s+be\s+(?:filed|made|paid|submitted|given|sent|issued|completed|allotted|repaid|created|registered)|"
    r"(?:re)?payable|due(?!\s+to\b)|directs?|ordered|hereby\s+orders?)\b",
    re.IGNORECASE,
)
_SUBJECT_WORDS = (
    r"(?:Board\s+of\s+Directors|(?:Respondent|Petitioner|Applicant|Transferor|Transferee|Holding|Subsidiary)\s+Compan(?:y|ies)|"
    # Titles of more than one word come first, so "the Company Secretary" isn't read as "the Company".
    r"Respondent\s+No\.\s?\d{1,2}|Company\s+Secretary|Managing\s+Director|Whole[\s-]time\s+Director|Chief\s+Financial\s+Officer|"
    r"Chief\s+Executive\s+Officer|Interim\s+Resolution\s+Professional|Resolution\s+Professional|Debenture\s+Trustee|Corporate\s+Debtor|"
    r"Service\s+Provider|Designated\s+Partners?|Statutory\s+Auditors?|Secretarial\s+Auditor|Scrutini[sz]er|Company|Borrowers?|Co-?borrowers?|Lenders?|Bank|Directors?|Board|Guarantors?|Promoters?|Respondents?|"
    r"Petitioners?|Applicants?|Appellants?|Service\s+Provider|Client|Contractor|Vendor|Purchaser|Buyer|Seller|Licensee|Licensor|"
    r"Lessee|Lessor|Tenant|Landlord|Auditors?|Members?|Shareholders?|Allottees?|Investors?|Subscribers?|Each\s+Party|Parties|Party|"
    r"Supplier|Customer|Consultant|Employer|Employee|Liquidator|Resolution\s+Professional|Interim\s+Resolution\s+Professional|"
    r"Registrar|Trustees?|Debenture\s+Trustee|Issuer|Managing\s+Director|Whole[\s-]time\s+Director|Company\s+Secretary|"
    r"Chief\s+Financial\s+Officer|Corporate\s+Debtor|Assessee|Noticee|Partners?|Designated\s+Partners?|LLP|Firm|Obligors?|Pledgor|Mortgagor)"
)
SUBJECT = re.compile(rf"\b(?:the\s+|each\s+|such\s+|said\s+)?({_SUBJECT_WORDS})\b")
BY_SUBJECT = re.compile(rf"\bby\s+(?:the\s+)?({_SUBJECT_WORDS})\b")
DIRECTED = re.compile(rf"\b(?:directs?|ordered|orders?|calls?\s+upon|requires?)\s+(?:that\s+)?(?:the\s+)?({_SUBJECT_WORDS})\b")
AFTER_PREPOSITION = re.compile(
    r"\b(?:of|to|for|with|from|in|on|at|by|into|upon|under|against|between|among|concerning|regarding|about|towards?)\s+"
    r"(?:(?:the|its|their|his|her|such|said|each|any)\s+)?$",
    re.IGNORECASE,
)

RULE = re.compile(r"\b[Rr]ules?\s+(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)")
CLAUSE = re.compile(r"\b(?:[Cc]lause|[Cc]l\.)\s+(\d{1,3}(?:\.\d{1,3})*(?:\s?\([0-9a-zA-Z]{1,4}\))*)")
ARTICLE = re.compile(r"\bArticles?\s+(\d{1,3}[A-Z]?)\b")
SHORT_SECTION = re.compile(r"(?<![A-Za-z])(?:s\.|u/s\.?)\s?(\d{1,3}[A-Z]?(?:\(\s?[0-9a-zA-Z]{1,4}\s?\))*)")
LEADING_NUMBER = re.compile(r"^\(?(\d{1,2}(?:\.\d{1,2}){1,3})\)?\s+(?=[A-Z])")
LEAD_IN = re.compile(r"^(?:\([a-zA-Z0-9]{1,4}\)\s+|(?:[a-z]|[ivx]{1,4}|\d{1,2})[.)]\s+|\d{1,2}(?:\.\d{1,2})+\.?\s+|"
                     r"(?i:resolved\s+(?:further\s+)?that|further\s+resolved\s+that|that|and|or|further,?)\s+)+")
# The trigger of a relative limit ends at a clause break; a comma before a year belongs to a date ("31st March, 2026").
TRIGGER_END = re.compile(r"[;:](?!\d)|,(?!\s*\d{4})|\s+(?:and|or|failing|provided|whichever|which|so\s+that|in\s+order\s+to|in\s+case|in\s+the\s+manner|together|as\s+(?:required|prescribed|per|stipulated|provided)|"
                         r"under|pursuant|in\s+terms|in\s+accordance|with\s+the|to\s+the|failing)\b|\.(?=\s|$)", re.IGNORECASE)
THIS_DOCUMENT = re.compile(r"\b(?:(?:the\s+)?date\s+of\s+(?:this|the\s+present)\s+(?:order|letter|notice|communication|sanction|agreement)|"
                           r"the\s+date\s+hereof|receipt\s+of\s+this\s+(?:order|letter|notice))\b", re.IGNORECASE)

# Sentences that only sound like duties: how accounts classify and measure ("benefits payable wholly within twelve
# months … are classified as short-term"; "expected to be realised within twelve months after the reporting period")
# and an auditor's comfort wording ("liabilities falling due within a period of one year … we neither give any
# guarantee"). Neither tells her that anyone must do anything by any date.
NOT_A_DUTY = re.compile(
    r"\b(?:is|are|were|was|be|been)\s+(?:classified|recogni[sz]ed|measured|presented|shown|disclosed|treated|considered|accounted|"
    r"derecogni[sz]ed|amortised|amortized|depreciated|charged|carried|stated)\b|\bfall(?:s|ing)?\s+due\b|\bfell\s+due\b|"
    r"\b(?:expected|due)\s+to\s+be\s+(?:settled|realised|realized|recovered|paid)\b|\bafter\s+the\s+(?:end\s+of\s+the\s+)?reporting\s+period\b|"
    r"\boperating\s+cycle\b|\bnothing\s+has\s+come\s+to\s+our\s+attention\b|\bwe\s+(?:neither|do\s+not|don't)\s+give\b|"
    r"\bin\s+our\s+opinion\b|\baccounting\s+polic(?:y|ies)\b|"
    # An amending instruction quotes time limits without imposing them: for the words "within sixty days", the words …
    r"\bshall\s+be\s+(?:substituted|inserted|omitted)\b|\bfor\s+the\s+words\b",
    re.IGNORECASE,
)

LEXICON = {"shall": 0.5, "within": 1.0, "on or before": 2.0, "not later than": 2.0, "no later than": 2.0, "days": 0.6,
           "due date": 1.5, "deadline": 2.0, "time limit": 2.0, "directed to": 1.5, "required to": 1.0, "comply": 0.8,
           "file": 0.4, "clear days": 1.5, "expiry of": 1.0, "undertakes": 1.0}


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _shift(base: date, count: int, unit: str, backwards: bool, clear: bool) -> date | None:
    unit = unit.lower()
    sign = -1 if backwards else 1
    try:
        if unit.startswith("day") or "days" in unit:
            # "21 clear days before" leaves both the day of sending and the day of the event out.
            return base + timedelta(days=sign * (count + (1 if clear and backwards else 0)))
        if "week" in unit:
            return base + timedelta(weeks=sign * count)
        if "month" in unit:
            return _add_months(base, sign * count)
        if "year" in unit:
            return _add_months(base, sign * 12 * count)
    except (OverflowError, ValueError):
        return None
    return None  # hours: no due date worth showing


def _trigger_end(sentence: str, start: int) -> int:
    m = TRIGGER_END.search(sentence, start, min(len(sentence), start + 160))
    end = m.start() if m else min(len(sentence), start + 120)
    return max(start, end)


def _limits(sentence: str, doc_date: date | None) -> list[tuple[int, int, str, str]]:
    """(start, end, deadline as written, ISO due date or "") for each time limit in a sentence."""
    found: list[tuple[int, int, str, str]] = []
    sentence_dates = [(date.fromisoformat(iso), s, e) for iso, s, e in dates(sentence)]
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= s or start >= e for s, e in taken)

    for m in ABSOLUTE.finditer(sentence):
        day = next((d for d in sentence_dates if d[1] == m.end()), None)
        if day and free(m.start(), day[2]):
            taken.append((m.start(), day[2]))
            found.append((m.start(), day[2], " ".join(sentence[m.start():day[2]].split()), day[0].isoformat()))
    for m in RELATIVE.finditer(sentence):
        lead = (m.group("lead") or "").lower()
        rel = (m.group("rel") or "").strip().lower()
        backwards = rel in ("before", "preceding") or rel.startswith(("prior", "in advance"))
        # "at least 3 years" is a qualification, not a time limit; only "at least 21 days before" is.
        if (not lead or lead.startswith(("at least", "not less", "a minimum"))) and not backwards:
            continue
        count = number_value(m.group("num"))
        if not count or not free(m.start(), m.end()):
            continue
        end = _trigger_end(sentence, m.end()) if rel else m.end()
        due = ""
        base = next((d[0] for d in sentence_dates if m.end() <= d[1] < end + 2), None)
        if base is None and rel and doc_date and THIS_DOCUMENT.search(sentence, m.end(), end + 2):
            base = doc_date
        if base is not None and rel not in ("since",):
            shifted = _shift(base, count, m.group("unit"), backwards, "clear" in m.group("unit").lower())
            due = shifted.isoformat() if shifted else ""
        for d in sentence_dates:  # a date the trigger runs from belongs to the deadline as written
            if m.end() <= d[1] < end + 2:
                end = max(end, d[2])
        taken.append((m.start(), end))
        found.append((m.start(), end, " ".join(sentence[m.start():end].split()).rstrip(",;. "), due))
    for m in EXPIRY.finditer(sentence):
        end = _trigger_end(sentence, m.end())
        if end - m.end() < 3 or not free(m.start(), end):
            continue
        day = next((d for d in sentence_dates if m.end() <= d[1] < end + 2), None)
        if day:
            end = max(end, day[2])
        taken.append((m.start(), end))
        found.append((m.start(), end, " ".join(sentence[m.start():end].split()).rstrip(",;. "), day[0].isoformat() if day else ""))
    found.sort()
    return found


def _who(sentence: str, oblige: re.Match[str]) -> str:
    directed = DIRECTED.search(sentence)
    if directed:
        return _subject_name(directed.group(1))
    before = sentence[: oblige.start()]
    subjects = list(SUBJECT.finditer(before))
    if subjects:
        # The doer heads the clause: in "Members desirous of information about the accounts of the Company are
        # requested to …" it is the Members; "of the Company" and "appointed by the Board" only describe someone.
        heads = [m for m in subjects if not AFTER_PREPOSITION.search(before, 0, m.start())]
        return _subject_name((heads or subjects)[-1].group(1))
    by = BY_SUBJECT.search(sentence, oblige.start())
    if by:
        return _subject_name(by.group(1))
    companies = list(COMPANY.finditer(before))
    if companies:
        return company_name(companies[-1].group(1)) or ""
    return ""


def _subject_name(raw: str) -> str:
    raw = " ".join(raw.split())
    if raw.lower() in ("board", "board of directors"):
        return "the Board"
    if raw in ("LLP", "Each Party", "Parties"):
        return raw
    return f"the {raw}"


def _basis(sentence: str) -> str:
    out: list[str] = []

    def add(value: str) -> None:
        if value not in out:
            out.append(value)

    lead = LEADING_NUMBER.match(sentence)
    if lead:
        add(f"clause {lead.group(1)}")
    for m in SECTION.finditer(sentence):
        add(f"s.{normal_section(m.group(1))}")
        more = SECTION_MORE.match(sentence, m.end())
        while more:
            add(f"s.{normal_section(more.group(1))}")
            more = SECTION_MORE.match(sentence, more.end())
    for m in SHORT_SECTION.finditer(sentence):
        add(f"s.{normal_section(m.group(1))}")
    for m in RULE.finditer(sentence):
        add(f"rule {normal_section(m.group(1))}")
    for m in REGULATION.finditer(sentence):
        add(f"reg. {normal_section(m.group(1))}")
    for m in CLAUSE.finditer(sentence):
        add(f"clause {normal_section(m.group(1))}")
    for m in ARTICLE.finditer(sentence):
        add(f"art. {m.group(1)}")
    return ", ".join(out[:4])


def _duty(sentence: str, start: int, end: int) -> str:
    """The part of the sentence that is this duty: from the previous limit (or the start) to the end of its clause."""
    tail = re.search(r"[;]|,\s+(?!\d{4})|$", sentence[end:])
    stop = end + (tail.start() if tail else 0)
    piece = sentence[start:stop].strip(" ,;:")
    piece = LEAD_IN.sub("", piece)
    if len(piece) > 320:  # keep the end, where the duty and its limit are
        cut = piece[-320:]
        piece = "…" + cut[cut.find(" ") + 1:]
    return piece[:1].upper() + piece[1:] if piece else piece


def _format(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day.strftime('%B %Y')}"


def analyse(doc: Doc) -> dict[str, Any] | None:
    try:
        doc_date = date.fromisoformat(doc.meeting_date) if doc.meeting_date else None
    except ValueError:
        doc_date = None
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for page, text in doc.pages:
        for _, _, sentence in sentences(text or ""):
            if len(sentence) < 20 or not re.search(r"(?i)within|before|later\s+than|\bby\b|least|less\s+than|minimum|expiry", sentence):
                continue
            oblige = OBLIGE.search(sentence)
            if not oblige or NOT_A_DUTY.search(sentence):
                continue
            limits = _limits(sentence, doc_date)
            if not limits:
                continue
            who = _who(sentence, oblige)
            basis = _basis(sentence)
            previous = 0
            for _, end, deadline, due in limits:
                duty = _duty(sentence, previous, end)
                previous = end
                if len(duty.split()) < 4:
                    duty = _duty(sentence, 0, end)
                key = (duty[:80].lower(), deadline.lower())
                if key in seen:
                    continue
                seen.add(key)
                strong = re.match(r"(?i)shall|must|(?:is|are|be)\s|required|directed|undertake", oblige.group(0))
                items.append({"duty": duty, "deadline": deadline, "due": due, "who": who, "basis": basis, "page": page,
                              "context": sentence[:600], "confidence": round(0.6 + (0.2 if strong else 0) + (0.1 if due else 0), 2)})
    if not items:
        return None
    dated = sorted(i["due"] for i in items if i["due"])
    earliest = dated[0] if dated else None
    count = len(items)
    noun = "duty" if count == 1 else "duties"
    if earliest:
        summary = f"{count} {noun} with deadlines; the earliest falls on {_format(earliest)}."
    else:
        summary = f"{count} {noun} with deadlines, each running from an event rather than a fixed date."
    upcoming = [d for d in dated if d >= date.today().isoformat()]
    facts = {"count": count, "earliest_due": earliest, "next_due": upcoming[0] if upcoming else None, "with_due_date": len(dated),
             "who": sorted({i["who"] for i in items if i["who"]})}
    highlights = [{"page": i["page"], "text": i["context"], "score": i["confidence"]}
                  for i in sorted(items, key=lambda i: (not i["due"], i["due"] or "", -i["confidence"]))[:5]]
    if not highlights:
        highlights = key_sentences(doc.pages, LEXICON, 5)
    score = min(1.0, 0.3 + 0.08 * count + 0.4 * relevance(doc.pages, LEXICON))
    return result(KIND, TITLE, COLUMNS, items, score, summary, ["deadlines"], highlights, facts)
