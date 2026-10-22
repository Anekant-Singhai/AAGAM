"""The Trash: a deleted document comes back as she left it, or goes for good."""

import pytest
from fastapi.testclient import TestClient
from helpers import ACME, USER, write_financials_pdf, write_notice_pdf, write_pdf

from aagam import editing, entities, finance, library, precedents, trash, workbook
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.web.app import create_app
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Source

CHANGE = {"X-AAGAM": "1"}


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


@pytest.fixture
def notice(db, settings, tmp_path):
    return library.add_document(db, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)["document_id"]


def letter(db, settings, tmp_path, name="letter.pdf"):
    path = write_pdf(tmp_path / name, ["Dear Sir, sanction of term loan facility by State Bank of India."])
    return library.add_document(db, settings, path, queue_ai=False)["document_id"]


def test_a_deleted_document_waits_in_the_trash(db, settings, notice):
    assert library.search(db, '"working capital"')["matching_documents"] == 1
    assert any(e["key"] == "01234567" for e in entities.browse(db, "din")["entities"])

    result = editing.delete_document(db, settings.home, notice)
    assert result["deleted"] == notice and result["trash_id"]
    assert (settings.home / result["file_kept_in"]).is_file()
    assert library.list_documents(db)["total"] == 0
    assert library.search(db, '"working capital"')["matching_documents"] == 0
    assert not any(e["key"] == "01234567" for e in entities.browse(db, "din")["entities"])
    assert precedents.search(db)["resolutions"] == []

    listed = trash.list_trash(db, settings.home)
    assert listed["count"] == 1 and listed["loose"] == []
    item = listed["items"][0]
    assert (item["id"], item["item_id"], item["kind"]) == (result["trash_id"], notice, "document")
    assert item["name"] == "NOTICE OF 10TH ANNUAL GENERAL MEETING" and "4 pages" in item["detail"]
    assert item["file_missing"] is False and item["size"] == listed["bytes"] > 0


def test_restoring_puts_back_everything_she_added(db, settings, notice):
    company_id = db.save("company", ACME, USER)
    db.conn.execute("UPDATE documents SET company_id = ? WHERE id = ?", (company_id, notice))
    db.save("company", {"paid_up_capital": 100_000_000}, Source("document", "test", document_id=notice, page=2, quote="₹10 crore"), company_id)
    page3 = library.page_text(db, notice, 3)["text"]
    editing.edit_page(db, settings.home, notice, 3, page3.replace("A12345", "A54321"))
    editing._set_meta(db, notice, "title", "Acme AGM 2026 (her title)")
    editing.set_document_details(db, notice, {"company_name": "Acme (her name)", "doc_date": "2026-09-01"})
    library.save_summary(db, notice, "Her summary of the notice.", "her")
    library.add_tag(db, notice, "group loans")
    library.remove_tag(db, notice, "notice")
    editing.hide_fact(db, "din", "01234567", notice)
    first, second, third, _ = library.document(db, notice)["resolutions"]
    editing.edit_clause(db, first["id"], {"title": "Adoption of accounts (her wording)"})
    editing.delete_clause(db, second["id"])
    work = workbook.create_work(db, "AGM 2026", "agm", company_id)
    workbook.attach(db, work["id"], notice)
    workbook.add_note(db, "Use item 4 as the s.186 precedent", "document", str(notice))
    workbook.add_note(db, "Check the s.185 wording", "resolution", str(third["id"]))
    folder_id = db.conn.execute("INSERT INTO folders (path) VALUES ('D:\\Clients')").lastrowid
    db.conn.execute("INSERT INTO folder_files (folder_id, rel_path, size, modified, status, document_id) VALUES (?, 'Acme/notice.pdf', 1, '2026-09-01T10:00:00', 'added', ?)",
                    (folder_id, notice))

    result = editing.delete_document(db, settings.home, notice)
    assert result["notes_kept"] == 1 and result["sources_unlinked"] == 1
    assert {n["target_kind"] for n in workbook.search_notes(db)} == {"general"}
    assert db.latest_sources("company", company_id)["paid_up_capital"]["document_id"] is None
    assert db.conn.execute("SELECT document_id FROM folder_files").fetchone()[0] is None

    restored = trash.restore(db, settings, result["trash_id"])
    assert restored == {"document_id": notice, "name": "Acme AGM 2026 (her title)"}  # its old number was free
    doc = library.document(db, notice)
    assert doc["client"] == ACME["name"] and doc["title"] == "Acme AGM 2026 (her title)"
    assert "A54321" in library.page_text(db, notice, 3)["text"] and doc["edited_pages"] == [3]
    assert (doc["summary"], doc["summary_by"]) == ("Her summary of the notice.", "her")
    assert (doc["company_name"], doc["doc_date"], doc["doc_date_basis"]) == ("Acme (her name)", "2026-09-01", "set by her")
    tags = {t["name"]: t["added_by"] for t in doc["tags"]}
    assert tags["group loans"] == "her" and "notice" not in tags and "agm" in tags  # automatic tags are read again
    titles = [r["title"] for r in doc["resolutions"]]
    assert titles[0] == "Adoption of accounts (her wording)" and second["title"] not in titles
    assert all(f["value"] != "01234567" for f in library.facts(db, notice).get("din", []))
    assert [w["id"] for w in workbook.works_of_document(db, notice)] == [work["id"]]
    assert [n["text"] for n in workbook.notes_on(db, "document", str(notice))] == ["Use item 4 as the s.186 precedent"]
    third_now = next(r for r in doc["resolutions"] if r["item_no"] == third["item_no"])
    assert [n["text"] for n in workbook.notes_on(db, "resolution", str(third_now["id"]))] == ["Check the s.185 wording"]
    source = db.latest_sources("company", company_id)["paid_up_capital"]
    assert source["document_id"] == notice and not source["note"]
    assert db.conn.execute("SELECT document_id FROM folder_files").fetchone()[0] == notice
    assert library.search(db, '"working capital"')["documents"][0]["document_id"] == notice
    assert trash.list_trash(db, settings.home)["count"] == 0


