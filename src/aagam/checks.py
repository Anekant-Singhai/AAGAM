"""Limits a Company Secretary works out before drafting: loans, investments, guarantees and borrowing.

Each result shows its working (the formula, the figures, the section it comes
from) so it can go straight into a note or an explanatory statement, and says
plainly where the answer rests on a reading she should confirm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from csdesk.errors import Invalid


def inr(rupees: float | int) -> str:
    """₹ with Indian digit grouping: ₹1,00,00,00,000."""
    value = round(rupees)
    sign, digits = ("-" if value < 0 else ""), str(abs(value))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{sign}₹{digits}"


def crore(rupees: float | int) -> str:
    return f"₹{rupees / 10_000_000:,.2f} crore"


@dataclass(frozen=True)
class Figures:
    """From the latest audited balance sheet, in whole rupees."""

    paid_up_capital: int
    free_reserves: int
    securities_premium: int = 0

    def __post_init__(self) -> None:
        for name in ("paid_up_capital", "free_reserves", "securities_premium"):
            if getattr(self, name) < 0 and name != "free_reserves":
                raise Invalid(f"{name.replace('_', ' ')} can't be negative.")


def loan_limits(
    figures: Figures,
    proposed: int = 0,
    outstanding: int = 0,
    company_class: str | None = None,
    to_wholly_owned_subsidiary: bool = False,
) -> dict[str, Any]:
    """Section 186: loans, guarantees, security and investments, existing plus proposed, against the limit."""
    base = figures.paid_up_capital + figures.free_reserves + figures.securities_premium
    option_a = 0.6 * base
    option_b = figures.free_reserves + figures.securities_premium
    limit = max(option_a, option_b, 0)
    total = outstanding + proposed
    over = total > limit
    steps = [
        f"Paid-up share capital + free reserves + securities premium = {inr(base)}",
        f"(a) 60% of that = {inr(option_a)}",
        f"(b) 100% of free reserves + securities premium = {inr(option_b)}",
        f"Limit under s.186(2) = the higher of (a) and (b) = {inr(limit)} ({crore(limit)})",
        f"Outstanding {inr(outstanding)} + proposed {inr(proposed)} = {inr(total)} ({crore(total)})",
    ]
    if to_wholly_owned_subsidiary:
        needs = "No special resolution is needed for a loan, guarantee or security to a wholly owned subsidiary (s.186(3) proviso); disclose it in the financial statements."
        status = "check"
    elif over:
        needs = (
            f"Over the limit by {inr(total - limit)} ({crore(total - limit)}). Prior approval of the members by special "
            "resolution is needed (s.186(3)). The resolution should state the total amount up to which the Board may go."
        )
        status = "special_resolution"
    else:
        needs = f"Within the limit, with {inr(limit - total)} ({crore(limit - total)}) to spare. A Board resolution passed with the consent of all directors present is enough (s.186(5))."
        status = "board_resolution"
    notes = [
        "Free reserves are as defined in s.2(43): they exclude unrealised gains, notional gains, revaluation of assets and changes in carrying amounts on fair valuation.",
        "Every loan, guarantee, security or investment also needs a Board resolution with the consent of all directors present, and the prior approval of the public financial institution where a term loan is subsisting (s.186(5)).",
        "A loan can't carry interest below the yield of the Government Security closest to its tenor (s.186(7)).",
        "Entries go in the register in Form MBP-2 (s.186(9), rule 12).",
    ]
    if company_class == "private":
        notes.append("Check whether an exemption applies to this private company; s.186 itself applies to private companies.")
    return {
        "section": "186",
        "limit": round(limit),
        "limit_text": crore(limit),
        "total": total,
        "status": status,
        "needs": needs,
        "steps": steps,
        "notes": notes,
        "basis": ["s.186(2)", "s.186(3)", "s.186(5)", "s.186(7)", "s.2(43)"],
    }


def borrowing_limits(figures: Figures, proposed: int = 0, outstanding: int = 0, company_class: str | None = None) -> dict[str, Any]:
    """Section 180(1)(c): borrowing, with money already borrowed, against paid-up capital + free reserves + securities premium."""
    limit = max(figures.paid_up_capital + figures.free_reserves + figures.securities_premium, 0)
    total = outstanding + proposed
    steps = [
        f"Limit = paid-up share capital + free reserves + securities premium = {inr(limit)} ({crore(limit)})",
        f"Already borrowed {inr(outstanding)} + proposed {inr(proposed)} = {inr(total)} ({crore(total)})",
        "Temporary loans from the company's bankers in the ordinary course of business are left out.",
    ]
    if company_class == "private":
        status = "check"
        needs = (
            "Section 180 doesn't apply to a private company (MCA exemption notification of 5 June 2015). "
            "Check its articles for any borrowing limit of their own."
        )
    elif total > limit:
        status = "special_resolution"
        needs = f"Over the limit by {inr(total - limit)} ({crore(total - limit)}): a special resolution under s.180(1)(c) is needed, stating the total the Board may borrow."
    else:
        status = "board_resolution"
        needs = f"Within the limit, with {inr(limit - total)} ({crore(limit - total)}) to spare: the Board can borrow under s.179(3)(d)."
    return {
        "section": "180(1)(c)",
        "limit": limit,
        "limit_text": crore(limit),
        "total": total,
        "status": status,
        "needs": needs,
        "steps": steps,
        "notes": [
            "Securing the borrowing by a charge on the undertaking may also need a special resolution under s.180(1)(a).",
            "File the special resolution in MGT-14 within 30 days (s.117).",
        ],
        "basis": ["s.180(1)(c)", "s.179(3)(d)", "s.117"],
    }


def director_loan_check(company_class: str | None = None) -> dict[str, Any]:
    """Section 185: what a loan to a director, or to a person a director is interested in, needs."""
    notes = [
        "A loan, guarantee or security for a director of the company or of its holding company, or their partner or relative, or a firm in which they are a partner, is prohibited (s.185(1)), with the exceptions in s.185(3).",
        "For any other person in whom a director is interested (s.185(2)): a special resolution is needed, the explanatory statement must disclose the full particulars of the loan, guarantee or security and its purpose, and the borrower must use the money for its principal business activities.",
    ]
    status = "special_resolution"
    if company_class == "private":
        status = "check"
        notes.append(
            "A private company may be outside s.185 (MCA exemption notification of 5 June 2015) if: no other body corporate has invested in "
            "its share capital; its borrowings from banks, financial institutions or bodies corporate are less than twice its paid-up share "
            "capital or ₹50 crore, whichever is lower; and it has no default in repaying them when the transaction is made."
        )
    return {"section": "185", "status": status, "notes": notes, "basis": ["s.185(1)", "s.185(2)", "s.185(3)"]}


def loans_and_borrowing(
    paid_up_capital: int,
    free_reserves: int,
    securities_premium: int = 0,
    proposed_loans_investments: int = 0,
    outstanding_loans_investments: int = 0,
    proposed_borrowing: int = 0,
    outstanding_borrowing: int = 0,
    company_class: str | None = None,
    to_wholly_owned_subsidiary: bool = False,
    include_director_loans: bool = False,
) -> dict[str, Any]:
    figures = Figures(paid_up_capital, free_reserves, securities_premium)
    out: dict[str, Any] = {
        "figures": {
            "paid_up_capital": inr(paid_up_capital),
            "free_reserves": inr(free_reserves),
            "securities_premium": inr(securities_premium),
        },
        "s186": loan_limits(figures, proposed_loans_investments, outstanding_loans_investments, company_class, to_wholly_owned_subsidiary),
    }
    if proposed_borrowing or outstanding_borrowing:
        out["s180"] = borrowing_limits(figures, proposed_borrowing, outstanding_borrowing, company_class)
    if include_director_loans:
        out["s185"] = director_loan_check(company_class)
    out["caution"] = "Figures are as entered; take them from the latest audited balance sheet. These are working notes, not an opinion."
    return out
