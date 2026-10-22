import pytest
from fastapi.testclient import TestClient
from helpers import ACME, USER, write_notice_pdf

from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.web.app import create_app

CHANGE = {"X-AAGAM": "1"}


@pytest.fixture
def client(settings):
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def upload(client, path, **form):
    with path.open("rb") as handle:
        return client.post("/api/documents", files={"files": (path.name, handle, "application/pdf")}, data=form, headers=CHANGE)


def test_upload_view_search_and_tag(client, tmp_path):
    response = upload(client, write_notice_pdf(tmp_path / "Acme notice.pdf"), tags="precedent")
    assert response.status_code == 200, response.text
    document_id = response.json()["results"][0]["document_id"]

    doc = client.get(f"/api/documents/{document_id}").json()
    assert doc["doc_type"] == "notice" and len(doc["resolutions"]) == 4
    assert "NOTICE OF 10TH ANNUAL GENERAL MEETING" in client.get(f"/api/documents/{document_id}/pages/2").json()["text"]
    assert client.get(f"/api/documents/{document_id}/file").headers["content-type"] == "application/pdf"
    assert client.get(f"/api/documents/{document_id}/pages/1/image").headers["content-type"] == "image/jpeg"

    hits = client.get("/api/search", params={"q": "working capital"}).json()
    assert hits["documents"][0]["pages"] == [4]
    assert client.get(f"/api/documents/{document_id}/search", params={"q": "proxy"}).json()["pages"][0]["page"] == 3

    tagged = client.post(f"/api/documents/{document_id}/tags", json={"add": ["Group loans"], "remove": ["precedent"]}, headers=CHANGE).json()
    names = {t["name"] for t in tagged["tags"]}
    assert "group loans" in names and "precedent" not in names
    assert {"name": "group loans", "kind": "topic", "documents": 1} in client.get("/api/tags").json()["tags"]


def test_precedents_and_the_loan_calculator(client, tmp_path):
    upload(client, write_notice_pdf(tmp_path / "notice.pdf"))
    found = client.get("/api/precedents", params={"section": "186", "kind": "special", "min_crore": 50}).json()
    assert found["count"] == 1
    full = client.get(f"/api/precedents/{found['resolutions'][0]['id']}").json()
    assert full["body"].startswith("RESOLVED THAT")
    figures = {"paid_up_capital": 100_000_000, "free_reserves": 500_000_000, "securities_premium": 200_000_000,
               "proposed_loans_investments": 1_000_000_000}
    result = client.post("/api/checks/loan-limits", json=figures, headers=CHANGE).json()
    assert result["s186"]["status"] == "special_resolution" and "s185" in result


def test_her_summary_and_document_changes(client, settings, tmp_path):
    with open_db(settings.db_path) as vault:
        vault.save("company", ACME, USER)
    document_id = upload(client, write_notice_pdf(tmp_path / "notice.pdf")).json()["results"][0]["document_id"]
    saved = client.put(f"/api/documents/{document_id}/summary", json={"summary": "AGM notice for FY 2025-26."}, headers=CHANGE).json()
    assert saved["summary_by"] == "her"
    changed = client.patch(f"/api/documents/{document_id}", json={"company": "Acme", "title": "Acme AGM 2026"}, headers=CHANGE).json()
    assert (changed["client"], changed["title"]) == (ACME["name"], "Acme AGM 2026")
    assert client.get("/api/documents", params={"company": "Acme"}).json()["total"] == 1
    queued = client.post(f"/api/documents/{document_id}/summarise", headers=CHANGE).json()
    assert queued["queued"] and queued["ai"]["enabled"] is False
    overview = client.get("/api/overview").json()
    assert overview["stats"]["documents"] == 1 and overview["stats"]["resolutions"] == 4


def test_other_websites_cant_use_it(client, tmp_path):
    path = write_notice_pdf(tmp_path / "notice.pdf")
    with path.open("rb") as handle:
        blind = client.post("/api/documents", files={"files": ("x.pdf", handle, "application/pdf")})
    assert blind.status_code == 403  # no X-AAGAM header: a cross-site form can't add it
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403  # DNS rebinding


def test_plain_errors(client):
    assert client.get("/api/documents/99").json() == {"detail": "There is no document 99."}
    assert client.get("/api/search", params={"q": " "}).status_code == 400
    assert client.post("/api/documents", files={"files": ("x.doc", b"old", "application/msword")}, headers=CHANGE).json()["results"][0]["error"].startswith("AAGAM can't read .doc")


def test_inbox_files_are_brought_in(client, settings, tmp_path):
    write_notice_pdf(settings.inbox_dir / "dropped notice.pdf")
    results = client.post("/api/inbox", headers=CHANGE).json()["results"]
    assert results[0]["file"] == "dropped notice.pdf" and results[0]["document_id"]
    assert client.get("/api/documents").json()["documents"][0]["resolutions"] == 4
