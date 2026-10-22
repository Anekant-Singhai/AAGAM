"""Law research: the Acts, provisions, notifications, circulars, standards and cases a document relies on."""

from __future__ import annotations

import time

from aagam.analysis import Doc
from aagam.analysis.law import analyse

NOTICE = """NOTICE is hereby given that an Extra-ordinary General Meeting of the Members of Sunrise Agro Industries Limited
(CIN L01111MH2001PLC123456) will be held on Tuesday, 20th January, 2026 at 11.00 a.m. through video conferencing.
SPECIAL BUSINESS
1. To approve loans, guarantees and investments under Sections 185, 186 and 188 of the Companies Act, 2013.
RESOLVED THAT pursuant to the provisions of Section 186(3) of the Companies Act, 2013 read with Rule 11 of the Companies
(Meetings of Board and its Powers) Rules, 2014 and other applicable provisions, if any, consent of the Members be and is
hereby accorded to the Board of Directors to give loans up to Rs. 50 crore.
In terms of Regulation 17(1A) of the Securities and Exchange Board of India (Listing Obligations and Disclosure
Requirements) Regulations, 2015, approval of the Members is sought for the continuation of the directorship.
The meeting is convened in accordance with MCA General Circular No. 09/2024 dated 19th September, 2024 and General
Circular No. 14/2020 dated 8th April, 2020 and the Secretarial Standard on General Meetings (SS-2) issued by the ICSI.
The transactions are material related party transactions and the approval of the Members under section 188 is required.
The Board recommends the resolution.
"""

OPINION = """LEGAL OPINION
In Vodafone International Holdings B.V. v. Union of India, (2012) 6 SCC 613, the Supreme Court held that a transfer of
shares between two non-resident companies was not taxable in India. Reliance is also placed on AIR 2020 SC 123 and on the
decision reported as [2023] 150 taxmann.com 45 (NCLAT). The principles were reiterated in (2019) 5 SCC 1.
The ratio of Vodafone International Holdings B.V. v. Union of India was followed by the Tribunal.
The scheme under section 230 of the Companies Act, 2013 must also be accounted for under Ind AS 103 and Ind AS 24.
Actual vs Budget figures are annexed.
"""


def _doc(text: str, pages: int = 1) -> Doc:
    return Doc(1, "other", "t", None, None, [(n + 1, text) for n in range(pages)])


def _by_reference(out: dict) -> dict[str, dict]:
    return {i["reference"]: i for i in out["items"]}


def test_notice_names_each_provision_with_its_act_once() -> None:
    out = analyse(_doc(NOTICE))
    assert out is not None and out["kind"] == "law" and out["tags"] == ["law"]
    refs = _by_reference(out)
    for reference in ("Companies Act, 2013 s.185", "Companies Act, 2013 s.186", "Companies Act, 2013 s.186(3)",
                      "Companies (Meetings of Board and its Powers) Rules, 2014 rule 11",
                      "SEBI (LODR) Regulations, 2015 reg. 17(1A)", "General Circular No. 09/2024", "SS-2"):
        assert reference in refs, reference
    # The bare "section 188" later on is the same provision, counted, not a second row.
    assert refs["Companies Act, 2013 s.188"]["count"] == 2
    assert not any(r.startswith("s.") for r in refs)
    assert refs["General Circular No. 09/2024"]["instrument"] == "Ministry of Corporate Affairs"
    assert refs["General Circular No. 09/2024"]["date"] == "2024-09-19"
    assert refs["SS-2"]["instrument"] == "Secretarial Standard on General Meetings"
    assert refs["SS-2"]["count"] == 1  # "Secretarial Standard on General Meetings (SS-2)" is one mention
    assert refs["Companies Act, 2013 s.186(3)"]["page"] == 1
    assert "Section 186(3)" in refs["Companies Act, 2013 s.186(3)"]["context"]
    assert "Companies Act, 2013 (ss.185, 186, 188)" in out["summary"]
    assert "reg. 17(1A)" in out["summary"] and "2 MCA circulars" in out["summary"]
    assert out["facts"]["by_type"]["section"] == 4
    assert out["facts"]["most_cited"][0] == {"reference": "Companies Act, 2013 s.188", "count": 2}
    assert out["highlights"] and 0 < out["score"] <= 1


