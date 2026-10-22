"""The law a document relies on: Acts, sections, rules, regulations, notifications, circulars and cases.

Every reference is read with rules. A section is tied to the Act named with it ("section 186 of the Companies Act,
2013"), else to the Act named in the same sentence, else to an Act named just before it, else to the document's own
Act (the one it calls "the Act", or the only one it names). Only a document that is plainly company law gets the
Companies Act, 2013 when it names no Act at all. Rules and regulations are tied to their Rules and Regulations the same
way. Each reference is kept once, with how often it appears and the page and sentence where it first does.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import Counter
from typing import Any

from ..extract import normal_section
from . import Doc, result
from .text import context, dates, key_sentences, relevance, sentences

KIND = "law"
TITLE = "Law cited"
COLUMNS = [
    {"key": "type", "label": "Type", "type": "text"},
    {"key": "reference", "label": "Reference", "type": "text"},
    {"key": "instrument", "label": "Act / instrument", "type": "text"},
    {"key": "count", "label": "Times", "type": "number"},
    {"key": "page", "label": "First page", "type": "number"},
]

_TYPES = ("act", "section", "rule", "regulation", "notification", "circular", "standard", "case")
_COMPANIES_ACT = "Companies Act, 2013"

# --- Named instruments: "Companies (Meetings of Board and its Powers) Rules, 2014" --------------------------------
# A name is capitalised words, parenthesised parts and a few joining words, ending in Act/Code/Rules/Regulations/Order
# and a year. The repetition is bounded and lazy, so each start costs at most a few dozen steps.
_CAP = r"[A-Z][\w'’&.\-]*"
_PAREN = r"\([A-Z][A-Za-z0-9\s,&'’\-]{0,90}\)"
_NAME = rf"(?:{_CAP})(?:\s+(?:{_CAP}|{_PAREN}|of|and|for|on|to|its|&)){{0,14}}?"
_INSTRUMENT = re.compile(
    rf"\b({_NAME})\s+(Act|ACT|Code|CODE|Rules|RULES|Regulations|REGULATIONS|Order|ORDER)\b,?\s*(?:of\s+)?((?:18|19|20)\d{{2}})\b"
)
_KIND_OF = {"act": "act", "code": "act", "rules": "rule", "order": "rule", "regulations": "regulation"}
# Words that can't be part of an Act's name, so a name starts after the last of them ("pursuant to the Companies Act").
_CUT = {"the", "in", "under", "pursuant", "per", "with", "by", "see", "as", "read", "whereas", "provisions", "terms",
        "accordance", "notice", "vide", "said", "this", "that", "also", "where", "while", "u/s", "from", "applicable",
        "relevant", "including", "namely", "whether", "is", "are", "was", "were", "has", "have"}
_JOIN = {"of", "and", "for", "on", "to", "its", "&"}
_ACRONYMS = {"SEBI", "LLP", "RBI", "IBC", "FEMA", "LODR", "ICDR", "SAST", "PIT", "SBEB", "MCA", "GST", "CSR", "KMP", "IEPF",
             "NBFC", "IFSC", "II", "III", "IV", "VI", "VII"}
_SEBI_SHORT = [
    (r"Listing|LODR", "LODR"), (r"Substantial\s+Acquisition|Takeover|SAST", "SAST"), (r"Insider\s+Trading|\bPIT\b", "PIT"),
    (r"Issue\s+of\s+Capital|ICDR", "ICDR"), (r"Share\s+Based\s+Employee|SBEB", "SBEB & SE"),
    (r"Buy-?\s?back", "Buy-back of Securities"), (r"Delisting", "Delisting of Equity Shares"),
]
_SHORT_NAMES = {"llp": "Limited Liability Partnership", "fema": "Foreign Exchange Management"}

# Instruments named without their year, or by their usual short names.
_ALIASES = [
    (re.compile(r"\b(?i:companies\s+act)\b(?!,?\s*(?:of\s+)?\d{4})"), _COMPANIES_ACT, "act"),
    (re.compile(r"\bIBC\b|\b(?i:insolvency\s+(?:and|&)\s+bankruptcy\s+code)\b(?!,?\s*\d{4})"), "Insolvency and Bankruptcy Code, 2016", "act"),
    (re.compile(r"\bFEMA\b"), "Foreign Exchange Management Act, 1999", "act"),
    (re.compile(r"\bLLP\s+Act\b(?!,?\s*\d{4})"), "Limited Liability Partnership Act, 2008", "act"),
    (re.compile(r"\bSEBI\s+Act\b(?!,?\s*\d{4})"), "SEBI Act, 1992", "act"),
    (re.compile(r"\b(?:SEBI\s+)?\(?\s*LODR\b\s*\)?(?:\s+Regulations\b)?|\b(?:SEBI\s+)?Listing\s+Regulations\b"), "SEBI (LODR) Regulations, 2015", "regulation"),
    (re.compile(r"\b(?:SEBI\s+)?\(?\s*SAST\s*\)?\s+Regulations\b|\bTakeover\s+(?:Code|Regulations)\b"), "SEBI (SAST) Regulations, 2011", "regulation"),
    (re.compile(r"\b(?:SEBI\s+)?\(?\s*PIT\s*\)?\s+Regulations\b|\bInsider\s+Trading\s+Regulations\b"), "SEBI (PIT) Regulations, 2015", "regulation"),
    (re.compile(r"\b(?:SEBI\s+)?\(?\s*ICDR\s*\)?\s+Regulations\b"), "SEBI (ICDR) Regulations, 2018", "regulation"),
]

# --- Provisions: "Sections 185, 186 and 188", "sub-section (3) of section 186", "Rule 11", "reg. 17(1A)" ----------
_NUM = r"\d{1,3}[A-Z]{0,3}(?!\d)(?:\s?\(\s?[0-9A-Za-z]{1,5}\s?\))*"
_PROVISION = re.compile(
    r"(?:(?i:sub-?clause)\s*\(\s*([a-z]{1,6}|\d{1,3})\s*\)\s+(?i:of)\s+)?"
    r"(?:(?i:clause)\s*\(\s*([a-zA-Z0-9]{1,5})\s*\)\s+(?i:of)\s+)?"
    r"(?:(?i:sub-?\s?(?:section|rule|regulation))\s*\(\s*([0-9]{1,3}[A-Z]{0,2})\s*\)\s+(?i:of)\s+)?"
    r"(?<!/)\b(?:(?i:(sections?|secs?\.|ss?\.|u/s\.?))|(?i:(rules?))|(?i:(regulations?|regs?\.?)))\s*-?\s*(" + _NUM + ")"
)
# Further numbers in a list ("185, 186 and 188"); a number only counts if what follows it reads like a list or a citation.
_MORE = re.compile(
    r"\s*(,\s*(?i:and|&|or)?|(?i:and|&|or|/|to))\s*(" + _NUM + r")"
    r"(?=\s*(?:[,&/);:.]|(?i:and|or|to|of|read|under|thereof|respectively)\b|$))"
)
_OF = re.compile(r"\s*,?\s*(?i:of|under|in)\s+(?:(?i:the)\s+)?(?:(?i:said)\s+)?")
_ANAPHORA = re.compile(r"(?i:(Act|Code|Rules|Regulations))\b(?!,?\s*(?:of\s+)?\d{4})")
_DEFINES_ACT = re.compile(
    r"\s*(?:\(\d{1,3}\s+of\s+\d{4}\)\s*)?,?\s*(?:\(\s*|(?i:hereinafter)\s+(?:(?i:referred\s+to\s+as|called)\s+)?)"
    r"(?:(?i:the)\s+)?[\"“‘']?\s*(?:(?i:the)\s+)?(?:(?i:said|principal)\s+)?(?i:act)\b"
)
_COMPANY_LAW = re.compile(
    r"Registrar\s+of\s+Companies|Ministry\s+of\s+Corporate\s+Affairs|\bMCA\b|\bCIN\b|Board\s+of\s+Directors|"
    r"[Gg]eneral\s+[Mm]eeting|Secretarial\s+Standard|\bROC\b|\bCompanies\s+\(|\bKey\s+Managerial\b"
)

# --- Notifications and circulars ----------------------------------------------------------------------------------
NOTIFICATION = re.compile(
    r"\b(G\.?\s?S\.?\s?R\.?|S\.\s?O\.)\s*(?:No\.?\s*)?(\d{1,5})\s*(\(\s*E\s*\))?"
    r"|\b(?i:notification)\s+(?i:no)\.?\s*[:.\-]?\s*(?!G\.?\s?S\.?\s?R|S\.\s?O\.)([A-Z0-9][A-Za-z0-9./\-]{1,40}[A-Za-z0-9])"
)
_CIRCULAR = re.compile(
    r"\b((?i:general\s+))?(?i:circular)\s+(?i:no)\.?\s*[:.\-]?\s*(\d{1,3})\s*/\s*((?:19|20)\d{2})\b"
    r"|\b(SEBI(?:/[A-Za-z0-9_\-]+){1,9}/(?:19|20)\d{2}/\d{1,6})\b"
    r"|\b(CIR/[A-Z]{2,6}(?:/[A-Za-z0-9\-]+){1,6}/(?:19|20)\d{2})\b"
    r"|\b(RBI/(?:19|20)\d{2}-\d{2}/\d{1,4})\b"
)
_DATED = re.compile(r"\s*,?\s*(?i:dated|dt\.?)\s*(?:(?i:the)\s+)?")
_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December")

# --- Standards ----------------------------------------------------------------------------------------------------
_STANDARD = re.compile(
    r"\bSS\s?[-–]?\s?([1-4])(?!\d)"
    r"|\b(?i:secretarial\s+standards?)\s*[-–]?\s*(?:No\.?\s*)?([1-4])(?!\d)"
    r"|\b(?i:secretarial\s+standards?\s+on\s+(general\s+meetings|meetings\s+of\s+(?:the\s+)?board))"
    r"|\b(?i:ind)\s?-?\s?AS\s*[-–]?\s*(\d{1,3})(?!\d)"
    r"|\b(?i:accounting\s+standard)\s*(?:\(AS\)\s*)?[-–]?\s*(\d{1,2})(?!\d)|\bAS\s?-\s?(\d{1,2})(?!\d)"
    r"|\bSA\s?(\d{3})(?!\d)"
    r"|\b((?i:secretarial\s+standards?))\b"
)
_SS_TITLES = {"1": "Meetings of the Board of Directors", "2": "General Meetings", "3": "Dividend",
              "4": "Report of the Board of Directors"}

# --- Cases --------------------------------------------------------------------------------------------------------
_CITATION = re.compile(
    r"[\[(]((?:18|19|20)\d{2})[\])]\s*(\d{1,4})?\s*(SCC|ITR|Comp\.?\s?Cas\.?|taxmann\.com|SCL|CLA|SCR|Bom\.?\s?LR|DLT|CTR|Taxman|Comp\s?LJ)"
    r"\s*(?:\([A-Za-z&]{1,6}\)\s*)?(\d{1,6})"
    r"(?:\s*\(\s*(SC|NCLAT|NCLT|SAT|CLB|Delhi|Bombay|Madras|Calcutta|[A-Z][a-z]{1,4}\.?(?:\s?HC)?|[A-Z][a-z]+\s+HC)\s*\))?"
    r"|\bAIR\s*((?:19|20)\d{2})\s*(SC|P\s?&\s?H|[A-Z][a-z]{1,5})\s*(\d{1,5})\b"
    r"|\b((?:19|20)\d{2})\s*SCC\s*OnLine\s*(SC|NCLAT|[A-Z][A-Za-z]{1,8})\s*(\d{1,6})\b"
)
_COURTS = {"SC": "Supreme Court", "NCLAT": "NCLAT", "NCLT": "NCLT", "SAT": "SAT", "CLB": "Company Law Board",
           "Del": "Delhi High Court", "Delhi": "Delhi High Court", "Bom": "Bombay High Court", "Bombay": "Bombay High Court",
           "Mad": "Madras High Court", "Madras": "Madras High Court", "Cal": "Calcutta High Court",
           "Calcutta": "Calcutta High Court", "Guj": "Gujarat High Court", "Kar": "Karnataka High Court",
           "All": "Allahabad High Court", "Ker": "Kerala High Court", "Raj": "Rajasthan High Court"}
_PARTY = r"[A-Z][\w.&'’/\-]*(?:\s+(?:[A-Z][\w.&'’/\-]*|of|and|&|for|\([A-Za-z]{1,3}\))){0,9}"
_CASE = re.compile(rf"\b({_PARTY})\s+(?:v\.|vs\.?|Vs\.?|versus|[Vv]/[Ss]\.?)\s+({_PARTY})")
_BETWEEN = re.compile(r"[\s,;:]*(?:(?i:reported\s+(?:in|at|as))\s*)?")
_CASE_LEAD = {"in", "see", "also", "as", "per", "following", "relying", "similarly", "cf", "cf.", "then",
              "thus", "hence", "further", "moreover", "however", "therefore", "accordingly", "applying", "where", "while"}
_CASE_STOP = {"The", "This", "It", "In", "Hence", "Therefore", "Accordingly", "Thus", "Further", "However", "Here",
              "Similarly", "We", "Our", "Its", "That", "A", "An", "Also", "See", "Hon'ble", "Hon’ble", "Supreme", "High"}
_NOT_PARTY = {"section", "sections", "rule", "rules", "regulation", "form", "schedule", "table", "year", "plan", "actual"}
_ABBREVIATIONS = {"corpn", "assn", "bros", "intl", "natl", "govt", "mfrs", "comm", "commr", "secy", "dept", "admn"}

_LEXICON = {
    "section": 1.0, "sections": 1.0, "sub-section": 1.0, "rule": 0.8, "rules": 0.8, "regulation": 1.0, "regulations": 1.0,
    "act, 2013": 1.5, "pursuant to": 1.5, "in terms of": 1.5, "read with": 1.5, "provisions of": 1.2,
    "in accordance with": 1.0, "under section": 1.5, "circular": 1.5, "notification": 1.2, "secretarial standard": 2.0,
    "held that": 2.0, "scc": 2.0, "supreme court": 1.5, "nclat": 1.5, "high court": 1.2, "judgment": 1.2, "ind as": 1.5,
}


def analyse(doc: Doc) -> dict[str, Any] | None:
    pages = [(page, text or "") for page, text in doc.pages]
    if not any(text.strip() for _, text in pages):
        return None
    mentions = {page: instrument_mentions(text) for page, text in pages}
    defaults = _defaults(pages, mentions)
    found = _Found(pages)
    for page, text in pages:
        _instruments(found, page, mentions[page])
        _provisions(found, page, text, mentions[page], defaults)
        _notifications(found, page, text, mentions[page], "Ministry of Corporate Affairs" if defaults["mca"] else "")
        _standards(found, page, text)
        _cases(found, page, text)
    items = found.items()
    if not items:
        return None
    words = sum(len(t.split()) for _, t in pages) or 1
    cites = sum(i["count"] for i in items)
    score = max(relevance(pages, _LEXICON), min(1.0, cites / max(words / 1000, 1) / 12))
    provisions = [i for i in items if i.get("provision")] or items
    by_type = Counter(i["type"] for i in items)
    facts = {
        "by_type": {t: by_type[t] for t in _TYPES if by_type[t]},
        "citations": cites,
        "most_cited": [{"reference": i["reference"], "count": i["count"]}
                       for i in sorted(provisions, key=lambda i: -i["count"])[:5]],
        "instruments": list(dict.fromkeys(i["instrument"] for i in items if i["type"] in ("act", "section", "rule", "regulation") and i["instrument"])),
        "principal_act": defaults["act"] or None,
    }
    return result(KIND, TITLE, COLUMNS, items, score, _summary(items), ["law"], key_sentences(pages, _LEXICON, 5), facts)


def instrument_mentions(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, normalised name, kind) for each Act, Code, Rules or Regulations named in the text."""
    found: list[tuple[int, int, str, str]] = []
    for m in _INSTRUMENT.finditer(text):
        raw = m.group(1)
        tokens = list(re.finditer(r"\([^()]*\)|\S+", raw))
        cut = 0
        for i, token in enumerate(tokens):
            if token.group(0).lower().strip(",.;:") in _CUT:
                cut = i + 1
        while cut < len(tokens) and tokens[cut].group(0).lower() in _JOIN:
            cut += 1
        if cut >= len(tokens):
            continue
        kind_word = m.group(2)
        name = _canonical(raw[tokens[cut].start():], kind_word, m.group(3))
        found.append((m.start(1) + tokens[cut].start(), m.end(), name, _KIND_OF[kind_word.lower()]))
    spans = [(s, e) for s, e, _, _ in found]
    starts = [s for s, _ in spans]
    for pattern, name, kind in _ALIASES:
        for m in pattern.finditer(text):
            i = bisect_right(starts, m.end()) - 1
            if i >= 0 and spans[i][1] > m.start():  # part of a name already read in full
                continue
            found.append((m.start(), m.end(), name, kind))
    found.sort()
    return found


