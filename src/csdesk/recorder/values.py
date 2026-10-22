"""What a typed value looks like, and which company-file field it came from.

The recorder never stores what she typed. It keeps the value's shape ("PAN",
"date DD/MM/YYYY", "text, 23 characters") and the company-file keys whose value
is the same ("company.cin", "party.din"). That is enough to write a recipe:
the shape gives the field's kind and date format, and the match gives its key.
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime
from typing import Any

from .. import validators
from ..errors import Invalid
from ..vault import Vault

_DATE_FORMATS = (
    (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y", "DD/MM/YYYY"),
    (r"\d{2}-\d{2}-\d{4}", "%d-%m-%Y", "DD-MM-YYYY"),
    (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y", "DD.MM.YYYY"),
    (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d", "YYYY-MM-DD"),
    (r"\d{2}-[A-Za-z]{3}-\d{4}", "%d-%b-%Y", "DD-Mon-YYYY"),
    (r"\d{2}/[A-Za-z]{3}/\d{4}", "%d/%b/%Y", "DD/Mon/YYYY"),
)
_IDENTIFIERS = (
    ("CIN", validators.cin),
    ("LLPIN", validators.llpin),
    ("GSTIN", validators.gstin),
    ("PAN", validators.pan),
    ("TAN", validators.tan),
    ("Aadhaar number", validators.aadhaar),
    ("email", validators.email),
)
SENSITIVE_SHAPES = frozenset({"PAN", "Aadhaar number"})
SENSITIVE_KEYS = frozenset({"pan", "aadhaar", "passport_no"})
_SKIP = frozenset({"id", "created_at", "updated_at", "notes", "kind", "entity_type"})


def date_format(text: str) -> tuple[str, str] | None:
    """(strptime format, how to describe it) when `text` is a date in a recognised style."""
    value = text.strip()
    for pattern, fmt, described in _DATE_FORMATS:
        if re.fullmatch(pattern, value):
            try:
                datetime.strptime(value, fmt)
            except ValueError:
                return None
            return fmt, described
    return None


def shape(text: str) -> dict[str, Any]:
    """Describe a typed value without keeping it."""
    value = text.strip()
    if not value:
        return {"shape": "empty"}
    found = date_format(value)
    if found:
        return {"shape": f"date {found[1]}", "date_format": found[0]}
    for name, check in _IDENTIFIERS:
        try:
            check(value)
            return {"shape": name}
        except Invalid:
            continue
    digits = re.sub(r"\s", "", value)
    if re.fullmatch(r"\d{8}", digits):
        return {"shape": "8 digits (a DIN?)"}
    if re.fullmatch(r"[1-9]\d{5}", digits):
        return {"shape": "6 digits (a PIN code?)"}
    if re.fullmatch(r"(\+91)?[6-9]\d{9}", digits):
        return {"shape": "10-digit mobile number"}
    if re.fullmatch(r"[₹]?\s*\d{1,3}(,\d{2,3})+(\.\d+)?|\d+(\.\d+)?", value):
        return {"shape": "number"}
    return {"shape": f"text, {len(value)} characters"}


def _normal(value: Any) -> set[str]:
    """The forms a value can be compared in: plain text, ISO date, bare number."""
    text = " ".join(str(value).split()).casefold()
    forms = {text}
    with contextlib.suppress(Invalid):
        forms.add(validators.iso_date(text))
    digits = re.sub(r"[₹,\s]|rs\.?|/-", "", text)
    if re.fullmatch(r"\d+", digits):
        forms.add(str(int(digits)))
    return forms


class Matcher:
    """Finds which company-file fields hold a given value. Values stay in this process."""

    def __init__(self, candidates: list[tuple[str, str, Any]]) -> None:
        self._candidates = [(key, who, _normal(value)) for key, who, value in candidates]

    @classmethod
    def empty(cls) -> Matcher:
        return cls([])

    @classmethod
    def from_vault(cls, vault: Vault, company_id: int | None, party_id: int | None = None) -> Matcher:
        candidates: list[tuple[str, str, Any]] = []
        if company_id is not None:
            for key, value in vault.company_row(company_id).items():
                if key not in _SKIP and value not in (None, "") and not isinstance(value, bool):
                    candidates.append((f"company.{key}", "", value))
        people: list[int] = [party_id] if party_id is not None else []
        if company_id is not None and party_id is None:
            people = sorted({p["party_id"] for p in vault.company_file(company_id)["people"]})
        for pid in people:
            party = vault.party(pid, reveal=True)
            who = "" if party_id is not None else party["name"]
            for key, value in party.items():
                if key not in _SKIP and key != "appointments" and value not in (None, ""):
                    candidates.append((f"party.{key}", who, value))
        return cls(candidates)

    def match(self, value: Any) -> list[str]:
        """Company-file keys holding this value, e.g. ["company.cin"] or ["party.din (Asha Rao)"]."""
        text = str(value).strip()
        if len(text) < 2:
            return []
        forms = _normal(text)
        found: list[str] = []
        for key, who, candidate in self._candidates:
            if forms & candidate:
                label = f"{key} ({who})" if who else key
                if label not in found:
                    found.append(label)
        return found


def describe_value(raw: dict[str, Any], matcher: Matcher) -> dict[str, Any]:
    """Turn the page's report of a changed value into what the recording keeps."""
    kind = raw.get("kind")
    if kind == "text":
        text = str(raw.get("text") or "")
        return {"kind": "text", **shape(text), "matches": matcher.match(text)}
    if kind == "select":
        option = str(raw.get("option") or "")
        return {"kind": "select", "option": option, "matches": matcher.match(option)}
    if kind == "radio":
        return {"kind": "radio", "option": str(raw.get("option") or ""), "checked": bool(raw.get("checked"))}
    if kind == "checkbox":
        return {"kind": "checkbox", "checked": bool(raw.get("checked"))}
    if kind == "file":
        return {"kind": "file", "files": [str(name) for name in raw.get("files") or []][:10]}
    return {"kind": "secret"}
