"""Ratios and the shape of the balance sheet, from the figures read out of the statements.

The eleven ratios are the ones Schedule III requires companies to disclose
(the 2021 amendment), with the change from the previous year. A change of
more than 25% has to be explained in the notes, so those are flagged.
Where a figure needed isn't in the statements (principal repayments for
DSCR, investment income for return on investment), the ratio says what is
missing instead of guessing.
"""

from __future__ import annotations

from typing import Any

Figures = dict[str, dict[str, Any]]


def _v(items: Figures, key: str, column: str) -> float | None:
    item = items.get(key)
    value = item.get(column) if item else None
    return float(value) if value is not None else None


def derived(items: Figures, column: str) -> dict[str, float | None]:
    """Totals the statements may not print in one line, worked out from their parts."""
    g = lambda key: _v(items, key, column)  # noqa: E731
    s = lambda *keys: sum(x for x in (g(k) for k in keys) if x is not None) if any(g(k) is not None for k in keys) else None  # noqa: E731
    equity = g("total_equity")
    if equity is None and g("share_capital") is not None:
        equity = (g("share_capital") or 0) + (g("other_equity") or 0)
    trade_payables = g("trade_payables")
    if trade_payables is None:
        trade_payables = s("msme_dues", "other_payables")
    borrowings = s("long_term_borrowings", "short_term_borrowings")
    leases = s("nc_lease_liabilities", "c_lease_liabilities")
    debt = (borrowings or 0) + (leases or 0) if borrowings is not None or leases is not None else None
    current_assets = g("total_current_assets") or s("inventories", "current_investments", "trade_receivables", "cash",
                                                    "other_bank_balances", "short_term_loans", "other_current_assets")
    current_liabilities = g("total_current_liabilities") or s("short_term_borrowings", "c_lease_liabilities", "msme_dues",
                                                              "other_payables", "other_current_liabilities", "short_term_provisions",
                                                              "current_tax_liabilities") or (trade_payables and s("short_term_borrowings", "other_current_liabilities"))
    total_assets = g("total_assets") or g("total_equity_and_liabilities")
    revenue = g("revenue")
    pbt, pat, finance = g("profit_before_tax"), g("profit_after_tax"), g("finance_costs")
    tax = g("tax_expense")
    if tax is None and pbt is not None and pat is not None:
        tax = pbt - pat
    cogs = s("materials", "purchases", "inventory_change", "direct_expenses")
    purchases = s("materials", "purchases", "direct_expenses")
    ebit = pbt + (finance or 0) if pbt is not None else None
    ebitda = ebit + (g("depreciation") or 0) if ebit is not None else None
    liabilities = total_assets - equity if total_assets is not None and equity is not None else None
    return {
        "equity": equity, "trade_payables": trade_payables, "borrowings": borrowings, "debt": debt,
        "current_assets": current_assets, "current_liabilities": current_liabilities, "total_assets": total_assets,
        "liabilities": liabilities, "revenue": revenue, "pbt": pbt, "pat": pat, "tax": tax, "finance_costs": finance,
        "cogs": cogs, "purchases": purchases, "ebit": ebit, "ebitda": ebitda,
        "working_capital": current_assets - current_liabilities if current_assets is not None and current_liabilities is not None else None,
        "inventories": g("inventories"), "receivables": g("trade_receivables"), "depreciation": g("depreciation"),
        "deferred_tax_liabilities": g("deferred_tax_liabilities"), "msme_dues": g("msme_dues"),
        "investments": s("non_current_investments", "current_investments"),
        "share_capital": g("share_capital"),
    }


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _avg(now: float | None, before: float | None) -> float | None:
    if now is None:
        return None
    return (now + before) / 2 if before is not None else now


