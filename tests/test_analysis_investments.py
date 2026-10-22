"""The investments analyser on the papers she actually reads: a notice raising the s.186 limit, a board resolution,
a financial-statement note, a guarantee for a subsidiary's loan, and documents that only mention investments."""

import time

from aagam.analysis import Doc
from aagam.analysis.investments import COLUMNS, analyse

AGM_NOTICE = """NOTICE is hereby given that the 15th Annual General Meeting of the Members of Alpha Industries Limited will be held on Friday, 26th September, 2025 at 11.00 a.m. at the Registered Office of the Company.

SPECIAL BUSINESS

4. Approval for loans, investments, guarantees and security under Section 186 of the Companies Act, 2013

To consider and if thought fit, to pass the following resolution as a Special Resolution:

"RESOLVED THAT pursuant to the provisions of Section 186 and other applicable provisions, if any, of the Companies Act, 2013 read with the Companies (Meetings of Board and its Powers) Rules, 2014 (including any statutory modification or re-enactment thereof for the time being in force), consent of the Members be and is hereby accorded to the Board of Directors of the Company to (i) give any loan to any person or other body corporate; (ii) give any guarantee or provide security in connection with a loan to any other body corporate or person; and (iii) acquire by way of subscription, purchase or otherwise the securities of any other body corporate, up to an aggregate amount of ₹100 crore (Rupees One Hundred Crore only) outstanding at any time, notwithstanding that the aggregate of the loans, guarantees, security and investments so far made together with the proposed ones may exceed sixty per cent of the paid-up share capital, free reserves and securities premium account of the Company or one hundred per cent of its free reserves and securities premium account, whichever is more.

RESOLVED FURTHER THAT the Board be and is hereby authorised to do all such acts, deeds and things as may be necessary to give effect to this resolution."

EXPLANATORY STATEMENT PURSUANT TO SECTION 102 OF THE COMPANIES ACT, 2013

Item No. 4: As per Section 186(3) of the Act, where the aggregate of loans and investments so far made, the amount for which guarantee or security has been provided exceeds the prescribed limits, prior approval of the members by special resolution is required. To meet the funding needs of its subsidiaries, the Board recommends to increase the limit to ₹100 crore. None of the Directors is concerned or interested in the resolution."""

BOARD_RESOLUTION = """CERTIFIED TRUE COPY OF THE RESOLUTION PASSED BY THE BOARD OF DIRECTORS OF BETA TECHNOLOGIES PRIVATE LIMITED AT ITS MEETING HELD ON 14TH AUGUST, 2025

"RESOLVED THAT pursuant to the provisions of Section 179(3) and Section 186 of the Companies Act, 2013, the approval of the Board be and is hereby accorded to invest ₹5,00,00,000 (Rupees Five Crore only) in 50,00,000 equity shares of ₹10 each of XYZ Private Limited, at par, by way of subscription to its rights issue.

RESOLVED FURTHER THAT Mr. Anil Mehta, Director, be and is hereby authorised to sign the application and do all acts necessary to give effect to this resolution."

For Beta Technologies Private Limited
Sd/-
Anil Mehta, Director (DIN 01234567)"""

FS_NOTE = """Beta Technologies Private Limited
Notes to the financial statements for the year ended 31st March, 2025
(All amounts in ₹ lakhs, unless otherwise stated)

5. Non-current investments
                                                                    As at 31.03.2025   As at 31.03.2024
Investment in equity instruments (unquoted, at cost)
Subsidiaries
XYZ Private Limited 50,00,000 equity shares of ₹10 each fully paid up        500.00        -
Gamma Solar Private Limited 10,000 equity shares of ₹10 each fully paid up     1.00      1.00
Investment in preference shares
Delta Finance Limited 2,00,000 8% cumulative redeemable preference shares of ₹100 each   200.00   200.00
Investment in mutual funds (quoted)
HDFC Liquid Fund - Direct Plan - Growth 1,234.567 units        25.50     10.00
Total non-current investments                                   726.50    211.00
Aggregate amount of unquoted investments                        701.00    201.00

6. Trade receivables
Unsecured, considered good                                    1,250.00    980.00"""

GUARANTEE = """Extract of the minutes of the meeting of the Board of Directors of Alpha Industries Limited held on 10th July, 2025

RESOLVED THAT pursuant to Section 186 of the Companies Act, 2013, the consent of the Board be and is hereby accorded to give a corporate guarantee of ₹25 crore in favour of State Bank of India for the term loan sanctioned to Beta Engineering Private Limited, a wholly owned subsidiary of the Company."""

