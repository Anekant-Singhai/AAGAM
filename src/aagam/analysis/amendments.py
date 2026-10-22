"""What an amending instrument changes: what is substituted, inserted or omitted, in which provision, from when.

Amending rules, Acts, notifications and circulars follow one drafting pattern: "In the said rules, in rule 2, in
sub-rule (1), for clause (t), the following clause shall be substituted, namely:—". Each "shall be substituted /
inserted / omitted" is one change. The provision it changes is put together from the "in rule 2, in sub-rule (1)"
phrases of the paragraph and sub-paragraphs it sits in, plus its own "for clause (t)" or "after rule 3". The new words
are the quoted text after "namely", or the words of "for the words "X", the words "Y" shall be substituted". The
instrument amended, the notification and the dates come from the preamble and the commencement clause.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from typing import Any

from . import Doc, result
from .law import NOTIFICATION, date_after, instrument_mentions, notification_reference, pretty_date
from .text import dates, key_sentences, relevance, sentences

KIND = "amendments"
TITLE = "Amendments"
COLUMNS = [
    {"key": "instrument", "label": "Instrument amended", "type": "text"},
    {"key": "notification", "label": "Notification", "type": "text"},
    {"key": "action", "label": "Change", "type": "text"},
    {"key": "target", "label": "Provision", "type": "text"},
    {"key": "effective", "label": "In force from", "type": "date"},
    {"key": "old", "label": "Old words", "type": "long"},
    {"key": "text", "label": "New words", "type": "long"},
]

_ACTION = re.compile(
    r"\b(?:shall|is\s+hereby|are\s+hereby|be\s+and\s+(?:is|are)\s+hereby)\s+(?:respectively\s+)?(?:be\s+|stand\s+)?"
    r"(substituted|inserted|omitted|deleted|added|renumbered|re-?numbered|re-?lettered|amended)\b",
    re.IGNORECASE,
)
_ACTIONS = {"substituted": "substituted", "inserted": "inserted", "added": "inserted", "omitted": "omitted",
            "deleted": "omitted", "renumbered": "renumbered", "re-numbered": "renumbered", "relettered": "renumbered",
            "re-lettered": "renumbered", "amended": "amended"}
_NOUNS = {"substituted": "substitution", "inserted": "insertion", "omitted": "omission", "renumbered": "renumbering",
          "amended": "amendment"}
_CONTAINER = re.compile(r"\s+(?i:as\s+follows|in\s+the\s+following\s+manner|as\s+under)")
_NAMELY = re.compile(
    r"\s*,?\s*(?i:namely|as\s+under|as\s+follows|by\s+the\s+following|with\s+the\s+following[^:\n]{0,40})\s*[:.,]?\s*[-—–]*\s*"
)
_RENUMBERED_AS = re.compile(r"\s+(?i:as)\s+(.{1,80}?)(?=\s*(?:;|\.(?:\s|$)|\bthereof\b|$))")

# Paragraph and sub-paragraph numbers that start a line, or follow a dash ("in clause (t),—(a) for …").
_MARKER = re.compile(r"(?:^|(?<=[—–:]))[ \t]*(?:(\d{1,3})\.(?=[ \t]+\S)|\((\d{1,3}[A-Z]?|[a-z]{1,4}|[A-Z])\)(?=\s))", re.M)
_WRAPPED = re.compile(r"\b(?i:sub-?\s?rule|sub-?\s?section|sub-?\s?regulation|rule|section|regulation|clause|item|para(?:graph)?|entry|proviso|of|in)\s*$")
_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii",
          "xviii", "xix", "xx"}

_UNITS = (r"sub-?\s?sections?|sub-?\s?rules?|sub-?\s?regulations?|sub-?\s?clauses?|sub-?\s?paragraphs?|sub-?\s?paras?|"
          r"sub-?\s?items?|sections?|rules?|regulations?|clauses?|items?|paragraphs?|paras?|provisos?|explanations?|"
          r"schedules?|divisions?|parts?|entry|entries|tables?|serial\s+numbers?|headings?|forms?|annexures?|chapters?|"
          r"articles?|columns?|rows?|long\s+title|preamble")
_LOCATOR = re.compile(
    r"(?:\b((?i:in|for|after|before|of|to))\s+)?(?:(?i:the)\s+)?"
    r"(?:((?i:following|new|said|existing|first|second|third|fourth|fifth|last|opening))\s+)?"
    rf"\b((?i:{_UNITS}))\b\s*(?:(?i:No)\.?\s*)?"
    r"((?:\(\s?\d{1,3}[A-Z]{0,3}\s?\)|\d{1,3}[A-Z]{0,3}(?!\d)|[IVXL]{1,7}\b|\(\s?[a-zA-Z]{1,5}\s?\))(?:\s?\(\s?[0-9a-zA-Z]{1,5}\s?\))*)?"
)
_PARENTS = {"section", "rule", "regulation", "article", "para"}
_CHILDREN = {"sub-section", "sub-rule", "sub-regulation", "clause", "sub-clause", "sub-para", "item", "sub-item"}
_UNNUMBERED = {"proviso", "Explanation", "heading", "Table", "long title", "preamble"}
_CAPITALISED = {"explanation": "Explanation", "schedule": "Schedule", "division": "Division", "part": "Part",
                "table": "Table", "form": "Form", "annexure": "Annexure", "chapter": "Chapter", "article": "Article",
                "serial number": "S. No.", "paragraph": "para", "sub-paragraph": "sub-para", "entries": "entry"}

_WORDS = r"(?:words?|figures?|letters?|brackets?|expressions?|signs?|symbols?|portion|numbers?|amount|digits?|marks?|commas?)"
_WORDS_GROUP = rf"{_WORDS}(?:\s*(?:,|and|&)\s*{_WORDS})*"
_FOR_WORDS = re.compile(rf"\b((?i:for|after|before))\s+(?i:the)\s+(?i:{_WORDS_GROUP})\b")
_THE_WORDS = re.compile(rf"\b(?i:the)\s+(?i:{_WORDS_GROUP})\b")
_QUOTED = re.compile(r"“([^”]{0,800})”|\"([^\"]{0,800})\"|‘([^’]{0,800})’|'([^'\n]{0,300})'")
# The end of a quoted new provision: its closing quote before ";" or ".", or before the next paragraph.
# A closing quote at the end of a line also ends it: SEBI numbers its changes "I.", "II.", which the other cues miss.
_CLOSE = re.compile(r"[\"”’'](?=[ \t]*[;.](?:\s|$)|\s*$|[ \t]*\n|[ \t]*(?:,?\s*(?:and|or))?\s*\n\s*(?:\(\w{1,5}\)|\d{1,3}\.\s|[IVXL]{1,6}\.\s|\[))")
_NEXT_PARA = re.compile(
    r"\n[ \t]*(?:(?:\d{1,3}|[IVXL]{1,6})\.[ \t]+(?:In|For|After|Before|Omission|Substitution|Insertion|Amendment|in|for|after|before)\b|\[\s*F\.\s?No\.|"
    r"\(\s*[a-z]{1,4}\s*\)[ \t]+(?:in|for|after|before)\s+(?:the\s+)?(?:words?|figures?|clause|sub-?rule|sub-?section|"
    r"rule|section|regulation|item|para|proviso|Explanation|Schedule|entry)\b)"
)
_LABEL = re.compile(r"^[\"“‘']?\s*(?:\((\d{1,3}[A-Z]{0,3}|[a-z]{1,4})\)|(\d{1,3}[A-Z]{1,3})\.)")

_FORCE = re.compile(
    r"(?i:shall\s+be\s+deemed\s+to\s+have\s+come\s+into\s+(?:force|effect)|shall\s+come\s+into\s+(?:force|effect)|"
    r"came\s+into\s+force|shall\s+(?:take|have)\s+effect|shall\s+be\s+(?:effective|applicable)|"
    r"with\s+effect\s+from|w\.\s?e\.\s?f\.?|effective\s+from)"
)
_ON_PUBLICATION = re.compile(r"\s*(?i:on|from|with\s+effect\s+from)?\s*(?i:the\s+)?(?i:date\s+of\s+(?:their|its|the|such)?\s*publication)")
_LATER_DATE = re.compile(r"\s*(?i:on|from)?\s*(?i:such\s+date\s+as\s+the\s+Central\s+Government)")
_IMMEDIATE = re.compile(r"\s*(?i:with\s+immediate\s+effect|immediately|at\s+once)")
_NEW_DELHI = re.compile(r"(?i:New\s+Delhi|Mumbai),?\s*(?:(?i:the)\s+)?")
_NOTIFICATION_DATED = re.compile(r"(?i:notification)[^.\n]{0,80}?\b(?i:dated)\s+(?:(?i:the)\s+)?")
_AMENDS = re.compile(r"(?i:further\s+to\s+amend|to\s+amend|amendments?\s+(?:in|to))\s+(?:(?i:the)\s+)?|\b[Ii]n\s+the\s+")
_HEREINAFTER = re.compile(r"\s*(?:\(\d{1,3}\s+of\s+\d{4}\)\s*)?,?\s*\(?\s*(?i:hereinafter\s+(?:referred\s+to\s+as|called))\s+(?i:the)\s+(?i:said|principal)")
_CALLED = re.compile(r"(?i:may\s+be\s+called)\s+(?:(?i:the)\s+)?")
_AMENDING = re.compile(r"(?i)\bamendment\b")

_LEXICON = {
    "shall be substituted": 3.0, "shall be inserted": 3.0, "shall be omitted": 3.0, "amendment rules": 3.0,
    "amendment regulations": 3.0, "(amendment)": 2.0, "further to amend": 3.0, "come into force": 2.0,
    "official gazette": 2.0, "notification": 1.5, "g.s.r.": 2.0, "namely": 1.0, "principal act": 2.0,
    "said rules": 2.0, "said regulations": 2.0, "hereinafter referred to as": 1.0, "the following": 1.0,
}


def analyse(doc: Doc) -> dict[str, Any] | None:
    pages = [(page, text or "") for page, text in doc.pages]
    text, offsets = _join(pages)
    if not _ACTION.search(text):
        return None  # nothing is substituted, inserted or omitted: not an amending text
    mentions = instrument_mentions(text)
    notification, notified = _notification(text)
    effective, basis = _effective(text, notified)
    amended = _amended(text, mentions)
    amending = _amending(text, mentions)
    changes = _changes(text, mentions)
    if not changes:
        return None
    items = []
    for change in changes:
        position = change.pop("_at")
        page = pages[bisect_right(offsets, position) - 1][0] if pages else 1
        items.append({"instrument": change.pop("_instrument") or amended, "notification": notification,
                      "action": change["action"], "target": change["target"], "effective": effective,
                      "old": change["old"], "text": change["text"], "page": page, "context": change["context"]})
    counts = Counter(i["action"] for i in items)
    facts = {
        "instrument": amended or None, "amending_instrument": amending or None, "notification": notification or None,
        "notification_date": notified, "effective": effective, "effective_basis": basis,
        "retrospective": basis == "deemed", "changes": {a: counts[a] for a in _NOUNS if counts[a]},
    }
    score = max(relevance(pages, _LEXICON), min(1.0, 0.35 + 0.1 * len(items)))
    return result(KIND, TITLE, COLUMNS, items, score, _summary(amended, effective, basis, counts), ["amendment"],
                  key_sentences(pages, _LEXICON, 5), facts)


def _join(pages: list[tuple[int, str]]) -> tuple[str, list[int]]:
    """All pages as one text (a new provision often runs over a page break) and where each page starts."""
    offsets, parts, at = [], [], 0
    for _, page_text in pages:
        offsets.append(at)
        parts.append(page_text)
        at += len(page_text) + 1
    return "\n".join(parts), offsets


# --- The instrument, the notification and the dates ---------------------------------------------------------------

def _notification(text: str) -> tuple[str, str | None]:
    """The notification number and its date: "G.S.R. 880(E)" dated, or the "New Delhi, the 1st December, 2025" line."""
    number, day = "", None
    m = NOTIFICATION.search(text)
    if m:
        number = notification_reference(m)[1]
        day = date_after(text, m.end())
    if day is None:
        for pattern in (_NEW_DELHI, _NOTIFICATION_DATED):
            for lead in pattern.finditer(text, 0, min(len(text), 20000)):
                day = next((iso for iso, start, _ in dates(text[lead.end(): lead.end() + 40]) if start <= 2), None)
                if day:
                    break
            if day:
                break
    return number, day


def _effective(text: str, notified: str | None) -> tuple[str | None, str]:
    """When the changes take effect, and why: "publication", "stated", "deemed" (retrospective) or "to be notified"."""
    found = list(_FORCE.finditer(text))
    # The commencement clause ("shall come into force") outranks a passing "with effect from".
    found.sort(key=lambda m: (0 if m.group(0).lower().startswith(("shall", "came")) else 1, m.start()))
    for m in found:
        if _ON_PUBLICATION.match(text, m.end()):
            return notified, "publication"
        if _LATER_DATE.match(text, m.end()):
            return None, "to be notified"
        if _IMMEDIATE.match(text, m.end()):
            return notified, "publication"
        window = text[m.end(): m.end() + 80]
        day = next((iso for iso, start, _ in dates(window) if start <= 30), None)
        if day:
            return day, "deemed" if "deemed" in m.group(0).lower() else "stated"
    return None, ""


def _amended(text: str, mentions: list[tuple[int, int, str, str]]) -> str:
    """The instrument being amended: the one "hereinafter referred to as the principal Act / said rules", the one "further
    to amend" or "In the …" names, else the amending instrument's name without "Amendment"."""
    plain = [m for m in mentions if not _AMENDING.search(m[2])]
    for _, end, name, _kind in plain:
        if _HEREINAFTER.match(text, end):
            return name
    by_start = {m[0]: m[2] for m in plain}
    for lead in _AMENDS.finditer(text):
        if name := by_start.get(lead.end()):
            return name
    amending = _amending(text, mentions)
    if amending:
        base = re.sub(r"\s*\(?\b(?:(?:First|Second|Third|Fourth|Fifth)\s+)?Amendment\b\)?", "", amending, flags=re.I)
        base = re.sub(r",\s*\d{4}$", "", base)
        same = [m[2] for m in plain if m[2].startswith(base)]
        return same[0] if same else base
    counts = Counter(m[2] for m in plain)
    return counts.most_common(1)[0][0] if counts else ""


