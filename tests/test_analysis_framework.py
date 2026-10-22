"""The analysis framework: shared text helpers, running every analyser, keeping results, registers across the library."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from helpers import write_notice_pdf

from aagam import analysis, library
from aagam.analysis import text
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.web.app import create_app


def test_sentences_keep_abbreviations_whole():
    found = [s for _, _, s in text.sentences("The loan of Rs. 5 crore to Acme Pvt. Ltd. is approved u/s. 186. It is secured. No. 4 follows.")]
    assert found[0] == "The loan of Rs. 5 crore to Acme Pvt. Ltd. is approved u/s. 186."
    assert found[1] == "It is secured."


def test_amounts_dates_and_scores():
    line = "invest up to ₹100 crore on or before 31st March, 2026 in equity shares"
    assert [a[0] for a in text.amounts(line)] == [1_000_000_000]
    assert [d[0] for d in text.dates(line)] == ["2026-03-31"]
    lexicon = {"equity shares": 2.0, "invest": 1.0}
    assert text.keyword_score(line, lexicon) == 3.0
    assert 0 < text.relevance([(1, line)], lexicon) <= 1
    assert text.key_sentences([(1, "The Board resolved to invest in equity shares of Acme Limited. The weather was fine.")], lexicon)[0]["page"] == 1
    assert text.rupees(1_000_000_000) == "₹100.00 crore"


FAKE = SimpleNamespace(
    KIND="fake", TITLE="Fake", COLUMNS=[{"key": "word", "label": "Word", "type": "text"}], __doc__="A test purpose.",
    analyse=lambda doc: analysis.result("fake", "Fake", FAKE.COLUMNS, [{"word": "working", "page": 4, "context": "x", "confidence": 1.0}], 0.5,
                                        "One word found.", tags=["fake-tag"]),
)
BROKEN = SimpleNamespace(KIND="broken", TITLE="Broken", COLUMNS=[], __doc__="Fails.", analyse=lambda doc: 1 / 0)


@pytest.fixture
def fake_purposes(monkeypatch):
    monkeypatch.setattr(analysis, "_modules", lambda: [BROKEN, FAKE])


def test_every_document_is_analysed_and_tagged(fake_purposes, settings, tmp_path):
    with open_db(settings.db_path) as vault:
        doc = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)
        found = analysis.for_document(vault, doc["document_id"])
        assert [a["kind"] for a in found] == ["fake"]  # the broken analyser didn't stop it
        assert "fake-tag" in {t["name"] for t in library.document(vault, doc["document_id"])["tags"]}
        register = analysis.register(vault, "fake", "work")
        assert register["count"] == 1 and register["items"][0]["document_id"] == doc["document_id"]
        assert analysis.register(vault, "fake", "nothing-like-this")["count"] == 0
        assert next(p for p in analysis.overview(vault) if p["kind"] == "fake")["items"] == 1


def test_the_insights_api(fake_purposes, settings, tmp_path):
    with open_db(settings.db_path) as vault:
        doc_id = library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)["document_id"]
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get(f"/api/documents/{doc_id}/analysis").json()["analyses"][0]["summary"] == "One word found."
        assert client.post(f"/api/documents/{doc_id}/analyse", headers={"X-AAGAM": "1"}).json()["analyses"][0]["kind"] == "fake"
        assert client.get("/api/insights").json()["purposes"][1]["documents"] == 1
        assert client.get("/api/insights/fake").json()["items"][0]["page"] == 4
        csv = client.get("/api/insights/fake?format=csv")
        assert csv.headers["content-type"].startswith("text/csv") and "working" in csv.text
        assert client.get("/api/insights/nonsense").status_code == 404


def test_every_real_purpose_loads():
    kinds = [c["kind"] for c in analysis.catalogue()]
    assert kinds == list(analysis.PURPOSES)
    assert all(c["columns"] and c["about"] for c in analysis.catalogue())
