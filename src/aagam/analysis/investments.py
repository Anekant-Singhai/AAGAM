"""Loans, investments, guarantees and security given or proposed (s.186), with investee, instrument and amount.

She looks for these in three kinds of paper. Resolutions and notices: a board resolution under s.179(3)
approving one investment, a notice asking members to approve a loan under s.185 or to raise the s.186(3)
limit. Financial statements: the notes listing non-current and current investments, loans given and
guarantees outstanding. Registers: MBP-2.

A sentence becomes an item only when it names an instrument, carries an amount or a quantity, and reads as
the company lending or investing (not borrowing, not issuing its own shares, not an accounting policy). A
sentence that authorises dealings with "any person or body corporate" up to an amount is the overall limit,
kept as its own item rather than mistaken for an investment. Tables in the notes are read line by line,
their bare figures scaled by the note's "₹ in lakhs" heading.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from ..extract import COMPANY, MARKET_BODIES, PERSON, SECTION, SECTION_MORE, clean_person, company_name, normal_section
from . import Doc, result
from .text import amounts, dates, key_sentences, nearest, relevance, rupees, sentence_at, sentences

log = logging.getLogger(__name__)

KIND = "investments"
TITLE = "Investments"
COLUMNS = [
    {"key": "investee", "label": "Investee / borrower", "type": "text"},
    {"key": "instrument", "label": "Instrument", "type": "text"},
    {"key": "amount", "label": "Amount", "type": "money"},
    {"key": "quantity", "label": "Quantity", "type": "text"},
    {"key": "date", "label": "Date", "type": "date"},
    {"key": "nature", "label": "Nature", "type": "text"},
    {"key": "approval", "label": "Approval", "type": "text"},
    {"key": "section", "label": "Section", "type": "text"},
    {"key": "lender", "label": "In favour of", "type": "text"},
]

LEXICON = {
    "section 186": 3.0, "186(3)": 3.0, "section 185": 2.0, "179(3)": 1.0, "mbp-2": 3.0, "mbp 2": 3.0,
    "inter-corporate deposit": 3.0, "inter corporate deposit": 3.0, "intercorporate deposit": 3.0,
    "acquire by way of subscription": 3.0, "guarantee or provide security": 3.0, "provide security": 2.0,
    "corporate guarantee": 2.5, "make investment": 2.5, "make investments": 2.5, "investment in": 2.0, "investments in": 2.0,
    "non-current investments": 2.5, "current investments": 1.5, "loans given": 2.0, "loan to": 1.5, "loans to": 1.5,
    "investment": 1.0, "investments": 1.0, "equity shares": 1.0, "preference shares": 1.5, "debentures": 1.0,
    "bonds": 0.8, "mutual fund": 1.5, "units of": 0.8, "fixed deposit": 1.0, "guarantee": 1.2, "guarantees": 1.2,
    "loan": 0.8, "loans": 0.8, "securities of": 1.5, "body corporate": 1.0, "wholly owned subsidiary": 1.0,
}

# Each instrument and how it is written. Order matters only where two could start at the same place.
_KINDS = [
    ("inter-corporate deposit", r"inter[\s-]?corporate\s+deposits?\b|\bICDs?\b"),
    ("fixed deposit", r"(?:fixed|term)\s+deposits?\b"),
    ("preference shares", r"preference\s+shares?\b|\bCCPS\b|\bOCRPS\b"),
    ("equity shares", r"equity\s+(?:shares?|instruments?)\b"),
    ("debentures", r"debentures?\b|\bNCDs?\b|\bCCDs?\b|\bOCDs?\b"),
    ("bonds", r"bonds?\b(?![\s-]*holders?)"),
    ("mutual fund units", r"mutual\s+funds?\b|liquid\s+funds?\b|units\s+of\s+(?:the\s+)?(?=(?-i:[A-Z]))"),
    ("capital contribution", r"capital\s+contribution\b|contribution\s+(?:to|towards)\s+(?:the\s+)?capital\b"),
    ("guarantee", r"guarantees?\b"),
    ("security", r"(?:provid|giv|creat|offer|furnish)\w*\s+(?:any\s+|a\s+|such\s+)?security\b"
                 r"|security\s+(?:in\s+connection\s+with|for\s+(?:the\s+|a\s+|any\s+)?(?:loans?|borrowings?|credit|facilit))|pledge\s+of\b"),
    ("loan", r"loans?\b"),
    ("securities", r"securities\b(?!\s+(?:and\s+exchange|premium|contracts?|appellate|\(listing))"),
    ("investment", r"investments?\b"),
]
_INSTRUMENT = re.compile("|".join(f"(?P<k{i}>(?<![\\w-])(?:{p}))" for i, (_, p) in enumerate(_KINDS)), re.IGNORECASE)
_LABELS = {f"k{i}": label for i, (label, _) in enumerate(_KINDS)}
_TAKEN_UP = {"equity shares", "preference shares", "debentures", "bonds", "mutual fund units", "capital contribution", "securities", "investment"}
_LOANS = {"loan", "inter-corporate deposit"}
_CHARGES = {"guarantee", "security"}

# What makes a mention a dealing of the company's own, and what makes it something else.
# "held" counts only as investments held in or by something ("held in", "held as"), not a meeting "held on".
_INVEST_CUE = re.compile(r"\binvest\w*|\bacquir\w*|\bacquisition|\bpurchas\w*|\bsubscri(?:be|bed|bing|ption)\s+(?:to|for|of|in)\b|\bbuy\w*|\bhold(?:s|ing)?\b|\bheld\s+(?:in|as|by)\b", re.I)
_GIVE_CUE = re.compile(r"\b(?:give|given|giving|grant\w*|advanc\w*|extend\w*|lend\w*|lent|provid\w*|made|make|making|plac\w*|sanction\w*)\b|\bloans?\s+(?:and\s+advances\s+)?to\b", re.I)
# The "borrowing companies" and "borrowers" of a loan the company gives are its recipients, not the company borrowing.
_BORROW = re.compile(
    r"\bborrow(?!ing\s+compan|ers?\b)\w*|\bloans?\s+(?:taken\s+|received\s+|availed\s+)?from\b|\bavailed\s+by\s+the\s+company\b|\bloans?\s+(?:taken|received|raised|availed)\b"
    r"|\b(?:taken|received|availed|raised)\s+(?:an?\s+|the\s+)?(?:\w+\s+)?(?:loans?|deposits?|ICDs?)\b|\baccept\w*\s+(?:of\s+)?(?:\w+\s+)?deposits?",
    re.I,
)
_OWN_ISSUE = re.compile(r"\bshare\s+capital\b|\bauthori[sz]ed\b|\bissued,?\s+subscribed\b|\b(?:issue|issuance|allot\w*|private\s+placement|rights\s+issue|buy-?back)\b", re.I)
# The company's own shares, including a director's shareholding in it (the details of directors seeking appointment).
_OWN_SHARES = re.compile(r"\b(?:shares|debentures|securities|capital)\s+of\s+the\s+company\b|\bshare\s*holding\s+(?:in|of)\s+the\s+company\b"
                         r"|\bshares\s+held\s+(?:in\s+the\s+company|by\s+(?:him|her|the\s+director))\b", re.I)
_OTHERS_TAKE_UP = re.compile(
    r"\b(?:investors?|subscribers?|allottees?|applicants?|members|shareholders|promoters?|acquirers?)\s+"
    r"(?:shall|will|has|have|had|agrees?\s+to|propos\w+\s+to|intends?\s+to|is\s+to)?\s*(?:subscribe|invest|acquire|purchase|take\s+up)", re.I)
_COMPANY_TAKES_UP = re.compile(r"\b(?:the\s+)?company\s+(?:shall|will|has|had|propos\w+\s+to|intends?\s+to|is\s+to)?\s*(?:invest|subscribe|acquire|purchase)", re.I)
_NOT_GIVEN = re.compile(r"\bbank\s+guarantees?\b|\bpersonal\s+guarantees?\b|\blimited\s+by\s+guarantees?\b", re.I)
_BOILERPLATE = re.compile(
    r"particulars\s+of\s+(?:loans|investments|guarantees)|accounting\s+polic|measured\s+at|fair\s+value\s+through|carried\s+at|"
    r"impairment|classified\s+as|recogni[sz]ed|given\s+in\s+(?:the\s+)?notes?|forms?\s+(?:an?\s+)?(?:integral\s+)?part|refer\s+note|"
    r"complied\s+with|compliance\s+with|not\s+(?:given|made|granted)\s+any|has\s+not\s+(?:given|made|granted)|no\s+(?:loans?|investments?|guarantees?)\b",
    re.I,
)
_ANY = re.compile(r"\bany\s+(?:other\s+)?(?:persons?|body\s+corporate|bodies\s+corporate|compan(?:y|ies)|entit(?:y|ies))\b", re.I)
_LIMIT_WORD = re.compile(r"\blimits?\b|\bceiling\b", re.I)
_LIMIT_CUE = re.compile(r"(?:up\s*to|not\s+exceed\w*|aggregate|limits?|ceiling|maximum|extent|sum)\W*(?:\w+\W+){0,3}$", re.I)
_RAISE = re.compile(r"\b(?:increas\w*|enhanc\w*|rais\w*|revis\w*)\b", re.I)
_APPROVING = re.compile(r"\b(?:consent|approval|sanction)\b[^.]{0,80}\b(?:accorded|given|granted|sought|obtained)\b|\bhereby\s+(?:approves?|authori[sz]e)"
                        r"|\bapproved\s+(?:to|the)\b|\bsubject\s+to\s+(?:the\s+)?approval\b", re.I)
_S186 = re.compile(r"(?:\bsections?|\bsec\.|\bu/s\.?|\bs\.)\s*186\b", re.I)
_S185 = re.compile(r"(?:\bsections?|\bsec\.|\bu/s\.?|\bs\.)\s*185\b", re.I)
_RELEVANT_SECTIONS = {"179", "180", "185", "186", "187", "188"}

# Amounts that are a price per share, not what was paid: "of ₹10 each", "at a premium of ₹40 per share".
_PER = re.compile(r"\s*(?:/-)?\s*(?:each\b|per\s+(?:equity\s+|preference\s+)?(?:share|unit|debenture|bond|annum)\b|p\.\s?a\.)", re.I)
_FACE_BEFORE = re.compile(r"(?:face|nominal|par)\s+value\s+(?:of\s+)?$|premium\s+(?:of\s+)?$|price\s+(?:of\s+)?$", re.I)
_RUPEE_BEFORE = re.compile(r"(?:₹|`|Rs\.?|INR|Rupees)\s*$", re.I)

_QUANTITY = re.compile(
    # The words between the count and the instrument are never numbers, so "as on March 31, 2022 100 Equity Shares" counts 100.
    r"(?<![\d,.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\s+(?:\([A-Za-z ,\-]{1,80}\)\s+)?(?:(?![\d,.]+\s)[\w%.\-]+\s+){0,4}?"
    r"(?:equity\s+shares?|preference\s+shares?|shares|debentures?|units|bonds?|NCDs|CCDs|CCPS|OCDs|warrants)\b"
    r"(?:\s+of\s+(?:(?:a\s+)?face\s+value\s+(?:of\s+)?)?(?:₹|`|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?\s*(?:/-)?\s*each)?",
    re.I,
)
_BANK = re.compile(r"\b((?:[A-Z][\w&.\-]*\s+){1,4}Bank(?:\s+of\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)?(?:\s+(?:Limited|Ltd\.?))?|Bank\s+of\s+[A-Z][a-z]+)")
_FUND = re.compile(r"\b((?:[A-Z][\w&.'\-]*\s+){1,6}(?:Mutual\s+Fund|Fund|Scheme|ETF)\b(?:\s*[-–]\s*(?:Direct|Regular)(?:\s+Plan)?(?:\s*[-–]\s*(?:Growth|IDCW|Dividend))?)?)")
_GROUP = re.compile(r"\b(?:to|in|of|for|by)\s+(?:its|the|a|an)\s+((?:wholly[\s-]owned\s+|step[\s-]down\s+|material\s+)?(?:subsidiary|subsidiaries|associate|joint\s+venture)(?:\s+compan(?:y|ies))?)\b", re.I)
_THE_COMPANY = re.compile(r"\s*,?\s*\(\s*(?:hereinafter\s+(?:referred\s+to\s+as\s+|called\s+)?)?[\"“'‘]?(?:the\s+)?[\"“'‘]?Company\b", re.I)
_OWN_RAW = re.compile(r"\b(?:Board|Directors|Members|Shareholders|Meeting|Notice|Report|Statements?)\s+of\b", re.I)
# Words that lead into a name in run-together text: "Equity Shares of XYZ Private Limited".
_LEAD = re.compile(
    r"^.*\b(?:shares?|equity|preference|debentures?|units?|investments?|loans?|guarantees?|deposits?|bonds?|securities|capital|"
    r"contribution|subsidiary|associate|venture|board|directors|members|shareholders|meeting|notice|resolution)\b\W+(?:of|in|to|for|by)\s+(?:the\s+)?(?:M/s\.?\s+)?",
    re.I,
)

# Notes to the financial statements and the MBP-2 register, read as tables.
_UNIT = re.compile(r"(?:₹|`|\brs\.?|\binr|\brupees|\bamounts?|\bfigures)\s*(?:are\s+|is\s+)?(?:stated\s+|presented\s+|expressed\s+)?in\s+(?:₹|`|rs\.?|inr|rupees)?\s*(crores?|lakhs?|lacs?|millions?|thousands?)\b", re.I)
_UNIT_SCALE = {"crore": 10_000_000, "lakh": 100_000, "lac": 100_000, "million": 1_000_000, "thousand": 1_000}
_NOTE_HEAD = re.compile(
    r"^\W*(?:note\s*(?:no\.?\s*)?)?(?:\d{1,2}(?:\.\d{1,2})?[a-z]?\W{0,3})?(?:\(?[a-z]\)\s*)?(?:non[\s-]?current|current|long[\s-]?term|short[\s-]?term|other)?\s*"
    r"(?:financial\s+assets\W{0,3})?(investments?|loans?(?:\s+and\s+advances)?|inter[\s-]?corporate\s+deposits?)\b(?!\s+(?:in|to|of|from|given|made)\b)[^\n]{0,40}$",
    re.I,
)
_NEW_NOTE = re.compile(r"^\W*(?:note\s*(?:no\.?\s*)?)?\d{1,2}[a-z]?\s*[.:\-–)]\s*[A-Za-z]", re.I)
_SKIP_LINE = re.compile(r"^\W*(?:total|sub[\s-]?total|grand\s+total|aggregate|less|market\s+value|book\s+value|particulars|as\s+at|year\s+ended|note)\b", re.I)
_NUMBER = re.compile(r"\(?-?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\)?|[-–—]")
_REGISTER = re.compile(r"\bMBP[\s-]?2\b|register\s+of\s+loans,?\s+guarantees?", re.I)


def analyse(doc: Doc) -> dict[str, Any] | None:
    score = relevance(doc.pages, LEXICON)
    full = doc.text
    has186, has185 = bool(_S186.search(full)), bool(_S185.search(full))
    register = bool(_REGISTER.search(full))
    own = _own_names(doc)
    items: list[dict[str, Any]] = []
    unit: int | None = None
    for page, text in doc.pages:
        unit = _unit(text) or unit
        try:
            page_dates = list(dates(text))
            consumed = _table_items(doc, page, text, page_dates, unit, register, own, items)
            _prose_items(doc, page, text, page_dates, consumed, own, has186, items)
        except Exception:  # one page of odd text mustn't cost the document its other investments
            log.exception("investments: page %s of document %s", page, doc.id)
    items = _dedupe(items)
    solid = [i for i in items if i["confidence"] >= 0.6]
    if not solid and score < 0.25:
        return None
    highlights = key_sentences(doc.pages, LEXICON, 4)
    # With nothing extracted, the document must still talk about the subject in its own words; the directors'
    # report line "particulars of loans, guarantees or investments ... are given in the notes" doesn't count.
    telling = [h for h in highlights if not _BOILERPLATE.search(h["text"])]
    if not items and (score < 0.4 or len(telling) < 2):
        return None
    tags = ["investments"]
    if has186 or any(str(i.get("section") or "").startswith("186") for i in items):
        tags.append("s.186")
    if has185 or any("185" in str(i.get("section") or "") for i in items):
        tags.append("s.185")
    facts = _facts(items)
    return result(KIND, TITLE, COLUMNS, items, score, _summary(items, facts, full), tags, highlights, facts)


# ---- prose: resolutions, notices, explanatory statements, reports ----

def _prose_items(doc: Doc, page: int, text: str, page_dates: list[tuple[str, int, int]], consumed: list[tuple[int, int]],
                 own: set[str], has186: bool, items: list[dict[str, Any]]) -> None:
    spans = sentences(text)
    limit_amounts: set[int] = set()  # where the amounts already taken as the overall limit start
    for index, (start, end, clean) in enumerate(spans):
        if any(start < c_end and c_start < end for c_start, c_end in consumed):
            continue
        chunk = text[start:end]
        triggers = [(m.start(), m.end(), _LABELS[m.lastgroup]) for m in _INSTRUMENT.finditer(chunk)]
        if not triggers:
            continue
        window = text[max(0, start - 800) : end + 200]
        parties = _parties(chunk, own)
        # Authority to deal with "any person or body corporate" up to an amount is the s.186(3) limit, not an
        # investment. A sentence that names its investee is a specific approval even when it mentions the limit.
        if not any(p[3] == "company" for p in parties) and (_ANY.search(chunk) or (_LIMIT_WORD.search(chunk) and (has186 or "186" in chunk))):
            ahead = text[start : spans[min(index + 2, len(spans) - 1)][1]]
            for value, s, _e, _shown_as in _money(ahead):
                if s + start in limit_amounts or not _LIMIT_CUE.search(ahead[max(0, s - 60) : s]):
                    continue
                limit_amounts.add(s + start)
                items.append(_item(page, sentence_at(text, start + s), "loans, guarantees, security and investments (limit)", "Any person or body corporate",
                                   value, None, _date(page_dates, start + s, doc), "limit", _approval(window),
                                   _sections(window) or ("186(3)" if has186 else None), None, 0.85))
                break
            continue
        money = [(v, s + start, e + start, shown) for v, s, e, shown in _money(chunk) if s + start not in limit_amounts]
        if _BOILERPLATE.search(chunk) and not money:
            continue
        labels = {t[2] for t in triggers}
        if labels - {"investment", "loan", "securities"}:
            triggers = [t for t in triggers if t[2] not in ("investment", "securities")] or triggers
        if labels & _CHARGES:
            first = min(t[0] for t in triggers if t[2] in _CHARGES)
            triggers = [t for t in triggers if not (t[2] == "loan" and t[0] > first)]  # the loan a guarantee secures
        quantities = _quantities(chunk)
        approval, nature, section = _approval(window), _nature(window, doc), _sections(window)
        named = any(p[3] == "company" for p in parties)
        allowed = {label: _counts(label, chunk, named) for label in {t[2] for t in triggers}}
        # One approval for loans, guarantees and security to several named parties up to one amount (the usual s.185
        # resolution: "to (i) X, (ii) Y and (iii) Z … not exceeding ₹20 crore") is one limit shared by them all,
        # not a ₹20 crore guarantee and a ₹20 crore security to the first of them.
        kinds = [k for k in ("loan", "guarantee", "security") if any(t[2] == k and allowed.get(k) for t in triggers)]
        named_parties = list(dict.fromkeys(p[0] for p in parties if p[3] in ("company", "person")))
        if len(kinds) >= 2 and len(money) == 1 and named_parties and _APPROVING.search(window):
            words = {"loan": "loans", "guarantee": "guarantees", "security": "security"}
            label = ", ".join(words[k] for k in kinds[:-1]) + " and " + words[kinds[-1]] + " (limit)"
            # The explanatory statement often doesn't repeat the section; the resolution above it named it.
            items.append(_item(page, clean, label, "; ".join(named_parties), money[0][0], None, _date(page_dates, money[0][1], doc),
                               "limit", approval, section or _section_before(text, start), None, 0.85))
            continue
        for t_start, _t_end, label in triggers[:40]:  # a "sentence" naming forty instruments is a table, read above
            if not allowed[label]:
                continue
            amount = nearest(money, start + t_start, 300)
            quantity = nearest(quantities, t_start, 200) if label in _TAKEN_UP else None
            if amount is None and quantity is None:
                continue
            party = _pick(parties, t_start, label)
            investee = party[0] if party else _fallback_party(chunk, t_start)
            lender = next((p[0] for p in parties if p[3] == "bank"), None) if label in _CHARGES else None
            confidence = 0.35 + (0.25 if amount else 0) + (0.15 if investee else 0) + (0.1 if quantity else 0) + (0.1 if section else 0)
            items.append(_item(page, clean, label, investee, amount[0] if amount else None, quantity[3] if quantity else None,
                               _date(page_dates, start + t_start, doc), nature, approval, section, lender, confidence))


def _counts(label: str, chunk: str, named: bool) -> bool:
    """Whether this mention is the company itself lending, investing or standing guarantee."""
    if label in _TAKEN_UP:
        if not _INVEST_CUE.search(chunk):
            return False
        if _OTHERS_TAKE_UP.search(chunk) and not _COMPANY_TAKES_UP.search(chunk):
            return False  # an investor subscribing to the company's shares: the company is issuing, not investing
        invests = bool(re.search(r"\binvest(?!or)", chunk, re.I))
        if _OWN_SHARES.search(chunk) and not invests:
            return False  # someone subscribing to the company's own shares
        return not _OWN_ISSUE.search(chunk) or invests or named
    if label in _LOANS:
        return bool(_GIVE_CUE.search(chunk)) and not _BORROW.search(chunk)
    if label == "guarantee":
        return not _NOT_GIVEN.search(chunk)
    return True


# ---- tables: notes to the financial statements, MBP-2 ----

def _table_items(doc: Doc, page: int, text: str, page_dates: list[tuple[str, int, int]], unit: int | None, register: bool,
                 own: set[str], items: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Items from the lines of an investments or loans note (or the whole of an MBP-2 register). Returns the lines used."""
    consumed: list[tuple[int, int]] = []
    in_note, default, current = register, ("loan" if register else "investment"), None
    as_at = None  # the note's first date: the current year's column ("As at 31.03.2025   As at 31.03.2024")
    for line_match in re.finditer(r"[^\n]+", text):
        line = line_match.group(0)
        if len(line) > 400:
            continue  # a paragraph, not a table row
        head = _NOTE_HEAD.match(line)
        if head:
            in_note, current, as_at = True, None, None
            kind = head.group(1).lower()
            default = "loan" if kind.startswith("loan") else "inter-corporate deposit" if "deposit" in kind else "investment"
            continue
        if not in_note:
            continue
        line_dates = sorted((d for d in page_dates if line_match.start() <= d[1] < line_match.end()), key=lambda d: d[1])
        as_at = as_at or (line_dates[0][0] if line_dates else None)
        if _SKIP_LINE.match(line):
            continue
        found = [_LABELS[m.lastgroup] for m in _INSTRUMENT.finditer(line)]
        label = next((f for f in found if f not in ("investment", "securities")), None) or (found[0] if found else None)
        tokens = line.split()
        tail: list[str] = []
        while tokens and _NUMBER.fullmatch(tokens[-1]):
            tail.insert(0, tokens.pop())
        money = _money(line)
        if not register and not tail and not money and not found and _NEW_NOTE.match(line):
            in_note = False  # the next note has begun ("6. Trade receivables"); a numbered row with figures hasn't
            continue
        if not tail and not money:
            if label:
                current = label  # a sub-heading: "Investment in equity instruments (unquoted)"
            continue
        parties = _parties(line, own)
        party = next((p for p in parties if p[3] != "person" or label in _LOANS), None)
        quantity = _quantities(line)
        if not party and not label:
            continue
        amount = money[0][0] if money else _bare(tail, unit)
        if amount is None and not quantity:
            continue
        label = label if label and label != "investment" else current or label or default
        if label == "investment" and _FUND.search(line):
            label = "mutual fund units"
        position = line_match.start()
        context = sentence_at(text, position)
        if len(context) > 300:
            context = " ".join(line.split())  # a table runs together as one "sentence"; the row says it better
        confidence = 0.4 + (0.25 if amount else 0) + (0.2 if party else 0) + (0.1 if quantity else 0)
        day = line_dates[0][0] if line_dates else as_at or _date(page_dates, position, doc)
        investee = party[0] if party else _row_party(" ".join(tokens))
        lender = next((p[0] for p in parties if p[3] == "bank"), None) if label in _CHARGES else None
        items.append(_item(page, context, label, investee, amount, quantity[0][3] if quantity else None, day,
                           "given" if register else "outstanding", "Register (MBP-2)" if register else None,
                           "186" if register else None, lender, confidence))
        consumed.append((line_match.start(), line_match.end()))
    return consumed