def notification_reference(m: re.Match) -> tuple[str, str]:
    """(key, reference) of a NOTIFICATION match: ("gsr880e", "G.S.R. 880(E)")."""
    if m.group(1):
        series = "G.S.R." if m.group(1).upper().startswith("G") else "S.O."
        reference = f"{series} {m.group(2)}{'(E)' if m.group(3) else ''}"
    else:
        reference = f"Notification No. {m.group(4)}"
    return re.sub(r"[^a-z0-9]", "", reference.lower()), reference


def date_after(text: str, end: int) -> str | None:
    """The ISO date written just after `end` as "dated 1st December, 2025", if there is one."""
    lead = _DATED.match(text, end)
    if not lead:
        return None
    window = text[lead.end(): lead.end() + 40]
    return next((iso for iso, start, _ in dates(window) if start <= 2), None)


def pretty_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{int(day)} {_MONTH_NAMES[int(month) - 1]} {year}"


# --- Reading ------------------------------------------------------------------------------------------------------

class _Found:
    """References found so far, one row each, counted; context is filled in at the end."""

    def __init__(self, pages: list[tuple[int, str]]) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.texts = dict(pages)
        self.alias: dict[str, str] = {}
        self._last: dict[str, tuple[int, int]] = {}
        self._order = 0

    def add(self, key: str, page: int, start: int, end: int, confidence: float, **fields: Any) -> dict[str, Any]:
        row = self.rows.get(key)
        last = self._last.get(key)
        self._last[key] = (page, end)
        if row is None:
            self._order += 1
            row = self.rows[key] = {**fields, "count": 1, "page": page, "_at": start, "_order": self._order,
                                    "confidence": confidence}
            return row
        # "Secretarial Standard on General Meetings (SS-2)" names one standard once, not twice.
        if not (last and last[0] == page and 0 <= start - last[1] < 12):
            row["count"] += 1
        row["confidence"] = max(row["confidence"], confidence)
        return row

    def items(self) -> list[dict[str, Any]]:
        rows = list(self.rows.values())
        rows = _merge_unattached(rows)
        if any(r["type"] == "standard" and r["reference"].startswith("SS-") for r in rows):
            rows = [r for r in rows if r["reference"] != "Secretarial Standards"]
        order = {t: i for i, t in enumerate(_TYPES)}
        rows.sort(key=lambda r: (order[r["type"]], r["_order"]))
        cache: dict[int, _Sentences] = {}
        out = []
        for r in rows:
            text = self.texts.get(r["page"], "")
            spans = cache.setdefault(r["page"], _Sentences(text))
            start, end, sentence = spans.at(r["_at"])
            if not sentence or len(sentence) > 320:
                sentence = context(text, r["_at"], r["_at"] + 20, 150)
            item = {k: v for k, v in r.items() if not k.startswith("_")}
            item["context"] = sentence
            item["confidence"] = round(item["confidence"], 2)
            out.append(item)
        return out


