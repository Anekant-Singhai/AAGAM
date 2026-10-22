"""The legal-matters analyser on the papers a CS meets: tribunal orders, notes to accounts, ROC orders, IBC petitions."""

from __future__ import annotations

import time

from aagam.analysis import Doc, legal


def _doc(text: str, *more: str) -> Doc:
    return Doc(1, "other", "t", None, None, [(n, t) for n, t in enumerate((text, *more), start=1)])


NCLT_ORDER = """BEFORE THE NATIONAL COMPANY LAW TRIBUNAL
MUMBAI BENCH, COURT - II

C.P. No. 123/MB/2024

In the matter of Sections 241 and 242 of the Companies Act, 2013

Ramesh Kumar Shah ...Petitioner
Versus
Shah Textiles Private Limited & Ors. ...Respondents

Order delivered on 12.03.2025

1. The present Company Petition has been filed by the Petitioner, holding 18% of the equity share capital of
Respondent No. 1, alleging acts of oppression and mismanagement by the majority shareholders. The Petitioner
contends that the allotment of 5,00,000 equity shares to Respondent No. 2 was made without notice to him.

2. The Respondents relied upon the judgment of the Hon'ble Supreme Court in Tata Consultancy Services Ltd. v.
Cyrus Investments Pvt. Ltd., (2021) 9 SCC 449, and submitted that the petition is not maintainable.

3. Heard the learned counsel for the parties. Arguments concluded. The matter is reserved for orders.
The matter is next listed on 15th January, 2026 for pronouncement.
"""

CONTINGENT_NOTE = """Note 34: Contingent liabilities and commitments

(a) Claims against the Company not acknowledged as debts:
(i) Income-tax demand of ₹2.45 crore for Assessment Year 2019-20 raised under section 143(3) of the Income-tax Act,
1961, against which the Company has filed an appeal which is pending before the CIT(A).
(ii) The Company received a show cause notice from the GST authorities under section 74 of the CGST Act, 2017
demanding ₹78,50,000 towards input tax credit availed in FY 2020-21; the Company has filed its reply and is
contesting the demand.
The management believes that the outcome of these proceedings will not have a material adverse effect on the
financial position of the Company.
"""

ROC_ORDER = """OFFICE OF THE REGISTRAR OF COMPANIES, MAHARASHTRA, MUMBAI

Adjudication Order No. ROC/MUM/ADJ/454/2024-25 dated 18.07.2024

In the matter of Bluefin Agro Private Limited (CIN U01400MH2015PTC123456)

ORDER UNDER SECTION 454 OF THE COMPANIES ACT, 2013 READ WITH THE COMPANIES (ADJUDICATION OF PENALTIES) RULES, 2014

1. A show cause notice was issued to the company and its officers in default for failure to file the
financial statements for FY 2022-23 within the time allowed under section 137 of the Companies Act, 2013.
2. Having considered the reply, the Adjudicating Officer hereby imposes a penalty of ₹1,50,000 on the company
and ₹50,000 on each officer in default under section 137(3) of the Act.
3. The penalty shall be paid within 90 days of receipt of this order; an appeal lies to the Regional Director
under section 454(5).
"""

IBC_PETITION = """IN THE NATIONAL COMPANY LAW TRIBUNAL, NEW DELHI BENCH

CP (IB) No. 45/ND/2025

State Bank of India ...Financial Creditor
Versus
Shree Ganesh Steels Private Limited ...Corporate Debtor

Application under section 7 of the Insolvency and Bankruptcy Code, 2016 read with Rule 4 of the Insolvency and
Bankruptcy (Application to Adjudicating Authority) Rules, 2016 for initiating the corporate insolvency resolution
process against the Corporate Debtor for a default of ₹12.6 crore in repayment of a term loan.

Present: Ld. Counsel for the Financial Creditor. None for the Corporate Debtor.
Notice was issued to the Corporate Debtor. List the matter for hearing on admission. Next date of hearing: 22/11/2026.
"""

AGM_NOTICE = """NOTICE is hereby given that the Tenth Annual General Meeting of the Members of Bluefin Agro Private Limited
will be held on Friday, 26th September, 2025 at 11.00 a.m. at the registered office of the Company.

ORDINARY BUSINESS
1. To receive, consider and adopt the audited financial statements of the Company for the financial year ended
31st March, 2025, together with the reports of the Board of Directors and the Auditors thereon.
2. To appoint a director in place of Mr. Anil Mehta (DIN: 01234567), who retires by rotation and being eligible,
offers himself for re-appointment.

SPECIAL BUSINESS
3. To approve the borrowing limits of ₹50 crore under section 180(1)(c) of the Companies Act, 2013, subject to the
approval of the members by way of a special resolution, and any other approvals as may be necessary.
A member entitled to attend and vote is entitled to appoint a proxy. The Hon'ble Ministry of Corporate Affairs has
allowed meetings through video conferencing.
"""