def _row_party(words: str) -> str | None:
    """Who a row is about when it names no company: "Loans to employees" -> "employees"."""
    m = re.search(r"\b(?:to|in)\s+([A-Za-z][\w &,.'\-]{2,60}?)\s*(?:\(|$)", words)
    return m.group(1).strip(" ,.") if m else None


def _unit(text: str) -> int | None:
    m = _UNIT.search(text)
    if not m:
        return None
    key = m.group(1).lower()
    key = key[:-1] if key.endswith("s") else key
    return _UNIT_SCALE.get(key)


def _bare(tail: list[str], unit: int | None) -> int | None:
    """The current year's figure from a table row's trailing numbers; decimals mark the money column over share counts."""
    numbers = [t for t in tail if any(ch.isdigit() for ch in t)]
    if not numbers:
        return None
    pick = next((t for t in numbers if "." in t), None) or (numbers[0] if len(numbers) <= 2 else None)
    if pick is None:
        return None
    try:
        value = float(pick.strip("()-").replace(",", "")) * (unit or 1)
    except ValueError:
        return None
    return round(value) if value >= 1 else None


# ---- pieces of an item ----

def _item(page: int, context: str, instrument: str, investee: str | None, amount: int | None, quantity: str | None,
          day: str | None, nature: str | None, approval: str | None, section: str | None, lender: str | None,
          confidence: float) -> dict[str, Any]:
    return {"investee": investee, "instrument": instrument, "amount": amount, "quantity": quantity, "date": day, "nature": nature,
            "approval": approval, "section": section, "lender": lender, "page": page, "context": context,
            "confidence": round(min(confidence, 0.95), 2)}