class _Sentences:
    def __init__(self, text: str) -> None:
        self.spans = sentences(text)
        self.starts = [s for s, _, _ in self.spans]

    def at(self, position: int) -> tuple[int, int, str]:
        i = bisect_right(self.starts, position) - 1
        return self.spans[i] if 0 <= i < len(self.spans) else (0, 0, "")


def _defaults(pages: list[tuple[int, str]], mentions: dict[int, list]) -> dict[str, Any]:
    """The instrument a bare provision belongs to when nothing near it says: the Act the document calls "the Act",
    else the one Act it relies on; the Companies Act, 2013 only for a document plainly under it."""
    counts: dict[str, Counter] = {"act": Counter(), "rule": Counter(), "regulation": Counter()}
    principal = None
    for page, text in pages:
        for _, end, name, kind in mentions[page]:
            counts[kind][name] += 1
            if kind == "act" and principal is None and _DEFINES_ACT.match(text, end):
                principal = name
    whole = "\n".join(t for _, t in pages)
    markers = {m.group(0).lower()[:8] for m in _COMPANY_LAW.finditer(whole)}
    out: dict[str, Any] = {kind: _dominant(counter) for kind, counter in counts.items()}
    if principal:
        out["act"] = principal
    elif not counts["act"] and len(markers) >= 2:
        out["act"] = _COMPANIES_ACT
    out["mca"] = bool(re.search(r"Ministry\s+of\s+Corporate\s+Affairs|\bMCA\b", whole))
    return out


