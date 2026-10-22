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
    # LLPs: the Limited Liability Partnership Act, 2008 ("s.") and the LLP Rules, 2009 ("rule").
    "llp_incorporation": {
        "label": "LLP: Incorporation",
        "steps": [
            ("Reserve the name in RUN-LLP (or apply for it in FiLLiP); a reserved name holds for three months", "s.15; rule 18"),
            ("At least two designated partners who are individuals, one of them resident in India", "s.7(1)"),
            ("DIN for each designated partner (applied for in FiLLiP for those who have none)", "s.7(6)"),
            ("Consent of every designated partner and partner, given in FiLLiP", "s.7(3)"),
            ("File FiLLiP with the subscription sheet, proof of the registered office and the partners' details", "s.11; rule 11"),
            ("Certificate of incorporation with the LLPIN (PAN and TAN come with it)", "s.12"),
            ("Sign the LLP agreement on stamp paper and file it in Form 3 within 30 days of incorporation", "s.23(2); rule 21(1)"),
            ("Partners bring in their contributions as the agreement says; open the bank account", "s.32"),
            ("Keep books of account at the registered office from the start", "s.34(1); rule 24(1)"),
        ],
    },
    "llp_annual_filing": {
        "label": "LLP: Annual filings (Form 8 and Form 11)",
        "steps": [
            ("Books of account on cash or accrual basis, by double entry, kept at the registered office", "s.34(1); rule 24(1)"),
            ("Statement of account and solvency within six months of the year end, signed by the designated partners", "s.34(2)"),
            ("Audit by a chartered accountant, unless turnover hasn't exceeded ₹40 lakh and contribution hasn't exceeded ₹25 lakh "
             "(confirm the proviso's reading with the auditor)", "rule 24(8)"),
            ("Form 11 (annual return) by 30 May, within 60 days of the year end", "s.35(1); rule 25(1)"),
            ("Form 11 certified by a company secretary in practice when contribution exceeds ₹50 lakh or turnover exceeds ₹5 crore", "rule 25(2)"),
            ("Form 8 (statement of account and solvency) by 30 October, signed by the designated partners and certified by a "
             "practising CA, CS or CMA", "s.34(3); rule 24(4)"),
            ("Form 4 and Form 3 filed for every change in partners or in the agreement during the year", "s.25(2), s.23(2)"),
            ("DIR-3 KYC for each designated partner when due (they hold DINs)", "rule 12A, Appointment and Qualification of Directors Rules"),
            ("Review the significant beneficial owners: LLP BEN-2 within 30 days of a BEN-1 declaration", "LLP (Significant Beneficial Owners) Rules, 2023"),
        ],
    },
    "llp_partner_change": {
        "label": "LLP: Partner joining or leaving",
        "steps": [
            ("Partners' consent as the LLP agreement requires for admitting or letting go a partner", "s.23(1), s.24"),
            ("Consent of the incoming partner or designated partner", "s.7(3)"),
            ("DIN for an incoming designated partner, with its KYC up to date", "s.7(6)"),
            ("Form 4 within 30 days of the change", "s.25(2); rule 22"),
            ("Form 3 within 30 days if the agreement changes (contribution, profit share, admission)", "s.23(2); rule 21(1)"),
            ("Still at least two partners and two designated partners, one resident in India", "s.6, s.7(1)"),
            ("A partner leaving: settle their share and contribution as the agreement says", "s.24"),
            ("Update the LLP's register of partners", None),
        ],
    },
    "llp_agreement_change": {
        "label": "LLP: Changing the LLP agreement",
        "steps": [
            ("Partners' consent as the agreement requires", "s.23(1)"),
            ("Supplementary agreement on stamp paper (under the state's stamp law), signed by the partners", None),
            ("Form 3 within 30 days of the change", "s.23(2); rule 21(1)"),
            ("Form 4 too if partners join, leave or change designation", "s.25(2)"),
            ("Update the books and the bank for any change in contributions", None),
        ],
    },
    "llp_office_change": {
        "label": "LLP: Changing the registered office",
        "steps": [
            ("Partners' consent as the agreement requires", "s.13(3)"),
            ("Moving to another state: consent of any secured creditors first", "rule 17"),
            ("Form 15 within 30 days of the change", "s.13(3); rule 17"),
            ("Form 3 too if the agreement names the registered office", "s.23(2)"),
            ("Update the letterhead, bank, GST and other registrations", None),
        ],
    },
    "llp_name_change": {
        "label": "LLP: Changing the name",
        "steps": [
            ("Reserve the new name in RUN-LLP", "s.15; rule 18"),
            ("Partners' consent as the agreement requires", "s.16"),
            ("Form 5 within 30 days", "s.16; rule 20(2)"),
            ("Form 3 for the change in the agreement's name clause", "s.23(2)"),
            ("New certificate of incorporation; update the PAN, bank, GST and letterhead", None),
        ],
    },
    "llp_strike_off": {
        "label": "LLP: Striking off (Form 24)",
        "steps": [
            ("Check it has carried on no business for at least a year (or never began) and has no liabilities", "s.75; rule 37"),
            ("Form 8 and Form 11 filed up to the end of the year in which it stopped business", "rule 37"),
            ("Consent of all partners; statement of account showing no assets or liabilities, certified by a CA", "rule 37"),
            ("File Form 24 with the designated partners' affidavit and indemnity bond", "s.75; rule 37"),
            ("Close the bank account and surrender GST and other registrations", None),
        ],
    },
    "other": {"label": "Other work", "steps": []},
}


def steps_for(kind: str) -> list[dict[str, Any]]:
    template = KINDS.get(kind, KINDS["other"])
    return [{"text": text, "basis": basis, "done": False, "done_at": None, "note": None} for text, basis in template["steps"]]