def _money(chunk: str) -> list[tuple[int, int, int, str]]:
    """Amounts in a piece of text, without face values and prices per share."""
    out = []
    for value, start, end, shown in amounts(chunk):
        if _PER.match(chunk, end) or _FACE_BEFORE.search(chunk[max(0, start - 30) : start]):
            continue
        out.append((value, start, end, shown))
    return out


def _quantities(chunk: str) -> list[tuple[str, int, int, str]]:
    out = []
    for m in _QUANTITY.finditer(chunk):
        if _RUPEE_BEFORE.search(chunk[max(0, m.start() - 8) : m.start()]):
            continue  # "₹10,000 in equity shares" is money, not a count
        out.append((m.group(1), m.start(), m.end(), " ".join(m.group(0).split())))
    return out


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()).replace("privatelimited", "pvtltd").replace("limited", "ltd")


def _own_names(doc: Doc) -> set[str]:
    """The company whose paper this is, so that it is never taken for its own investee."""
    own = {_norm(company_name(doc.company_name) or doc.company_name)} if doc.company_name else set()
    for _, text in doc.pages[:3]:
        for m in COMPANY.finditer(text):
            if _OWN_RAW.search(m.group(1)) or _THE_COMPANY.match(text, m.end()):
                cut = _LEAD.match(m.group(1))
                name = company_name(m.group(1)[cut.end() :] if cut else m.group(1))
                if name:
                    own.add(_norm(name))
    return own


