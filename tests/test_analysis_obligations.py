"""Obligations and deadlines: duties with time limits, read from resolutions, sanction letters, orders and agreements."""

from __future__ import annotations

import time

from aagam.analysis import Doc
from aagam.analysis.obligations import analyse, number_value

PRIVATE_PLACEMENT = """CERTIFIED TRUE COPY OF THE RESOLUTION PASSED BY THE BOARD OF DIRECTORS OF ACME WIDGETS PRIVATE LIMITED
AT ITS MEETING HELD ON 12TH OCTOBER, 2026

RESOLVED THAT pursuant to Sections 42 and 62(1)(c) of the Companies Act, 2013 read with Rule 14 of the Companies
(Prospectus and Allotment of Securities) Rules, 2014, the consent of the Board be and is hereby accorded to offer
10,00,000 equity shares of Rs. 10 each on a private placement basis.

RESOLVED FURTHER THAT the Company shall allot the securities within sixty days of receipt of application money,
failing which it shall repay the application money within fifteen days from the expiry of the said sixty days.

RESOLVED FURTHER THAT the Company shall file the return of allotment in Form PAS-3 with the Registrar within
fifteen days of the date of allotment as required under section 42(9) of the Act.

The meeting concluded at 5.30 p.m. with a vote of thanks to the Chair.
"""

SANCTION = """HDFC Bank Ltd
Ref: HDFC/CB/2026/118                                             Date: 2nd February, 2026
To, M/s Acme Widgets Pvt Ltd

Sub: Sanction of Term Loan of Rs. 25 crore

We are pleased to sanction the facility on the terms below. The Borrower shall create an equitable mortgage over
the factory at Pune in favour of the Bank on or before 31st March, 2026. The Borrower shall submit the stock
statement not later than 10.04.2026. The Borrower shall furnish audited financial statements within 180 days of the
close of each financial year.
"""

NCLT = """IN THE NATIONAL COMPANY LAW TRIBUNAL, MUMBAI BENCH
C.P. No. 214/MB/2026

ORDER

Heard the counsel. The Respondent Company is directed to hold the annual general meeting and file the pending annual
returns within 4 weeks from the date of this order. This Tribunal directs the Respondent No. 2 to furnish a
compliance affidavit within thirty (30) days of the order dated 1st September, 2026.
"""

AGREEMENT = """8.2 The Service Provider shall deliver the final report not later than forty-five days after the
Effective Date. 8.3 Notice of every general meeting shall be given at least 21 clear days before the meeting to be
held on 30th November, 2026."""


def _doc(text: str, meeting_date: str | None = None) -> Doc:
    return Doc(1, "other", "t", None, meeting_date, [(1, text)])


def test_number_words():
    assert number_value("thirty") == 30
    assert number_value("forty-five") == 45
    assert number_value("one hundred and eighty") == 180
    assert number_value("thirty (30)") == 30
    assert number_value("a") == 1
    assert number_value("6") == 6


def test_private_placement_resolution():
    out = analyse(_doc(PRIVATE_PLACEMENT))
    assert out and out["kind"] == "obligations" and out["tags"] == ["deadlines"]
    deadlines = [i["deadline"] for i in out["items"]]
    assert "within sixty days of receipt of application money" in deadlines
    pas3 = next(i for i in out["items"] if "PAS-3" in i["duty"])
    assert pas3["deadline"] == "within fifteen days of the date of allotment"
    assert pas3["who"] == "the Company"
    assert "s.42(9)" in pas3["basis"]
    assert pas3["due"] == ""  # allotment has no date in the text
    # The consent sentence has no time limit and the closing line no duty.
    assert not any("consent of the Board" in i["duty"] for i in out["items"])
    assert out["facts"]["count"] == len(out["items"]) >= 3


