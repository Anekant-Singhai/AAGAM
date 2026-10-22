"""The terms of a contract or deed: parties, date, term, consideration, governing law, termination and the like.

Read from agreements, deeds, MoUs, sanction letters, term sheets and engagement letters. Each term is found by
the words a draftsman uses for it ("governed by the laws of", "hereinafter referred to as", "events of default")
and given as a short value with the sentence it came from, so she can check the clause before relying on it.
A document counts as an agreement only when it reads like one and at least the parties, or three terms, are found;
a board resolution that merely mentions a loan agreement is left alone.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..extract import COMPANY, PERSON, company_name
from . import Doc, result
from .obligations import NUMBER, number_value
from .text import amounts, dates, key_sentences, relevance, rupees, sentences

KIND = "agreements"
TITLE = "Agreement terms"
COLUMNS = [
    {"key": "term", "label": "Term", "type": "text"},
    {"key": "value", "label": "What it says", "type": "long"},
]

LEXICON = {"this agreement": 3.0, "agreement": 1.0, "this deed": 3.0, "deed": 1.0, "memorandum of understanding": 3.0,
           "hereinafter referred to as": 3.0, "hereinafter called": 3.0, "witnesseth": 3.0, "whereas": 1.5, "parties": 1.5,
           "governing law": 3.0, "governed by": 2.0, "jurisdiction": 1.5, "arbitration": 2.0, "indemnify": 2.0, "indemnity": 2.0,
           "confidential": 1.5, "termination": 2.0, "terminate": 1.5, "in witness whereof": 3.0, "effective date": 2.5,
           "force majeure": 2.5, "event of default": 2.5, "events of default": 2.5, "sanction": 1.5, "sanctioned": 1.5,
           "borrower": 2.0, "lender": 2.0, "term sheet": 3.0, "engagement": 1.0, "fees": 1.0, "consideration": 1.5,
           "covenants": 1.5, "rate of interest": 1.5, "tenure": 1.5, "licensor": 2.0, "licensee": 2.0, "lessor": 2.0,
           "lessee": 2.0, "service provider": 2.0, "assign": 1.0, "stamp duty": 1.5, "executed": 1.0}

# Words that say the document itself is an agreement, not merely one that mentions one.
ITSELF = re.compile(r"(?i)\b(?:this|the\s+present)\s+(?:agreement|deed|memorandum\s+of\s+understanding|mou|contract|term\s+sheet|"
                    r"engagement\s+letter|letter\s+of\s+engagement|sanction\s+letter|lease|licen[cs]e)\b|\bthese\s+presents\b|"
                    r"\bwe\s+are\s+pleased\s+to\s+sanction\b|\bhereinafter\s+(?:referred\s+to\s+as|called)\b|\bin\s+witness\s+whereof\b")
HEADING = re.compile(r"(?i)\b(?:agreement|deed|memorandum\s+of\s+understanding|\bmou\b|term\s+sheet|sanction\s+letter|"
                     r"engagement\s+letter|letter\s+of\s+engagement|contract|lease|sanction\s+of)\b")
AGREEMENT_TYPES = {"agreement", "deed", "contract", "sanction_letter", "mou", "engagement_letter"}

BETWEEN = re.compile(r"(?i)\b(?:by\s+and\s+)?between\b[\s:]*")
AND = re.compile(r"(?:\bAND\b|(?<=[),])\s*and\b)[\s:]*")
# The parties' paragraph ends at the recitals or the first blank line after a full stop.
PARTIES_END = re.compile(r"\.\s*\n\s*\n|\bWHEREAS\b|\bRECITALS?\b|\bNOW\s+TH|\bIT\s+IS\s+(?:HEREBY\s+)?AGREED\b", re.IGNORECASE)
ROLE = re.compile(r"hereinafter\s+(?:jointly\s+|collectively\s+|individually\s+)?(?:referred\s+to\s+as|called)\s+(?:the\s+)?[\"“'‘]?"
                  r"([A-Z][A-Za-z ]{1,30}?)[\"”'’]", re.IGNORECASE)
NAME_START = re.compile(r"(?:M/s\.?\s*)?")
TO_BLOCK = re.compile(r"\bTo,?\s+(?:M/s\.?\s*)?")
TITLED = re.compile(r"\b(?:Mr|Ms|Mrs|Shri|Smt|Sri|Dr)\.?\s+[A-Z]")

DATE_LEAD = re.compile(r"(?i)\b(?:made|entered\s+into|executed|signed|dated|date)\b[^.]{0,40}$")
EFFECTIVE = re.compile(r"(?i)\beffective\s+(?:from|date|as\s+(?:of|on|from)|on)\b|\bcommence\s+(?:from|on)\b|\bcommencement\s+date\b")
TERM = re.compile(rf"(?i)\b(?:term|tenure|tenor|period|duration)\b(?:\s+of\s+(?:this\s+\w+|the\s+(?:loan|facility|agreement|engagement|lease|licen[cs]e|deed)))?"
                  rf"[^.;]{{0,60}}?\b(?P<period>{NUMBER}\s+(?:years?|months?|days?))\b")
INTEREST = re.compile(r"(?i)\b(?:rate\s+of\s+interest|interest\s+rate|interest|ROI)\b[^.;%]{0,80}?(\d{1,2}(?:\.\d{1,2})?)\s*%\s*(p\.?\s*a\.?|per\s+annum)?")
FLOATING = re.compile(r"(?i)\b(MCLR|repo\s+rate|EBLR|RLLR|EBR|base\s+rate|T-?bill)\b")
LOAN = re.compile(r"(?i)\b(?:loan|facility|term\s+loan|sanction(?:ed)?\s+(?:amount|limit)|limit|principal\s+amount|working\s+capital)\b")
FEES = re.compile(r"(?i)\b(?:fees?|consideration|retainer|remuneration|price|rent|licen[cs]e\s+fee|royalty|compensation)\b")
PAYMENT = re.compile(r"(?i)\b(?:payable|paid|invoices?|invoiced|repay(?:able|ment)?|instal?ments?|EMIs?)\b")
PAYMENT_WHEN = re.compile(rf"(?i)\bwithin\s+{NUMBER}\s+days|\b(?:monthly|quarterly|half[\s-]yearly|annually|in\s+advance|in\s+arrears|instal?ments?|EMIs?|on\s+receipt)\b")
LAW = re.compile(r"(?i)\b(?:governed\s+by|construed\s+in\s+accordance\s+with|interpreted\s+in\s+accordance\s+with|subject\s+to)\s+"
                 r"(?:and\s+construed\s+in\s+accordance\s+with\s+)?(?:the\s+)?laws?\s+(?:of|in\s+force\s+in)\s+(?:the\s+)?"
                 r"(?-i:(Republic\s+of\s+India|India|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))")
_PLACE = r"(?-i:([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))"
COURTS = re.compile(rf"\bcourts?\s+(?:and\s+tribunals\s+)?(?:at|of|in)\s+{_PLACE}[^.;]{{0,40}}?\bjurisdiction|"
                    rf"\bjurisdiction\s+of\s+(?:the\s+)?(?:competent\s+)?courts?\s+(?:and\s+tribunals\s+)?(?:at|of|in)\s+{_PLACE}", re.IGNORECASE)
SEAT = re.compile(rf"(?i)\b(?:seat|venue|place)\s+(?:and\s+venue\s+)?of\s+(?:the\s+)?arbitration\s+(?:proceedings\s+)?(?:shall\s+be|is|will\s+be)\s+"
                  rf"(?:at\s+|in\s+)?{_PLACE}")
TRIBUNAL = re.compile(r"(?i)\b(sole\s+arbitrator|three\s+(?:\(3\)\s+)?arbitrators|arbitral\s+tribunal\s+of\s+three)\b")
INSTITUTION = re.compile(r"\b(MCIA|SIAC|ICC|LCIA|DIAC|NPAC|ICA|IIAM|Mumbai\s+Centre\s+for\s+International\s+Arbitration)\b")
NOTICE_PERIOD = re.compile(rf"(?i)\b(?P<num>{NUMBER})\s+(?P<unit>days?|months?)['’]?s?\s+(?:prior\s+|advance\s+)?(?:written\s+)?notice")
GROUNDS = [("on material breach", r"material\s+breach|breach"), ("on insolvency", r"insolven|bankrupt|winding[\s-]up|liquidat"),
           ("on change of control", r"change\s+(?:of|in)\s+control"), ("for convenience", r"convenience|without\s+(?:any\s+)?(?:cause|reason)"),
           ("on force majeure", r"force\s+majeure")]
SIMPLE = [
    ("Renewal", re.compile(r"(?i)\brenew(?:al|ed|able)?\b|\bextended\s+(?:for|by)\s+(?:a\s+)?further\b|\bautomatically\s+(?:renew|extend)")),
    ("Indemnity", re.compile(r"(?i)\bindemnif(?:y|ies|ied)\b|\bindemnity\b")),
    ("Confidentiality", re.compile(r"(?i)\bconfidential(?:ity)?\b[^.]{0,120}\b(?:shall|agree|undertake|not\s+disclose|keep)|"
                                   r"\b(?:shall|agree|undertake)[^.]{0,60}\b(?:not\s+disclose|confidential)")),
    ("Non-compete / non-solicit", re.compile(r"(?i)\bnon-?\s?(?:compete|competition|solicit(?:ation)?)\b|\bshall\s+not\s+(?:directly\s+or\s+indirectly\s+)?"
                                             r"(?:compete|solicit|engage\s+in\s+any\s+(?:competing|similar)\s+business)")),
    ("Security / guarantee", re.compile(r"(?i)\bsecured\s+by\b|\bsecurity\s+(?:shall|for|by\s+way|interest)\b|\bhypothecation\b|\bmortgage\b|"
                                        r"\bpledge\b|\b(?:personal|corporate)\s+guarantee\b|\bguaranteed\s+by\b|\bcharge\s+(?:on|over)\b")),
    ("Stamp duty", re.compile(r"(?i)\bstamp\s+duty\b|\bstamp\s+paper\b|\bduly\s+stamped\b|\bnon-judicial\s+stamp\b")),
    ("Notices", re.compile(r"(?i)\bnotices?\b[^.]{0,80}\b(?:addressed|sent|delivered|given)\b|\baddress\s+for\s+(?:notices|communication)")),
    ("Assignment", re.compile(r"(?i)\b(?:shall\s+not|may\s+not|may|can(?:not)?|entitled\s+to)\s+assign\b|\bassign(?:ment)?\s+(?:of\s+)?"
                              r"(?:this\s+agreement|its\s+rights|any\s+of\s+its|the\s+benefit)\b")),
    ("Force majeure", re.compile(r"(?i)\bforce\s+majeure\b")),
]
DEFAULTS = re.compile(r"(?i)\bevents?\s+of\s+default\b")
LIST_ITEM = re.compile(r"^\(?(?:[a-z]|[ivx]{1,4}|\d{1,2})\)\s*")
WITNESS = re.compile(r"(?i)\bin\s+witness\s+whereof\b|\bsigned\s+and\s+delivered\b|\byours\s+(?:faithfully|truly|sincerely)\b|\baccepted\s+by\b")
NAME_LINE = re.compile(r"\bName\s*[:\-–]\s*((?:[A-Z][A-Za-z.'\-]+\s+){0,3}[A-Z][A-Za-z.'\-]+)")
DESIGNATION = re.compile(r"(?i)\b(Managing\s+Director|Whole[\s-]time\s+Director|Director|Authori[sz]ed\s+Signatory|Designated\s+Partner|"
                         r"Partner|Chief\s+Financial\s+Officer|CFO|Company\s+Secretary|Chief\s+Manager|Branch\s+Manager|Proprietor|CEO)\b")

ORDER = ["Parties", "Date of agreement", "Effective date", "Term / tenure", "Loan amount", "Consideration / fees", "Interest rate",
         "Payment terms", "Governing law", "Jurisdiction", "Seat of arbitration", "Arbitration", "Termination", "Renewal", "Indemnity",
         "Confidentiality", "Non-compete / non-solicit", "Security / guarantee", "Stamp duty", "Notices", "Events of default",
         "Assignment", "Force majeure", "Signatories"]


def _clip(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    text = re.sub(r"^\(?(?:\d{1,2}(?:\.\d{1,2})*|[a-z]|[ivx]{1,4})[.)]?\s+(?=[A-Z])", "", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut[: cut.rfind(" ")] + "…"


def _name_at(text: str, pos: int) -> tuple[str, int] | None:
    """The party named at `pos` (a company, a titled person or a capitalised name up to a comma), and where it ends."""
    pos = NAME_START.match(text, pos).end()
    m = COMPANY.match(text, pos)
    if m and len(m.group(1)) < 120:
        name = company_name(m.group(1))
        if name:
            return name, m.end()
    if TITLED.match(text, pos):
        m = PERSON.match(text, pos) or PERSON.search(text, pos, pos + 12)
        if m:
            return " ".join(text[pos:m.end()].split()), m.end()
    # Words may be a single capital or numeral, as in "Bluewater Ventures Fund I" or "Scheme A".
    m = re.compile(r"((?:[A-Z][A-Za-z&.'\-]*\s+){0,5}[A-Z][A-Za-z&.'\-]*)(?=\s*[,(]|\s+having\b|\s+a\s+)").match(text, pos)
    if m and not re.match(r"(?i)(?:the|this|that|whereas|and)\b", m.group(1)):
        return " ".join(m.group(1).split()), m.end()
    return None


def _parties(text: str) -> list[str]:
    head = text[:6000]
    out: list[str] = []
    between = BETWEEN.search(head)
    if between:
        window = head[between.end(): between.end() + 3000]
        stop = PARTIES_END.search(window)
        window = window[: stop.start() + 1] if stop else window
        first = _name_at(window, 0)
        if first:
            names = [first]
            for m in AND.finditer(window, first[1]):
                if len(names) == 4:
                    break
                found = _name_at(window, m.end())
                if found and found[0] not in [n[0] for n in names] and m.start() - names[-1][1] > 0:
                    names.append(found)
            for index, (name, end) in enumerate(names):
                limit = names[index + 1][1] if index + 1 < len(names) else end + 600
                role = ROLE.search(window, end, limit)
                out.append(f"{name} ({role.group(1).strip()})" if role else name)
    if not out:
        # A letter: the addressee after "To," and the sender at the top.
        to = TO_BLOCK.search(head[:1500])
        if to:
            addressee = _name_at(head, to.end())
            sender = COMPANY.search(head[:400])
            sender_name = company_name(sender.group(1)) if sender and sender.start() < (to.start() if to else 400) else None
            if sender_name and (not addressee or sender_name != addressee[0]):
                out.append(sender_name)
            if addressee:
                out.append(addressee[0])
    return out


def _kind(doc: Doc, text: str) -> str:
    for line in text[:800].splitlines()[:12]:
        line = " ".join(line.split())
        if HEADING.search(line) and len(line.split()) <= 8:
            words = re.sub(r"(?i)^sub(?:ject)?\s*[:.\-]\s*", "", line)
            if re.match(r"(?i)sanction\s+of", words):
                return "Sanction letter"
            return words[:1].upper() + words[1:].lower().replace("mou", "MoU")
    if re.search(r"(?i)\bwe\s+are\s+pleased\s+to\s+sanction\b", text[:3000]):
        return "Sanction letter"
    return "Agreement"


def _put(found: dict[str, dict[str, Any]], term: str, value: str, page: int, sentence: str, confidence: float) -> None:
    if term not in found and value:
        found[term] = {"term": term, "value": value, "page": page, "context": sentence[:600], "confidence": confidence}


def _terms(doc: Doc) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    grounds: list[str] = []
    termination: dict[str, Any] | None = None
    defaults: list[str] = []
    collecting_defaults = 0
    label = ""
    for page, text in doc.pages:
        for start, _, sentence in sentences(text or ""):
            if collecting_defaults:
                if LIST_ITEM.match(sentence) and len(defaults) < 8:
                    defaults.append(_clip(LIST_ITEM.sub("", sentence), 90).rstrip(";,. "))
                    continue
                collecting_defaults = 0
            # Term sheets read "Rate of interest: 9.25% p.a."; the label is split off as a sentence of its own.
            if sentence.endswith(":") and len(sentence) < 50 and not DEFAULTS.search(sentence):
                label = sentence
                continue
            sentence, label = (f"{label} {sentence}" if label else sentence), ""
            lower = sentence.lower()
            if "Date of agreement" not in found and start < 3000 and page == doc.pages[0][0]:
                for iso, s, _ in dates(sentence):
                    if DATE_LEAD.search(sentence[max(0, s - 60): s]):
                        _put(found, "Date of agreement", _long_date(iso), page, sentence, 0.8)
                        found["Date of agreement"]["iso"] = iso
                        break
            if "Effective date" not in found and EFFECTIVE.search(sentence):
                day = next(iter(dates(sentence)), None)
                if day:
                    _put(found, "Effective date", _long_date(day[0]), page, sentence, 0.75)
                    found["Effective date"]["iso"] = day[0]
            if "Term / tenure" not in found and (m := TERM.search(sentence)):
                period = m.group("period")
                count = number_value(period.rsplit(" ", 1)[0])
                unit = period.rsplit(" ", 1)[1].lower()
                if count:
                    unit = unit if unit.endswith("s") or count == 1 else unit + "s"
                    unit = unit[:-1] if count == 1 and unit.endswith("s") else unit
                    tail = re.search(r"(?i)\b(?:from|commencing|starting|with\s+effect\s+from)\b[^.;,]{0,60}", sentence[m.end():])
                    _put(found, "Term / tenure", f"{count} {unit}" + (f" {' '.join(tail.group(0).split())}" if tail else ""), page, sentence, 0.75)
            money = list(amounts(sentence))
            if money:
                biggest = max(money)
                if "Loan amount" not in found and LOAN.search(sentence) and not FEES.search(sentence[: biggest[1]][-40:]):
                    _put(found, "Loan amount", rupees(biggest[0]), page, sentence, 0.75)
                    found["Loan amount"]["rupees"] = biggest[0]
                elif "Consideration / fees" not in found and FEES.search(sentence):
                    per = " a month" if re.search(r"(?i)\bmonthly\b|\bper\s+(?:month|mensem)\b", sentence) else (
                        " a year" if re.search(r"(?i)\bannual\b|\bper\s+annum\b|\byearly\b", sentence) else "")
                    _put(found, "Consideration / fees", f"{rupees(biggest[0])}{per} ({biggest[3]})", page, sentence, 0.7)
                    found["Consideration / fees"].update(rupees=biggest[0], per=per)
            if "Interest rate" not in found and (m := INTEREST.search(sentence)):
                value = f"{m.group(1)}%" + (" p.a." if m.group(2) else "")
                floating = FLOATING.search(sentence)
                _put(found, "Interest rate", value + (f" (linked to {floating.group(1)})" if floating else ""), page, sentence, 0.8)
            if "Payment terms" not in found and PAYMENT.search(sentence) and PAYMENT_WHEN.search(sentence):
                _put(found, "Payment terms", _clip(sentence), page, sentence, 0.6)
            if "Governing law" not in found and (m := LAW.search(sentence)):
                place = " ".join(m.group(1).split())
                _put(found, "Governing law", "Laws of India" if place.endswith("India") else f"Laws of {place}", page, sentence, 0.9)
            if "Jurisdiction" not in found and (m := COURTS.search(sentence)):
                place = m.group(1) or m.group(2)
                exclusive = " (exclusive)" if "exclusive" in lower else ""
                _put(found, "Jurisdiction", f"Courts at {place}{exclusive}", page, sentence, 0.85)
            if "Seat of arbitration" not in found and (m := SEAT.search(sentence)):
                _put(found, "Seat of arbitration", m.group(1), page, sentence, 0.85)
            if "Arbitration" not in found and "arbitrat" in lower and re.search(r"(?i)\b(?:referred|settled|resolved|submitted)\s+to\s+arbitration|"
                                                                               r"\barbitration\s+(?:and\s+conciliation|in\s+accordance|under)|"
                                                                               r"\barbitrator", sentence):
                parts = []
                if tribunal := TRIBUNAL.search(sentence):
                    parts.append(tribunal.group(1).lower())
                if "conciliation act" in lower:
                    parts.append("under the Arbitration and Conciliation Act, 1996")
                if institution := INSTITUTION.search(sentence):
                    parts.append(f"rules of {institution.group(1)}")
                _put(found, "Arbitration", "Arbitration, " + ", ".join(parts) if parts else _clip(sentence), page, sentence, 0.75)
            if "terminat" in lower:
                notice = NOTICE_PERIOD.search(sentence)
                for label, pattern in GROUNDS:
                    if label not in grounds and re.search(pattern, lower):
                        grounds.append(label)
                if notice and (termination is None or "notice" not in termination):
                    count = number_value(notice.group("num"))
                    unit = notice.group("unit").lower().rstrip("s") + ("s" if count != 1 else "")
                    termination = {"notice": f"{count} {unit}' notice" if count != 1 else f"{count} {unit}'s notice", "page": page,
                                   "sentence": sentence}
                elif termination is None and re.search(r"(?i)\bmay\s+terminate|\bshall\s+(?:be\s+entitled\s+to\s+)?terminate|\bterminable\b", sentence):
                    termination = {"page": page, "sentence": sentence}
            for term, pattern in SIMPLE:
                if term not in found and pattern.search(sentence):
                    if term == "Stamp duty" and money:
                        _put(found, term, f"{rupees(money[0][0])}: {_clip(sentence, 160)}", page, sentence, 0.7)
                    else:
                        _put(found, term, _clip(sentence), page, sentence, 0.65)
            if "Events of default" not in found and DEFAULTS.search(sentence):
                if re.search(r"(?i)\b(?:following|include|constitute|means|any\s+of|each\s+of)\b", sentence) and sentence.rstrip().endswith((":", "-")):
                    collecting_defaults = page
                    found["Events of default"] = {"term": "Events of default", "value": "", "page": page, "context": sentence[:600],
                                                  "confidence": 0.7}
                else:
                    _put(found, "Events of default", _clip(sentence), page, sentence, 0.65)
    if defaults and "Events of default" in found:
        found["Events of default"]["value"] = "; ".join(defaults)
    if "Events of default" in found and not found["Events of default"]["value"]:
        found["Events of default"]["value"] = _clip(found["Events of default"]["context"])
    if termination:
        value = termination.get("notice", "")
        if grounds:
            value = f"{value}; " if value else ""
            value += ", ".join(grounds)
        _put(found, "Termination", value or _clip(termination["sentence"]), termination["page"], termination["sentence"], 0.75)
    return found


def _signatories(doc: Doc) -> dict[str, Any] | None:
    for page, text in reversed(doc.pages):
        marks = list(WITNESS.finditer(text or ""))
        if not marks:
            continue
        window = text[marks[-1].start(): marks[-1].start() + 2500]
        names: list[str] = []
        for m in [*PERSON.finditer(window), *NAME_LINE.finditer(window)]:
            raw = window[m.start(): m.end()] if m.re is PERSON else m.group(1)
            name = " ".join(raw.split("\n")[0].split())  # a signature block puts the designation on the next line
            end = (m.start() if m.re is PERSON else m.start(1)) + len(raw.split("\n")[0])
            designation = DESIGNATION.search(window, end, end + 80)
            shown = f"{name} ({' '.join(designation.group(1).split())})" if designation else name
            if not any(name in n for n in names):
                names.append(shown)
        if names:
            return {"term": "Signatories", "value": ", ".join(names[:6]), "page": page, "context": " ".join(window[:400].split()),
                    "confidence": 0.6}
    return None


def _long_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {day.strftime('%B %Y')}"


def analyse(doc: Doc) -> dict[str, Any] | None:
    text = doc.text
    if not text.strip():
        return None
    # Whether a document is an agreement shows in its opening pages; scoring all of a 150-page bundle costs time for nothing.
    score = relevance(doc.pages[:20], LEXICON)
    itself = bool(ITSELF.search(text)) or doc.doc_type in AGREEMENT_TYPES
    if score < 0.25 or (not itself and score < 0.6):
        return None
    # Meeting notices, annual reports and accounts mention agreements without being one ("hereinafter referred to as
    # the Board"); they count only if the opening reads like an agreement's ("by and between …").
    if doc.doc_type in ("notice", "annual_report", "financial_statements", "auditor_report", "minutes") and not BETWEEN.search(text[:3000]):
        return None
    found = _terms(doc)
    parties = _parties(text)
    if parties:
        found["Parties"] = {"term": "Parties", "value": "; ".join(parties), "page": doc.pages[0][0], "context": "",
                            "confidence": 0.8}
        between = BETWEEN.search(text[:6000])
        found["Parties"]["context"] = " ".join(text[between.start(): between.start() + 400].split()) if between else ""
    signatories = _signatories(doc)
    if signatories:
        found["Signatories"] = signatories
    if not parties and len(found) < 3:
        return None
    items = [found[t] for t in ORDER if t in found]
    for item in items:
        item.setdefault("page", doc.pages[0][0])

    kind = _kind(doc, text)
    names = [re.sub(r"\s*\([^)]*\)$", "", p) for p in parties]
    summary = kind
    if len(names) >= 2:
        summary += f" between {', '.join(names[:-1])} and {names[-1]}"
    elif names:
        summary += f" with {names[0]}"
    if "Date of agreement" in found:
        summary += f" dated {found['Date of agreement']['value']}"
    money = found.get("Loan amount") or found.get("Consideration / fees")
    deal = []
    if money:
        deal.append(rupees(money["rupees"]) + money.get("per", ""))
    if "Interest rate" in found:
        deal.append(f"at {found['Interest rate']['value'].split(' (')[0].replace(' p.a.', '')}")
    if "Term / tenure" in found:
        deal.append(f"for {found['Term / tenure']['value'].split(' from')[0]}")
    law = []
    if "Governing law" in found:
        law.append("Indian law" if found["Governing law"]["value"] == "Laws of India" else found["Governing law"]["value"])
    if "Jurisdiction" in found:
        law.append(found["Jurisdiction"]["value"].replace("Courts at ", "").replace(" (exclusive)", "") + " courts")
    elif "Seat of arbitration" in found:
        law.append(f"arbitration seated at {found['Seat of arbitration']['value']}")
    clauses = [" ".join(deal)] if deal else []
    if law:
        clauses.append(", ".join(law))
    notice = found.get("Termination", {}).get("value", "")
    if "notice" in notice:
        clauses.append(f"{notice.split(';')[0]} to terminate")
    summary += (": " + "; ".join(clauses) if clauses else "") + "."

    facts = {"kind": kind, "parties": names, "date": found.get("Date of agreement", {}).get("iso"),
             "governing_law": found.get("Governing law", {}).get("value"), "term": found.get("Term / tenure", {}).get("value"),
             "amount": money["rupees"] if money else None, "interest_rate": found.get("Interest rate", {}).get("value"),
             "terms_found": len(items)}
    # The clauses that carry the deal, in the order she reads a contract: who, what money, which law, how it ends.
    telling = ["Parties", "Loan amount", "Consideration / fees", "Interest rate", "Governing law", "Jurisdiction", "Term / tenure",
               "Termination", "Events of default"]
    highlights = [{"page": found[t]["page"], "text": found[t]["context"], "score": found[t]["confidence"]}
                  for t in telling if t in found and found[t].get("context")][:5]
    if not highlights:
        highlights = key_sentences(doc.pages[:10], LEXICON, 5)
    return result(KIND, TITLE, COLUMNS, items, max(score, min(1.0, 0.2 + 0.05 * len(items))), summary, ["agreement"], highlights, facts)
