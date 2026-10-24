"""Facts a Company Secretary looks for in a document, found by rules.

Each match keeps its page and the words around it, so every fact can be
checked against the page it came from. Identifiers are checked the same way
the company file checks them (CIN shape, PAN holder letter, GSTIN check
character), which drops most false matches. PANs are stored masked.

No AI is involved: this runs on every document as it arrives, in well under a
second, on any laptop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from csdesk import validators
from csdesk.errors import Invalid
from csdesk.vault import mask

CONTEXT = 70
MAX_PER_VALUE = 20

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
            ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
            ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"

DATE_PATTERNS = [
    re.compile(rf"\b{_DAY}\s*(?:day\s+of\s+)?{_MONTH}\.?,?\s*(\d{{4}})\b", re.IGNORECASE),  # 30th September, 2024
    re.compile(rf"\b{_MONTH}\.?\s+{_DAY},?\s*(\d{{4}})\b", re.IGNORECASE),  # September 30, 2024
    re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b"),  # 30/09/2024
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),  # 2024-09-30
]

# `, ₹, Rs., INR. Indian PDFs often print the rupee sign from a font that maps it to a backtick, which some
# fonts turn into a left quote (‘); a left quote counts only when a crore/lakh amount follows.
_RUPEE = r"(?:₹|`|Rs\.?|INR|Rupees|‘(?=\s*[\d,]+(?:\.\d+)?\s*(?:crores?|cr\.?|lakhs?|lacs?)\b))"
AMOUNT = re.compile(
    rf"{_RUPEE}\s*([\d,]+(?:\.\d+)?)\s*(?:/-)?\s*(crores?|cr\.?|lakhs?|lacs?|lakh|millions?|mn\.?|billions?|bn\.?)?(?![a-z])",
    re.IGNORECASE,
)
_SCALE = {"crore": 10_000_000, "cr": 10_000_000, "lakh": 100_000, "lac": 100_000, "million": 1_000_000, "mn": 1_000_000,
          "billion": 1_000_000_000, "bn": 1_000_000_000}

CIN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")
LLPIN = re.compile(r"\bLLPIN\s*[:\-–]?\s*([A-Z]{3}-\d{4})\b")
PAN = re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")
GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_TITLE = r"(?:Mr|Ms|Mrs|Miss|Shri|Smt|Sri|Kum|Dr|CA|CS|Adv)\.?"
PERSON = re.compile(rf"\b{_TITLE}\s+((?:[A-Z][a-zA-Z'\-]*\.?\s+){{0,4}}[A-Z][a-zA-Z'\-]+)")
DIN = re.compile(r"\bDIN\s*(?:No\.?|Number)?\s*[:\-–.]?\s*(\d{8})\b")
FRN = re.compile(r"(?:\bFRN|Firm\s+Registration\s+(?:No\.?|Number))\s*[:.\-–]?\s*(\d{6}[A-Z]{0,2}|[A-Z]?\d{5,6}[A-Z]?)\b", re.IGNORECASE)
MEMBERSHIP = re.compile(r"\b(?:M\.?\s?No\.?|Membership\s+No\.?|ACS|FCS)\s*[:.\-–]?\s*([AF]\s?-?\s?\d{3,6}|\d{4,6})\b")
SECTION = re.compile(r"\b(?:[Ss]ections?|SECTIONS?|Sec\.|u/s\.?)\s+(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)")
SECTION_MORE = re.compile(r"\s*(?:,|and|&|/|to)\s*(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)\b")
ACT = re.compile(
    r"\bof\s+(?:the\s+)?((?:Companies|Income[\s-]?tax|Limited Liability Partnership|Securities and Exchange Board of India|"
    r"Foreign Exchange Management|Indian Stamp|Insolvency and Bankruptcy|Depositories|Indian Contract|Arbitration and Conciliation)"
    r"[A-Za-z ,()]*?Act,?\s*\d{4})",
    re.IGNORECASE,
)
REGULATION = re.compile(r"\bRegulations?\s+(\d{1,3}[A-Z]?(?:\s?\(\s?[0-9a-zA-Z]{1,4}\s?\))*)")
# An LLP's name runs before "LLP" just as a company's runs before "Limited": "Sri Subramanya Solar Power Projects LLP".
COMPANY = re.compile(
    r"((?:[A-Z][\w&'.\-]*\s+)(?:(?:[A-Z][\w&'.\-]*|&|-|–|of|and|the|\(India\)|\(I\))\s+){0,7}?"
    r"(?:(?i:private\s+limited|pvt\.?\s*ltd\.?|limited|ltd\.?)|LLP))(?![A-Za-z])"
)
# Bodies that appear in nearly every listed company's papers but are never the company itself.
MARKET_BODIES = re.compile(
    r"(?i)^(?:bse|national\s+stock\s+exchange|metropolitan\s+stock\s+exchange|central\s+depository|national\s+securities\s+depository|"
    r"link\s+intime|kfin\s*tech|bigshare|skyline\s+financial|cameo\s+corporate|purva\s+sharegistry|india)\b"
)
_COMPANY_SKIP = {"for", "the", "of", "to", "m/s", "m/s.", "and", "dear", "on", "by", "in", "with", "from", "said", "said,",
                 "a", "an", "our", "your", "its", "this", "that", "at", "as", "registered", "office", "member"}


@dataclass(frozen=True)
class Mention:
    page_no: int
    kind: str
    value: str
    shown: str
    detail: str | None
    context: str


def _context(text: str, start: int, end: int) -> str:
    left = text[max(0, start - CONTEXT) : start]
    right = text[end : end + CONTEXT]
    return " ".join(f"{left}{text[start:end]}{right}".split())


def parse_date(groups: tuple[str, ...], pattern_index: int) -> date | None:
    try:
        if pattern_index == 0:
            day, month, year = int(groups[0]), _MONTHS[groups[1].lower().rstrip(".")], int(groups[2])
        elif pattern_index == 1:
            month, day, year = _MONTHS[groups[0].lower().rstrip(".")], int(groups[1]), int(groups[2])
        elif pattern_index == 2:
            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
        else:
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
        if not 1900 <= year <= 2100:
            return None
        return date(year, month, day)
    except (KeyError, ValueError):
        return None


def amount_in_rupees(number: str, scale: str | None) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    if scale:
        key = scale.lower().rstrip(".")
        key = key[:-1] if key.endswith("s") else key  # crores, lakhs, lacs, millions
        value *= _SCALE.get(key, 1)
    return round(value) if value >= 1 else None


def normal_section(raw: str) -> str:
    return re.sub(r"\s+", "", raw)


def company_name(raw: str) -> str | None:
    raw = re.sub(r"^.*\b(?:Meeting|Members|Shareholders|Directors|Notice|Board|Report|Statements?)\s+of\s+(?:the\s+)?", "", raw)
    # An agreement's heading run into its first line ("LIMITED LIABILITY PARTNERSHIP AGREEMENT This LLP...") isn't a name.
    raw = re.sub(r"(?i)^(?:.*\b)?(?:LLP|partnership|supplementary|shareholders'?|joint\s+venture)\s+(?:\w+\s+)?agreement\s+(?:this\s+)?", "", raw)
    raw = re.sub(r"\s*&\s*", " & ", raw)
    raw = re.sub(r"(?i)^(?:name\s+of\s+(?:the\s+)?company|company\s+name)\b[\s:\-–]*", "", raw)
    if re.search(r"\d{5}", raw):
        return None  # a table row run together ("Company Name Begin Date L31909MP20..."), not a name
    words = raw.split()
    while words and words[0].lower().strip(",") in _COMPANY_SKIP:
        words.pop(0)
    if len(words) < 2:
        return None
    name = " ".join(words)
    shouting = name.isupper()
    name = re.sub(r"\bPvt\.?\s*Ltd\.?$", "Private Limited", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLtd\.?$", "Limited", name, flags=re.IGNORECASE)
    if shouting or name.replace("Limited", "").replace("Private", "").strip().isupper():
        name = " ".join(_soften(w) for w in name.split())
    return name


def _soften(word: str) -> str:
    """One word of a name written in capitals, in title case; initials and acronyms ("NCC", "HDFC", "J.") stay as they are."""
    if "-" in word.strip("-"):
        return "-".join(_soften(part) for part in word.split("-"))
    if word in ("&", "LLP", "-", "") or len(word) <= 3 and "." in word:
        return word
    letters = re.sub(r"[^A-Za-z]", "", word)
    if letters and not re.search(r"[AEIOUY]", letters.upper()):
        return word  # no vowels: an acronym
    return word.capitalize()


def find_mentions(pages: list[tuple[int, str]]) -> list[Mention]:
    """All facts on the given (page number, text) pairs, in page order."""
    found: list[Mention] = []
    seen: dict[tuple[str, str], int] = {}

    def add(page_no: int, text: str, kind: str, value: str, shown: str, start: int, end: int, detail: str | None = None) -> None:
        key = (kind, value)
        if seen.get(key, 0) >= MAX_PER_VALUE:
            return
        seen[key] = seen.get(key, 0) + 1
        context = _context(text, start, end)
        if kind == "pan":
            context = context.replace(value, shown)
        found.append(Mention(page_no, kind, value, shown, detail, context))

    for page_no, text in pages:
        for m in CIN.finditer(text):
            add(page_no, text, "cin", m.group(0), m.group(0), m.start(), m.end())
        for m in LLPIN.finditer(text):
            add(page_no, text, "llpin", m.group(1), m.group(1), m.start(1), m.end(1))
        for m in PAN.finditer(text):
            try:
                value = validators.pan(m.group(0))
            except Invalid:
                continue
            add(page_no, text, "pan", value, mask(value) or "", m.start(), m.end(), validators.PAN_HOLDER[value[3]])
        for m in GSTIN.finditer(text):
            try:
                value = validators.gstin(m.group(0))
            except Invalid:
                continue
            add(page_no, text, "gstin", value, value, m.start(), m.end())
        for m in EMAIL.finditer(text):
            add(page_no, text, "email", m.group(0).lower(), m.group(0), m.start(), m.end())

        # A DIN usually follows the person's name: "Mr. Dipesh Godha (DIN: 07529876)".
        for m in DIN.finditer(text):
            before = text[max(0, m.start() - 90) : m.start()]
            people = list(PERSON.finditer(before))
            who = clean_person(" ".join(people[-1].group(1).split())) if people else _name_before(before)
            add(page_no, text, "din", m.group(1), m.group(1), m.start(), m.end(), who)
        for m in PERSON.finditer(text):
            name = clean_person(" ".join(m.group(1).split()).rstrip("."))
            if name:
                add(page_no, text, "person", name, m.group(0).strip(), m.start(), m.end())
        for m in FRN.finditer(text):
            add(page_no, text, "frn", m.group(1).upper(), m.group(0).strip(), m.start(), m.end())
        for m in MEMBERSHIP.finditer(text):
            value = re.sub(r"[\s\-]", "", m.group(1)).upper()
            add(page_no, text, "membership_no", value, m.group(0).strip(), m.start(), m.end())

        for index, pattern in enumerate(DATE_PATTERNS):
            for m in pattern.finditer(text):
                day = parse_date(m.groups(), index)
                if day:
                    add(page_no, text, "date", day.isoformat(), m.group(0), m.start(), m.end())
        for m in AMOUNT.finditer(text):
            rupees = amount_in_rupees(m.group(1), m.group(2))
            if rupees:
                add(page_no, text, "amount", str(rupees), " ".join(m.group(0).split()), m.start(), m.end())

        for m in SECTION.finditer(text):
            numbers = [m.group(1)]
            tail_end = m.end()
            while True:
                more = SECTION_MORE.match(text, tail_end)
                if not more or len(numbers) >= 8:
                    break
                numbers.append(more.group(1))
                tail_end = more.end()
            act = ACT.search(text, tail_end, tail_end + 90)
            act_name = " ".join(act.group(1).split()) if act and act.start() - tail_end < 40 else None
            for number in numbers:
                add(page_no, text, "section", normal_section(number), f"Section {number}", m.start(), tail_end, act_name)
        for m in REGULATION.finditer(text):
            add(page_no, text, "regulation", normal_section(m.group(1)), m.group(0), m.start(), m.end())
        for m in COMPANY.finditer(text):
            name = company_name(m.group(1))
            if name:
                add(page_no, text, "company", name, m.group(1).strip(), m.start(1), m.end(1))
    return found


NAME_BEFORE = re.compile(r"((?:[A-Z][A-Za-z.'\-]+\s+){1,3}[A-Z][A-Za-z.'\-]+)[\s,:]*\(?\s*$")
NOT_NAMES = {"director", "directors", "managing", "chairman", "company", "secretary", "the", "and", "of", "din", "for", "limited", "ltd"}


# Words that make a "name" an organisation, and words a table or form leaves stuck to the end of one.
ORG_WORDS = {"limited", "ltd", "llp", "private", "pvt", "industries", "enterprises", "steel", "cement", "power", "projects", "leasing",
             "services", "solutions", "infra", "infraprojects", "finance", "bank", "trust", "corporation", "company", "exchange",
             "consultancy", "insulation", "associates", "co", "group", "holdings", "ventures", "traders", "exports"}
JUNK_TAIL = {"din", "yes", "no", "nil", "na", "n.a", "date", "dated", "place", "sd", "director", "chairman", "managing", "and", "the", "of",
             "mr", "ms", "mrs", "shri", "sri", "smt"}  # a title at the end belongs to the next name


def clean_person(name: str | None) -> str | None:
    """A person's name without the table debris around it; None if it is really an organisation."""
    if not name:
        return None
    words = name.split()
    if any(w.lower().strip(".,") in ORG_WORDS for w in words):
        return None
    while words and words[-1].lower().strip(".,:") in JUNK_TAIL:
        words.pop()
    cleaned = " ".join(words).rstrip(".,")
    return cleaned if len(cleaned) > 3 else None


def _name_before(before: str) -> str | None:
    """A name written without "Mr."/"Ms." just before "(DIN ...)": "I, ASHA RAO (DIN 01234567)"."""
    m = NAME_BEFORE.search(before)
    if not m:
        return None
    words = [w for w in m.group(1).split() if w.lower().strip(".") not in NOT_NAMES]
    if len(words) < 2:
        return None
    return clean_person(" ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in words))


def sections_of(text: str) -> list[str]:
    """Section numbers referred to in a piece of text, base number first, without duplicates: ['185', '186', '186(3)']."""
    out: list[str] = []
    for mention in find_mentions([(1, text)]):
        if mention.kind == "section" and (mention.detail is None or mention.detail.lower().startswith("companies")):
            for value in (mention.value.split("(")[0], mention.value):
                if value not in out:
                    out.append(value)
    return out


def largest_amount(text: str) -> int | None:
    amounts = [amount_in_rupees(m.group(1), m.group(2)) for m in AMOUNT.finditer(text)]
    amounts = [a for a in amounts if a]
    return max(amounts) if amounts else None
