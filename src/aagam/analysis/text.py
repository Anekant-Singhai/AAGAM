"""Text helpers every analyser shares: sentences, context, keyword scoring, amounts and dates with their places."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from ..extract import AMOUNT, DATE_PATTERNS, amount_in_rupees, parse_date

# Abbreviations that end with a full stop but don't end a sentence.
_ABBREV = re.compile(
    r"\b(?:Rs|No|Nos|Ltd|Pvt|Co|Inc|Sec|Secs|S|Ss|Mr|Ms|Mrs|Dr|Shri|Smt|Sri|viz|i\.e|e\.g|etc|vs|v|Hon'ble|Honble|Cl|Para|Art|Reg|Regn|Govt|Dept|Ch|Vol|pp|p|Sl|St|Jr|Sr|Bros|Mfg|Corpn|Assn|Admn|Addl|Asstt|Dy|Jt|Gen|Spl|Misc|approx|cf|ibid|Gaz)\.$",
    re.IGNORECASE,
)


# A full stop may be followed by the closing quote of a resolution: '… principal business activities.” “RESOLVED FURTHER'.
_BREAK = re.compile(r"[.;:?!][\"”’']*(?=\s+[A-Z(\"“‘0-9])|\n\s*\n")


@dataclass(frozen=True)
class Span:
    page: int
    start: int
    end: int
    text: str


def sentences(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) for each sentence. Line breaks inside a sentence are joined; abbreviations don't split."""
    return list(_sentences(text))


@lru_cache(maxsize=512)
def _sentences(text: str) -> tuple[tuple[int, int, str], ...]:
    # Cached: analysers ask for the sentence around many places on the same page.
    out: list[tuple[int, int, str]] = []
    start = 0
    for m in _BREAK.finditer(text):
        end = m.end()
        # Only the last few characters can hold the abbreviation; looking further back made long pages slow.
        if m.group(0) == "." and _ABBREV.search(text[max(start, end - 16):end].rstrip()):
            continue
        clean = " ".join(text[start:end].split())
        if clean:
            out.append((start, end, clean))
        start = end
    tail = " ".join(text[start:].split())
    if tail:
        out.append((start, len(text), tail))
    return tuple(out)


def sentence_at(text: str, position: int) -> str:
    """The sentence that holds `position`."""
    for start, end, sentence in sentences(text):
        if start <= position < end:
            return sentence
    return context(text, position, position, 160)


def context(text: str, start: int, end: int, chars: int = 140) -> str:
    left = text[max(0, start - chars) : start]
    right = text[end : end + chars]
    return " ".join(f"{left}{text[start:end]}{right}".split())


def keyword_score(text: str, lexicon: dict[str, float]) -> float:
    """Sum of weights of the lexicon's phrases found in the text (each phrase counted up to three times)."""
    pattern, weights = _compiled(tuple(lexicon.items()))
    hits: dict[str, int] = {}
    for m in pattern.finditer(text.lower()):
        hits[m.group(0)] = hits.get(m.group(0), 0) + 1
    return sum(weights.get(" ".join(phrase.split()), 0.0) * min(n, 3) for phrase, n in hits.items())


@lru_cache(maxsize=64)
def _compiled(items: tuple[tuple[str, float], ...]) -> tuple[re.Pattern[str], dict[str, float]]:
    """One pattern for a whole lexicon, longest phrases first, so a page is read once rather than once per phrase."""
    phrases = sorted({p.lower() for p, _ in items}, key=len, reverse=True)
    body = "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in phrases) or "(?!)"
    return re.compile(rf"(?<![a-z])(?:{body})(?![a-z])"), {" ".join(p.lower().split()): w for p, w in items}


def relevance(pages: list[tuple[int, str]], lexicon: dict[str, float], scale: float = 12.0) -> float:
    """0 to 1: how much a document is about the lexicon's subject (keyword weight per thousand words, squashed)."""
    words = sum(len(t.split()) for _, t in pages) or 1
    raw = sum(keyword_score(t, lexicon) for _, t in pages)
    density = raw / max(words / 1000, 1)
    return round(min(1.0, density / scale), 3)


def key_sentences(pages: list[tuple[int, str]], lexicon: dict[str, float], limit: int = 5, min_words: int = 6) -> list[dict]:
    """The sentences that say most about the subject: the extractive summary of a document, with their pages."""
    scored = []
    for page, text in pages:
        for _, _, sentence in sentences(text):
            words = len(sentence.split())
            if words < min_words or words > 90:
                continue
            score = keyword_score(sentence, lexicon)
            if score > 0:
                scored.append((score / (words ** 0.35), page, sentence))
    scored.sort(key=lambda s: -s[0])
    seen: set[str] = set()
    out = []
    for score, page, sentence in scored:
        key = sentence[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"page": page, "text": sentence, "score": round(score, 2)})
        if len(out) == limit:
            break
    return out


def amounts(text: str) -> Iterator[tuple[int, int, int, str]]:
    """(rupees, start, end, as written) for each amount in the text."""
    for m in AMOUNT.finditer(text):
        value = amount_in_rupees(m.group(1), m.group(2))
        if value:
            yield value, m.start(), m.end(), " ".join(m.group(0).split())


def dates(text: str) -> Iterator[tuple[str, int, int]]:
    """(ISO date, start, end) for each date in the text."""
    seen: set[int] = set()
    for index, pattern in enumerate(DATE_PATTERNS):
        for m in pattern.finditer(text):
            if m.start() in seen:
                continue
            day = parse_date(m.groups(), index)
            if day:
                seen.add(m.start())
                yield day.isoformat(), m.start(), m.end()


def nearest(items: list[tuple], position: int, max_distance: int = 300) -> tuple | None:
    """The item (whose 2nd and 3rd fields are start and end) closest to `position`, if within reach."""
    best, best_distance = None, max_distance + 1
    for item in items:
        start, end = item[1], item[2]
        distance = 0 if start <= position <= end else min(abs(position - start), abs(position - end))
        if distance < best_distance:
            best, best_distance = item, distance
    return best


def rupees(value: int | None) -> str:
    if value is None:
        return ""
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:,.2f} crore"
    if value >= 100_000:
        return f"₹{value / 100_000:,.2f} lakh"
    return f"₹{value:,}"
