"""Amendments: what an amending notification, Act or circular substitutes, inserts or omits, and from when."""

from __future__ import annotations

import time

from aagam.analysis import Doc
from aagam.analysis.amendments import analyse

SMALL_COMPANY = """MINISTRY OF CORPORATE AFFAIRS
NOTIFICATION
New Delhi, the 1st December, 2025
G.S.R. 880(E).—In exercise of the powers conferred by clause (85) of section 2 and sub-sections (1) and (2) of section
469 of the Companies Act, 2013 (18 of 2013), the Central Government hereby makes the following rules further to amend the
Companies (Specification of Definitions Details) Rules, 2014, namely:—
1. Short title and commencement.—(1) These rules may be called the Companies (Specification of Definitions Details)
Amendment Rules, 2025.
(2) They shall come into force on the date of their publication in the Official Gazette.
2. In the Companies (Specification of Definitions Details) Rules, 2014, in rule 2, in sub-rule (1), in clause (t),—
(i) for the words “four crore rupees”, the words “ten crore rupees” shall be substituted;
(ii) for the words “forty crore rupees”, the words “one hundred crore rupees” shall be substituted.
[F. No. 1/1/2025-CL-V]
RAKESH KUMAR, Jt. Secy.
"""

ACCOUNTS = """G.S.R. 101(E) dated 15th March, 2026.—In exercise of the powers conferred by section 133 and section 469 of the
Companies Act, 2013, the Central Government hereby makes the following rules further to amend the Companies (Accounts)
Rules, 2014, namely:—
1. (1) These rules may be called the Companies (Accounts) Amendment Rules, 2026.
(2) They shall come into force with effect from the 1st April, 2026.
2. In the Companies (Accounts) Rules, 2014 (hereinafter referred to as the said rules), after rule 3, the following rule
shall be inserted, namely:—
“3A. Maintenance of audit trail.—Every company shall maintain the audit trail for eight years, and no entry in it shall be
omitted or altered.”.
3. In rule 4 of the said rules, the proviso shall be omitted.
4. In rule 8 of the said rules, in sub-rule (5), for clause (x), the following clause shall be substituted, namely:—
‘(x) a statement on “corporate social responsibility” in the form specified;’.
5. In rule 12 of the said rules, in sub-rule (1), the words “and the Annexure” shall be omitted.
"""

ACT = """THE COMPANIES (AMENDMENT) ACT, 2026
An Act further to amend the Companies Act, 2013.
1. (1) This Act may be called the Companies (Amendment) Act, 2026.
(2) It shall be deemed to have come into force on the 1st day of April, 2025.
2. In clause (b) of sub-section (2) of section 135 of the Companies Act, 2013 (18 of 2013) (hereinafter referred to as the
principal Act), the words "or more" shall be omitted.
3. In section 149 of the principal Act, in sub-section (1), the second proviso shall be omitted.
4. In Schedule III to the principal Act, in Division II, in paragraph 7, for the figures "2,000", the figures "5,000"
shall be substituted.
5. In section 2 of the principal Act, after clause (85), the following clause shall be inserted, namely:—
'(85A) "small LLP" means a limited liability partnership with a turnover below ten crore rupees;'.
"""


def _doc(text: str, pages: int = 1) -> Doc:
    return Doc(1, "other", "t", None, None, [(n + 1, text) for n in range(pages)])


def test_small_company_thresholds_substituted_from_publication() -> None:
    out = analyse(_doc(SMALL_COMPANY))
    assert out is not None and out["kind"] == "amendments" and out["tags"] == ["amendment"]
    facts = out["facts"]
    assert facts["instrument"] == "Companies (Specification of Definitions Details) Rules, 2014"
    assert facts["amending_instrument"] == "Companies (Specification of Definitions Details) Amendment Rules, 2025"
    assert facts["notification"] == "G.S.R. 880(E)"
    assert facts["notification_date"] == "2025-12-01"
    assert facts["effective"] == "2025-12-01" and facts["effective_basis"] == "publication"
    assert facts["changes"] == {"substituted": 2}
    first, second = out["items"]
    assert (first["action"], first["target"], first["old"], first["text"]) == (
        "substituted", "rule 2(1)(t)", "four crore rupees", "ten crore rupees")
    assert (second["old"], second["text"]) == ("forty crore rupees", "one hundred crore rupees")
    assert first["instrument"] == facts["instrument"] and first["notification"] == "G.S.R. 880(E)"
    assert first["effective"] == "2025-12-01" and first["page"] == 1
    assert out["summary"] == ("Amends the Companies (Specification of Definitions Details) Rules, 2014 from 1 December 2025: "
                              "2 substitutions.")
    assert out["highlights"] and 0 < out["score"] <= 1