def _dominant(counter: Counter) -> str:
    """The one instrument of a kind the document relies on: the only one, or one cited at least twice as often as the rest."""
    if not counter:
        return ""
    (name, top), *rest = counter.most_common()
    return name if top >= 2 * sum(n for _, n in rest) else ""


def _instruments(found: _Found, page: int, mentions: list) -> None:
    for start, end, name, kind in mentions:
        found.add(f"{kind}:{_key(name)}", page, start, end, 0.95, type=kind, reference=name, instrument=name)


def _provisions(found: _Found, page: int, text: str, mentions: list, defaults: dict[str, Any]) -> None:
    by_start = {s: (name, kind) for s, _, name, kind in mentions}
    starts = [s for s, _, _, _ in mentions]
    spans = _Sentences(text)
    for m in _PROVISION.finditer(text):
        kind = "section" if m.group(4) else "rule" if m.group(5) else "regulation"
        suffix = "".join(f"({g})" for g in (m.group(3), m.group(2), m.group(1)) if g)
        numbers = [normal_section(m.group(7)) + suffix]
        end = m.end()
        while more := _MORE.match(text, end):
            number = normal_section(more.group(2))
            low, high = numbers[-1], number
            if more.group(1).lower() == "to" and low.isdigit() and high.isdigit() and 0 < int(high) - int(low) <= 10:
                numbers.extend(str(n) for n in range(int(low) + 1, int(high)))  # "sections 230 to 232"
            numbers.append(number)
            end = more.end()
        instrument, confidence = _instrument_for(kind, text, m.start(), end, mentions, starts, by_start, spans, defaults)
        short = {"section": "s.", "rule": "rule ", "regulation": "reg. "}[kind]
        for number in dict.fromkeys(numbers):
            reference = f"{instrument} {short}{number}" if instrument else f"{short}{number}"
            found.add(f"{kind}:{_key(instrument)}:{number}", page, m.start(), end, confidence, type=kind, reference=reference,
                      instrument=instrument, provision=number)


