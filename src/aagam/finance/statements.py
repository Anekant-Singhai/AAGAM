"""Reading the figures out of financial statements in the Schedule III format.

Indian companies present their balance sheet and statement of profit and
loss in the format of Schedule III to the Companies Act, 2013 (Division I
for companies on the Accounting Standards, Division II for Ind AS). The
captions are prescribed, so they can be found by their words. The same
caption means different things in different places ("Borrowings" under
non-current or current liabilities), so the reader follows the section
headings as it goes down the page.

Figures are read from the end of each line (current year, then previous
year), skipping a note number. "(1,234)" is negative, "-" is nil. The unit
printed at the top ("₹ in lakhs", "Rs. in thousands") turns them into whole
rupees. Everything read is marked with its page, and anything she corrects
is kept as hers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..extract import DATE_PATTERNS, parse_date

# (key, label, statement, section it must sit in or None, pattern). The first pattern that fits a line wins.
CATALOGUE: list[tuple[str, str, str, str | None, str]] = [
    # Balance sheet: equity
    ("share_capital", "Equity share capital", "bs", None, r"^(?:\(a\)\s*)?(?:equity\s+)?share\s+capital\b"),
    ("other_equity", "Other equity / reserves and surplus", "bs", None, r"^(?:\(b\)\s*)?(?:other\s+equity|reserves\s+(?:and|&)\s+surplus)\b"),
    ("total_equity", "Total equity", "bs", None, r"^total\s+(?:equity\b(?!\s+and)|shareholders'?\s*funds)"),
    # Non-current liabilities
    ("long_term_borrowings", "Long-term borrowings", "bs", "nc_liab", r"^(?:\(i\)\s*|\(a\)\s*)?(?:long[\s-]term\s+)?borrowings\b"),
    ("nc_lease_liabilities", "Lease liabilities (non-current)", "bs", "nc_liab", r"^(?:\(\w+\)\s*)?lease\s+liabilities\b"),
    ("deferred_tax_liabilities", "Deferred tax liabilities (net)", "bs", "nc_liab", r"^(?:\(\w+\)\s*)?deferred\s+tax\s+liabilit"),
    ("long_term_provisions", "Long-term provisions", "bs", "nc_liab", r"^(?:\(\w+\)\s*)?(?:long[\s-]term\s+)?provisions\b"),
    ("total_non_current_liabilities", "Total non-current liabilities", "bs", None, r"^total\s+non[\s-]current\s+liabilities"),
    # Current liabilities
    ("short_term_borrowings", "Short-term borrowings", "bs", "c_liab", r"^(?:\(i\)\s*|\(a\)\s*)?(?:short[\s-]term\s+)?borrowings\b"),
    ("c_lease_liabilities", "Lease liabilities (current)", "bs", "c_liab", r"^(?:\(\w+\)\s*)?lease\s+liabilities\b"),
    ("msme_dues", "Trade payables: dues of micro and small enterprises", "bs", "c_liab", r"(?:total\s+)?(?:outstanding\s+)?dues\s+(?:of|to)\s+micro\s+(?:enterprises\s+)?(?:and|&)\s+small"),
    ("other_payables", "Trade payables: dues of others", "bs", "c_liab", r"(?:total\s+)?(?:outstanding\s+)?dues\s+(?:of|to)\s+(?:creditors\s+)?other\s+than\s+micro"),
    ("trade_payables", "Trade payables", "bs", "c_liab", r"^(?:\(\w+\)\s*)?trade\s+pay\w{0,2}les\b"),
    ("other_current_liabilities", "Other current liabilities", "bs", "c_liab", r"^(?:\(\w+\)\s*)?other\s+current\s+liabilities\b"),
    ("short_term_provisions", "Short-term provisions", "bs", "c_liab", r"^(?:\(\w+\)\s*)?(?:short[\s-]term\s+)?provisions\b"),
    ("current_tax_liabilities", "Current tax liabilities (net)", "bs", "c_liab", r"^(?:\(\w+\)\s*)?current\s+tax\s+liabilit"),
    ("total_current_liabilities", "Total current liabilities", "bs", None, r"^total\s+current\s+liabilities"),
    ("total_equity_and_liabilities", "Total equity and liabilities", "bs", None, r"^total\s+(?:equity\s+and\s+liabilities|of\s+equity|liabilities\s+and\s+equity)"),
    # Non-current assets
    ("ppe", "Property, plant and equipment", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?(?:property,?\s+plant\s+(?:and|&)\s+equipment|tangible\s+assets)\b"),
    ("cwip", "Capital work-in-progress", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?capital\s+work[\s-]in[\s-]progress"),
    ("intangible_assets", "Intangible assets", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?(?:other\s+)?intangible\s+assets\b(?!\s+under)"),
    ("non_current_investments", "Non-current investments", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?(?:non[\s-]current\s+)?investments\b"),
    ("long_term_loans", "Long-term loans and advances", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?(?:long[\s-]term\s+)?loans(?:\s+(?:and|&)\s+advances)?\b"),
    ("deferred_tax_assets", "Deferred tax assets (net)", "bs", "nc_assets", r"^(?:\(\w+\)\s*)?deferred\s+tax\s+assets"),
    ("total_non_current_assets", "Total non-current assets", "bs", None, r"^total\s+non[\s-]current\s+assets"),
    # Current assets
    ("inventories", "Inventories", "bs", "c_assets", r"^(?:\(\w+\)\s*)?inventories\b"),
    ("current_investments", "Current investments", "bs", "c_assets", r"^(?:\(\w+\)\s*)?(?:current\s+)?investments\b"),
    ("trade_receivables", "Trade receivables", "bs", "c_assets", r"^(?:\(\w+\)\s*)?trade\s+receivables\b"),
    ("cash", "Cash and cash equivalents", "bs", "c_assets", r"^(?:\(\w+\)\s*)?cash\s+(?:and|&)\s+(?:cash\s+equivalents|bank\s+balances)"),
    ("other_bank_balances", "Other bank balances", "bs", "c_assets", r"^(?:\(\w+\)\s*)?(?:other\s+)?bank\s+balances\s+other\s+than"),
    ("short_term_loans", "Short-term loans and advances", "bs", "c_assets", r"^(?:\(\w+\)\s*)?(?:short[\s-]term\s+)?loans(?:\s+(?:and|&)\s+advances)?\b"),
    ("other_current_assets", "Other current assets", "bs", "c_assets", r"^(?:\(\w+\)\s*)?other\s+current\s+assets\b"),
    ("total_current_assets", "Total current assets", "bs", None, r"^total\s+current\s+assets"),
    ("total_assets", "Total assets", "bs", None, r"^total\s+assets\b"),
    # Statement of profit and loss
    ("revenue", "Revenue from operations", "pl", None, r"^(?:i\.?\s+|\(i\)\s*)?revenue\s+from\s+operations\b"),
    ("other_income", "Other income", "pl", None, r"^(?:ii\.?\s+|\(ii\)\s*)?other\s+income\b"),
    ("total_income", "Total income", "pl", None, r"^(?:iii\.?\s+)?total\s+(?:income|revenue)\b"),
    ("materials", "Cost of materials consumed", "pl", None, r"^(?:\(\w+\)\s*)?cost\s+of\s+(?:\w+\s+){0,2}materials?\s+consumed"),
    ("direct_expenses", "Direct costs (construction, operating, services)", "pl", None,
     r"^(?:\(\w+\)\s*)?(?:construction|manufacturing|project|direct|operating)\s+(?:and\s+\w+\s+)?expenses\b|^(?:\(\w+\)\s*)?cost\s+of\s+(?:services|revenue|sales)\b"),
    ("purchases", "Purchases of stock-in-trade", "pl", None, r"^(?:\(\w+\)\s*)?purchases?\s+of\s+stock[\s-]in[\s-]trade"),
    ("inventory_change", "Changes in inventories", "pl", None, r"^(?:\(\w+\)\s*)?changes?\s+in\s+inventories"),
    ("employee_costs", "Employee benefits expense", "pl", None, r"^(?:\(\w+\)\s*)?employee\s+benefits?\s+expenses?"),
    ("finance_costs", "Finance costs", "pl", None, r"^(?:\(\w+\)\s*)?finance\s+costs?\b"),
    ("depreciation", "Depreciation and amortisation", "pl", None, r"^(?:\(\w+\)\s*)?depreciation(?:\s+(?:and|&)\s+amorti[sz]ation)?(?:\s+expenses?)?\b"),
    ("other_expenses", "Other expenses", "pl", None, r"^(?:\(\w+\)\s*)?other\s+expenses\b"),
    ("total_expenses", "Total expenses", "pl", None, r"^(?:iv\.?\s+)?total\s+expenses\b"),
    ("exceptional_items", "Exceptional items", "pl", None, r"^(?:\w+\.?\s+)?exceptional\s+items?\b(?!\s+and)"),
    ("profit_before_tax", "Profit before tax", "pl", None, r"^(?:\w+\.?\s+)?(?:net\s+)?profit\s*/?\s*\(?(?:loss)?\)?\s+before\s+tax"),
    ("tax_expense", "Total tax expense", "pl", None, r"^(?:\w+\.?\s+)?(?:total\s+)?tax\s+expenses?\b\s*(?:\(net\))?\s*[\d(\-–]"),
    ("profit_after_tax", "Profit for the year", "pl", None, r"^(?:\w+\.?\s+)?(?:net\s+)?profit\s*/?\s*\(?(?:loss)?\)?\s+for\s+the\s+(?:year|period)\b"),
    ("eps_basic", "Earnings per share: basic (₹)", "pl", None, r"^(?:\(\w+\)\s*)?basic\b"),
]
SECTIONS = [
    ("nc_liab", r"^(?:\(?\d\)?\.?\s*|\(?[a-z]\)\s*)?non[\s-]current\s+liabilities\b(?!\s*\d)"),
    ("c_liab", r"^(?:\(?\d\)?\.?\s*|\(?[a-z]\)\s*)?current\s+liabilities\b(?!\s*\d)"),
    ("nc_assets", r"^(?:\(?\d\)?\.?\s*|\(?[a-z]\)\s*)?non[\s-]current\s+assets\b(?!\s*\d)"),
    ("c_assets", r"^(?:\(?\d\)?\.?\s*|\(?[a-z]\)\s*)?current\s+assets\b(?!\s*\d)"),
    ("equity", r"^(?:\(?\d\)?\.?\s*|\(?[a-z]\)\s*)?(?:equity|shareholders'?\s+funds)\b(?!\s*share)(?!\s*\d)"),
]
_COMPILED = [(k, label, st, sec, re.compile(p, re.IGNORECASE)) for k, label, st, sec, p in CATALOGUE]
_SECTIONS = [(name, re.compile(p, re.IGNORECASE)) for name, p in SECTIONS]
LABELS = {k: label for k, label, *_ in CATALOGUE}

BALANCE_SHEET = re.compile(r"(?i)balance\s+sheet\s+as\s+(?:at|on)")
PROFIT_LOSS = re.compile(
    r"(?i)statement\s+of\s+(?:\w+\s+){0,2}profit\s+(?:and|&)\s+loss|profit\s+(?:and|&)\s+loss\s+(?:account|statement)"
)
CONSOLIDATED = re.compile(r"(?i)consolidated")
NOTES = re.compile(r"(?i)notes\s+(?:to|forming\s+part\s+of)\s+(?:the\s+)?(?:standalone\s+|consolidated\s+)?(?:financial\s+statements|accounts)|accounting\s+policies")


def heading(text: str, lines: int = 8) -> str:
    """The first few lines of a page, where a statement names itself."""
    return "\n".join([line for line in text.split("\n") if line.strip()][:lines])


def is_statement_page(text: str) -> bool:
    head = heading(text)
    return bool(BALANCE_SHEET.search(head) or PROFIT_LOSS.search(head)) and not NOTES.search(head)
NUMBER = re.compile(r"\(\s*[\d,]+(?:\.\d+)?\s*\)|-?[\d,]*\d(?:\.\d+)?|(?<![\w])[-–—](?![\w])")
UNIT = re.compile(
    r"(?i)(?:amount|amounts|figures|all\s+amounts?)?\s*\(?\s*(?:in\s+)?(?:₹|rs\.?|inr|`|rupees)\s*(?:in\s+)?(crores?|lakhs?|lacs?|thousands?|'000|000s|millions?)\b"
    r"|(?:₹|rs\.?|inr|`)\s*(?:in\s+)?(crores?|lakhs?|lacs?|thousands?|millions?)"
    r"|(?:amounts?|figures)\s+(?:are\s+)?in\s+(?:\S{1,2}\s+)?(crores?|lakhs?|lacs?|thousands?|millions?)\b"
)
# Under a "Trade payables" heading, the two parts are often written short.
PAYABLE_PARTS = [
    ("msme_dues", re.compile(r"(?i)^(?:\(\w+\)\s*)?(?:micro|msme)\b")),
    ("other_payables", re.compile(r"(?i)^(?:\(\w+\)\s*)?others?\b")),
]
# A row of figures with no caption, at the end of a section, is that section's total.
SECTION_TOTALS = {
    "nc_assets": "total_non_current_assets",
    "c_assets": "total_current_assets",
    "equity": "total_equity",
    "nc_liab": "total_non_current_liabilities",
    "c_liab": "total_current_liabilities",
}
LEADING_NUMERAL = re.compile(r"^(?:[IVX]{1,4}|[ivx]{1,4}|\d{1,2})[.)]?\s+(?=\D)")
_FACTOR = {"crore": 10_000_000, "lakh": 100_000, "lac": 100_000, "thousand": 1_000, "'000": 1_000, "000": 1_000, "million": 1_000_000}


@dataclass
class Statement:
    basis: str = "standalone"
    period_end: str | None = None
    prior_period_end: str | None = None
    unit: str | None = None
    unit_factor: int = 1
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    pages: list[int] = field(default_factory=list)

    def value(self, key: str, column: str = "current") -> int | None:
        item = self.items.get(key)
        return item.get(column) if item else None


def parse_number(token: str) -> float | None:
    token = token.strip()
    if token in ("-", "–", "—"):
        return 0.0
    negative = token.startswith("(") and token.endswith(")")
    digits = token.strip("()").replace(",", "").strip()
    try:
        value = float(digits)
    except ValueError:
        return None
    return -value if negative else value


def figures(rest: str) -> list[float]:
    """The amounts at the end of a line, without the note number."""
    tokens = [t for t in NUMBER.findall(rest) if t.strip()]
    values = [parse_number(t) for t in tokens]
    numbers = [(t, v) for t, v in zip(tokens, values, strict=True) if v is not None]
    # A leading small number without thousands separators is the note ("3", "4.1"), not an amount.
    first_is_note = bool(numbers) and _looks_like_note(numbers[0][0])
    if first_is_note and len(numbers) == 1:
        return []  # "(b) Trade payables 15": only the note; the amounts are on the lines below
    if first_is_note and (len(numbers) >= 3 or (len(numbers) == 2 and not _looks_like_note(numbers[1][0]))):
        numbers = numbers[1:]
    return [v for _, v in numbers[-2:]]


def _looks_like_note(token: str) -> bool:
    """Note numbers are "3", "14", "6.1", "5a"; "37.78" is an amount."""
    return bool(re.fullmatch(r"\d{1,2}(?:\.\d)?[a-z]?", token.strip()))


def repair(items: dict[str, dict[str, Any]]) -> None:
    """Fix revenue misread by a scanner (24,668.23 read as 24.66823) when total income says what it must be."""
    for column in ("current", "previous"):
        revenue, other, total = (items.get(k, {}).get(column) for k in ("revenue", "other_income", "total_income"))
        if not revenue or total is None or other is None or abs(revenue + other - total) <= max(abs(total) * 0.005, 1000):
            continue
        implied = total - other
        ratio = implied / revenue if revenue else 0
        if any(abs(ratio - 10 ** k) / 10 ** k < 0.002 for k in range(1, 6)):
            item = items["revenue"]
            item.setdefault("repaired", {})[column] = revenue
            item[column] = implied


def unit_of(text: str) -> tuple[str | None, int]:
    m = UNIT.search(text)
    if not m:
        return None, 1
    word = (m.group(1) or m.group(2) or m.group(3) or "").lower()
    key = word.rstrip("s") if word not in ("'000", "000s") else "'000"
    return " ".join(m.group(0).split()).strip("() "), _FACTOR.get(key, 1)


def _periods(text: str) -> list[str]:
    """Quarter-end dates in the heading (the columns are "As at 31 March 2026", "As at 31 March 2025")."""
    hits: list[tuple[int, str]] = []
    for index, pattern in enumerate(DATE_PATTERNS):
        for m in pattern.finditer(text):
            day = parse_date(m.groups(), index)
            if day and day.month in (3, 6, 9, 12) and day.day >= 28:
                hits.append((m.start(), day.isoformat()))
    return list(dict.fromkeys(iso for _, iso in sorted(hits)))


def read_statements(pages: list[tuple[int, str]]) -> list[Statement]:
    """Standalone and consolidated statements found in the pages, standalone first."""
    out: dict[str, Statement] = {}
    for page_no, text in pages:
        head = heading(text)
        is_bs, is_pl = bool(BALANCE_SHEET.search(head)), bool(PROFIT_LOSS.search(head))
        if not (is_bs or is_pl) or NOTES.search(head):
            continue
        basis = "consolidated" if CONSOLIDATED.search(head) else "standalone"
        statement = out.setdefault(basis, Statement(basis=basis))
        if statement.unit is None:
            statement.unit, statement.unit_factor = unit_of(text[:1500])
        periods = _periods(text[:1500])
        if periods and statement.period_end is None:
            statement.period_end = max(periods)
            earlier = [p for p in periods if p < statement.period_end]
            statement.prior_period_end = max(earlier) if earlier else None
        kind = "bs" if is_bs else "pl"
        found = _read_page(text, kind, page_no, statement.unit_factor)
        if found:
            statement.pages.append(page_no)
            for key, item in found.items():
                statement.items.setdefault(key, item)
    for statement in out.values():
        repair(statement.items)
    return sorted(out.values(), key=lambda s: s.basis != "standalone")


def _read_page(text: str, kind: str, page_no: int, factor: int) -> dict[str, dict[str, Any]]:
    section: str | None = None
    payables_heading_at = -10
    found: dict[str, dict[str, Any]] = {}
    lines = [" ".join(line.split()) for line in text.split("\n")]

    def keep(key: str, values: list[float], line: str) -> None:
        scale = 1 if key == "eps_basic" else factor
        found[key] = {
            "label": LABELS[key],
            "current": round(values[0] * scale) if len(values) >= 1 else None,
            "previous": round(values[1] * scale) if len(values) >= 2 else None,
            "page": page_no,
            "as_written": line[:160],
            "by": "auto",
        }

    for index, line in enumerate(lines):
        if not line:
            continue
        label_part = LEADING_NUMERAL.sub("", re.sub(r"^[^\w(]+", "", line))  # junk a scanner left, then "IV."
        for name, pattern in _SECTIONS:
            if pattern.match(label_part):
                section = name
        if kind == "bs" and section in SECTION_TOTALS and not re.search(r"[A-Za-z]{2}", line):
            values = figures(line)
            total_key = SECTION_TOTALS[section]
            if len(values) >= 1 and total_key not in found and any(k for k in found if _section_of(k) == section):
                keep(total_key, values, line)  # an uncaptioned total closing the section
            continue
        if kind == "bs" and section == "c_liab" and index - payables_heading_at <= 4:
            part = next((key for key, pattern in PAYABLE_PARTS if pattern.match(label_part)), None)
            if part and part not in found:
                values = figures(label_part)
                if values:
                    keep(part, values, line)
                continue
        for key, _label, statement, needs_section, pattern in _COMPILED:
            if statement != kind or key in found:
                continue
            if needs_section and needs_section != section:
                continue
            m = pattern.search(label_part)
            if not m:
                continue
            if key == "trade_payables":
                payables_heading_at = index
            values = figures(label_part[m.end():])
            if not values and index + 1 < len(lines) and not re.search(r"[A-Za-z]{3}", lines[index + 1]):
                values = figures(lines[index + 1])  # the figures wrapped onto the next line
            if not values:
                break
            keep(key, values, line)
            break
    return found


_SECTION_OF = {key: sec for key, _l, _s, sec, _p in CATALOGUE if sec}
_SECTION_OF.update({"share_capital": "equity", "other_equity": "equity"})


def _section_of(key: str) -> str | None:
    return _SECTION_OF.get(key)