def _amending(text: str, mentions: list[tuple[int, int, str, str]]) -> str:
    by_start = {m[0]: m[2] for m in mentions}
    for lead in _CALLED.finditer(text):
        if name := by_start.get(lead.end()):
            return name
    return next((m[2] for m in mentions if _AMENDING.search(m[2])), "")


# --- The changes --------------------------------------------------------------------------------------------------

def _changes(text: str, mentions: list[tuple[int, int, str, str]]) -> list[dict[str, Any]]:
    # "(1)" at the start of a line is a sub-paragraph, unless the line before ends "… in sub-rule" and it was wrapped.
    markers = [m for m in _MARKER.finditer(text)
               if m.group(1) or not _WRAPPED.search(text[max(0, m.start() - 25): m.start()].rstrip(" \t\n"))]
    spans = sentences(text)
    starts = [s for s, _, _ in spans]
    mention_starts = [m[0] for m in mentions]
    stack: list[tuple[str, int]] = []  # (style, position) of the paragraphs the reading is inside
    last_letter = ""
    consumed: list[tuple[int, int]] = []  # quoted new provisions, which are not read for locators
    done = 0  # everything before this has been read
    at_marker = 0
    out: list[dict[str, Any]] = []
    for trigger in _ACTION.finditer(text):
        p = trigger.start()
        if p < done:
            continue  # inside a quoted new provision
        while at_marker < len(markers) and markers[at_marker].start() < p:
            marker = markers[at_marker]
            at_marker += 1
            if marker.start() < done:
                continue
            style, last_letter = _style(marker, last_letter)
            for i, (s, _) in enumerate(stack):
                if s == style:
                    del stack[i:]
                    break
            stack.append((style, marker.start(marker.lastindex or 0)))
        action = _ACTIONS[trigger.group(1).lower()]
        if action == "amended" and _CONTAINER.match(text, trigger.end()):
            done = trigger.end()
            continue  # "Schedule III shall be amended as follows": a heading over the changes that follow
        i = bisect_right(starts, p) - 1
        sentence_start = spans[i][0] if i >= 0 else 0
        top = stack[-1][1] if stack else sentence_start
        inner_start = max(top, sentence_start, p - 1500) if stack else max(sentence_start, p - 1500)
        clause_start = max(inner_start, done)
        clause = text[clause_start:p]
        # The provision: "in" phrases of the enclosing paragraphs, then this one's, then its own "for / after" phrase.
        context = []
        for (_, a), (_, b) in zip(stack, stack[1:], strict=False):
            context += _groups(_visible(text, a, min(b, a + 600), consumed), ("in",))
        context += _groups(_visible(text, inner_start, p, consumed), ("in",))
        own = _groups(_visible(text, clause_start, p, consumed), ("for", "after", "before", None))
        old, new, anchor = _words(clause, action)
        if not new and action in ("substituted", "inserted") or action == "renumbered":
            block = _block(text, trigger.end(), action)
            if block:
                new, end_at = block
                consumed.append((trigger.end(), end_at))
                done = end_at
            else:
                done = trigger.end()
        else:
            done = trigger.end()
        target = _target(context, own, action, new, anchor)
        k = bisect_right(mention_starts, p) - 1
        floor = stack[0][1] if stack else sentence_start
        instrument = ""
        while k >= 0 and mentions[k][0] >= floor:
            if not _AMENDING.search(mentions[k][2]):
                instrument = mentions[k][2]
                break
            k -= 1
        sentence = spans[i][2] if i >= 0 else ""
        out.append({"action": action, "target": target, "old": old, "text": new, "_at": p, "_instrument": instrument,
                    "context": sentence if len(sentence) <= 400 else sentence[:400] + "…"})
    return out