def _instrument_for(kind: str, text: str, start: int, end: int, mentions: list, starts: list[int], by_start: dict,
                    spans: _Sentences, defaults: dict[str, Any]) -> tuple[str, float]:
    want = {"section": "act", "rule": "rule", "regulation": "regulation"}[kind]
    of = _OF.match(text, end)
    if of:
        if hit := by_start.get(of.end()):
            return hit[0], 0.95
        if (ana := _ANAPHORA.match(text, of.end())) and (named := defaults[_KIND_OF[ana.group(1).lower()]]):
            return named, 0.9  # "of the Act": the document's own Act
    s0, s1, _ = spans.at(start)
    lo, hi = bisect_left(starts, min(s0, start - 400)), bisect_right(starts, max(s1, end))
    near = [mm for mm in mentions[lo:hi] if mm[3] == want]
    same = [mm for mm in near if s0 <= mm[0] < max(s1, end)]
    if same:
        return min(same, key=lambda mm: abs(mm[0] - start))[2], 0.85
    before = [mm for mm in near if 0 <= start - mm[1] <= 400]
    if before:
        return before[-1][2], 0.75
    if defaults[want]:
        return defaults[want], 0.6
    return "", 0.4


def _notifications(found: _Found, page: int, text: str, mentions: list, mca: str) -> None:
    spans = _Sentences(text)
    for m in NOTIFICATION.finditer(text):
        key, reference = notification_reference(m)
        day = date_after(text, m.end())
        s0, s1, _ = spans.at(m.start())
        named = [mm for mm in mentions if s0 <= mm[0] < s1]
        instrument = min(named, key=lambda mm: abs(mm[0] - m.start()))[2] if named else ""
        row = found.add(f"notification:{key}", page, m.start(), m.end(), 0.95, type="notification", reference=reference,
                        instrument=instrument, date=None)
        if day and not row.get("date"):
            row["date"], row["reference"] = day, f"{reference} dated {pretty_date(day)}"
        if instrument and not row["instrument"]:
            row["instrument"] = instrument
    for m in _CIRCULAR.finditer(text):
        if m.group(2):
            number = f"{int(m.group(2)):02d}/{m.group(3)}"
            key, issuer = number, "Ministry of Corporate Affairs" if m.group(1) or mca else ""
            reference = f"{'General ' if m.group(1) else ''}Circular No. {number}"
        else:
            reference = m.group(4) or m.group(5) or m.group(6)
            key, issuer = reference.lower(), "RBI" if reference.startswith("RBI") else "SEBI"
        day = date_after(text, m.end())
        row = found.add(f"circular:{key}", page, m.start(), m.end(), 0.95, type="circular", reference=reference,
                        instrument=issuer, date=day)
        if m.group(1) and not row["reference"].startswith("General"):
            row["reference"], row["instrument"] = reference, issuer
        if day and not row.get("date"):
            row["date"] = day


