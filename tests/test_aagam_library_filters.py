"""The library by date, folder, kind and client: each document's date, the filters and their counts, and filing
documents under the client they point to."""

import os
import time

import pytest
from fastapi.testclient import TestClient
from helpers import ACME, USER, write_financials_pdf, write_notice_pdf, write_pdf

from aagam import editing, library
from aagam.config import AagamSettings
from aagam.db import migrate, open_db
from aagam.web.app import create_app
from csdesk.errors import Invalid

CHANGE = {"X-AAGAM": "1"}


@pytest.fixture
def db(settings):
    with open_db(settings.db_path, actor="test") as vault:
        yield vault


def add(db, settings, path, **more):
    return library.add_document(db, settings, path, queue_ai=False, **more)["document_id"]


def letter(path, date_line="Date: 15/04/2024", body="We resign as directors with effect from today."):
    return write_pdf(path, [f"To,\nThe Board of Directors\n{date_line}\nSubject: Resignation\nDear Sirs,\n{body}"])


def test_each_document_gets_its_own_date(db, settings, tmp_path):
    notice = add(db, settings, write_notice_pdf(tmp_path / "notice.pdf"))
    accounts = add(db, settings, write_financials_pdf(tmp_path / "accounts.pdf"))
    dated = add(db, settings, letter(tmp_path / "letter.pdf"))
    plain = add(db, settings, write_pdf(tmp_path / "memo.pdf", ["Board memo\nThe auditors met on 2nd March, 2025 to discuss the plan."]))
    undated = add(db, settings, write_pdf(tmp_path / "undated.pdf", ["Some words with no date at all in them."]))

    def date_of(document_id):
        doc = library.document(db, document_id)
        return doc["doc_date"], doc["doc_date_basis"]

    assert date_of(notice) == ("2026-09-30", "the meeting date")
    day, basis = date_of(accounts)
    assert day == "2026-03-31" and basis.startswith("the accounts' date")
    assert date_of(dated) == ("2024-04-15", "“Date: 15/04/2024”")
    assert date_of(plain) == ("2025-03-02", "the first date on page 1, “2nd March, 2025”")
    day, basis = date_of(undated)
    assert basis == "the day it was added" and day == db.conn.execute("SELECT substr(ingested_at, 1, 10) FROM documents WHERE id = ?", (undated,)).fetchone()[0]


def test_a_file_s_own_date_stands_in_when_the_words_give_none(db, settings, tmp_path):
    path = write_pdf(tmp_path / "scan-note.pdf", ["Nothing dated here."])
    stamp = time.mktime((2023, 7, 14, 10, 0, 0, 0, 0, -1))
    os.utime(path, (stamp, stamp))
    document_id = add(db, settings, path, origin=library.Origin.of_file(path))
    doc = library.document(db, document_id)
    assert (doc["doc_date"], doc["doc_date_basis"]) == ("2023-07-14", "the day the file was last changed")
    assert doc["source_path"] == str(path.resolve()) and doc["file_modified"].startswith("2023-07-14")


def test_her_date_wins_and_lasts(db, settings, tmp_path):
    document_id = add(db, settings, letter(tmp_path / "letter.pdf"))
    editing.set_document_details(db, document_id, {"doc_date": "2024-04-20"})
    library.index_document(db, document_id, keep_type=True, home=settings.home)
    doc = library.document(db, document_id)
    assert (doc["doc_date"], doc["doc_date_basis"], doc["fy"]) == ("2024-04-20", "set by her", "2024-25")
    with pytest.raises(Invalid):
        editing.set_document_details(db, document_id, {"doc_date": "20 April"})
    editing.set_document_details(db, document_id, {"doc_date": ""})  # cleared: worked out again
    doc = library.document(db, document_id)
    assert (doc["doc_date"], doc["doc_date_basis"]) == ("2024-04-15", "“Date: 15/04/2024”")


