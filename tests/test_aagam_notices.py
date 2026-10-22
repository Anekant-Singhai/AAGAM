import os
from pathlib import Path

import pytest
from helpers import NOTICE_PAGES

from aagam.notices import split_notice
from aagam.text import reflow, strip_running_lines
from csdesk.documents.intake import extract_pages


def pages():
    return list(enumerate(NOTICE_PAGES, start=1))


def test_items_are_found_and_special_business_renumbered():
    notice = split_notice(pages())
    assert notice.meeting_kind == "agm"
    assert [(i.number, i.business, i.resolution_kind) for i in notice.items] == [
        (1, "ordinary", "ordinary"),
        (2, "ordinary", "ordinary"),
        (3, "special", "special"),
        (4, "special", "special"),
    ]  # the numbered notes after the signature are not business


def test_resolution_text_title_sections_and_amount():
    items = split_notice(pages()).items
    loans = items[3]
    assert loans.title == "Approval for making investments, giving loans, guarantees and security under Section 186"
    assert loans.body.startswith("RESOLVED THAT pursuant to Section 186(3)")
    assert "RESOLVED FURTHER THAT the Board" in loans.body  # carried over the page break
    assert "Notice of AGM" not in loans.body  # the running header is gone
    assert loans.sections == ["186", "186(3)", "186(2)"]
    assert loans.topics == ["loans-investments"]
    assert loans.max_amount == 1_000_000_000
    assert (loans.page_from, loans.page_to) == (2, 3)
    assert items[2].sections == ["185"] and items[2].max_amount == 250_000_000


def test_statements_numbered_from_1_are_matched_to_the_special_business():
    items = split_notice(pages()).items
    assert items[0].statement is None and items[1].statement is None
    assert items[2].statement.startswith("Section 185 allows loans")
    assert "exceed the limit under section 186(2)" in items[3].statement


def test_running_headers_are_removed():
    cleaned = strip_running_lines(pages())
    assert all("Notice of AGM" not in text for _, text in cleaned[1:])


def test_reflow_joins_wrapped_lines_and_keeps_resolved_paragraphs():
    text = "RESOLVED THAT the Board\nbe authorised to borrow.\nRESOLVED FURTHER THAT the\nSecretary may file forms."
    assert reflow(text) == "RESOLVED THAT the Board be authorised to borrow.\n\nRESOLVED FURTHER THAT the Secretary may file forms."


REAL = Path(os.environ.get("AAGAM_REAL_NOTICES", "")) if os.environ.get("AAGAM_REAL_NOTICES") else None


@pytest.mark.skipif(REAL is None, reason="set AAGAM_REAL_NOTICES to a folder of real notices to run")
@pytest.mark.parametrize(
    "name, expected",
    [
        ("godha-2024.pdf", [("185", None), ("186", 1_000_000_000)]),
        ("hginfra-2022.pdf", [("186", 60_000_000_000), ("185", 500_000_000)]),
        ("bse-6ef67ccd.pdf", [("185", 200_000_000), ("186", 500_000_000), ("188", None)]),
    ],
)
def test_real_listed_company_notices(name, expected):
    notice = split_notice([(p.page_no, p.text) for p in extract_pages(REAL / name)])
    special = [(i.sections[0], i.max_amount) for i in notice.items if i.sections and i.sections[0] in ("185", "186", "188")]
    assert special == expected
    assert all(i.statement for i in notice.items if i.business == "special")