def _company(raw: str) -> str | None:
    """company_name(), keeping the document's own casing ("XYZ Private Limited") unless the whole name is in capitals."""
    name = company_name(raw)
    if not name or raw.isupper():
        return name
    written = {w.lower(): w for w in raw.split()}
    return " ".join(w if w in ("Private", "Limited") else written.get(w.lower(), w) for w in name.split())


def _parties(chunk: str, own: set[str]) -> list[tuple[str, int, int, str]]:
    """Companies, banks, funds and people named in a piece of text: (name, start, end, kind)."""
    out: list[tuple[str, int, int, str]] = []
    for m in COMPANY.finditer(chunk):
        raw = m.group(1)
        if _OWN_RAW.search(raw) or _THE_COMPANY.match(chunk, m.end()):
            continue
        cut = _LEAD.match(raw)
        name = _company(raw[cut.end() :] if cut else raw)
        if not name or MARKET_BODIES.search(name) or _norm(name) in own:
            continue
        out.append((name, m.start() + (cut.end() if cut else 0), m.end(), "bank" if re.search(r"\bBank\b", name) else "company"))
    for kind, pattern in (("bank", _BANK), ("fund", _FUND)):
        for m in pattern.finditer(chunk):
            name = re.sub(r"^(?:The|In|Of|To|With)\s+", "", m.group(1).strip())
            if len(name.split()) >= 2 and not any(s <= m.start() < e for _, s, e, _ in out):
                out.append((name, m.start(), m.end(), kind))
    for m in PERSON.finditer(chunk):
        name = clean_person(m.group(1))
        if name and not any(s <= m.start() < e for _, s, e, _ in out):
            out.append((" ".join(m.group(0).split()[:1] + name.split()), m.start(), m.end(), "person"))
    return sorted(out, key=lambda p: p[1])