def test_financial_years():
    assert library.fy_of("2024-09-30") == "2024-25"
    assert library.fy_of("2025-03-31") == "2024-25"
    assert library.fy_of("2025-04-01") == "2025-26"
    assert library.fy_of("1999-12-31") == "1999-00"
    assert library.fy_of(None) is None


@pytest.fixture
def shelf(db, settings, tmp_path):
    """A small library: a notice (FY 2026-27), accounts (FY 2025-26), a letter (FY 2024-25), a text note and a scan,
    some from a folder."""
    db.conn.execute("INSERT INTO folders (id, path) VALUES (7, ?)", (str(tmp_path / "Clients"),))
    folder = lambda inside: library.Origin(folder_id=7, folder=inside)  # noqa: E731
    ids = {
        "notice": add(db, settings, write_notice_pdf(tmp_path / "notice.pdf"), origin=folder("Acme/2026-27")),
        "accounts": add(db, settings, write_financials_pdf(tmp_path / "accounts.pdf"), origin=folder("Acme/2025-26/Accounts")),
        "letter": add(db, settings, letter(tmp_path / "letter.pdf"), origin=folder("Beta")),
    }
    note = tmp_path / "note.txt"
    note.write_text("Call the bank about the sanction letter. Date: 01/01/2025", encoding="utf-8")
    ids["note"] = add(db, settings, note)
    ids["scan"] = add(db, settings, write_pdf(tmp_path / "scan.pdf", [""]), origin=library.Origin(modified="2023-01-05T09:00:00"))
    company_id = db.save("company", ACME, USER)
    db.conn.execute("UPDATE documents SET company_id = ? WHERE id IN (?, ?)", (company_id, ids["notice"], ids["accounts"]))
    return {**ids, "company_id": company_id}


def names(result):
    return [d["original_name"] for d in result["documents"]]


def test_filters_by_date_year_and_financial_year(db, shelf):
    assert names(library.list_documents(db, fy="2024-25")) == ["note.txt", "letter.pdf"]
    assert names(library.list_documents(db, fy="2025-26")) == ["accounts.pdf"]
    assert names(library.list_documents(db, year="2026")) == ["accounts.pdf", "notice.pdf"]
    between = library.list_documents(db, date_from="2024-04-01", date_to="2025-12-31")
    assert set(names(between)) == {"letter.pdf", "note.txt"}
    assert names(library.list_documents(db, sort="oldest")) == ["scan.pdf", "letter.pdf", "note.txt", "accounts.pdf", "notice.pdf"]
    assert names(library.list_documents(db, sort="newest")) == ["notice.pdf", "accounts.pdf", "note.txt", "letter.pdf", "scan.pdf"]
    # By title where it has one ("Call the bank...", "NOTICE OF 10TH...", "Statement of Profit and Loss..."), else by file name.
    assert names(library.list_documents(db, sort="name")) == ["note.txt", "letter.pdf", "notice.pdf", "scan.pdf", "accounts.pdf"]
    for bad in ({"fy": "2024-26"}, {"fy": "24-25"}, {"date_from": "1 April"}, {"year": "26"}):
        with pytest.raises(Invalid):
            library.list_documents(db, **bad)
    with pytest.raises(Invalid):
        library.list_documents(db, sort="biggest")
    with pytest.raises(Invalid):
        library.list_documents(db, colour="red")


