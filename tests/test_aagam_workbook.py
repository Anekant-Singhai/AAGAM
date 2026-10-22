import pytest
from helpers import ACME, NOTICE_PAGES, USER, write_notice_pdf, write_pdf

from aagam import everything, library, review, workbook
from aagam.db import open_db
from csdesk.errors import Invalid


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


def test_a_piece_of_work_with_its_checklist_documents_and_notes(db, settings, tmp_path):
    company_id = db.save("company", ACME, USER)
    agm = workbook.create_work(db, "AGM 2026, Acme Widgets", "agm", company_id, due_on="2026-09-30", meeting_date="2026-09-26")
    assert agm["kind_label"] == "Annual general meeting" and agm["progress"] == {"done": 0, "total": len(agm["checklist"])}
    assert any(step["basis"] == "s.101(1)" for step in agm["checklist"])
    doc = library.add_document(db, settings, write_notice_pdf(tmp_path / "notice.pdf"), company_id=company_id, queue_ai=False)
    workbook.attach(db, agm["id"], doc["document_id"])
    workbook.tick(db, agm["id"], 2, note="Sent by email on 3 September")
    workbook.add_note(db, "Members asked for the CSR spend to be explained", "work", str(agm["id"]), pinned=True)
    got = workbook.work(db, agm["id"])
    assert got["progress"]["done"] == 1 and got["checklist"][2]["note"] == "Sent by email on 3 September"
    assert got["documents"][0]["id"] == doc["document_id"] and got["notes"][0]["pinned"] == 1
    assert workbook.works_of_document(db, doc["document_id"])[0]["title"] == "AGM 2026, Acme Widgets"

    # She edits the list: a step of her own, one removed.
    steps = got["checklist"]
    steps.append({"text": "Book the hall at the Chamber of Commerce"})
    del steps[0]
    edited = workbook.set_checklist(db, agm["id"], steps)
    assert edited["checklist"][-1] == {"text": "Book the hall at the Chamber of Commerce", "basis": None, "done": False, "done_at": None, "note": None}

    done = workbook.change_work(db, agm["id"], status="done")
    assert done["closed_at"] is not None
    assert workbook.list_works(db, status="done")[0]["id"] == agm["id"]
    assert workbook.list_works(db, query="acme")[0]["company"] == ACME["name"]
    with pytest.raises(Invalid):
        workbook.create_work(db, "Something", "party")


def test_notes_are_searchable_everywhere(db, settings, tmp_path):
    doc = library.add_document(db, settings, write_pdf(tmp_path / "letter.pdf", ["Sanction of term loan by State Bank"]), queue_ai=False)
    workbook.add_note(db, "Bank wants the s.180(1)(c) resolution before disbursement", "document", str(doc["document_id"]))
    workbook.add_note(db, "Call Vikram about DIR-3 KYC", pinned=True)
    assert workbook.search_notes(db, "disbursement")[0]["target"] == str(doc["document_id"])
    assert workbook.search_notes(db)[0]["text"].startswith("Call Vikram")  # pinned first
    assert everything.search_all(db, "disbursement")["notes"]
    note = workbook.search_notes(db, "Vikram")[0]
    workbook.change_note(db, note["id"], text="Called Vikram: KYC done", pinned=False)
    assert workbook.note(db, note["id"])["text"] == "Called Vikram: KYC done"
    workbook.delete_note(db, note["id"])
    assert not workbook.search_notes(db, "Vikram")
    with pytest.raises(Invalid):
        workbook.add_note(db, "  ")


def test_the_notice_checker(db, settings, tmp_path):
    doc = library.add_document(db, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)
    result = review.check_notice(db, doc["document_id"])
    by_text = {f["text"]: f for f in result["findings"]}
    assert result["counts"]["missing"] >= 1
    assert any(f["status"] == "missing" and "proxies" in f["text"] for f in result["findings"]) is False  # the notice has one
    assert by_text["The CIN is printed."]["status"] == "ok"
    assert any(f["text"] == "Item 4 (s.186) states the amount: ₹100.00 crore." for f in result["findings"])
    interest = [f for f in result["findings"] if "concerned or interested" in f["text"]]
    assert {f["item"] for f in interest} == {3, 4}  # the statements don't say whether directors are interested
    assert any(f["status"] == "check" and "e-voting" in f["text"] for f in result["findings"])
    with pytest.raises(Invalid):
        review.check_notice(db, library.add_document(db, settings, write_pdf(tmp_path / "x.pdf", ["A letter"]), queue_ai=False)["document_id"])


def test_short_notice_is_caught(db, settings, tmp_path):
    pages = list(NOTICE_PAGES)
    pages[2] = pages[2].replace("Company Secretary M. No. A12345", "Company Secretary M. No. A12345\nDate: 15th September, 2026")
    doc = library.add_document(db, settings, write_pdf(tmp_path / "short.pdf", pages), queue_ai=False)
    result = review.check_notice(db, doc["document_id"])
    short = [f for f in result["findings"] if "clear days" in f["text"]][0]
    assert short["status"] == "missing" and "14 clear days" in short["text"]