def _pick(parties: list[tuple[str, int, int, str]], position: int, label: str) -> tuple[str, int, int, str] | None:
    """The party a mention is about: the first named after it, else the nearest before it."""
    kinds = {"fixed deposit": ("bank",), "mutual fund units": ("fund", "company")}.get(label, ("company", "fund", "person"))
    if label in _LOANS or label in _CHARGES:
        kinds = ("company", "person")
    after = [p for p in parties if p[3] in kinds and p[1] >= position - 2 and p[1] - position <= 300]
    if after:
        return after[0]
    before = [p for p in parties if p[3] in kinds and p[2] <= position and position - p[2] <= 200]
    return before[-1] if before else None


def _fallback_party(chunk: str, position: int) -> str | None:
    m = _GROUP.search(chunk, max(0, position - 40))
    return " ".join(m.group(1).lower().split()) if m and m.start() - position <= 200 else None


def _date(page_dates: list[tuple[str, int, int]], position: int, doc: Doc) -> str | None:
    found = nearest(page_dates, position, 400)
    return found[0] if found else doc.meeting_date


def _sections(window: str) -> str | None:
    found: list[str] = []
    for m in SECTION.finditer(window):
        values = [m.group(1)]
        tail = m.end()
        while more := SECTION_MORE.match(window, tail):
            values.append(more.group(1))
            tail = more.end()
        for value in values:
            value = normal_section(value)
            if re.match(r"\d+", value).group(0) in _RELEVANT_SECTIONS and value not in found:
                found.append(value)
    return ", ".join(found) or None