def test_statements_she_corrected_come_back(db, settings, tmp_path):
    document_id = library.add_document(db, settings, write_financials_pdf(tmp_path / "accounts.pdf"), queue_ai=False)["document_id"]
    fid = finance.listing(db)[0]["id"]
    finance.correct(db, fid, "revenue", 620_000_000, 510_000_000)
    workbook.add_note(db, "Revenue agreed with the CA", "financials", str(fid))

    result = editing.delete_document(db, settings.home, document_id)
    assert finance.listing(db) == []
    assert workbook.search_notes(db)[0]["text"].startswith("On the deleted statements of")

    trash.restore(db, settings, result["trash_id"])
    assert [f["id"] for f in finance.listing(db)] == [fid]
    revenue = finance.get(db, fid)["items"]["revenue"]
    assert (revenue["current"], revenue["previous"], revenue["by"]) == (620_000_000, 510_000_000, "her")
    assert [n["text"] for n in workbook.notes_on(db, "financials", str(fid))] == ["Revenue agreed with the CA"]


def test_restoring_when_a_new_document_has_taken_its_number(db, settings, notice, tmp_path):
    work = workbook.create_work(db, "AGM 2026", "agm")
    workbook.attach(db, work["id"], notice)
    workbook.add_note(db, "Keep for the precedent file", "document", str(notice))
    result = editing.delete_document(db, settings.home, notice)
    newcomer = letter(db, settings, tmp_path)
    assert newcomer == notice  # SQLite hands out the freed number again

    restored = trash.restore(db, settings, result["trash_id"])["document_id"]
    assert restored != notice
    assert library.document(db, restored)["title"] == "NOTICE OF 10TH ANNUAL GENERAL MEETING"
    assert library.document(db, newcomer)["original_name"] == "letter.pdf"
    assert [w["id"] for w in workbook.works_of_document(db, restored)] == [work["id"]]
    assert workbook.works_of_document(db, newcomer) == []
    assert [n["text"] for n in workbook.notes_on(db, "document", str(restored))] == ["Keep for the precedent file"]
    assert library.search(db, '"working capital"')["documents"][0]["document_id"] == restored
    stored = db.conn.execute("SELECT stored_path FROM documents WHERE id = ?", (restored,)).fetchone()[0]
    assert (settings.home / stored).is_file()