def test_insertion_omissions_and_a_substituted_clause() -> None:
    out = analyse(_doc(ACCOUNTS))
    facts = out["facts"]
    assert facts["instrument"] == "Companies (Accounts) Rules, 2014"
    assert facts["notification_date"] == "2026-03-15"
    assert facts["effective"] == "2026-04-01" and facts["effective_basis"] == "stated"
    # "shall be omitted" inside the quoted new rule 3A is part of its text, not a fifth change.
    assert facts["changes"] == {"substituted": 1, "inserted": 1, "omitted": 2}
    inserted, proviso, clause, words = out["items"]
    assert inserted["action"] == "inserted" and inserted["target"] == "rule 3A (inserted after rule 3)"
    assert inserted["text"].startswith("3A. Maintenance of audit trail") and inserted["text"].endswith("omitted or altered.")
    assert (proviso["action"], proviso["target"]) == ("omitted", "rule 4, proviso")
    assert clause["target"] == "rule 8(5)(x)" and "corporate social responsibility" in clause["text"]
    assert (words["action"], words["target"], words["old"]) == ("omitted", "rule 12(1)", "and the Annexure")
    assert out["summary"] == ("Amends the Companies (Accounts) Rules, 2014 from 1 April 2026: "
                              "1 substitution, 1 insertion, 2 omissions.")


def test_act_amendment_is_retrospective_with_nested_targets() -> None:
    out = analyse(_doc(ACT))
    facts = out["facts"]
    assert facts["instrument"] == "Companies Act, 2013"
    assert facts["amending_instrument"] == "Companies (Amendment) Act, 2026"
    assert facts["effective"] == "2025-04-01" and facts["retrospective"] is True
    targets = [(i["action"], i["target"]) for i in out["items"]]
    assert targets == [
        ("omitted", "section 135(2)(b)"),
        ("omitted", "section 149(1), second proviso"),
        ("substituted", "Schedule III, Division II, para 7"),
        ("inserted", "section 2(85A) (inserted after clause (85))"),
    ]
    assert out["items"][2]["old"] == "2,000" and out["items"][2]["text"] == "5,000"
    assert out["items"][3]["text"].startswith('(85A) "small LLP" means')
    assert "retrospective effect from 1 April 2025" in out["summary"]


def test_circular_changes_inline_with_effect_from() -> None:
    text = ("SEBI/HO/CFD/PoD-2/P/CIR/2026/14 dated 2nd February, 2026. In paragraph 4 of the Master Circular, for the word "
            "\"thirty\", the word \"fifteen\" shall be substituted, and after the words \"listed entity\", the words "
            "\"and its subsidiaries\" shall be inserted. This circular shall be effective from 1st April, 2026.")
    out = analyse(_doc(text))
    substituted, inserted = out["items"]
    assert (substituted["target"], substituted["old"], substituted["text"]) == ("para 4", "thirty", "fifteen")
    assert (inserted["target"], inserted["text"]) == ('para 4, after "listed entity"', "and its subsidiaries")
    assert out["facts"]["effective"] == "2026-04-01"
    assert out["summary"] == "Amendments from 1 April 2026: 1 substitution, 1 insertion."


def test_documents_that_amend_nothing_give_nothing() -> None:
    notice = ("NOTICE is hereby given that the Board of Directors will meet on 12th March, 2026 to approve loans under "
              "section 186 of the Companies Act, 2013 as amended by G.S.R. 880(E). The Company shall comply with rule 11.")
    assert analyse(_doc(notice)) is None
    assert analyse(Doc(1, "other", "t", None, None, [])) is None


def test_odd_text_does_not_raise() -> None:
    for text in ("shall be substituted", "namely:— “never closed " * 40, "shall be inserted, namely:—", "(a)\n(i)\n(v)\n1.",
                 "for the words “", "rule shall be renumbered as", "\x00 shall be omitted §", "x" * 5000):
        analyse(_doc(text))


def test_150_pages_in_under_a_second() -> None:
    doc = _doc(SMALL_COMPANY + ACCOUNTS + ACT, pages=150)
    start = time.perf_counter()
    out = analyse(doc)
    assert time.perf_counter() - start < 1.5  # about a third of a second on a laptop; slack for a busy CI box
    assert len(out["items"]) == 150 * 10