def _style(marker: re.Match, last_letter: str) -> tuple[str, str]:
    """Which numbering a paragraph uses: "2.", "(1)", "(a)", "(i)" or "(A)". "(i)" after "(h)" is a letter."""
    if marker.group(1):
        return "number", ""
    label = marker.group(2)
    if label.isdigit() or label[:-1].isdigit():
        return "bracket", ""
    if label.isupper():
        return "capital", last_letter
    if label in _ROMAN and not (len(label) == 1 and last_letter and ord(label) - ord(last_letter) == 1):
        return "roman", last_letter
    return "letter", label


def _visible(text: str, a: int, b: int, consumed: list[tuple[int, int]]) -> str:
    """text[a:b] without the quoted new provisions and quoted words in it, so their words aren't read as locators."""
    pieces, pos = [], a
    for s, e in consumed:
        if e <= pos or s >= b:
            continue
        pieces.append(text[pos:s])
        pos = max(pos, e)
    pieces.append(text[pos:b] if pos < b else "")
    return _QUOTED.sub(" ", " ".join(pieces))


def _groups(snippet: str, preps: tuple[str | None, ...]) -> list[tuple[str | None, str, str, str]]:
    """Locators in a phrase, in order from the outside in: "in clause (b) of sub-section (2) of section 135" reads as
    section 135, sub-section (2), clause (b). Only groups whose first word is one of `preps` are kept."""
    groups: list[list[tuple[str | None, str, str, str]]] = []
    for m in _LOCATOR.finditer(snippet):
        prep = m.group(1).lower() if m.group(1) else None
        modifier = (m.group(2) or "").lower()
        if modifier in ("following", "new", "said"):
            continue
        unit = _unit(m.group(3))
        number = re.sub(r"\s+", "", m.group(4) or "")
        if not number and unit not in _UNNUMBERED:
            continue
        ordinal = modifier if modifier in ("first", "second", "third", "fourth", "fifth", "last", "opening") else ""
        entry = (prep, unit, number, ordinal)
        if prep in ("of", "to") and groups:
            groups[-1].append(entry)
        else:
            groups.append([entry])
    out = []
    for group in groups:
        if group[0][0] in preps:
            out.extend(reversed(group))
    return out