RATIOS: list[dict[str, str]] = [
    {"key": "current_ratio", "name": "Current ratio", "formula": "Current assets ÷ current liabilities", "unit": "times"},
    {"key": "debt_equity", "name": "Debt-equity ratio", "formula": "Total debt (borrowings + lease liabilities) ÷ shareholders' equity", "unit": "times"},
    {"key": "dscr", "name": "Debt service coverage ratio", "formula": "(Profit after tax + depreciation + finance costs) ÷ (finance costs + principal repaid in the year)", "unit": "times"},
    {"key": "roe", "name": "Return on equity", "formula": "Profit after tax ÷ average shareholders' equity", "unit": "%"},
    {"key": "inventory_turnover", "name": "Inventory turnover", "formula": "Cost of goods sold (or revenue) ÷ average inventory", "unit": "times"},
    {"key": "receivables_turnover", "name": "Trade receivables turnover", "formula": "Revenue from operations ÷ average trade receivables", "unit": "times"},
    {"key": "payables_turnover", "name": "Trade payables turnover", "formula": "Purchases (materials + stock-in-trade) ÷ average trade payables", "unit": "times"},
    {"key": "net_capital_turnover", "name": "Net capital turnover", "formula": "Revenue from operations ÷ working capital", "unit": "times"},
    {"key": "net_profit_ratio", "name": "Net profit ratio", "formula": "Profit after tax ÷ revenue from operations", "unit": "%"},
    {"key": "roce", "name": "Return on capital employed", "formula": "EBIT ÷ (equity + total debt + deferred tax liability)", "unit": "%"},
    {"key": "roi", "name": "Return on investment", "formula": "Income from investments ÷ average investments", "unit": "%"},
]


def _ratio_values(now: dict[str, float | None], before: dict[str, float | None] | None, principal_repaid: float | None) -> dict[str, Any]:
    b = before or {}
    pct = lambda x: x * 100 if x is not None else None  # noqa: E731
    stock_base = now["cogs"] if now["cogs"] not in (None, 0) else now["revenue"]
    debt_service = (now["finance_costs"] or 0) + principal_repaid if principal_repaid is not None else None
    capital = (now["equity"] or 0) + (now["debt"] or 0) + (now["deferred_tax_liabilities"] or 0) if now["equity"] is not None else None
    return {
        "current_ratio": _div(now["current_assets"], now["current_liabilities"]),
        "debt_equity": _div(now["debt"], now["equity"]),
        "dscr": _div((now["pat"] or 0) + (now["depreciation"] or 0) + (now["finance_costs"] or 0), debt_service) if now["pat"] is not None else None,
        "roe": pct(_div(now["pat"], _avg(now["equity"], b.get("equity")))),
        "inventory_turnover": _div(stock_base, _avg(now["inventories"], b.get("inventories"))),
        "receivables_turnover": _div(now["revenue"], _avg(now["receivables"], b.get("receivables"))),
        "payables_turnover": _div(now["purchases"], _avg(now["trade_payables"], b.get("trade_payables"))),
        "net_capital_turnover": _div(now["revenue"], now["working_capital"]),
        "net_profit_ratio": pct(_div(now["pat"], now["revenue"])),
        "roce": pct(_div(now["ebit"], capital)),
        "roi": None,
    }


MISSING = {
    "dscr": "Needs the principal repaid in the year (from the cash flow statement or loan schedule).",
    "roi": "Needs income from investments (from the notes).",
}


def analyse(items: Figures, principal_repaid: int | None = None) -> dict[str, Any]:
    now, before = derived(items, "current"), derived(items, "previous")
    has_previous = any(v is not None for v in before.values())
    current = _ratio_values(now, before if has_previous else None, principal_repaid)
    # Previous-year ratios use the previous year's own closing figures (no year before it to average with).
    previous = _ratio_values(before, None, None) if has_previous else {}
    ratios = []
    for spec in RATIOS:
        key = spec["key"]
        value, prior = current.get(key), previous.get(key)
        change = ((value - prior) / abs(prior) * 100) if value is not None and prior not in (None, 0) else None
        ratios.append({
            **spec,
            "current": round(value, 2) if value is not None else None,
            "previous": round(prior, 2) if prior is not None else None,
            "change_pct": round(change, 1) if change is not None else None,
            "explain": change is not None and abs(change) > 25,
            "missing": MISSING.get(key) if value is None and key in MISSING else (None if value is not None else "A figure it needs wasn't found."),
        })
    return {
        "ratios": ratios,
        "derived": {"current": now, "previous": before},
        "liabilities": liability_profile(now),
        "checks": consistency(items) + checks(now),
    }


