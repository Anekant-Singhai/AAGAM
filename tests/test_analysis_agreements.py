"""Agreement terms: parties, date, money, law, termination and the rest, read from loan and services agreements."""

from __future__ import annotations

import time

from aagam.analysis import Doc
from aagam.analysis.agreements import analyse

LOAN = """LOAN AGREEMENT

This Loan Agreement is made and entered into at Mumbai on this 12th day of March, 2026 by and between
Acme Widgets Pvt Ltd, a company incorporated under the Companies Act, 2013 having its registered office at
Andheri East, Mumbai (hereinafter referred to as the "Borrower") AND HDFC Bank Ltd, a banking company having its
registered office at Lower Parel, Mumbai (hereinafter referred to as the "Lender").

WHEREAS the Borrower has requested the Lender for a term loan and the Lender has agreed to lend on the terms below.

1. The Lender agrees to lend and the Borrower agrees to borrow a term loan of Rs. 25 crore (the "Loan").
2. The tenure of the Loan shall be 5 years from the date of first disbursement.
3. The Loan shall carry a rate of interest of 9.5% per annum linked to the Lender's MCLR.
4. The Loan shall be repaid in 20 equal quarterly instalments commencing from June 2027.
5. The Loan shall be secured by a first charge on the movable assets of the Borrower and the personal guarantee of its
promoters.
6. The following shall constitute Events of Default:
(a) non-payment of any instalment on its due date;
(b) breach of any covenant;
(c) the Borrower being wound up.
7. The Lender may terminate this Agreement by giving ninety days' written notice, or forthwith on material breach or
insolvency of the Borrower.
8. This Agreement shall be governed by and construed in accordance with the laws of India and the courts at Mumbai shall
have exclusive jurisdiction.
9. The Borrower shall not assign any of its rights under this Agreement without the prior written consent of the Lender.
10. Stamp duty of Rs. 5,00,000 payable on this Agreement shall be borne by the Borrower.

IN WITNESS WHEREOF the parties have signed this Agreement on the date first written above.
For Acme Widgets Pvt Ltd
Mr. Rajesh Mehta
Managing Director
For HDFC Bank Ltd
Ms. Priya Nair
Authorised Signatory
"""

SERVICES = """SERVICES AGREEMENT

This Agreement is entered into on 1st April, 2026 between Brightline Consulting LLP (hereinafter called the
"Service Provider") and Acme Widgets Private Limited (hereinafter called the "Client").

1. The Agreement shall be effective from 1st April, 2026 and shall continue for a term of two (2) years.
2. The Client shall pay a monthly retainer fee of Rs. 1,50,000 plus GST. Invoices shall be payable within thirty days of
receipt.
3. Either party may terminate this Agreement for convenience by giving 30 days' prior written notice.
4. The Agreement may be renewed for a further period of one year by mutual written consent.
5. The Service Provider shall indemnify the Client against all losses arising from its negligence.
6. Each party shall keep the Confidential Information of the other party confidential and shall not disclose it to any
third party.
7. During the term and for twelve months thereafter, the Service Provider shall not directly or indirectly solicit any
employee of the Client.
8. Any dispute shall be referred to arbitration by a sole arbitrator under the Arbitration and Conciliation Act, 1996.
The seat of arbitration shall be Bengaluru.
9. Neither party shall be liable for delay caused by force majeure events.
10. All notices under this Agreement shall be sent to the addresses first written above by registered post or email.
"""

BOARD_MINUTES = """MINUTES OF THE MEETING OF THE BOARD OF DIRECTORS OF ACME WIDGETS PRIVATE LIMITED HELD ON 12TH MARCH, 2026

The Chairman informed the Board that the Company proposes to avail a term loan from HDFC Bank Ltd. The Board noted the
draft loan agreement placed before it. RESOLVED THAT the Board approves borrowing up to Rs. 25 crore and authorises
Mr. Rajesh Mehta, Managing Director, to sign the documents. The meeting ended with a vote of thanks.
"""


def _doc(text: str) -> Doc:
    return Doc(1, "other", "t", None, None, [(1, text)])


def _terms(out: dict) -> dict[str, str]:
    return {i["term"]: i["value"] for i in out["items"]}