def _standards(found: _Found, page: int, text: str) -> None:
    for m in _STANDARD.finditer(text):
        g = m.groups()
        if g[0] or g[1] or g[2]:
            number = g[0] or g[1] or ("2" if g[2].lower().startswith("general") else "1")
            reference, instrument = f"SS-{number}", f"Secretarial Standard on {_SS_TITLES[number]}"
        elif g[3]:
            reference, instrument = f"Ind AS {int(g[3])}", "Indian Accounting Standards"
        elif g[4] or g[5]:
            reference, instrument = f"AS {int(g[4] or g[5])}", "Accounting Standards (ICAI)"
        elif g[6]:
            reference, instrument = f"SA {g[6]}", "Standards on Auditing"
        else:
            reference, instrument = "Secretarial Standards", "Secretarial Standards (ICSI)"
        found.add(f"standard:{_key(reference)}", page, m.start(), m.end(), 0.9, type="standard", reference=reference,
                  instrument=instrument)


def _cases(found: _Found, page: int, text: str) -> None:
    cites = [(m.start(), m.end(), *_citation(m)) for m in _CITATION.finditer(text)]
    used: set[int] = set()
    for m in _CASE.finditer(text):
        name = _case_name(m.group(1), m.group(2))
        if not name:
            continue
        cite = next((c for c in cites if 0 <= c[0] - m.end() <= 40 and _BETWEEN.fullmatch(text, m.end(), c[0])), None)
        if len(name.split()) < 4 and not cite:  # "Actual vs Budget" is not a case
            continue
        name_key = "case:" + _key(name)
        cite_key = "case:" + _key(cite[2]) if cite else ""
        key = found.alias.get(cite_key) or found.alias.get(name_key) or cite_key or name_key
        reference = f"{name}, {cite[2]}" if cite else name
        court = cite[3] if cite else ""
        row = found.add(key, page, m.start(), cite[1] if cite else m.end(), 0.95 if cite else 0.7, type="case",
                        reference=reference, instrument=court, citation=cite[2] if cite else "")
        if cite and not row.get("citation"):
            row.update(reference=reference, instrument=court, citation=cite[2])
        found.alias[name_key] = key
        if cite:
            found.alias[cite_key] = key
            used.add(cite[0])
    for start, end, reference, court in cites:
        if start in used:
            continue
        key = found.alias.get("case:" + _key(reference), "case:" + _key(reference))
        found.alias["case:" + _key(reference)] = key
        found.add(key, page, start, end, 0.9, type="case", reference=reference, instrument=court, citation=reference)


