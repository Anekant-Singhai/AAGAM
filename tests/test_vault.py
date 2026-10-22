import pytest
from helpers import ACME, USER

from csdesk.errors import Invalid, NotFound
from csdesk.vault import ENTITIES, Source


def person(vault, name="Asha Rao", **fields):
    return vault.save("party", {"kind": "individual", "name": name, **fields}, USER)


def test_a_cin_fills_in_class_listing_and_industry_code(vault):
    company_id = vault.save("company", ACME, USER)
    row = vault.company_row(company_id)
    assert (row["entity_type"], row["company_class"], row["is_listed"], row["nic_code"]) == ("company", "private", 0, "74999")
    sources = vault.latest_sources("company", company_id)
    assert sources["cin"]["source_kind"] == "user"
    assert sources["company_class"]["source_kind"] == "derived"
    assert sources["company_class"]["note"] == "from the CIN"


def test_an_llpin_makes_an_llp(vault):
    company_id = vault.save("company", {"name": "Rao & Shah LLP", "cin": "aab-1234"}, USER)
    assert vault.company_row(company_id)["entity_type"] == "llp"


def test_a_directors_pan_cannot_go_on_the_company(vault):
    with pytest.raises(Invalid, match="director's PAN"):
        vault.save("company", {"name": "X", "pan": "ABCPE1234F"}, USER)


def test_an_individual_needs_an_individual_pan(vault):
    with pytest.raises(Invalid, match="not an individual"):
        person(vault, pan="AABCE1234F")


def test_pan_is_masked_in_every_reply_and_in_the_history(vault):
    party_id = vault.save(
        "party",
        {"kind": "individual", "name": "Asha Rao", "pan": "abcpe1234f", "din": "01234567"},
        Source("user", "test", quote="Her PAN is ABCPE1234F"),
    )
    assert vault.party(party_id)["pan"] == "XXXXXX234F"
    assert vault.party(party_id, reveal=True)["pan"] == "ABCPE1234F"
    assert vault.find_parties("asha")[0]["pan"] == "XXXXXX234F"
    history = vault.field_history("party", party_id, "pan")
    assert history[0]["value"] == "XXXXXX234F"
    assert "ABCPE1234F" not in history[0]["quote"]


def test_a_duplicate_din_points_to_the_existing_person(vault):
    first = person(vault, din="01234567")
    with pytest.raises(Invalid, match=f"id {first}"):
        person(vault, "Someone Else", din="01234567")


def test_an_update_changes_only_the_fields_given(vault):
    company_id = vault.save("company", {**ACME, "email": "cs@acme.example"}, USER)
    vault.save("company", {"roc": "RoC-Mumbai"}, USER, company_id)
    row = vault.company_row(company_id)
    assert (row["email"], row["roc"], row["cin"]) == ("cs@acme.example", "RoC-Mumbai", ACME["cin"])


def test_a_new_record_says_what_it_still_needs(vault):
    with pytest.raises(Invalid, match="also needs: name"):
        vault.save("company", {"email": "cs@acme.example"}, USER)


def test_format_errors_read_plainly(vault):
    with pytest.raises(Invalid, match="cin: 'U123' is neither a CIN"):
        vault.save("company", {"name": "X", "cin": "U123"}, USER)


def test_a_document_source_must_exist(vault):
    with pytest.raises(NotFound, match="no document 99"):
        vault.save("company", {"name": "X"}, Source("document", "test", document_id=99, page=1))


def test_appointments_are_checked(vault):
    company_id = vault.save("company", ACME, USER)
    bank = vault.save("party", {"kind": "organisation", "name": "State Bank of India", "org_type": "bank"}, USER)
    with pytest.raises(Invalid, match="only an individual"):
        vault.save("appointment", {"company_id": company_id, "party_id": bank, "role": "director"}, USER)
    director = person(vault)
    with pytest.raises(Invalid, match="before the appointment date"):
        vault.save(
            "appointment",
            {"company_id": company_id, "party_id": director, "role": "director",
             "date_of_appointment": "2026-05-01", "date_of_cessation": "2026-04-01"},
            USER,
        )


def test_companies_are_found_by_id_cin_or_name(vault):
    widgets = vault.save("company", ACME, USER)
    holdings = vault.save("company", {"name": "Acme Holdings Private Limited"}, USER)
    assert vault.resolve_company(str(widgets)) == widgets
    assert vault.resolve_company(ACME["cin"].lower()) == widgets
    assert vault.resolve_company("widgets") == widgets
    assert vault.resolve_company("Acme Holdings Private Limited") == holdings
    with pytest.raises(Invalid, match="2 companies match"):
        vault.resolve_company("acme")
    with pytest.raises(NotFound):
        vault.resolve_company("Zenith")


def test_every_model_field_has_a_column(vault):
    for name, spec in ENTITIES.items():
        columns = {row[1] for row in vault.conn.execute(f"PRAGMA table_info({spec.table})")}
        assert not set(spec.model.model_fields) - columns, name


def test_every_write_is_logged(vault):
    vault.save("company", ACME, USER)
    actions = [row["action"] for row in vault.conn.execute("SELECT action FROM activity")]
    assert actions == ["save company"]