def test_opinion_cites_cases_with_courts() -> None:
    out = analyse(_doc(OPINION))
    refs = _by_reference(out)
    vodafone = refs["Vodafone International Holdings B.V. v. Union of India, (2012) 6 SCC 613"]
    assert vodafone["type"] == "case" and vodafone["instrument"] == "Supreme Court" and vodafone["count"] == 2
    assert refs["AIR 2020 SC 123"]["instrument"] == "Supreme Court"
    assert refs["[2023] 150 taxmann.com 45 (NCLAT)"]["instrument"] == "NCLAT"
    assert refs["(2019) 5 SCC 1"]["type"] == "case"
    assert refs["Ind AS 103"]["type"] == "standard" and "Ind AS 24" in refs
    assert "Companies Act, 2013 s.230" in refs
    assert not any("Budget" in r for r in refs)  # "Actual vs Budget" is not a case
    assert out["facts"]["by_type"]["case"] == 4


def test_section_goes_with_the_act_named_in_its_sentence() -> None:
    text = ("The Company has spent on CSR under section 135 of the Companies Act, 2013. The donation also qualifies for "
            "deduction under section 80G as allowed by the Income-tax Act, 1961.")
    refs = _by_reference(analyse(_doc(text)))
    assert "Companies Act, 2013 s.135" in refs
    assert refs["Income-tax Act, 1961 s.80G"]["confidence"] == 0.85


def test_the_act_means_the_act_the_document_defines() -> None:
    text = ("This report is made under the Limited Liability Partnership Act, 2008 (the Act). The partners note "
            "that the statement of account must be filed under section 34 of the Act.")
    refs = _by_reference(analyse(_doc(text)))
    assert refs["Limited Liability Partnership Act, 2008 s.34"]["confidence"] == 0.9


def test_companies_act_is_assumed_only_for_company_law() -> None:
    board = ("The Board of Directors approved the borrowing under section 179(3). The return will be filed with the "
             "Registrar of Companies before the annual general meeting.")
    item = analyse(_doc(board))["items"][0]
    assert item["reference"] == "Companies Act, 2013 s.179(3)" and item["confidence"] == 0.6
    plain = "The landlord may terminate the lease under section 106 after giving fifteen days' notice."
    item = analyse(_doc(plain))["items"][0]
    assert item["reference"] == "s.106" and item["instrument"] == ""


def test_notifications_and_sebi_circulars() -> None:
    text = ("The thresholds were revised by notification G.S.R. 880(E) dated 1st December, 2025. Later, G.S.R. 880(E) was "
            "relied on again. SEBI circular SEBI/HO/CFD/CFD-PoD-2/P/CIR/2023/123 dated 13th July, 2023 applies.")
    refs = _by_reference(analyse(_doc(text)))
    note = refs["G.S.R. 880(E) dated 1 December 2025"]
    assert note["type"] == "notification" and note["count"] == 2 and note["date"] == "2025-12-01"
    circular = refs["SEBI/HO/CFD/CFD-PoD-2/P/CIR/2023/123"]
    assert circular["instrument"] == "SEBI" and circular["date"] == "2023-07-13"


def test_capitals_and_ranges() -> None:
    text = "SCHEME OF ARRANGEMENT UNDER SECTIONS 230 TO 232 OF THE COMPANIES ACT, 2013"
    refs = _by_reference(analyse(_doc(text)))
    assert {"Companies Act, 2013 s.230", "Companies Act, 2013 s.231", "Companies Act, 2013 s.232"} <= set(refs)


def test_documents_without_law_give_nothing() -> None:
    assert analyse(_doc("Minutes of the meeting. The Board discussed the sales figures. Actual vs Budget was reviewed.")) is None
    assert analyse(Doc(1, "other", "t", None, None, [])) is None
    assert analyse(Doc(1, "other", "t", None, None, [(1, ""), (2, "   ")])) is None


def test_odd_text_does_not_raise() -> None:
    for text in ("Section", "Section (((( v. v. v.", "Rules, 2014 Act, 2013", "S. 1 s. 2 u/s", "[2023] taxmann.com",
                 "“unclosed quote " * 50, "A v. B", "G.S.R. (E)", "SS- Ind AS", "x" * 5000, "\x00﻿§ 12"):
        analyse(_doc(text))


def test_150_pages_in_under_a_second() -> None:
    doc = _doc(NOTICE + OPINION, pages=150)
    start = time.perf_counter()
    out = analyse(doc)
    assert time.perf_counter() - start < 1.5  # about half a second on a laptop; slack for a busy CI box
    assert _by_reference(out)["Companies Act, 2013 s.188"]["count"] == 300
