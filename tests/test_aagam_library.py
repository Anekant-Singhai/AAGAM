import pytest
from helpers import ACME, USER, write_notice_pdf, write_pdf

from aagam import library, precedents
from aagam.db import open_db
from csdesk.documents import ingest as core_ingest
from csdesk.errors import Invalid


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


@pytest.fixture
def notice(db, settings, tmp_path):
    return library.add_document(db, settings, write_notice_pdf(tmp_path / "Acme AGM notice 2026.pdf"), tags=["precedent"], queue_ai=False)


def test_a_notice_is_recognised_and_indexed(db, notice):
    doc = library.document(db, notice["document_id"])
    assert doc["doc_type"] == "notice"
    assert "Annual General Meeting" in doc["detected_why"]
    assert (doc["company_name"], doc["company_cin"], doc["meeting_kind"], doc["meeting_date"]) == (
        "Acme Widgets Limited", "L74999MH2015PLC123456", "agm", "2026-09-30")
    assert doc["title"] == "NOTICE OF 10TH ANNUAL GENERAL MEETING"
    tags = {t["name"]: t["added_by"] for t in doc["tags"]}
    assert tags["precedent"] == "her"
    assert {"notice", "agm", "s.185", "s.186", "special-resolution", "loans-investments", "loans-to-directors"} <= set(tags)
    assert [(r["item_no"], r["resolution_kind"]) for r in doc["resolutions"]] == [(1, "ordinary"), (2, "ordinary"), (3, "special"), (4, "special")]
    din = doc["facts"]["din"][0]
    assert (din["value"], din["detail"], din["pages"]) == ("01234567", "Asha Rao", [2])


def test_search_finds_pages_and_marks_the_words(db, notice):
    found = library.search(db, '"principal business activities"')
    assert found["matching_documents"] == 1
    hit = found["documents"][0]
    assert hit["pages"] == [2, 4]
    assert "[[principal business activities]]" in hit["passages"][0]["text"]
    assert library.search(db, "guarant")["documents"]  # prefix match: guarantee, guarantees
    assert library.search(db, "loans", tag="precedent")["documents"]
    assert not library.search(db, "loans", tag="client-file")["documents"]
    inside = library.search_in_document(db, notice["document_id"], "proxy")
    assert [p["page"] for p in inside["pages"]] == [3]
    with pytest.raises(Invalid):
        library.search(db, "  ")


def test_pages_brought_in_by_the_core_are_searchable_too(db, settings, tmp_path):
    info = core_ingest(db, settings, write_pdf(tmp_path / "letter.pdf", ["Sanction of term loan facility by State Bank"]))
    assert library.search(db, "sanction")["documents"][0]["document_id"] == info["document_id"]


def test_precedent_library(db, notice):
    s186 = precedents.search(db, section="186", resolution_kind="special")["resolutions"]
    assert len(s186) == 1 and s186[0]["max_amount"] == 1_000_000_000 and s186[0]["company_name"] == "Acme Widgets Limited"
    assert precedents.search(db, section="s.185")["resolutions"][0]["title"].startswith("Approval for giving loans")
    assert len(precedents.search(db, min_amount=500_000_000)["resolutions"]) == 1
    assert precedents.search(db, query="working capital", with_statement=True)["resolutions"][0]["item_no"] == 3
    assert precedents.search(db, topic="loans-to-directors")["count"] == 1
    full = precedents.get(db, s186[0]["id"])
    assert full["body"].startswith("RESOLVED THAT") and "section 186(2)" in full["statement"]
    assert {"topic": "loans-investments", "resolutions": 1} in precedents.topics(db)


def test_tags_and_suggestions(db, notice):
    document_id = notice["document_id"]
    library.suggest_tags(db, document_id, ["working capital", "notice", "group loans"])
    assert library.document(db, document_id)["suggested_tags"] == ["working capital", "group loans"]  # "notice" is already a tag
    library.add_tag(db, document_id, "Working  Capital")
    doc = library.document(db, document_id)
    assert doc["suggested_tags"] == ["group loans"]
    assert {"name": "working capital", "added_by": "her"} in doc["tags"]
    library.remove_tag(db, document_id, "precedent")
    assert "precedent" not in {t["name"] for t in library.document(db, document_id)["tags"]}
    with pytest.raises(Invalid):
        library.add_tag(db, document_id, " ")


def test_her_summary_is_never_replaced_by_ai(db, notice):
    document_id = notice["document_id"]
    library.save_summary(db, document_id, "AI summary", "local:qwen3:4b")
    library.save_summary(db, document_id, "Claude's summary", "claude")
    library.save_summary(db, document_id, "Her own summary", "her", ["Rs. 100 crore under s.186"])
    with pytest.raises(Invalid, match="herself"):
        library.save_summary(db, document_id, "Another AI summary", "claude")
    doc = library.document(db, document_id)
    assert (doc["summary"], doc["summary_by"], doc["key_points"]) == ("Her own summary", "her", ["Rs. 100 crore under s.186"])


def test_reindex_keeps_her_tags_and_type(db, notice):
    document_id = notice["document_id"]
    db.conn.execute("UPDATE documents SET doc_type = 'annual_report' WHERE id = ?", (document_id,))
    assert library.reindex_all(db) == 1
    doc = library.document(db, document_id)
    assert doc["doc_type"] == "annual_report" and "precedent" in {t["name"] for t in doc["tags"]}
    assert len(doc["resolutions"]) == 4  # annual reports carry the notice, so they are split too


def test_documents_of_a_client(db, settings, tmp_path):
    company_id = db.save("company", ACME, USER)
    library.add_document(db, settings, write_pdf(tmp_path / "ctc.pdf", ["CERTIFIED TRUE COPY OF THE RESOLUTION passed by the Board"]),
                         company_id=company_id, queue_ai=False)
    listed = library.list_documents(db, company_id=company_id)
    assert listed["total"] == 1 and listed["documents"][0]["doc_type"] == "board_resolution"
    assert listed["documents"][0]["client"] == ACME["name"]
    assert library.stats(db)["documents"] == 1