def test_sanction_letter_absolute_dates():
    out = analyse(_doc(SANCTION))
    assert out
    mortgage = next(i for i in out["items"] if "mortgage" in i["duty"])
    assert mortgage["deadline"] == "on or before 31st March, 2026"
    assert mortgage["due"] == "2026-03-31"
    assert mortgage["who"] == "the Borrower"
    stock = next(i for i in out["items"] if "stock statement" in i["duty"])
    assert stock["due"] == "2026-04-10"
    audited = next(i for i in out["items"] if "audited" in i["duty"])
    assert audited["deadline"].startswith("within 180 days of the close")
    assert out["facts"]["earliest_due"] == "2026-03-31"
    assert out["summary"] == "3 duties with deadlines; the earliest falls on 31 March 2026."


def test_nclt_order_weeks_and_dated_trigger():
    out = analyse(_doc(NCLT, meeting_date="2026-09-15"))
    assert out
    agm = next(i for i in out["items"] if "annual general meeting" in i["duty"])
    assert agm["deadline"] == "within 4 weeks from the date of this order"
    assert agm["due"] == "2026-10-13"  # four weeks from the order's own date
    assert agm["who"] == "the Respondent Company"
    affidavit = next(i for i in out["items"] if "affidavit" in i["duty"])
    assert affidavit["due"] == "2026-10-01"
    assert affidavit["who"] == "the Respondent No. 2"


def test_agreement_clauses_and_clear_days():
    out = analyse(_doc(AGREEMENT))
    assert out
    report = next(i for i in out["items"] if "final report" in i["duty"])
    assert report["deadline"] == "not later than forty-five days after the Effective Date"
    assert report["basis"] == "clause 8.2" and report["who"] == "the Service Provider"
    notice = next(i for i in out["items"] if "general meeting" in i["duty"])
    assert notice["deadline"].startswith("at least 21 clear days before the meeting")
    assert notice["due"] == "2026-11-08"  # 21 clear days: neither the day of sending nor the meeting day counts


def test_dates_without_duties_are_not_obligations():
    text = ("The Board met on 12th March, 2026 and noted the accounts for the year ended 31st March, 2025. "
            "The company was incorporated on 1st April, 2001. Mr. Rao has at least 20 years of experience in finance. "
            "The return was filed within 30 days last year.")
    assert analyse(_doc(text)) is None
    assert analyse(_doc("")) is None
    # Odd text and a document date that isn't one must not raise.
    analyse(Doc(1, "other", None, None, "not a date", [(1, "))) ;; shall within within 9999 days before 31.02.2026 of x")]))
    analyse(Doc(1, "other", None, None, "2026-01-01", [(1, "The Company shall pay within 9999 years from 1st January, 2026.")]))


def test_large_document_is_fast():
    pages = [(n, PRIVATE_PLACEMENT + SANCTION + NCLT * 2) for n in range(1, 151)]
    started = time.perf_counter()
    out = analyse(Doc(1, "other", "t", None, None, pages))
    assert out and time.perf_counter() - started < 2.0


def test_accounting_and_audit_wording_is_not_a_duty():
    text = (
        "All employee benefits payable wholly within twelve months of rendering the service are classified as short term "
        "employee benefits. An asset is treated as current when it is expected to be realised within twelve months after the "
        "reporting period. On the basis of the financial ratios, nothing has come to our attention which causes us to believe "
        "that the Company is not capable of meeting its liabilities as and when they fall due within a period of one year from "
        "the balance sheet date. We neither give any guarantee nor any assurance that all liabilities falling due within a "
        "period of one year from the balance sheet date will get discharged by the Company as and when they fall due."
    )
    assert analyse(Doc(1, "financial_statements", "Accounts", None, None, [(1, text)])) is None
    real = "The Company shall file Form PAS-3 with the Registrar within fifteen days of the allotment."
    assert analyse(Doc(1, "other", "t", None, None, [(1, real)]))["items"][0]["deadline"] == "within fifteen days of the allotment"
