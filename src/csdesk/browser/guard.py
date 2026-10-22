"""What the tools may never press.

Submitting, signing with a DSC, paying and filing are hers. Every click the
form filler makes goes through guarded_click, and every navigation through
check_url. A click is allowed only when the button's name is on a short list
(save, next, add...) and nothing about it looks like submit, sign or pay.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from ..errors import Blocked

_FORBIDDEN = re.compile(
    r"\b(submit\w*|submission|pay|payment|paid|sign|signing|signature|affix\w*|dsc|e-?sign|file\s+(the\s+)?form|"
    r"proceed\s+to\s+pay|make\s+payment|generate\s+challan|challan)\b",
    re.IGNORECASE,
)
_ALLOWED = re.compile(
    r"^(save|save\s+as\s+draft|save\s+draft|save\s+and\s+continue|next|previous|back|continue|"
    r"add|add\s+(row|more|director|item|details)|ok|close|cancel|search|pre-?fill|fetch|validate|"
    r"check|check\s+form|verify|upload|attach|browse|remove|delete\s+row)$",
    re.IGNORECASE,
)
_FORBIDDEN_URL = re.compile(r"(?<![a-z])(pay|payment|payments|gateway|checkout|challan|dsc|e-?sign)(?![a-z])", re.IGNORECASE)


Verdict = Literal["allowed", "hers", "not_listed", "unnamed"]


def click_verdict(*names: str | None) -> tuple[Verdict, str]:
    """Whether CS Desk may press a control with these names (text, value, aria-label, title), and the name that decided it."""
    labels = [" ".join(name.split()) for name in names if name and name.strip()]
    if not labels:
        return "unnamed", ""
    for label in labels:
        if _FORBIDDEN.search(label):
            return "hers", label
    if not _ALLOWED.match(labels[0]):
        return "not_listed", labels[0]
    return "allowed", labels[0]


def check_click(*names: str | None) -> None:
    """Raise Blocked unless the control's names are all harmless and the first one is on the allowed list."""
    verdict, label = click_verdict(*names)
    if verdict == "unnamed":
        raise Blocked("CS Desk won't press a control whose name it can't read.")
    if verdict == "hers":
        raise Blocked(f"'{label}' is hers to press. CS Desk stops before submitting, signing or paying.")
    if verdict == "not_listed":
        raise Blocked(f"'{label}' isn't on the list of buttons CS Desk may press (save, next, add and the like).")


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if _FORBIDDEN_URL.search(f"{parsed.path}?{parsed.query}"):
        raise Blocked("That page looks like a payment or signing step, which is hers to open.")


async def guarded_click(locator: Any) -> str:
    """Click a Playwright locator only if check_click allows it. Returns the name it pressed."""
    text = (await locator.inner_text()).strip()
    names = [text, await locator.get_attribute("value"), await locator.get_attribute("aria-label"), await locator.get_attribute("title")]
    check_click(*names)
    await locator.click()
    return next(name for name in names if name and name.strip())