def test_filters_by_folder_kind_scan_and_client(db, shelf):
    assert set(names(library.list_documents(db, folder_id=7))) == {"notice.pdf", "accounts.pdf", "letter.pdf"}
    assert set(names(library.list_documents(db, folder_id=7, within="Acme"))) == {"notice.pdf", "accounts.pdf"}
    assert names(library.list_documents(db, folder_id=7, within="Acme/2025-26")) == ["accounts.pdf"]
    assert names(library.list_documents(db, folder_id=7, within="Acme/2025")) == []  # a folder's name, not a prefix of it
    assert names(library.list_documents(db, kind="text")) == ["note.txt"]
    assert names(library.list_documents(db, scanned=True)) == ["scan.pdf"]
    assert "scan.pdf" not in names(library.list_documents(db, scanned=False))
    assert set(names(library.list_documents(db, company_id=shelf["company_id"]))) == {"notice.pdf", "accounts.pdf"}
    assert set(names(library.list_documents(db, no_client=True))) == {"letter.pdf", "note.txt", "scan.pdf"}
    assert names(library.list_documents(db, name="Beta")) == ["letter.pdf"]  # the folder's name counts as its name too
    row = library.list_documents(db, kind="pdf", folder_id=7, within="Beta")["documents"][0]
    assert (row["kind"], row["fy"], row["source_folder"], row["folder_id"]) == ("pdf", "2024-25", "Beta", 7)


def test_facets_count_each_filter_s_choices(db, shelf):
    found = library.facets(db, library.Filters(folder_id=7))
    assert {f["key"]: f["documents"] for f in found["fys"]} == {"2026-27": 1, "2025-26": 1, "2024-25": 1}
    assert [f["key"] for f in library.facets(db, library.Filters())["fys"]] == ["2026-27", "2025-26", "2024-25", "2022-23"]  # latest first
    assert {c["label"]: c["documents"] for c in found["clients"]} == {ACME["name"]: 2, "No client": 1}
    assert [(f["key"], f["documents"]) for f in found["folders"]] == [(7, 3)] and found["folders"][0]["label"].endswith("Clients")
    assert {i["key"]: i["documents"] for i in found["inside"]} == {"Acme": 2, "Beta": 1}
    deeper = library.facets(db, library.Filters(folder_id=7, within="Acme"))
    assert {i["key"]: i["documents"] for i in deeper["inside"]} == {"Acme/2026-27": 1, "Acme/2025-26": 1}
    # A filter's own choices ignore that filter, so she can switch between them.
    by_type = library.facets(db, library.Filters(doc_type="notice"))
    assert sum(t["documents"] for t in by_type["types"]) == 5
    assert {k["key"]: k["documents"] for k in library.facets(db, library.Filters())["kinds"]} == {"pdf": 4, "text": 1}


def test_a_document_is_filed_under_the_client_it_points_to(db, settings, tmp_path):
    acme = db.save("company", ACME, USER)
    beta = db.save("company", {"name": "Beta Traders Limited", "cin": "L51909DL2001PLC123456"}, USER)
    db.save("company", {"name": "Beta Traders Private Limited"}, USER)

    by_cin = write_pdf(tmp_path / "board.pdf", ["CIN: L51909DL2001PLC123456\nCERTIFIED TRUE COPY OF THE RESOLUTION passed by the Board"])
    document_id = add(db, settings, by_cin, work_out_client=True)
    doc = library.document(db, document_id)
    assert (doc["company_id"], doc["client_why"]) == (beta, "its CIN L51909DL2001PLC123456")

    in_folder = add(db, settings, letter(tmp_path / "a.pdf"), work_out_client=True, origin=library.Origin(folder="Clients/Acme Widgets/2024"))
    assert (library.document(db, in_folder)["company_id"], library.document(db, in_folder)["client_why"]) == (acme, "the folder “Acme Widgets”")
    # "Beta Traders" fits two clients, so it is left for her.
    ambiguous = add(db, settings, letter(tmp_path / "b.pdf", body="Another letter."), work_out_client=True, origin=library.Origin(folder="Beta Traders"))
    assert library.document(db, ambiguous)["company_id"] is None
    # Another company's document never is.
    precedent = add(db, settings, write_notice_pdf(tmp_path / "other.pdf"), tags=["precedent"], work_out_client=True,
                    origin=library.Origin(folder="Acme Widgets"))
    assert library.document(db, precedent)["company_id"] is None
    # Without the option nothing changes.
    plain = add(db, settings, letter(tmp_path / "c.pdf", body="Yet another letter."), origin=library.Origin(folder="Acme Widgets"))
    assert library.document(db, plain)["company_id"] is None


