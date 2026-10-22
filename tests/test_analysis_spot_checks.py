"""Papers written differently from the ones each analyser was built against: what a check of the whole found and fixed."""

from aagam.analysis import Doc, agreements, amendments, investments, legal, obligations
from aagam.classify import detect


def doc(text: str, doc_type: str = "other") -> Doc:
    return Doc(1, doc_type, "t", None, None, [(1, text)])


SEBI_AMENDMENT = """SECURITIES AND EXCHANGE BOARD OF INDIA
NOTIFICATION
Mumbai, the 12th December, 2024
No. SEBI/LAD-NRO/GN/2024/218.- In exercise of the powers conferred by section 11 of the Securities and Exchange Board of India Act, 1992, the Board hereby makes the following regulations to further amend the Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015, namely,-
1. These regulations may be called the Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) (Third Amendment) Regulations, 2024.
2. They shall come into force on the date of their publication in the Official Gazette.
3. In the Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015,-
I. in regulation 17, in sub-regulation (1), after clause (e), the following new clause shall be inserted, namely,-
"(f) the board of directors shall have at least one woman independent director."
II. in regulation 23, in sub-regulation (1), the proviso shall be omitted.
III. in regulation 24A, in sub-regulation (1), for the words "within sixty days", the words "within forty-five days" shall be substituted.
"""


def test_an_amendment_numbered_in_roman_keeps_every_change():
    out = amendments.analyse(doc(SEBI_AMENDMENT))
    assert [i["action"] for i in out["items"]] == ["inserted", "omitted", "substituted"]
    substituted = out["items"][2]
    assert substituted["target"] == "regulation 24A(1)"
    assert (substituted["old"], substituted["text"]) == ("within sixty days", "within forty-five days")
    # The time limits it quotes are the law's new words, not anyone's duty.
    assert obligations.analyse(doc(SEBI_AMENDMENT)) is None


CONTINGENT = """Note 32: Contingent liabilities and commitments
(b) The Company has received a demand of Rs. 1,85,60,000 under section 143(3) of the Income-tax Act, 1961 for Assessment Year 2021-22. The Company has filed an appeal before the Commissioner of Income Tax (Appeals), which is pending.
(c) The Directorate General of GST Intelligence issued a show cause notice dated 14th June, 2024 demanding Rs. 3.2 crore under section 74 of the CGST Act, 2017. The Company has filed its reply and the matter is pending adjudication.
"""


def test_a_matter_told_over_two_sentences_is_one_matter():
    out = legal.analyse(doc(CONTINGENT, "financial_statements"))
    tax, gst = out["items"]
    assert (tax["forum"], tax["amount"], tax["status"]) == ("CIT(A)", 18_560_000, "pending")
    assert "143(3) IT Act" in tax["sections"]
    assert (gst["amount"], gst["status"]) == (32_000_000, "pending")
    assert "₹5.06 crore at stake" in out["summary"]


SSA = """SHARE SUBSCRIPTION AGREEMENT
This Share Subscription Agreement is made at Pune on this 5th day of January, 2026 by and between Acme Widgets Private Limited, a company incorporated under the Companies Act, 2013 having its registered office at Pune (hereinafter referred to as the "Company") of the First Part; AND Bluewater Ventures Fund I, a SEBI registered alternative investment fund (hereinafter referred to as the "Investor") of the Second Part.
1. The Investor shall subscribe to 2,50,000 equity shares of Rs. 10 each at a premium of Rs. 390 per share aggregating to Rs. 10 crore.
2. The Company shall allot the shares within 30 days of receipt of the subscription amount.
3. Any dispute shall be referred to arbitration by a sole arbitrator under the Arbitration and Conciliation Act, 1996, seated in Mumbai.
"""


def test_a_share_subscription_agreement_read_from_the_issuers_side():
    assert investments.analyse(doc(SSA)) is None  # the investor subscribes; the company issues, it doesn't invest
    assert legal.analyse(doc(SSA)) is None or not legal.analyse(doc(SSA))["items"]  # a dispute clause is no proceeding
    parties = next(i["value"] for i in agreements.analyse(doc(SSA))["items"] if i["term"] == "Parties")
    assert parties == "Acme Widgets Private Limited (Company); Bluewater Ventures Fund I (Investor)"


S185 = (
    "“RESOLVED THAT pursuant to the provisions of Section 185 of the Companies Act, 2013, consent of the members of the Company, be and is "
    "hereby accorded to the Board of Directors of the Company to advance any loan including any loan represented by a book debt or give any "
    "guarantee or provide any security in connection with any loan taken to/by (i) Sri Chakra Cement Limited, (ii) Sri Subramanya Solar Power "
    "Projects LLP and (iii) Envean Leasing and Investments Limited, in which any director of the Company is deemed to be interested, for an "
    "amount not exceeding Rs.20,00,00,000/- (Rupees Twenty Crores only), in a financial year, to be utilized for the principal business "
    "activities by the borrowing companies.” “RESOLVED FURTHER THAT Sri Vijay Kumar Kapilavai, Managing Director, be and is hereby "
    "authorized to finalize the terms of the aforesaid loan, guarantee or security.”\n"
    "The Board of Directors at their meeting held on 26th May, 2023 approved to give loans, give guarantee and provide security not exceeding "
    "Rs.20,00,00,000/- (Rupees Twenty Crores only) in a financial year to (i) Sri Chakra Cement Limited, (ii) Sri Subramanya Solar Power "
    "Projects LLP and (iii) Envean Leasing and Investments Limited, subject to approval of the members of the Company."
)


def test_a_section_185_approval_is_one_limit_shared_by_its_parties():
    """As Aditya Spinners' 2023 notice words it: one ₹20 crore approval for three related parties, told twice."""
    out = investments.analyse(doc(S185, "notice"))
    (item,) = out["items"]
    assert item["investee"] == "Sri Chakra Cement Limited; Sri Subramanya Solar Power Projects LLP; Envean Leasing and Investments Limited"
    assert (item["amount"], item["section"], item["nature"]) == (200_000_000, "185", "limit")
    assert out["summary"] == "S.185 approval up to ₹20 crore for 3 parties in which a director is interested."


def test_the_company_secretary_is_not_the_company():
    text = "The Board noted that the Company Secretary shall file Form MGT-14 within thirty days of the passing of the resolution."
    assert obligations.analyse(doc(text))["items"][0]["who"] == "the Company Secretary"


def test_the_doer_heads_the_clause():
    """As Aditya Spinners' notice words it: the Company is only what the information is about."""
    text = ("Members desirous of obtaining any information concerning the accounts and operations of the Company are requested "
            "to address their queries to the Company Secretary at least 7 (Seven) days before the date of the Meeting.")
    assert obligations.analyse(doc(text, "notice"))["items"][0]["who"] == "the Members"
    text = "The Scrutinizer appointed by the Board shall submit the report within 2 working days of the conclusion of the meeting."
    assert obligations.analyse(doc(text, "notice"))["items"][0]["who"] == "the Scrutinizer"


def test_a_superscript_ordinal_read_as_a_symbol():
    """Godha's notice: the PDF gives "8™" and "8®" for 8th."""
    assert detect([(1, "NOTICE OF 8™ ANNUAL GENERAL MEETING\nNotice is hereby given")]).title == "NOTICE OF 8th ANNUAL GENERAL MEETING"
    assert detect([(1, "Notice of the 21®Annual General Meeting of the Members")]).title == "Notice of the 21st Annual General Meeting of the Members"