def _unit(raw: str) -> str:
    unit = re.sub(r"\s+", " ", raw.lower())
    unit = re.sub(r"^sub-?\s?", "sub-", unit)
    if unit not in ("entries", "long title", "preamble") and unit.endswith("s") and not unit.endswith("ss"):
        unit = unit[:-1]
    if unit.startswith("serial number"):
        unit = "serial number"
    return _CAPITALISED.get(unit, unit)


def _compose(path: list[tuple[str | None, str, str, str]]) -> str:
    """'rule 2(1)(t)', 'section 135(2)(b)', 'Schedule III, Division II, para 7', 'rule 4, second proviso'."""
    seen, parts, base = set(), [], ""
    for _, unit, number, ordinal in path:
        if (unit, number) in seen:
            continue
        seen.add((unit, number))
        if unit in _PARENTS and number:
            base = f"{unit} {number}"  # a new rule replaces the one before it
        elif unit in _CHILDREN and number:
            bracketed = number if number.startswith("(") else f"({number})"
            base = base + bracketed if base else f"{unit} {bracketed}"
        elif unit in _UNNUMBERED:
            if base:
                parts.append(base)
                base = ""
            parts.append(f"{ordinal} {unit}".strip())
        else:
            if base:
                parts.append(base)
                base = ""
            parts.append(f"{unit} {number}")
    if base:
        parts.append(base)
    return ", ".join(parts)