def _citation(m: re.Match) -> tuple[str, str]:
    """(reference, court) of a law-report citation."""
    g = m.groups()
    if g[2]:
        report = re.sub(r"\s+", " ", g[2])
        report = "Comp Cas" if report.lower().startswith("comp") and "cas" in report.lower() else report
        opening = m.group(0)[0]
        closing = "]" if opening == "[" else ")"
        reference = f"{opening}{g[0]}{closing} {g[1] + ' ' if g[1] else ''}{report} {g[3]}"
        court = g[4] or ("SC" if report in ("SCC", "SCR") else "")
        if g[4]:
            reference += f" ({g[4]})"
    elif g[5]:
        court = re.sub(r"\s+", "", g[6])
        reference = f"AIR {g[5]} {court} {g[7]}"
    else:
        court = g[9]
        reference = f"{g[8]} SCC OnLine {court} {g[10]}"
    return reference, _COURTS.get(court.rstrip("."), court)


def _case_name(left: str, right: str) -> str | None:
    """'Vodafone International Holdings B.V. v. Union of India' from the words either side of "v.", trimmed to the parties."""
    lines = left.split("\n")
    while len(lines) > 1 and lines[0].strip().isupper():  # a heading above the sentence ("LEGAL OPINION")
        lines.pop(0)
    words = " ".join(lines).split()
    for i in range(len(words) - 2, -1, -1):  # a sentence ended inside the run of capitalised words: "…the Board. Vodafone…"
        bare = words[i][:-1]
        if words[i].endswith(".") and bare.lower() not in _ABBREVIATIONS and (
                (bare.isalpha() and len(bare) >= 4) or any(c.isdigit() for c in bare)):
            words = words[i + 1:]
            break
    for i in range(len(words) - 1, -1, -1):  # "In Vodafone…", "See also Vodafone…"
        if words[i].lower() in _CASE_LEAD:
            words = words[i + 1:]
            break
    while words and words[0].lower() in ("the", "and", "&"):
        words = words[1:]
    kept = []
    for word in right.split():
        if kept and word in _CASE_STOP:
            break
        bare = word[:-1]
        if word.endswith(".") and bare.isalpha() and len(bare) >= 4 and bare.lower() not in _ABBREVIATIONS:
            kept.append(bare)
            break
        kept.append(word)
    while kept and kept[-1].lower() in _JOIN:
        kept.pop()
    while words and words[-1].lower() in _JOIN:
        words.pop()
    if not words or not kept or words[0].lower() in _NOT_PARTY or kept[0].lower() in _NOT_PARTY:
        return None
    return f"{' '.join(words)} v. {' '.join(kept)}"