def test_nclt_oppression_order() -> None:
    out = legal.analyse(_doc(NCLT_ORDER))
    assert out is not None and out["kind"] == "legal" and "litigation" in out["tags"]
    assert len(out["items"]) == 1  # the cited Tata v. Cyrus judgment is authority, not a matter of hers
    m = out["items"][0]
    assert m["case_no"] == "C.P. No. 123/MB/2024"
    assert m["forum"] == "NCLT Mumbai"
    assert m["nature"].startswith("Oppression and mismanagement")
    assert {"241", "242"} <= set(m["sections"])
    assert m["parties"] == "Ramesh Kumar Shah v. Shah Textiles Private Limited & Ors."
    assert m["status"] == "reserved"
    assert m["next_date"] == "2026-01-15"
    assert m["page"] == 1 and m["confidence"] >= 0.8
    assert out["highlights"] and out["score"] > 0.3


def test_contingent_liabilities_note() -> None:
    out = legal.analyse(_doc(CONTINGENT_NOTE))
    assert out is not None
    items = out["items"]
    assert len(items) == 2
    tax = next(i for i in items if i["forum"] == "CIT(A)")
    assert tax["nature"] == "Income-tax dispute" and tax["status"] == "pending"
    assert tax["amount"] == 24_500_000 and "143(3) IT Act" in tax["sections"]
    gst = next(i for i in items if i["forum"] == "GST authorities")
    assert gst["nature"] == "GST demand (show-cause notice)"
    assert gst["amount"] == 7_850_000 and "74 CGST Act" in gst["sections"]
    assert out["facts"]["total_amount"] == 24_500_000 + 7_850_000
    assert out["summary"].startswith("2 matters:") and "crore at stake" in out["summary"]


def test_roc_adjudication_order() -> None:
    out = legal.analyse(_doc(ROC_ORDER))
    assert out is not None
    matters = [i for i in out["items"] if i["case_no"]]
    assert len(matters) == 1
    m = matters[0]
    assert m["case_no"] == "Adjudication Order No. ROC/MUM/ADJ/454/2024-25"
    assert m["forum"] == "ROC Mumbai"
    assert m["nature"] == "Adjudication of penalty (s.454)"
    assert m["status"] == "penalty imposed"
    assert m["amount"] == 150_000
    assert "454" in m["sections"] and "137" in m["sections"]
    # The appeal to the Regional Director is a right the order mentions, not a separate proceeding.
    assert all(i["forum"] != "Regional Director" for i in out["items"])


def test_ibc_section_7_petition() -> None:
    out = legal.analyse(_doc(IBC_PETITION))
    assert out is not None and len(out["items"]) == 1
    m = out["items"][0]
    assert m["case_no"] == "CP (IB) No. 45/ND/2025"
    assert m["forum"] == "NCLT New Delhi"
    assert m["nature"] == "Insolvency (s.7 IBC, financial creditor)"
    assert "7 IBC" in m["sections"]
    assert m["parties"] == "State Bank of India v. Shree Ganesh Steels Private Limited"
    assert m["amount"] == 126_000_000
    assert m["next_date"] == "2026-11-22"
    assert out["facts"]["next_date"] == "2026-11-22"


def test_mentions_of_one_case_merge_across_pages() -> None:
    first = "The Company has filed Company Appeal (AT) (Insolvency) No. 1234 of 2023 before the NCLAT, Principal Bench."
    second = "In Company Appeal (AT) (Insolvency) No. 1234 of 2023 the NCLAT has granted an interim stay on the CIRP. It is listed on 03.02.2026."
    out = legal.analyse(_doc(first, second))
    assert out is not None and len(out["items"]) == 1
    m = out["items"][0]
    assert m["forum"] == "NCLAT Principal Bench" and m["status"] == "stayed" and m["next_date"] == "2026-02-03"


def test_agm_notice_is_not_a_legal_matter() -> None:
    assert legal.analyse(_doc(AGM_NOTICE)) is None


def test_denials_and_statute_wording_are_not_matters() -> None:
    text = ("There are no proceedings pending under the Insolvency and Bankruptcy Code, 2016. No significant and material orders "
            "were passed by the regulators or courts or tribunals impacting the going concern status. If a company fails to file "
            "its return, the company shall be liable to a penalty of ₹10,000 and in case of continuing failure, with a further "
            "penalty of ₹100 for each day.")
    out = legal.analyse(_doc(text))
    assert out is None or out["items"] == []


def test_odd_text_and_speed() -> None:
    odd = legal.analyse(_doc("", "   ", "v. v. vs ... C.P. No. ... No. ( ) ₹ ₹ High Court of", "(((((" * 500, "No. " * 200))
    assert odd is None or isinstance(odd["items"], list)
    pages = [NCLT_ORDER, CONTINGENT_NOTE, ROC_ORDER, IBC_PETITION, AGM_NOTICE] * 30
    started = time.perf_counter()
    out = legal.analyse(_doc(*pages))
    assert time.perf_counter() - started < 3
    assert out is not None and len({i["case_no"] for i in out["items"] if i["case_no"]}) == 3