def _target(context: list, own: list, action: str, new: str, anchor: str) -> str:
    where = [g for g in own if g[0] in ("after", "before")]
    plain = [g for g in own if g[0] not in ("after", "before")]
    target = _compose(context + plain)
    if where and action == "inserted":
        prep, unit, number, ordinal = where[0]
        label = _LABEL.match(new or "")
        if label and unit in _PARENTS | _CHILDREN:
            number_new = label.group(1) or label.group(2)
            return f"{_compose(context + [(None, unit, number_new, '')])} (inserted {prep} {_compose([where[0]])})"
        position = f"{prep} {_compose([where[0]])}"
        return f"{target}, {position}" if target else position
    if anchor:
        return f'{target}, after "{anchor}"' if target else f'after "{anchor}"'
    return target


def _words(clause: str, action: str) -> tuple[str, str, str]:
    """(old words, new words, anchor) from 'for the words "X", the words "Y" shall be substituted' and the like."""
    if action in ("substituted", "inserted"):
        lead = _last(_FOR_WORDS, clause)
        if lead is not None:
            rest = clause[lead.end():]
            first = _QUOTED.search(rest)
            then = _THE_WORDS.search(rest, first.end()) if first else None
            before = _quoted(rest[: then.start()] if then else rest)
            after = _quoted(rest[then.end():]) if then else []
            if lead.group(1).lower() == "for" and action == "substituted":
                return "; ".join(before), "; ".join(after), ""
            return "", "; ".join(after), "; ".join(before)
        then = _last(_THE_WORDS, clause)
        if then is not None and action == "inserted" and (words := _quoted(clause[then.end():])):
            return "", "; ".join(words), ""  # "at the end, the words "X" shall be added"
        return "", "", ""
    if action == "omitted" and (then := _last(_THE_WORDS, clause)) is not None:
        return "; ".join(_quoted(clause[then.end():])), "", ""
    return "", "", ""