def test_client_found_by_name_and_statements_follow(db, settings, tmp_path):
    acme = db.save("company", ACME, USER)
    document_id = add(db, settings, write_financials_pdf(tmp_path / "accounts.pdf"), work_out_client=True)
    doc = library.document(db, document_id)
    assert doc["company_id"] == acme and doc["client_why"] == f"its company name, “{ACME['name']}”"
    assert {r["company_id"] for r in db._rows("SELECT company_id FROM financials WHERE document_id = ?", (document_id,))} == {acme}


def test_older_documents_are_dated_in_the_background(db, settings, tmp_path):
    document_id = add(db, settings, letter(tmp_path / "letter.pdf"))
    db.conn.execute("UPDATE doc_meta SET doc_date = NULL, doc_date_basis = NULL WHERE document_id = ?", (document_id,))
    assert library.backfill_dates(db) == 1
    assert library.document(db, document_id)["doc_date"] == "2024-04-15"
    assert library.backfill_dates(db) == 0


def test_upgrading_the_database_dates_meetings(db, settings, tmp_path):
    document_id = add(db, settings, write_notice_pdf(tmp_path / "notice.pdf"))
    db.conn.execute("UPDATE doc_meta SET doc_date = NULL WHERE document_id = ?", (document_id,))
    db.conn.execute("UPDATE aagam_meta SET value = '5' WHERE key = 'schema_version'")
    migrate(db.conn)
    assert db.conn.execute("SELECT doc_date FROM doc_meta WHERE document_id = ?", (document_id,)).fetchone()[0] == "2026-09-30"
    migrate(db.conn)  # once up to date, nothing happens


@pytest.fixture
def client(settings):
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_upload_keeps_folders_and_files_by_client(client, settings, tmp_path):
    with open_db(settings.db_path) as vault:
        acme = vault.save("company", ACME, USER)
    first, second = letter(tmp_path / "one.pdf"), letter(tmp_path / "two.pdf", body="A second letter.")
    with first.open("rb") as a, second.open("rb") as b:
        response = client.post(
            "/api/documents",
            files=[("files", ("one.pdf", a, "application/pdf")), ("files", ("two.pdf", b, "application/pdf"))],
            data={"company": "auto", "paths": ["Acme Widgets/2024/one.pdf", "Loose/two.pdf"], "modified": ["2024-04-16T10:00:00", ""]},
            headers=CHANGE,
        )
    assert response.status_code == 200, response.text
    one, two = (r["document_id"] for r in response.json()["results"])
    doc = client.get(f"/api/documents/{one}").json()
    assert (doc["source_folder"], doc["company_id"], doc["file_modified"]) == ("Acme Widgets/2024", acme, "2024-04-16T10:00:00")
    assert client.get(f"/api/documents/{two}").json()["company_id"] is None

    listed = client.get("/api/documents", params={"fy": "2024-25", "sort": "oldest", "company": "none"}).json()
    assert [d["id"] for d in listed["documents"]] == [two]
    assert client.get("/api/documents", params={"company": "Acme"}).json()["total"] == 1
    facets = client.get("/api/documents/facets", params={"kind": "pdf"}).json()
    assert {f["key"] for f in facets["fys"]} == {"2024-25"} and facets["kinds"][0]["key"] == "pdf"
    assert client.get("/api/documents", params={"fy": "2024"}).status_code == 400
    assert "file_kinds" in client.get("/api/meta").json()

    changed = client.patch(f"/api/documents/{two}", json={"company": "Acme", "doc_date": "2024-05-01"}, headers=CHANGE).json()
    assert (changed["client_why"], changed["doc_date"], changed["doc_date_basis"]) == ("set by her", "2024-05-01", "set by her")