def _merge_unattached(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A bare "section 186" joins the one "Companies Act, 2013 s.186" row when there is exactly one to join."""
    named: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("provision") and r["instrument"]:
            named.setdefault((r["type"], r["provision"]), []).append(r)
    out = []
    for r in rows:
        targets = named.get((r["type"], r.get("provision", ""))) if r.get("provision") and not r["instrument"] else None
        if targets and len(targets) == 1:
            target = targets[0]
            target["count"] += r["count"]
            if (r["page"], r["_at"]) < (target["page"], target["_at"]):
                target["page"], target["_at"], target["_order"] = r["page"], r["_at"], min(r["_order"], target["_order"])
            continue
        out.append(r)
    return out


def _summary(items: list[dict[str, Any]]) -> str:
    groups: dict[str, dict[str, Any]] = {}
    for i in items:
        if i["type"] in ("act", "section", "rule", "regulation"):
            g = groups.setdefault(i["instrument"], {"weight": 0, "act": False, "section": [], "rule": [], "regulation": []})
            g["weight"] += i["count"]
            if i["type"] == "act":
                g["act"] = True
            elif i.get("provision"):
                g[i["type"]].append(i["provision"])
    parts = []
    for name, g in sorted(groups.items(), key=lambda kv: -kv[1]["weight"]):
        cited = []
        for kind, one, many in (("section", "s.", "ss."), ("rule", "rule ", "rules "), ("regulation", "reg. ", "regs. ")):
            numbers = _shown(g[kind])
            if numbers:
                cited.append(f"{one if len(numbers) == 1 else many}{', '.join(numbers)}")
        label = name or "provisions of an unnamed Act"
        parts.append(f"{label} ({'; '.join(cited)})" if cited else label)
    parts = parts[:5]
    circulars = Counter(i["instrument"] for i in items if i["type"] == "circular")
    for issuer, n in circulars.items():
        short = {"Ministry of Corporate Affairs": "MCA "}.get(issuer, f"{issuer} " if issuer else "")
        parts.append(f"{n} {short}circular{'s' if n > 1 else ''}")
    notes = [i["reference"] for i in items if i["type"] == "notification"]
    if notes:
        parts.append(", ".join(notes) if len(notes) <= 2 else f"{len(notes)} notifications")
    standards = [i["reference"] for i in items if i["type"] == "standard"]
    if standards:
        parts.append(", ".join(standards[:4]) + (" and others" if len(standards) > 4 else ""))
    cases = [i for i in items if i["type"] == "case"]
    if cases:
        parts.append(cases[0]["reference"][:90] if len(cases) == 1 else f"{len(cases)} cases")
    if not parts:
        return "Cites law."
    lead = "Relies on the " if items and any(i["type"] == "act" for i in items) and groups and parts[0].split(" (")[0] in groups else "Relies on "
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"{lead}{joined}."


def _shown(numbers: list[str]) -> list[str]:
    """Provisions for the summary, in order, with "186(3)" folded into "186" when both are cited."""
    unique = list(dict.fromkeys(numbers))
    bases = {n for n in unique if "(" not in n}
    kept = [n for n in unique if "(" not in n or n.split("(")[0] not in bases]
    def order(n: str) -> tuple[int, str]:
        digits = re.match(r"\d+", n)
        return (int(digits.group(0)) if digits else 0, n)
    kept.sort(key=order)
    return kept[:8] + (["…"] if len(kept) > 8 else [])


# --- Names --------------------------------------------------------------------------------------------------------

def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _title(name: str) -> str:
    """A name printed in capitals, in title case: "COMPANIES (ACCOUNTS)" → "Companies (Accounts)"; acronyms stay."""
    def word(m: re.Match) -> str:
        w = m.group(0)
        if w.upper() in _ACRONYMS:
            return w.upper()
        if w.lower() in _JOIN | {"the", "in"} and m.start() > 0:
            return w.lower()
        return w[0].upper() + w[1:].lower()
    return re.sub(r"[A-Za-z][A-Za-z'’\-]*", word, name)


def _canonical(name: str, kind_word: str, year: str) -> str:
    name = " ".join(name.split())
    if kind_word.isupper():
        name = _title(name)
    name = re.sub(r"(?i)^Securities\s+and\s+Exchange\s+Board\s+of\s+India\b", "SEBI", name)
    if name.upper().startswith("SEBI") and kind_word.lower().startswith("regulation"):
        for pattern, short in _SEBI_SHORT:
            if re.search(pattern, name, re.IGNORECASE):
                amend = re.search(r"(?i)\b(?:(?:first|second|third|fourth|fifth)\s+)?amendment\b", name)
                name = f"SEBI ({short})" + (f" ({amend.group(0).title()})" if amend else "")
                break
    name = _SHORT_NAMES.get(name.lower(), name)
    name = re.sub(r"(?i)\bIncome[\s-]?tax\b", "Income-tax", name)
    kind = {"act": "Act", "code": "Code", "rules": "Rules", "regulations": "Regulations", "order": "Order"}[kind_word.lower()]
    return f"{name} {kind}, {year}"