def _section_before(text: str, position: int) -> str | None:
    """The last of the relevant sections (179 to 188) named before a place on the page."""
    found = None
    for m in SECTION.finditer(text, 0, position):
        value = normal_section(m.group(1))
        if re.match(r"\d+", value).group(0) in _RELEVANT_SECTIONS:
            found = value
    return found


def _approval(window: str) -> str | None:
    w = window.lower()
    if "special resolution" in w:
        out = "Special resolution"
    elif "ordinary resolution" in w:
        out = "Ordinary resolution"
    elif re.search(r"(?:approval|consent)\s+of\s+(?:the\s+)?(?:members|shareholders)|(?:members|shareholders)'?\s+(?:approval|consent)", w):
        out = "Members' approval"
    elif re.search(r"board\s+resolution|resolution\s+of\s+the\s+board|(?:meeting\s+of\s+the|consent\s+of\s+the|approval\s+of\s+the)\s+board|resolved\s+that", w):
        out = "Board resolution"
    else:
        return None
    return out + (" (s.186(3))" if re.search(r"186\s*\(\s*3\s*\)", w) else "")


def _nature(window: str, doc: Doc) -> str | None:
    w = window.lower()
    if doc.doc_type == "notice" or re.search(r"\bpropos\w*|\bseek\w*|\brecommend\w*|to\s+consider\s+and\s+if\s+thought\s+fit", w):
        return "proposed"
    if re.search(r"\bresolved\b|\bapprov\w*", w):
        return "approved"
    if re.search(r"\bas\s+at\b|\boutstanding\b|\bheld\b", w):
        return "outstanding"
    if re.search(r"\b(?:given|made|granted|advanced|placed|extended)\b", w):
        return "given"
    return None