UNRELATED = """LEAVE AND LICENCE AGREEMENT

This Leave and Licence Agreement is made at Mumbai on 1st April, 2025 between Mr. Ramesh Patil (the Licensor) and Alpha Industries Limited (the Licensee). The Licensor grants the Licensee the use of office premises at Andheri East for a period of 36 months at a monthly licence fee of ₹1,50,000 and a refundable security deposit of ₹5,00,000. The Licensee shall pay electricity charges and keep the premises in good repair. Either party may terminate this agreement by giving three months' notice in writing."""

DIRECTORS_REPORT = """DIRECTORS' REPORT

Your Directors have pleasure in presenting the 15th Annual Report of the Company together with the audited financial statements for the year ended 31st March, 2025. The revenue from operations grew by 12% to ₹480 crore and the profit after tax stood at ₹36 crore. The Board recommends a dividend of ₹2 per equity share. Particulars of loans, guarantees or investments under Section 186 of the Companies Act, 2013 are given in the notes to the financial statements. There was no change in the nature of business during the year. The Company has a robust risk management framework and internal financial controls commensurate with its size."""


def _doc(text: str, doc_type: str = "notice") -> Doc:
    return Doc(1, doc_type, "t", None, None, [(1, text)])


def test_notice_raising_the_s186_limit():
    out = analyse(_doc(AGM_NOTICE))
    assert out is not None
    limits = [i for i in out["items"] if i["nature"] == "limit"]
    assert len(limits) == 1, out["items"]
    limit = limits[0]
    assert limit["amount"] == 1_000_000_000
    assert limit["approval"].startswith("Special resolution")
    assert "186" in limit["section"]
    assert "₹100 crore" in limit["context"]
    # The authority to deal with "any body corporate" is the limit, not a guarantee or loan of ₹100 crore.
    assert not [i for i in out["items"] if i["nature"] != "limit"]
    assert out["facts"]["limit"] == 1_000_000_000
    assert out["summary"] == "The limit under s.186 is raised to ₹100 crore."
    assert out["tags"][:2] == ["investments", "s.186"]
    assert out["highlights"] and out["score"] > 0.3


def test_board_resolution_approving_an_investment():
    out = analyse(_doc(BOARD_RESOLUTION, "resolutions"))
    assert out is not None
    assert len(out["items"]) == 1, out["items"]
    item = out["items"][0]
    assert item["investee"] == "XYZ Private Limited"
    assert item["instrument"] == "equity shares"
    assert item["amount"] == 50_000_000  # not the ₹10 face value
    assert item["quantity"] == "50,00,000 equity shares of ₹10 each"
    assert item["date"] == "2025-08-14"
    assert item["approval"] == "Board resolution"
    assert item["section"] == "179(3), 186"
    assert item["nature"] == "approved"
    assert item["page"] == 1 and "XYZ Private Limited" in item["context"]
    assert item["confidence"] >= 0.8
    assert out["summary"] == "1 investment, ₹5 crore in all."


def test_financial_statement_note_listing_investments():
    out = analyse(_doc(FS_NOTE, "financial_statements"))
    assert out is not None
    got = {(i["investee"], i["instrument"], i["amount"]) for i in out["items"]}
    assert got == {
        ("XYZ Private Limited", "equity shares", 50_000_000),
        ("Gamma Solar Private Limited", "equity shares", 100_000),
        ("Delta Finance Limited", "preference shares", 20_000_000),
        ("HDFC Liquid Fund - Direct Plan - Growth", "mutual fund units", 2_550_000),
    }, out["items"]
    xyz = next(i for i in out["items"] if i["investee"] == "XYZ Private Limited")
    assert xyz["quantity"] == "50,00,000 equity shares of ₹10 each"
    assert xyz["nature"] == "outstanding" and xyz["date"] == "2025-03-31"
    assert out["facts"]["total_amount"] == 72_650_000  # the note's own total, ₹726.50 lakh
    assert out["facts"]["by_instrument"] == {"equity shares": 2, "preference shares": 1, "mutual fund units": 1}
    assert out["summary"] == "4 investments, ₹7.26 crore in all."


