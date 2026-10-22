"""Her corrections and deletions: they take effect, and re-reading a document doesn't undo them."""

import pytest
from fastapi.testclient import TestClient
from helpers import ACME, NOTICE_PAGES, USER, write_financials_pdf, write_notice_pdf, write_pdf

from aagam import editing, entities, finance, library, precedents, workbook
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.web.app import create_app
from csdesk.errors import Invalid

CHANGE = {"X-AAGAM": "1"}


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


@pytest.fixture
def notice(db, settings, tmp_path):
    return library.add_document(db, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)["document_id"]


def reread(db, settings, document_id):
    library.index_document(db, document_id, keep_type=True, home=settings.home)


def test_deleting_a_document_keeps_the_file_in_the_bin_and_her_notes(db, settings, notice):
    stored = db.conn.execute("SELECT stored_path FROM documents WHERE id = ?", (notice,)).fetchone()[0]
    company_id = db.save("company", ACME, USER)
    db.save("company", {"paid_up_capital": 100_000_000}, editing_source(notice), company_id)
    workbook.add_note(db, "Use item 4 as the s.186 precedent", "document", str(notice))
    assert library.search(db, '"working capital"')["matching_documents"] == 1

    result = editing.delete_document(db, settings.home, notice)
    assert result["notes_kept"] == 1 and result["sources_unlinked"] == 1
    assert (settings.home / result["file_kept_in"]).is_file() and not (settings.home / stored).exists()
    assert db.conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] == 0
    assert library.search(db, '"working capital"')["matching_documents"] == 0  # the search index is clean too
    note = workbook.search_notes(db)[0]
    assert note["target_kind"] == "general" and note["text"].startswith("On the deleted document")
    source = db.latest_sources("company", company_id)["paid_up_capital"]
    assert source["document_id"] is None and "source document deleted" in source["note"]


def editing_source(document_id):
    from csdesk.vault import Source

    return Source("document", "test", document_id=document_id, page=2, quote="paid-up capital of ₹10 crore")


def test_her_page_text_and_document_details_survive_re_reading(db, settings, notice):
    page = library.page_text(db, notice, 2)["text"]
    editing.edit_page(db, settings.home, notice, 2, page.replace("01234567", "07654321"))
    reread(db, settings, notice)
    assert "07654321" in library.page_text(db, notice, 2)["text"]
    assert any(f["value"] == "07654321" for f in library.facts(db, notice)["din"])
    assert library.document(db, notice)["edited_pages"] == [2]

    editing.set_document_details(db, notice, {"company_name": "Acme Widgets Ltd (corrected)", "meeting_date": "2026-09-26"})
    reread(db, settings, notice)
    doc = library.document(db, notice)
    assert doc["company_name"] == "Acme Widgets Ltd (corrected)" and doc["meeting_date"] == "2026-09-26"
    assert {r["company_name"] for r in precedents.search(db)["resolutions"]} == {"Acme Widgets Ltd (corrected)"}
    with pytest.raises(Invalid):
        editing.set_document_details(db, notice, {"meeting_date": "26 September"})


def test_resolutions_she_edits_or_deletes_stay_that_way(db, settings, notice):
    first, second, *_ = library.document(db, notice)["resolutions"]
    edited = editing.edit_clause(db, first["id"], {"title": "Adoption of accounts (her wording)", "sections": ["s.129"], "resolution_kind": "ordinary"})
    assert edited["title"] == "Adoption of accounts (her wording)" and edited["sections"] == ["129"]
    editing.delete_clause(db, second["id"])
    reread(db, settings, notice)
    titles = [r["title"] for r in library.document(db, notice)["resolutions"]]
    assert titles[0] == "Adoption of accounts (her wording)" and second["title"] not in titles
    assert precedents.search(db, "her wording")["resolutions"]  # the search index follows her edit


def test_facts_hidden_here_or_everywhere_and_names_she_chose(db, settings, notice, tmp_path):
    other = library.add_document(db, settings, write_pdf(tmp_path / "copy.pdf", [*NOTICE_PAGES, "A copy for the file."]), queue_ai=False)["document_id"]
    editing.hide_fact(db, "din", "01234567", notice)
    reread(db, settings, notice)
    assert "din" not in library.facts(db, notice) or all(f["value"] != "01234567" for f in library.facts(db, notice)["din"])
    assert any(f["value"] == "01234567" for f in library.facts(db, other)["din"])  # only hidden in the one document

    hidden = editing.hide_fact(db, "person", "Asha Rao")
    reread(db, settings, other)
    assert all(e["key"] != "asha rao" for e in entities.browse(db, "person")["entities"])
    editing.unhide(db, hidden["id"], settings.home)
    assert any(e["key"] == "asha rao" for e in entities.browse(db, "person")["entities"])

    editing.rename_entity(db, "person", "asha rao", "Asha R. Rao")
    assert entities.dossier(db, "person", "asha rao")["name"] == "Asha R. Rao"


