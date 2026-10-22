"""Checklists for the work a CS does, each step with where it comes from.

These are the steps a careful CS ticks through for each kind of job. They
are a starting point: she can add, remove and reword steps in any piece of
work, and her list is what's kept. Statutory steps cite the Act, rules or
Secretarial Standards (SS-1 for board meetings, SS-2 for general meetings).
"""

from __future__ import annotations

from typing import Any

KINDS: dict[str, dict[str, Any]] = {
    "board_meeting": {
        "label": "Board meeting",
        "steps": [
            ("Fix the date, time and place (or video conference); at least four meetings a year, no more than 120 days apart", "s.173(1); SS-1 para 2"),
            ("Send notice to every director at least 7 days before, at their registered address or email", "s.173(3); SS-1 para 3.1"),
            ("Send the agenda and notes on agenda at least 7 days before (shorter notice needs an independent director present, if the company has one)", "s.173(3) proviso; SS-1 para 3.4"),
            ("Check the quorum: one third of the total strength or two directors, whichever is higher", "s.174(1); SS-1 para 3.5"),
            ("Get the attendance register signed", "SS-1 para 4"),
            ("Take MBP-1 disclosures of interest (first meeting of the year, and on any change); interested directors stay out", "s.184(1), (2); rule 9"),
            ("Circulate draft minutes within 15 days", "SS-1 para 7.4"),
            ("Sign the minutes within 30 days and keep them at the registered office", "s.118; SS-1 para 7.6"),
            ("File MGT-14 for resolutions that need it within 30 days", "s.117(3), s.179(3)"),
            ("Issue certified true copies of resolutions needed by banks or others", None),
        ],
    },
    "agm": {
        "label": "Annual general meeting",
        "steps": [
            ("Board meeting: approve the financial statements, board's report and notice of AGM", "s.134(1), s.173"),
            ("Hold the AGM within six months of the year end, and within 15 months of the last AGM", "s.96(1)"),
            ("Send the notice at least 21 clear days before (shorter notice needs consent of 95% of members entitled to vote)", "s.101(1)"),
            ("Notice gives the day, date, time and place (or VC), and the business; CIN and registered office on it", "s.101(2); s.12(3)(c); SS-2 para 1.2"),
            ("Explanatory statement for every item of special business, with directors' interests", "s.102(1)"),
            ("Statement that a member may appoint a proxy (not needed for a meeting held only by VC)", "s.105(2); MCA circulars on VC meetings"),
            ("Route map and landmark for a meeting held at a physical place", "SS-2 para 1.2.4"),
            ("Remote e-voting with a cut-off date, if listed or 1,000 or more members", "s.108; rule 20"),
            ("Send the notice and annual report to every member, director and the auditor", "s.101(3), s.136(1)"),
            ("Check the quorum at the meeting (private company: two members present)", "s.103(1)"),
            ("Scrutiniser's report and results, as the rules require", "rule 20, rule 21"),
            ("Sign the minutes within 30 days", "s.118; SS-2 para 17"),
            ("AOC-4 within 30 days", "s.137(1)"),
            ("MGT-7 or MGT-7A within 60 days", "s.92(4)"),
            ("MGT-14 for special resolutions within 30 days", "s.117(3)"),
            ("ADT-1 within 15 days if an auditor was appointed or re-appointed", "s.139(1); rule 4(2)"),
            ("DIR-12 within 30 days for directors appointed or regularised", "s.170(2)"),
        ],
    },
    "egm": {
        "label": "Extraordinary general meeting",
        "steps": [
            ("Board meeting: approve the business and the notice", "s.100(1), s.173"),
            ("Send the notice at least 21 clear days before (shorter notice: majority in number holding 95% of the paid-up capital)", "s.101(1) proviso"),
            ("Explanatory statement for every item", "s.102(1)"),
            ("Statement on proxies; e-voting if listed or 1,000 or more members", "s.105(2); s.108; rule 20"),
            ("Sign the minutes within 30 days", "s.118"),
            ("MGT-14 for special resolutions within 30 days", "s.117(3)"),
        ],
    },
    "annual_filing": {
        "label": "Annual filings",
        "steps": [
            ("AOC-4 (or AOC-4 XBRL) within 30 days of the AGM", "s.137(1)"),
            ("MGT-7 or MGT-7A within 60 days of the AGM", "s.92(4)"),
            ("ADT-1 within 15 days, if an auditor was appointed", "s.139(1)"),
            ("DPT-3 by 30 June, with the auditor's certificate where needed", "rule 16, 16A, Acceptance of Deposits Rules"),
            ("MSME-1 by 30 April and 31 October, if MSME dues are over 45 days", "MSE payments order, 2019"),
            ("DIR-3 KYC for each director when due (once in three years, by 30 June)", "rule 12A"),
            ("CSR-2, if CSR applies", "rule 12(1B), CSR Rules"),
            ("Review the register of significant beneficial owners (BEN-2 if anything changed)", "s.90; SBO Rules"),
        ],
    },
    "director_appointment": {
        "label": "Appointing a director",
        "steps": [
            ("Consent in DIR-2 and declaration in DIR-8 that they are not disqualified", "s.152(5), s.164; rule 8, 14"),
            ("Check the DIN is active and its KYC is up to date", "rule 12A"),
            ("Disclosure of interest in MBP-1", "s.184(1)"),
            ("Board resolution appointing them (additional director holds office until the next AGM)", "s.161(1)"),
            ("For an independent director: databank registration, declaration of independence, letter of appointment", "s.149(6), (7); rule 6; Schedule IV"),
            ("DIR-12 within 30 days", "s.170(2)"),
            ("Update the register of directors and KMP", "s.170(1)"),
            ("Regularise at the next general meeting, if appointed as an additional director", "s.161(1), s.152"),
        ],
    },
    "allotment": {
        "label": "Allotment of shares",
        "steps": [
            ("Check the authorised capital is enough; if not, increase it (SH-7 within 30 days)", "s.61, s.64"),
            ("Board and member approvals for the route: rights (s.62(1)(a)), preferential or private placement (s.42, s.62(1)(c))", "s.42, s.62"),
            ("For a private placement: PAS-4 offer letter, a separate bank account, no use of money before allotment", "s.42; rule 14"),
            ("Valuation report from a registered valuer where required", "s.62(1)(c); rule 13"),
            ("Board resolution allotting the shares", None),
            ("PAS-3 within 15 days (private placement) or 30 days (others)", "s.42; s.39(4), rule 12"),
            ("Share certificates within two months, or credit in demat", "s.56(4)"),
            ("Update the register of members", "s.88"),
        ],
    },
    "charge": {
        "label": "Creating or satisfying a charge",
        "steps": [
            ("Board resolution for the borrowing and the security (and s.180(1)(a)/(c) approval if needed)", "s.179(3)(d), s.180"),
            ("CHG-1 within 30 days of creation or modification", "s.77(1)"),
            ("CHG-4 within 30 days of satisfaction", "s.82(1)"),
            ("Update the register of charges in CHG-7", "s.85; rule 10"),
        ],
    },
    "due_diligence": {
        "label": "Due diligence / search report",
        "steps": [
            ("Master data from MCA: status, capital, registered office, ROC", None),
            ("Directors and KMP, with their other directorships", None),
            ("Charges registered and satisfied", "s.77, s.82"),
            ("Filing history: annual returns and financial statements for the last three years", "s.92, s.137"),
            ("Statutory registers and minute books", "s.88, s.118, s.170, s.186(9)"),
            ("Pending litigation, defaults and notices", None),
            ("Title documents for assets charged or to be charged", None),
            ("Write the report with sources for every fact", None),
        ],
    },
    "secretarial_audit": {
        "label": "Secretarial audit (MR-3)",
        "steps": [
            ("Letter of engagement; check the company's applicability", "s.204; rule 9"),
            ("Companies Act and rules: registers, returns, meetings, minutes", None),
            ("Securities Contracts (Regulation) Act and rules; Depositories Act", None),
            ("FEMA: foreign investment, overseas investment and ECB", None),
            ("SEBI regulations (for a listed company): LODR, takeover, insider trading", None),
            ("Secretarial Standards SS-1 and SS-2", "s.118(10)"),
            ("Other laws specific to the company's business", None),
            ("Board composition, notices, agenda, minutes; systems and processes", None),
            ("Draft MR-3 with observations; discuss with management; sign with UDIN", None),
        ],
    },
    "other": {"label": "Other work", "steps": []},
}


def steps_for(kind: str) -> list[dict[str, Any]]:
    template = KINDS.get(kind, KINDS["other"])
    return [{"text": text, "basis": basis, "done": False, "done_at": None, "note": None} for text, basis in template["steps"]]