# ---- the whole document ----

def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One item per investee, instrument and amount; a mention without an amount yields to one with it."""
    best: dict[tuple, dict[str, Any]] = {}
    for item in items:
        # The same limit told twice (the resolution and its explanatory statement) is one item, whatever words each uses;
        # the fuller telling ("loans, guarantees and security") is kept.
        limit = item["instrument"].endswith("(limit)")
        base = re.match(r"\d*", str(item["section"] or "")).group(0)  # "186(2)" and "186" are one section
        key = (_norm(item["investee"] or ""), f"limit:{base}" if limit else item["instrument"], item["amount"])
        kept = best.get(key)
        if kept is None or item["confidence"] > kept["confidence"] or (
                limit and item["confidence"] == kept["confidence"] and len(item["instrument"]) > len(kept["instrument"])):
            best[key] = item
    with_amount = {(k[0], k[1]) for k in best if k[2] is not None}
    return [i for k, i in best.items() if k[2] is not None or (k[0], k[1]) not in with_amount]


def _category(instrument: str) -> str:
    if instrument.endswith("(limit)"):
        return "limit"
    if instrument in _LOANS:
        return "loan"
    return instrument if instrument in _CHARGES else "investment"


def _facts(items: list[dict[str, Any]]) -> dict[str, Any]:
    dealings = [i for i in items if _category(i["instrument"]) != "limit"]
    # A s.185 approval is a limit too, but not the s.186 one; the summary names each by its section.
    limits = [i["amount"] for i in items if _category(i["instrument"]) == "limit" and i["amount"] and "185" not in str(i["section"] or "")]
    limits185 = [i for i in items if _category(i["instrument"]) == "limit" and i["amount"] and "185" in str(i["section"] or "")]
    total = sum(i["amount"] or 0 for i in dealings)
    return {
        "limit_185": max((i["amount"] for i in limits185), default=None),
        "parties_185": sorted({n for i in limits185 for n in str(i["investee"] or "").split("; ") if n and not n.startswith("Any ")}),
        "items": len(dealings),
        "total_amount": total,
        "total": _shown(total) if total else "",
        "by_instrument": dict(Counter(i["instrument"] for i in dealings)),
        "by_category": dict(Counter(_category(i["instrument"]) for i in dealings)),
        "limit": max(limits) if limits else None,
        "investees": sorted({i["investee"] for i in dealings if i["investee"]}),
    }


def _summary(items: list[dict[str, Any]], facts: dict[str, Any], full: str) -> str:
    words = {"investment": ("investment", "investments"), "loan": ("loan", "loans"), "guarantee": ("guarantee", "guarantees"),
             "security": ("security given", "securities given")}
    parts = [f"{n} {words[c][n != 1]}" for c in ("investment", "loan", "guarantee", "security") if (n := facts["by_category"].get(c))]
    said = ""
    if parts:
        said = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        if facts["total_amount"]:
            said += f", {facts['total']} in all"
    if facts["limit"]:
        verb = "raised to" if _RAISE.search(full) else "set at"
        limit = f"the limit under s.186 is {verb} {_shown(facts['limit'])}"
        said = f"{said}; {limit}" if said else limit[0].upper() + limit[1:]
    if facts.get("limit_185"):
        whom = f" for {len(facts['parties_185'])} parties in which a director is interested" if len(facts["parties_185"]) > 1 else ""
        limit = f"s.185 approval up to {_shown(facts['limit_185'])}{whom}"
        said = f"{said}; {limit}" if said else limit[0].upper() + limit[1:]
    if not said:
        return "Speaks of loans, guarantees or investments but names none in particular."
    return said + "."


def _shown(value: int) -> str:
    return rupees(value).replace(".00 ", " ")