def test_tags_renamed_deleted_or_taken_off_stay_that_way(db, settings, notice):
    tags = lambda: {t["name"] for t in library.document(db, notice)["tags"]}  # noqa: E731
    assert {"notice", "agm", "special-resolution"} <= tags()
    editing.rename_tag(db, "agm", "annual meeting")
    editing.delete_tag(db, "special-resolution")
    library.remove_tag(db, notice, "notice")
    reread(db, settings, notice)
    assert "annual meeting" in tags() and "agm" not in tags() and "special-resolution" not in tags() and "notice" not in tags()
    library.add_tag(db, notice, "special-resolution")  # she adds it back by hand: that wins
    reread(db, settings, notice)
    assert "special-resolution" in tags()


def test_statements_she_corrects_or_deletes(db, settings, tmp_path):
    document_id = library.add_document(db, settings, write_financials_pdf(tmp_path / "accounts.pdf"), queue_ai=False)["document_id"]
    library.index_new(db, settings, document_id, queue_ai=False)
    fid = finance.listing(db)[0]["id"]
    before = finance.get(db, fid)["items"]["revenue"]["current"]
    out = finance.edit_header(db, fid, {"unit": "crore", "period_end": "2026-03-31", "company_name": "Acme (her name)"})
    assert out["statement"]["unit_factor"] == 10_000_000 and out["statement"]["company_name"] == "Acme (her name)"
    assert finance.get(db, fid)["items"]["revenue"]["current"] == before * 100  # lakhs → crore
    finance.extract(db, document_id, settings.home)
    again = finance.get(db, fid)
    assert again["unit_factor"] == 10_000_000 and again["items"]["revenue"]["current"] == before * 100

    finance.delete(db, fid)
    finance.extract(db, document_id, settings.home)
    assert finance.listing(db) == []  # deleted statements aren't read again


def test_deleting_records_in_the_company_file(db, settings, notice):
    company_id = db.save("company", ACME, USER)
    person = db.save("party", {"kind": "individual", "name": "Asha Rao", "din": "01234567"}, USER)
    meeting = db.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26"}, USER)
    db.save("appointment", {"company_id": company_id, "party_id": person, "role": "director", "meeting_id": meeting}, USER)
    db.conn.execute("UPDATE documents SET company_id = ? WHERE id = ?", (company_id, notice))
    work = workbook.create_work(db, "AGM 2026", "agm", company_id)

    assert db.dependents("meeting", meeting)["unlinks"] == {"appointments.meeting_id": 1}
    db.delete("meeting", meeting)
    assert db.conn.execute("SELECT meeting_id FROM appointments").fetchone()[0] is None

    preview = db.dependents("company", company_id)
    assert preview["deletes"] == {"appointment": 1} and preview["unlinks"] == {"documents.company_id": 1, "works.company_id": 1}
    db.delete("company", company_id)
    assert db.conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0
    assert db.conn.execute("SELECT company_id FROM documents WHERE id = ?", (notice,)).fetchone()[0] is None
    assert workbook.work(db, work["id"])["company_id"] is None
    assert db.party(person)["name"] == "Asha Rao"  # people are kept; only their position went

    workbook.delete_work(db, work["id"])
    assert workbook.list_works(db) == []


def test_the_company_file_through_the_window(settings):
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        schema = client.get("/api/records/schema").json()["entities"]
        assert {"company", "party", "appointment", "meeting"} <= set(schema)
        assert next(f for f in schema["party"] if f["name"] == "pan")["sensitive"] is True
        assert next(f for f in schema["company"] if f["name"] == "company_class")["enum"] == ["private", "public", "opc"]

        made = client.post("/api/records/company", json={"data": ACME}, headers=CHANGE)
        assert made.status_code == 200, made.text
        company_id = made.json()["id"]
        changed = client.patch(f"/api/records/company/{company_id}", json={"data": {"paid_up_capital": 50_000_000, "roc": "RoC-Mumbai"}}, headers=CHANGE)
        assert changed.json()["paid_up_capital"] == 50_000_000 and changed.json()["sources"]["roc"]["source_kind"] == "user"
        bad = client.patch(f"/api/records/company/{company_id}", json={"data": {"cin": "nonsense"}}, headers=CHANGE)
        assert bad.status_code == 400

        person = client.post("/api/records/party", json={"data": {"kind": "individual", "name": "Asha Rao", "pan": "ABCPE1234F"}}, headers=CHANGE).json()
        assert person["pan"] == "XXXXXX234F"
        # Sending the masked value back (an unchanged form) leaves the real PAN alone.
        client.patch(f"/api/records/party/{person['id']}", json={"data": {"pan": "XXXXXX234F", "email": "asha@example.com"}}, headers=CHANGE)
        client.post("/api/records/appointment", json={"data": {"company_id": company_id, "party_id": person["id"], "role": "director"}}, headers=CHANGE)
        file = client.get(f"/api/companies/{company_id}/file").json()
        assert file["people"][0]["name"] == "Asha Rao" and file["people"][0]["pan"] == "XXXXXX234F"

        assert client.delete(f"/api/records/company/{company_id}").status_code == 403  # changes need the AAGAM header
        gone = client.delete(f"/api/records/company/{company_id}", headers=CHANGE).json()
        assert gone["deletes"] == {"appointment": 1}
        assert client.get(f"/api/records/company/{company_id}").status_code == 404