def test_a_document_whose_file_left_the_bin_can_only_be_deleted_forever(db, settings, notice):
    result = editing.delete_document(db, settings.home, notice)
    (settings.home / result["file_kept_in"]).unlink()
    assert trash.list_trash(db, settings.home)["items"][0]["file_missing"] is True
    with pytest.raises(Invalid, match="Delete it forever instead"):
        trash.restore(db, settings, result["trash_id"])
    assert trash.delete_forever(db, settings.home, result["trash_id"]) == {"deleted": result["trash_id"]}
    assert trash.list_trash(db, settings.home)["count"] == 0
    with pytest.raises(NotFound):
        trash.restore(db, settings, result["trash_id"])


def test_deleting_forever_and_emptying_the_trash(db, settings, notice, tmp_path):
    other = letter(db, settings, tmp_path)
    first = editing.delete_document(db, settings.home, notice)
    second = editing.delete_document(db, settings.home, other)
    older = settings.home / "bin" / "2025-01-01 1200 old letter.pdf"
    older.write_bytes(b"%PDF-1.4 deleted before the Trash existed")

    listed = trash.list_trash(db, settings.home)
    assert listed["count"] == 3 and [f["name"] for f in listed["loose"]] == ["2025-01-01 1200 old letter.pdf"]
    trash.delete_forever(db, settings.home, first["trash_id"])
    assert not (settings.home / first["file_kept_in"]).exists() and (settings.home / second["file_kept_in"]).is_file()

    assert trash.empty(db, settings.home) == {"deleted": 2, "files": 2}
    assert list((settings.home / "bin").iterdir()) == []
    assert trash.list_trash(db, settings.home) == {"items": [], "loose": [], "bytes": 0, "count": 0}


def test_files_from_before_the_trash_can_come_back_and_nothing_outside_the_bin_is_touched(db, settings, notice):
    (settings.home / "bin").mkdir(exist_ok=True)
    write_pdf(settings.home / "bin" / "2025-01-01 1200 sanction.pdf", ["Dear Sir, sanction of term loan facility by State Bank."])
    back = trash.restore_loose(db, settings, "2025-01-01 1200 sanction.pdf")["document_id"]
    assert library.document(db, back)["original_name"] == "sanction.pdf"
    assert not (settings.home / "bin" / "2025-01-01 1200 sanction.pdf").exists()

    for bad in ("..\\csdesk.db", "../csdesk.db", "C:\\Windows\\win.ini", "..", ""):
        with pytest.raises(Invalid):
            trash.restore_loose(db, settings, bad)
        with pytest.raises(Invalid):
            trash.delete_loose(db, settings.home, bad)
    assert settings.db_path.is_file()

    kept = editing.delete_document(db, settings.home, notice)["file_kept_in"]
    name = (settings.home / kept).name
    with pytest.raises(Invalid, match="belongs to a document in the Trash"):
        trash.delete_loose(db, settings.home, name)
    with pytest.raises(NotFound):
        trash.delete_loose(db, settings.home, "no such file.pdf")


def test_many_documents_at_once(db, settings, notice, tmp_path):
    other = letter(db, settings, tmp_path)
    result = trash.trash_documents(db, settings.home, [notice, other, 999])
    assert result["trashed"] == [notice, other]
    assert result["failed"] == [{"id": 999, "error": "There is no document 999."}]
    assert trash.list_trash(db, settings.home)["count"] == 2 and library.list_documents(db)["total"] == 0