def test_guarantee_for_a_subsidiarys_term_loan():
    out = analyse(_doc(GUARANTEE, "minutes"))
    assert out is not None
    assert len(out["items"]) == 1, out["items"]  # the term loan is what is guaranteed, not a loan given
    item = out["items"][0]
    assert item["instrument"] == "guarantee"
    assert item["investee"] == "Beta Engineering Private Limited"
    assert item["lender"] == "State Bank of India"
    assert item["amount"] == 250_000_000
    assert item["section"] == "186"
    assert item["approval"] == "Board resolution"
    assert item["date"] == "2025-07-10"
    assert out["summary"] == "1 guarantee, ₹25 crore in all."


def test_loan_to_a_directors_concern_under_s185():
    text = ("RESOLVED THAT pursuant to Section 185 of the Companies Act, 2013 and subject to the approval of the members by special resolution, "
            "the Board be and is hereby authorised to give a loan of ₹50 lakh to Kappa Ventures Private Limited, a company in which "
            "Mr. Rakesh Sharma, Director, is interested, at an interest rate of 9% per annum, repayable within three years.")
    out = analyse(_doc(text, "resolutions"))
    assert out is not None
    item = out["items"][0]
    assert (item["instrument"], item["investee"], item["amount"]) == ("loan", "Kappa Ventures Private Limited", 5_000_000)
    assert item["section"] == "185" and item["approval"] == "Special resolution"
    assert "s.185" in out["tags"]


def test_unrelated_documents_are_not_about_investments():
    assert analyse(_doc(UNRELATED, "other")) is None  # a "security deposit" under a licence is not s.186 security
    assert analyse(_doc(DIRECTORS_REPORT, "annual_report")) is None  # boilerplate only
    assert analyse(_doc("", "other")) is None


def test_share_capital_and_borrowing_are_not_investments():
    text = ("Note 12. Equity share capital\nAuthorised: 1,00,00,000 equity shares of ₹10 each ₹10,00,00,000\n"
            "Issued, subscribed and paid-up: 50,00,000 equity shares of ₹10 each fully paid up ₹5,00,00,000\n\n"
            "The Company has availed a term loan of ₹20 crore from HDFC Bank Limited, secured by hypothecation of its plant.")
    out = analyse(_doc(text, "financial_statements"))
    assert out is None or not out["items"]


def test_duplicates_across_resolution_and_explanatory_statement_collapse():
    text = BOARD_RESOLUTION + "\n\n" + BOARD_RESOLUTION.replace("CERTIFIED TRUE COPY", "EXTRACT")
    out = analyse(Doc(1, "resolutions", "t", None, None, [(1, BOARD_RESOLUTION), (2, text)]))
    assert out is not None and len(out["items"]) == 1


def test_columns_and_item_keys_agree():
    out = analyse(_doc(GUARANTEE, "minutes"))
    keys = {c["key"] for c in COLUMNS}
    assert all(c["type"] in {"text", "money", "date", "number", "list", "long"} for c in COLUMNS)
    for item in out["items"]:
        assert keys <= set(item) and {"page", "context", "confidence"} <= set(item)
        assert 0 <= item["confidence"] <= 1


def test_long_document_is_quick_and_odd_text_does_not_raise():
    filler = DIRECTORS_REPORT + "\n" + "The Company continued to invest in people, processes and technology during the year. " * 20
    pages = [(n, filler) for n in range(1, 150)] + [(150, FS_NOTE)]
    started = time.perf_counter()
    out = analyse(Doc(9, "annual_report", "Annual Report", "Beta Technologies Private Limited", None, pages))
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, elapsed
    assert out is not None and len(out["items"]) == 4
    for odd in ("₹" * 5000, "(" * 3000 + "loan", "investment " * 4000, "\n" * 2000 + "1,00,00,00,00,00,00,000 equity shares", "₹. crore lakh , , ,"):
        analyse(_doc(odd))


def test_a_directors_shareholding_is_not_an_investment():
    """The details of a director seeking re-appointment, as notices print them (H.G. Infra, 2022)."""
    text = (
        "Name of Director(s) Mr. Harendra Singh\nDIN 00402458\nDate of First Appointment on the Board January 21, 2003\n"
        "Shareholding in the Company as on March 31,\n2022\n100 Equity Shares of face value of `10 each\n"
        "Details of Remuneration last drawn (FY 2021-22) ` 26.00 millions\n"
        "Details of proposed remuneration ` 30.00 millions as approved by the shareholders at the 19th AGM held on September 06, 2021"
    )
    out = analyse(Doc(1, "notice", "AGM notice", None, None, [(1, text)]))
    assert out is None or all(i["instrument"] != "equity shares" for i in out["items"])