def _last(pattern: re.Pattern, text: str) -> re.Match | None:
    """The last match: the words phrase nearest the "shall be …" it belongs to."""
    found = None
    for found in pattern.finditer(text):  # noqa: B007 - the loop is how the last one is reached
        pass
    return found


def _quoted(region: str) -> list[str]:
    return [" ".join(next(g for g in m.groups() if g is not None).split()) for m in _QUOTED.finditer(region)]


def _block(text: str, start: int, action: str) -> tuple[str, int] | None:
    """The new provision after "namely:—", quoted, up to its closing quote or the next paragraph; or the new number
    after "renumbered as"."""
    if action == "renumbered":
        m = _RENUMBERED_AS.match(text, start)
        return (" ".join(m.group(1).split()), m.end()) if m else None
    lead = _NAMELY.match(text, start)
    if not lead or lead.end() == start:
        return None
    s = lead.end()
    limit = min(len(text), s + 6000)
    para = _NEXT_PARA.search(text, s + 1, limit)
    cut = para.start() if para else limit
    if s < len(text) and text[s] in "\"“‘'":
        close = _CLOSE.search(text, s + 1, cut)
        if close:
            cut = close.end()
    words = " ".join(text[s:cut].split()).strip()
    words = words[1:] if words[:1] in "\"“‘'" else words
    words = re.sub(r"[\"”’']?\s*[;.]?\s*$", "", words) if words[-1:] in "\"”’';." else words
    if not words:
        return None
    return (words if len(words) <= 2000 else words[:2000] + "…"), cut


def _summary(amended: str, effective: str | None, basis: str, counts: Counter) -> str:
    changes = ", ".join(f"{counts[a]} {_NOUNS[a]}{'s' if counts[a] > 1 else ''}" for a in _NOUNS if counts[a])
    when = ""
    if effective:
        when = f" with retrospective effect from {pretty_date(effective)}" if basis == "deemed" else f" from {pretty_date(effective)}"
    elif basis == "publication":
        when = " from its publication in the Gazette"
    elif basis == "to be notified":
        when = " from a date to be notified"
    return f"Amends the {amended}{when}: {changes}." if amended else f"Amendments{when}: {changes}."