def test_loan_agreement():
    out = analyse(_doc(LOAN))
    assert out and out["kind"] == "agreements" and out["tags"] == ["agreement"]
    terms = _terms(out)
    assert terms["Parties"] == "Acme Widgets Private Limited (Borrower); HDFC Bank Limited (Lender)"
    assert terms["Date of agreement"] == "12 March 2026"
    assert terms["Loan amount"] == "₹25.00 crore"
    assert terms["Interest rate"] == "9.5% p.a. (linked to MCLR)"
    assert terms["Term / tenure"].startswith("5 years from the date of first disbursement")
    assert terms["Governing law"] == "Laws of India"
    assert terms["Jurisdiction"] == "Courts at Mumbai (exclusive)"
    assert terms["Termination"] == "90 days' notice; on material breach, on insolvency"
    assert "non-payment of any instalment" in terms["Events of default"] and "breach of any covenant" in terms["Events of default"]
    assert "Security / guarantee" in terms and "Assignment" in terms and "Payment terms" in terms
    assert terms["Stamp duty"].startswith("₹5.00 lakh")
    assert "Mr. Rajesh Mehta (Managing Director)" in terms["Signatories"]
    assert "Ms. Priya Nair (Authorised Signatory)" in terms["Signatories"]
    assert out["facts"]["parties"] == ["Acme Widgets Private Limited", "HDFC Bank Limited"]
    assert out["facts"]["governing_law"] == "Laws of India"
    assert out["summary"] == ("Loan agreement between Acme Widgets Private Limited and HDFC Bank Limited dated 12 March 2026: "
                              "₹25.00 crore at 9.5% for 5 years; Indian law, Mumbai courts; 90 days' notice to terminate.")
    assert all(i["page"] == 1 and "confidence" in i for i in out["items"])


def test_services_agreement():
    out = analyse(_doc(SERVICES))
    assert out
    terms = _terms(out)
    assert terms["Parties"] == "Brightline Consulting LLP (Service Provider); Acme Widgets Private Limited (Client)"
    assert terms["Date of agreement"] == "1 April 2026"
    assert terms["Effective date"] == "1 April 2026"
    assert terms["Term / tenure"] == "2 years"
    assert terms["Consideration / fees"] == "₹1.50 lakh a month (Rs. 1,50,000)"
    assert "thirty days" in terms["Payment terms"]
    assert terms["Termination"] == "30 days' notice; for convenience"
    assert terms["Arbitration"] == "Arbitration, sole arbitrator, under the Arbitration and Conciliation Act, 1996"
    assert terms["Seat of arbitration"] == "Bengaluru"
    for term in ("Renewal", "Indemnity", "Confidentiality", "Non-compete / non-solicit", "Force majeure", "Notices"):
        assert term in terms, term
    assert out["summary"].startswith("Services agreement between Brightline Consulting LLP and Acme Widgets Private Limited dated 1 April 2026")


SANCTION = """HDFC Bank Ltd
Ref: HDFC/CB/2026/118                                             Date: 2nd February, 2026
To, M/s Acme Widgets Pvt Ltd

Sub: Sanction of Term Loan

We are pleased to sanction a term loan of Rs. 25 crore on the terms below. The tenor of the facility shall be 60 months.
Rate of interest: 9.25% p.a. linked to the Bank's repo rate. The facility shall be secured by hypothecation of stocks and
the personal guarantee of the promoters. The sanction is governed by the laws of India.
Yours faithfully,
For HDFC Bank Ltd
Name: Anil Kapoor
Chief Manager
"""


def test_sanction_letter():
    out = analyse(_doc(SANCTION))
    assert out
    terms = _terms(out)
    assert terms["Parties"] == "HDFC Bank Limited; Acme Widgets Private Limited"
    assert terms["Loan amount"] == "₹25.00 crore"
    assert terms["Term / tenure"] == "60 months"
    assert terms["Interest rate"] == "9.25% p.a. (linked to repo rate)"
    assert "Security / guarantee" in terms
    assert terms["Signatories"] == "Anil Kapoor (Chief Manager)"
    assert out["summary"] == ("Sanction letter between HDFC Bank Limited and Acme Widgets Private Limited dated 2 February 2026: ₹25.00 crore at 9.25% "
                              "for 60 months; Indian law.")


def test_documents_that_are_not_agreements():
    assert analyse(_doc(BOARD_MINUTES)) is None
    assert analyse(_doc("Notice is hereby given that the 12th Annual General Meeting will be held on 30th September, 2026.")) is None
    assert analyse(_doc("")) is None
    assert analyse(Doc(1, "agreement", None, None, None, [(1, "this agreement ((( between AND and ))) hereinafter")])) is None


def test_large_agreement_is_fast():
    pages = [(n, LOAN + SERVICES) for n in range(1, 151)]
    started = time.perf_counter()
    out = analyse(Doc(1, "agreement", "t", None, None, pages))
    assert out and time.perf_counter() - started < 2.0


def test_a_meeting_notice_is_not_an_agreement():
    notice = (
        "NOTICE is hereby given that the 8th Annual General Meeting of the members of Godha Cabcon & Insulation Limited "
        "(hereinafter referred to as the Company) will be held on 30 September 2024. The Company has entered into an agreement "
        "with National Stock Exchange of India Limited. The Board of Directors (hereinafter referred to as the Board) recommends "
        "a limit of ₹100 crore under section 186. Governing law: the Companies Act, 2013. The term of office is five years. "
        "Termination of the contract is not proposed. Confidentiality of the e-voting process is ensured."
    )
    assert analyse(Doc(1, "notice", "AGM notice", None, None, [(1, notice)])) is None
