"""Format checks for Indian identifiers and for the dates and amounts on company papers.

Each function returns the value in its standard form, or raises Invalid with a
message saying what is wrong. The point is to catch an OCR slip (an "O" read
as "0", a dropped digit) before it reaches a form.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import Invalid

_CIN = re.compile(r"[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}")
_LLPIN = re.compile(r"[A-Z]{3}-\d{4}")
_PAN = re.compile(r"[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]")
_TAN = re.compile(r"[A-Z]{4}\d{5}[A-Z]")
_DIN = re.compile(r"\d{8}")
_PIN = re.compile(r"[1-9]\d{5}")
_MOBILE = re.compile(r"[6-9]\d{9}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_GSTIN = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")

# Fourth character of a PAN says what kind of holder it belongs to.
PAN_HOLDER = {
    "P": "individual",
    "C": "company",
    "F": "firm or LLP",
    "H": "HUF",
    "A": "association of persons",
    "B": "body of individuals",
    "T": "trust",
    "L": "local authority",
    "J": "artificial juridical person",
    "G": "government",
}

# Characters 13-15 of a CIN: (company class it implies, if any; description).
CIN_OWNERSHIP = {
    "PTC": ("private", "private limited company"),
    "PLC": ("public", "public limited company"),
    "OPC": ("opc", "one person company"),
    "NPL": (None, "not-for-profit licence (section 8) company"),
    "GOI": (None, "Government of India company"),
    "SGC": (None, "State Government company"),
    "FTC": ("private", "subsidiary of a foreign company"),
    "GAP": ("public", "general association, public"),
    "GAT": ("private", "general association, private"),
    "ULL": ("public", "unlimited liability, public"),
    "ULT": ("private", "unlimited liability, private"),
    "FLC": (None, "financial lease company"),
}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value)).upper()


def cin(value: Any) -> str:
    v = _compact(value)
    if not _CIN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid CIN: expected 21 characters like U74999MH2015PTC123456.")
    return v


def llpin(value: Any) -> str:
    v = _compact(value)
    if not _LLPIN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid LLPIN: expected the form AAB-1234.")
    return v


def is_llpin(value: Any) -> bool:
    return bool(_LLPIN.fullmatch(_compact(value)))


def cin_or_llpin(value: Any) -> str:
    v = _compact(value)
    if _CIN.fullmatch(v) or _LLPIN.fullmatch(v):
        return v
    raise Invalid(
        f"{value!r} is neither a CIN (21 characters, e.g. U74999MH2015PTC123456) nor an LLPIN (e.g. AAB-1234)."
    )


def parse_cin(value: Any) -> dict[str, Any]:
    """What a CIN says about the company: listing, industry code, state, year, ownership."""
    v = cin(value)
    code = v[12:15]
    company_class, ownership = CIN_OWNERSHIP.get(code, (None, None))
    return {
        "listed": v[0] == "L",
        "nic_code": v[1:6],
        "state_code": v[6:8],
        "year": int(v[8:12]),
        "ownership_code": code,
        "ownership": ownership,
        "company_class": company_class,
        "is_section8": code == "NPL",
        "registration_no": v[15:],
    }


def pan(value: Any) -> str:
    v = _compact(value)
    if not _PAN.fullmatch(v):
        raise Invalid(
            "That PAN is not valid: expected 5 letters, 4 digits and a letter (like ABCPE1234F), "
            "with a holder-type letter (P, C, F, H, A, B, T, L, J or G) in 4th place."
        )
    return v


def pan_holder(value: Any) -> str:
    return PAN_HOLDER[pan(value)[3]]


def tan(value: Any) -> str:
    v = _compact(value)
    if not _TAN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid TAN: expected 4 letters, 5 digits and a letter (like MUMA12345B).")
    return v


def din(value: Any) -> str:
    # A DIN typed as a number loses its leading zero; put it back.
    v = str(value).zfill(8) if isinstance(value, int) else _compact(value)
    if not _DIN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid DIN: expected 8 digits.")
    return v


# Verhoeff check digit tables (used by Aadhaar).
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(digit)]]
    return c == 0


def verhoeff_digit(number: str) -> str:
    """The check digit to append to `number`."""
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _D[c][_P[(i + 1) % 8][int(digit)]]
    return str(_INV[c])


def aadhaar(value: Any) -> str:
    v = re.sub(r"[\s-]", "", str(value))
    if not re.fullmatch(r"[2-9]\d{11}", v) or not verhoeff_valid(v):
        raise Invalid("That is not a valid Aadhaar number (12 digits ending in a check digit). Re-read it from the card.")
    return v


_BASE36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _BASE36.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _BASE36[(36 - total % 36) % 36]


def gstin(value: Any) -> str:
    v = _compact(value)
    if not _GSTIN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid GSTIN: expected 15 characters like 27AAPFU0939F1ZV.")
    if gstin_check_char(v[:14]) != v[14]:
        raise Invalid(f"{value!r} fails the GSTIN check character, so one character is probably misread.")
    return v


def pin(value: Any) -> str:
    v = re.sub(r"\s", "", str(value))
    if not _PIN.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid PIN code: expected 6 digits.")
    return v


def mobile(value: Any) -> str:
    v = re.sub(r"[\s\-()]", "", str(value))
    v = re.sub(r"^(\+91|0091|0)", "", v)
    if not _MOBILE.fullmatch(v):
        raise Invalid("That is not a valid Indian mobile number: expected 10 digits starting with 6, 7, 8 or 9.")
    return v


def email(value: Any) -> str:
    v = str(value).strip().lower()
    if not _EMAIL.fullmatch(v):
        raise Invalid(f"{value!r} is not a valid email address.")
    return v


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y")


def iso_date(value: Any) -> str:
    """Accepts ISO dates and the usual Indian styles (26/09/2026, 26-09-2026, 26th September 2026)."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", " ".join(str(value).split()), flags=re.IGNORECASE)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise Invalid(f"{value!r} is not a date I can read; use YYYY-MM-DD (or DD/MM/YYYY).")


def rupees(value: Any) -> int:
    """Whole rupees from 100000, "1,00,000", "Rs. 1,00,000/-" or "₹1,00,000"."""
    if isinstance(value, bool):
        raise Invalid(f"{value!r} is not an amount in rupees.")
    if isinstance(value, int):
        return value
    text = re.sub(r"(?i)(rs\.?|inr|₹|/-|\s|,)", "", str(value))
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise Invalid(f"{value!r} is not an amount in rupees; write the full number, e.g. 1000000.") from None
    if amount != amount.to_integral_value():
        raise Invalid(f"{value!r} has paise; amounts are kept in whole rupees.")
    return int(amount)


def fin_year(value: Any) -> str:
    """Financial year in the form 2025-26."""
    v = _compact(value).replace("/", "-")
    m = re.fullmatch(r"(\d{4})-(\d{2}|\d{4})", v)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if (len(m.group(2)) == 2 and (start + 1) % 100 == end) or start + 1 == end:
            return f"{start}-{(start + 1) % 100:02d}"
    raise Invalid(f"{value!r} is not a financial year; use the form 2025-26.")


def month_day(value: Any) -> str:
    v = str(value).strip()
    m = re.fullmatch(r"(\d{2})-(\d{2})", v)
    if m:
        try:
            date(2001, int(m.group(1)), int(m.group(2)))
            return v
        except ValueError:
            pass
    raise Invalid(f"{value!r} is not a month and day; give the financial year end as MM-DD, e.g. 03-31.")
