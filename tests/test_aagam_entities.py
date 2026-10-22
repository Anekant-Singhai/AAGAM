import pytest
from helpers import ACME, USER, write_financials_pdf, write_notice_pdf, write_pdf

from aagam import entities, everything, library
from aagam.db import open_db
from csdesk.errors import Invalid, NotFound


@pytest.fixture
def db(settings, tmp_path):
    with open_db(settings.db_path, actor="test") as vault:
        library.add_document(vault, settings, write_notice_pdf(tmp_path / "notice.pdf"), queue_ai=False)
        library.add_document(vault, settings, write_pdf(tmp_path / "consent.pdf", [
            "Form DIR-2: consent to act as director\nI, ASHA RAO (DIN 01234567), consent to act as a director of\n"
            "ACME WIDGETS LTD. GSTIN 27AAPFU0939F1ZV"]), queue_ai=False)
        yield vault


def test_spellings_are_grouped(db):
    people = {e["key"]: e for e in entities.browse(db, "person")["entities"]}
    assert people["asha rao"]["documents"] == 2  # "Mr. Asha Rao" in the notice, "ASHA RAO" would be missed without the DIN
    companies = {e["key"]: e for e in entities.browse(db, "company")["entities"]}
    assert companies["acme widgets limited"]["documents"] == 2  # "Acme Widgets Limited" and "ACME WIDGETS LTD."
    assert entities.key_of("company", "Godha Cabcon& Insulation Pvt. Ltd.") == "godha cabcon and insulation private limited"
    with pytest.raises(Invalid):
        entities.browse(db, "spaceship")


def test_a_persons_dossier_follows_the_din(db):
    db.save("company", ACME, USER)
    party = db.save("party", {"kind": "individual", "name": "Asha Rao", "din": "01234567"}, USER)
    db.save("appointment", {"company_id": 1, "party_id": party, "role": "director"}, USER)
    d = entities.dossier(db, "person", "asha rao")
    assert d["identifiers"]["DIN"] == ["01234567"]
    assert {doc["doc_type"] for doc in d["documents"]} == {"notice", "consent_dir2"}
    assert d["company_file"][0]["appointments"][0]["company"] == ACME["name"]
    assert any(e["key"] == "acme widgets limited" for e in d["appears_with"])
    din = entities.dossier(db, "din", "01234567")
    assert din["identifiers"]["Named as"] == ["Asha Rao"]


def test_a_companys_dossier_has_its_resolutions_and_financials(db, settings, tmp_path):
    library.add_document(db, settings, write_financials_pdf(tmp_path / "fs.pdf"), queue_ai=False)
    d = entities.dossier(db, "company", "acme widgets limited")
    assert [r["item_no"] for r in d["resolutions"]] == [1, 2, 3, 4]
    assert d["identifiers"]["CIN"] == ["L74999MH2015PLC123456"]
    cin = entities.dossier(db, "cin", "L74999MH2015PLC123456")
    assert cin["cin"]["listed"] is True and cin["cin"]["state"] == "Maharashtra"
    assert len(cin["resolutions"]) == 4
    fs = entities.dossier(db, "company", "acme widgets private limited")
    assert fs["financials"][0]["basis"] == "standalone"


def test_gstin_decoded_and_linked_through_its_pan(db):
    db.save("company", {**ACME, "pan": "AAPFU0939F"} | {"cin": None, "name": "Ufa Partners LLP", "entity_type": "llp"}, USER)
    info = entities.gstin_info("27aapfu0939f1zv")
    assert (info["state"], info["pan"], info["pan_holder"], info["registration_no"]) == ("Maharashtra", "XXXXXX939F", "firm or LLP", "1")
    d = entities.dossier(db, "gstin", "27AAPFU0939F1ZV")
    assert d["company_file"][0]["name"] == "Ufa Partners LLP" and d["company_file"][0]["matched_by"] == "the PAN inside the GSTIN"
    with pytest.raises(NotFound):
        entities.dossier(db, "person", "nobody at all")


def test_search_everything(db):
    db.save("company", ACME, USER)
    found = everything.search_all(db, "acme")
    assert found["documents"] and found["entities"] and found["companies"][0]["name"] == ACME["name"]
    assert everything.search_all(db, "U74999MH2015PTC123456")["looks_like"] == "cin"
    assert everything.search_all(db, "27AAPFU0939F1ZV")["looks_like"] == "gstin"
    with pytest.raises(Invalid):
        everything.search_all(db, "  ")