def _money(rupees: float) -> str:
    """An amount the way she would say it: ₹246.68 crore, ₹24.67 lakh."""
    sign, v = ("−" if rupees < 0 else ""), abs(rupees)
    if v >= 10_000_000:
        return f"{sign}₹{v / 10_000_000:,.2f} crore"
    if v >= 100_000:
        return f"{sign}₹{v / 100_000:,.2f} lakh"
    return f"{sign}₹{v:,.0f}"


def consistency(items: Figures) -> list[dict[str, str]]:
    """Do the statements add up? A line that doesn't is usually misread (a scanner's comma read as a point)."""
    out = []

    def check(column: str, total_key: str, part_keys: list[str], what: str, signs: list[int] | None = None) -> None:
        total = _v(items, total_key, column)
        parts = [_v(items, k, column) for k in part_keys]
        if total is None or any(p is None for p in parts):
            return
        signs = signs or [1] * len(parts)
        worked = sum(s * p for s, p in zip(signs, parts, strict=True))  # type: ignore[operator]
        if abs(worked - total) > max(abs(total) * 0.01, 1000):
            year = "this year" if column == "current" else "last year"
            out.append({"level": "verify", "text": f"{what} doesn't add up {year}: the parts make {_money(worked)} but the total is {_money(total)}. Check these lines against the page."})

    for key, item in items.items():
        for column, was in (item.get("repaired") or {}).items():
            year = "this year" if column == "current" else "last year"
            out.append({"level": "verify", "text": f"{item.get('label', key)} {year} was read as {_money(was)}, which doesn't fit the totals; "
                        f"AAGAM used {_money(item[column])} (total income − other income). Check it on page {item.get('page')}."})
    for column in ("current", "previous"):
        check(column, "total_assets", ["total_equity_and_liabilities"], "Total assets against total equity and liabilities")
        check(column, "total_income", ["revenue", "other_income"], "Total income (revenue + other income)")
        check(column, "profit_before_tax", ["total_income", "total_expenses"], "Profit before tax (income − expenses)", [1, -1])
        check(column, "total_equity", ["share_capital", "other_equity"], "Total equity (share capital + other equity)")
    return out


def liability_profile(now: dict[str, float | None]) -> dict[str, Any]:
    """Where the money comes from: equity, borrowings, trade payables, everything else."""
    total = now["total_assets"]
    if not total:
        return {}
    equity = now["equity"] or 0
    borrowings = now["debt"] or 0
    payables = now["trade_payables"] or 0
    other = max(total - equity - borrowings - payables, 0)
    parts = [("Equity", equity), ("Borrowings and leases", borrowings), ("Trade payables", payables), ("Other liabilities and provisions", other)]
    return {
        "total": total,
        "parts": [{"name": n, "amount": round(a), "share": round(a / total * 100, 1)} for n, a in parts],
        "msme_share_of_payables": round(now["msme_dues"] / payables * 100, 1) if payables and now["msme_dues"] is not None else None,
    }


def checks(now: dict[str, float | None]) -> list[dict[str, str]]:
    """Things in the figures a CS or CA should look at."""
    out = []
    if now["equity"] is not None and now["equity"] < 0:
        out.append({"level": "alert", "text": "Net worth is negative: the company's losses exceed its capital and reserves."})
    if now["working_capital"] is not None and now["working_capital"] < 0:
        out.append({"level": "warn", "text": "Working capital is negative: current liabilities exceed current assets."})
    if now["msme_dues"]:
        out.append({"level": "info", "text": "Dues to micro and small enterprises are outstanding. If any is over 45 days, MSME-1 is due half-yearly, and the interest is disallowed for tax."})
    if now["pat"] is not None and now["pat"] < 0:
        out.append({"level": "warn", "text": "The company made a loss this year. Check managerial remuneration against Schedule V, and the CSR spend if the obligation arose earlier."})
    if now["debt"] and now["equity"] and now["debt"] / now["equity"] > 2:
        out.append({"level": "warn", "text": "Debt is more than twice equity. Check the borrowing limit under s.180(1)(c) and the loan covenants."})
    return out
