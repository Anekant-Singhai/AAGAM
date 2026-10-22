"""What applies to a company, from its class and its figures, and the work that follows for her.

Each test states its threshold and its source. Where the answer depends on a
fact that isn't in the statements (is it a holding or subsidiary company? how
much is borrowed from banks?), the test says "check" and names the fact,
unless she has recorded it. Each test that applies also names the service a
CS can offer for it, which is how a client's compliance list becomes her
work list.

Thresholds are as of October 2026, including the small-company limits
raised on 1 December 2025 (G.S.R. 880(E)) and the Income-tax Act, 2025, in
force from 1 April 2026.
"""

from __future__ import annotations

from typing import Any

CRORE = 10_000_000


def _cr(value: float | None) -> str:
    return "not known" if value is None else f"₹{value / CRORE:,.2f} crore"


def assess(company: dict[str, Any], now: dict[str, float | None], facts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """`company` is the company-file row (class, listed, section 8...); `now` the derived figures; `facts` what she has told us."""
    f = facts or {}
    cls = (company.get("company_class") or "").lower() or None
    listed = bool(company.get("is_listed")) or bool(f.get("listed"))
    section8 = bool(company.get("is_section8"))
    paid_up = now.get("share_capital")
    turnover = now.get("revenue")
    net_profit = now.get("pbt")  # s.198 net profit is close to profit before tax; the exact figure is worked out separately
    net_worth = now.get("equity")
    bank_borrowings = f.get("bank_borrowings", now.get("borrowings"))
    holding_or_sub = f.get("holding_or_subsidiary")
    deposits = f.get("deposits")
    public = cls == "public"
    out: list[dict[str, Any]] = []

    def add(key: str, title: str, status: str, why: str, basis: str, work: str | None = None, missing: str | None = None) -> None:
        out.append({"key": key, "title": title, "status": status, "why": why, "basis": basis, "work": work if status != "no" else None, "missing": missing})

    # Small company: s.2(85), limits raised to ₹10 crore / ₹100 crore from 1 December 2025.
    if cls == "private" and not section8 and paid_up is not None and turnover is not None:
        small = paid_up <= 10 * CRORE and turnover <= 100 * CRORE
        status = ("check" if holding_or_sub is None else "no" if holding_or_sub else "yes") if small else "no"
        add("small_company", "Small company", status,
            f"Paid-up {_cr(paid_up)} (limit ₹10 crore), turnover {_cr(turnover)} (limit ₹100 crore)."
            + (" A holding or subsidiary company can't be a small company." if small else ""),
            "s.2(85); rule 2(1)(t) as amended by G.S.R. 880(E), 1 Dec 2025",
            "Annual return in MGT-7A, two board meetings a year, lighter penalties (s.446B), no cash flow statement. Tell the client what they save.",
            "Is it a holding or subsidiary company?" if small and holding_or_sub is None else None)

    # CSR: s.135(1), in the immediately preceding financial year.
    if turnover is not None or net_profit is not None or net_worth is not None:
        hits = [label for label, value, limit in (("net worth", net_worth, 500 * CRORE), ("turnover", turnover, 1000 * CRORE),
                                                   ("net profit", net_profit, 5 * CRORE)) if value is not None and value >= limit]
        status = "yes" if hits else "no"
        obligation = 0.02 * net_profit if net_profit and net_profit > 0 else None
        add("csr", "Corporate social responsibility", status,
            ("Meets " + ", ".join(hits) + "." if hits else "Below all three limits (net worth ₹500 crore, turnover ₹1,000 crore, net profit ₹5 crore).")
            + (f" 2% of this year's profit is about {_cr(obligation)}; the obligation is 2% of the average of the last three years' s.198 net profit." if hits and obligation else ""),
            "s.135(1), (5); Companies (CSR Policy) Rules, 2014",
            "CSR policy, committee (if the obligation exceeds ₹50 lakh), board report annexure, CSR-2, unspent-amount transfers and impact assessment.")

    # Secretarial audit: s.204, rule 9.
    if listed:
        add("secretarial_audit", "Secretarial audit (MR-3)", "yes", "Every listed company.", "s.204(1); rule 9; SEBI LODR reg. 24A",
            "Secretarial audit report in MR-3 and the annual secretarial compliance report: a practising CS's own work.")
    elif public and (paid_up is not None or turnover is not None):
        hit = (paid_up or 0) >= 50 * CRORE or (turnover or 0) >= 250 * CRORE
        borrowed = bank_borrowings is not None and bank_borrowings >= 100 * CRORE
        status = "yes" if hit or borrowed else ("check" if f.get("bank_borrowings") is None and (now.get("borrowings") or 0) >= 100 * CRORE else "no")
        add("secretarial_audit", "Secretarial audit (MR-3)", status,
            f"Public company: paid-up {_cr(paid_up)} (limit ₹50 crore), turnover {_cr(turnover)} (limit ₹250 crore), "
            f"bank/PFI borrowings {_cr(bank_borrowings)} (limit ₹100 crore).",
            "s.204(1); rule 9(1)", "Secretarial audit report in MR-3: a practising CS's own work.",
            "How much of the borrowing is from banks or public financial institutions?" if status == "check" else None)
    elif cls == "private" and bank_borrowings is not None:
        status = "yes" if bank_borrowings >= 100 * CRORE and f.get("bank_borrowings") is not None else (
            "check" if bank_borrowings >= 100 * CRORE else "no")
        add("secretarial_audit", "Secretarial audit (MR-3)", status,
            f"Private company: applies only if borrowings from banks or public financial institutions are ₹100 crore or more ({_cr(bank_borrowings)} borrowed in all).",
            "s.204(1); rule 9(1)(c)", "Secretarial audit report in MR-3.",
            "How much of the borrowing is from banks or public financial institutions?" if status == "check" else None)

    # Internal audit: s.138, rule 13.
    if listed or turnover is not None:
        if listed:
            status, why = "yes", "Every listed company."
        elif public:
            hit = (paid_up or 0) >= 50 * CRORE or (turnover or 0) >= 200 * CRORE or (bank_borrowings or 0) > 100 * CRORE or (deposits or 0) >= 25 * CRORE
            status, why = ("yes" if hit else "no"), f"Unlisted public company: paid-up {_cr(paid_up)} (₹50 crore), turnover {_cr(turnover)} (₹200 crore), borrowings {_cr(bank_borrowings)} (over ₹100 crore)."
        else:
            hit = (turnover or 0) >= 200 * CRORE or (bank_borrowings or 0) > 100 * CRORE
            status, why = ("yes" if hit else "no"), f"Private company: turnover {_cr(turnover)} (₹200 crore) or borrowings {_cr(bank_borrowings)} (over ₹100 crore)."
        add("internal_audit", "Internal audit", status, why, "s.138; rule 13", "Board appoints the internal auditor; resolution and records.")

    # Whole-time KMP and company secretary: s.203, rules 8 and 8A.
    if listed or (paid_up is not None and paid_up >= 10 * CRORE):
        add("whole_time_cs", "Whole-time company secretary", "yes",
            "Listed company." if listed else f"Paid-up capital {_cr(paid_up)} is ₹10 crore or more.",
            "s.203; rules 8 and 8A",
            "The company must employ a whole-time CS (and, if listed or a public company with ₹10 crore paid-up, an MD/CEO/manager and CFO): an appointment, or a retainer to support the in-house CS.")
    elif paid_up is not None:
        add("whole_time_cs", "Whole-time company secretary", "no", f"Paid-up capital {_cr(paid_up)} is under ₹10 crore.", "s.203; rule 8A")

    # Independent directors, audit committee, NRC: s.149(4), s.177, s.178; rules 4 and 6.
    if listed or public:
        loans = (now.get("borrowings") or 0) + (deposits or 0)
        hit = listed or (paid_up or 0) >= 10 * CRORE or (turnover or 0) >= 100 * CRORE or loans > 50 * CRORE
        add("independent_directors", "Independent directors, audit committee and NRC", "yes" if hit else "no",
            "Listed company: one third of the board independent." if listed else
            f"Unlisted public company: paid-up {_cr(paid_up)} (₹10 crore), turnover {_cr(turnover)} (₹100 crore), loans, debentures and deposits {_cr(loans)} (over ₹50 crore).",
            "s.149(4), s.177, s.178; rules 4 and 6 of the Meetings of Board and Appointment of Directors Rules",
            "At least two independent directors (databank registration, DIR-12, letters of appointment), audit committee and NRC charters, meetings and minutes.")

    # Woman director: s.149(1), rule 3.
    if listed or (public and ((paid_up or 0) >= 100 * CRORE or (turnover or 0) >= 300 * CRORE)):
        add("woman_director", "Woman director", "yes", "Listed company." if listed else "Public company with paid-up ₹100 crore or turnover ₹300 crore.",
            "s.149(1); rule 3", "Appointment and DIR-12; filling a vacancy within three months.")

    # Auditor rotation: s.139(2), rule 5.
    if listed or (public and (paid_up or 0) >= 10 * CRORE) or (cls == "private" and (paid_up or 0) >= 50 * CRORE) or (bank_borrowings or 0) >= 50 * CRORE:
        add("auditor_rotation", "Rotation of auditors", "yes" if f.get("bank_borrowings") is not None or listed or (paid_up or 0) >= 10 * CRORE else "check",
            "Individual auditors rotate after one term of five years, firms after two (s.139(2)).", "s.139(2); rule 5",
            "Track the auditor's terms in the company file; ADT-1 for each appointment.")

    # XBRL filing of financial statements.
    if listed or (paid_up is not None and paid_up >= 5 * CRORE) or (turnover is not None and turnover >= 100 * CRORE):
        add("xbrl", "Financial statements in XBRL (AOC-4 XBRL)", "yes",
            "Listed, or paid-up ₹5 crore or more, or turnover ₹100 crore or more.", "Companies (Filing of Documents and Forms in XBRL) Rules, 2015",
            "Tagging the financial statements and filing AOC-4 XBRL instead of AOC-4.")

    # CARO 2020.
    if cls == "private" and not section8 and paid_up is not None:
        reserves = (net_worth or 0) - (paid_up or 0)
        exempt = (paid_up + max(reserves, 0)) <= 1 * CRORE and (turnover or 0) <= 10 * CRORE and (now.get("borrowings") or 0) <= 1 * CRORE
        add("caro", "Auditor's report under CARO 2020", "no" if exempt and holding_or_sub is False else ("check" if exempt else "yes"),
            "Exempt only if paid-up plus reserves are ₹1 crore or less, bank borrowings never exceeded ₹1 crore in the year, revenue is ₹10 crore or less, and it is not a holding or subsidiary company. Small companies are exempt too.",
            "Companies (Auditor's Report) Order, 2020, para 1(2)", "The auditor reports on 21 matters. Many are secretarial (loans, deposits, statutory dues, related parties), so get them in order first.",
            "Is it a holding or subsidiary company?" if exempt and holding_or_sub is None else None)

    # Tax audit: Income-tax Act, 2025 s.63 (s.44AB of the 1961 Act up to tax year 2025-26).
    if turnover is not None:
        hit = turnover > 1 * CRORE
        add("tax_audit", "Tax audit", "yes" if turnover > 10 * CRORE else ("check" if hit else "no"),
            f"Turnover {_cr(turnover)}: tax audit applies above ₹1 crore, or above ₹10 crore if cash receipts and payments are each within 5%.",
            "Income-tax Act, 2025, s.63 (Form 26); s.44AB of the 1961 Act for FY 2025-26",
            "A CA's audit. The CS side is keeping the statutory registers and related-party records it relies on.",
            "Are cash receipts and payments each within 5% of the total?" if hit and turnover <= 10 * CRORE else None)

    # MSME-1.
    if now.get("msme_dues"):
        add("msme_1", "MSME-1 half-yearly return", "check", f"Dues to micro and small enterprises: {_cr(now.get('msme_dues'))}. Due if any is outstanding beyond 45 days.",
            "MSE payments order, 2019 (s.405)", "Ageing of MSME dues each half-year; MSME-1 by 30 April and 31 October.",
            "Is any MSME due outstanding for more than 45 days?")

    # Deposits and DPT-3.
    if now.get("borrowings"):
        add("dpt_3", "Return of deposits (DPT-3)", "yes" if cls in ("private", "public") else "check",
            "The company has borrowings, so loans and money not treated as deposits must be reported each year.", "s.73-76; rules 16 and 16A, Acceptance of Deposits Rules",
            "Classify each loan (from directors, relatives, banks, other companies), get the auditor's certificate, file DPT-3 by 30 June.")
    return out