def test_a_restore_that_fails_leaves_it_in_the_trash(settings, tmp_path, monkeypatch):
    with open_db(settings.db_path) as vault:
        document_id = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)["document_id"]
        kept = editing.delete_document(vault, settings.home, document_id)

    def boom(*args, **kwargs):
        raise RuntimeError("reading failed")

    monkeypatch.setattr(library, "index_new", boom)
    with pytest.raises(RuntimeError), open_db(settings.db_path) as vault:
        trash.restore(vault, settings, kept["trash_id"])
    assert (settings.home / kept["file_kept_in"]).is_file()  # back in the bin, with the database rolled back
    with open_db(settings.db_path) as vault:
        assert vault.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert trash.list_trash(vault, settings.home)["count"] == 1


def test_a_document_that_cant_be_moved_stays_while_the_rest_go(db, settings, notice, tmp_path, monkeypatch):
    other = letter(db, settings, tmp_path)
    stuck = db.conn.execute("SELECT stored_path FROM documents WHERE id = ?", (notice,)).fetchone()[0]
    real_move = trash.shutil.move

    def move(src, dst):
        if str(src).endswith(stuck.split("/")[-1]):
            raise PermissionError("the file is open in another program")
        return real_move(src, dst)

    monkeypatch.setattr(trash.shutil, "move", move)
    result = trash.trash_documents(db, settings.home, [notice, other])
    assert result["trashed"] == [other] and result["failed"][0]["id"] == notice
    assert library.document(db, notice)["title"] == "NOTICE OF 10TH ANNUAL GENERAL MEETING"  # untouched
    assert (settings.home / stuck).is_file() and library.search(db, '"working capital"')["matching_documents"] == 1
    assert [i["item_id"] for i in trash.list_trash(db, settings.home)["items"]] == [other]


def test_the_trash_through_the_window(settings, tmp_path):
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        def upload(path):
            with path.open("rb") as handle:
                response = client.post("/api/documents", files={"files": (path.name, handle, "application/pdf")}, headers=CHANGE)
            return response.json()["results"][0]["document_id"]

        document_id = upload(write_notice_pdf(tmp_path / "notice.pdf"))
        gone = client.delete(f"/api/documents/{document_id}", headers=CHANGE).json()
        assert gone["deleted"] == document_id and gone["trash_id"]
        listed = client.get("/api/trash").json()
        assert listed["count"] == 1 and listed["items"][0]["id"] == gone["trash_id"]

        assert client.post("/api/trash/empty").status_code == 403  # changes need the AAGAM header
        back = client.post(f"/api/trash/{gone['trash_id']}/restore", headers=CHANGE).json()
        assert back["document_id"] == document_id
        assert client.get(f"/api/documents/{document_id}").json()["doc_type"] == "notice"

        bulk = client.post("/api/documents/trash", json={"ids": [document_id]}, headers=CHANGE).json()
        assert bulk == {"trashed": [document_id], "failed": []}
        item = client.get("/api/trash").json()["items"][0]["id"]
        assert client.delete(f"/api/trash/{item}", headers=CHANGE).json() == {"deleted": item}
        assert client.post(f"/api/trash/{item}/restore", headers=CHANGE).status_code == 404

        write_pdf(settings.home / "bin" / "2025-01-01 1200 old.pdf", ["An old letter about a term loan."])
        write_pdf(settings.home / "bin" / "2025-01-01 1201 older.pdf", ["An older letter."])
        assert [f["name"] for f in client.get("/api/trash").json()["loose"]] == ["2025-01-01 1200 old.pdf", "2025-01-01 1201 older.pdf"]
        restored = client.post("/api/trash/loose/restore", json={"name": "2025-01-01 1200 old.pdf"}, headers=CHANGE).json()
        assert client.get(f"/api/documents/{restored['document_id']}").json()["original_name"] == "old.pdf"
        assert client.delete("/api/trash/loose", params={"name": "..\\csdesk.db"}, headers=CHANGE).status_code == 400
        assert client.delete("/api/trash/loose", params={"name": "2025-01-01 1201 older.pdf"}, headers=CHANGE).json() == {"deleted": "2025-01-01 1201 older.pdf"}

        client.delete(f"/api/documents/{restored['document_id']}", headers=CHANGE)
        assert client.post("/api/trash/empty", headers=CHANGE).json() == {"deleted": 1, "files": 1}
        assert client.get("/api/trash").json()["count"] == 0
