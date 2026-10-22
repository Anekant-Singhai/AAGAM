from datetime import date

from helpers import ACME, USER

from csdesk.duedates import due_items, upcoming

TODAY = date(2026, 10, 9)


def company(vault, **fields):
    return vault.save("company", {**ACME, **fields}, USER)


def person(vault, name, din, **fields):
    return vault.save("party", {"kind": "individual", "name": name, "din": din, **fields}, USER)


def only(items, form):
    found = [item for item in items if item.form == form]
    assert len(found) == 1, [(i.form, i.trigger) for i in items]
    return found[0]


def test_an_agm_starts_the_aoc4_and_mgt7_clocks(vault):
    company_id = company(vault, is_small_company=False)
    meeting = vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26", "fy": "2025-26"}, USER)
    items = due_items(vault, TODAY, company_id)
    aoc4, mgt7 = only(items, "AOC-4"), only(items, "MGT-7")
    assert (aoc4.due, aoc4.law, aoc4.trigger) == (date(2026, 10, 26), "s.137(1)", f"meeting:{meeting}")
    assert (mgt7.due, mgt7.law) == (date(2026, 11, 25), "s.92(4)")
    assert not [i for i in items if i.form == "AGM"]  # this year's AGM is on file


def test_a_small_company_files_mgt7a(vault):
    company_id = company(vault, is_small_company=True)
    vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26"}, USER)
    assert only(due_items(vault, TODAY, company_id), "MGT-7A").due == date(2026, 11, 25)


def test_a_missing_agm_shows_as_overdue(vault):
    company_id = company(vault)
    agm = only(due_items(vault, TODAY, company_id), "AGM")
    assert agm.due == date(2026, 9, 30) and agm.state(TODAY) == "overdue"


def test_the_agm_cannot_be_more_than_15_months_after_the_last(vault):
    company_id = company(vault)
    vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2025-06-15", "fy": "2024-25"}, USER)
    agm = only(due_items(vault, TODAY, company_id), "AGM")
    assert agm.due == date(2026, 9, 15) and "15 months" in agm.basis


def test_first_agm_for_a_company_incorporated_after_january(vault):
    # s.2(41): incorporated 10-02-2025, so the first year runs to 31-03-2026 and the first AGM is due by 31-12-2026.
    company_id = company(vault, date_of_incorporation="2025-02-10")
    agm = only(due_items(vault, TODAY, company_id), "AGM")
    assert (agm.due, agm.certainty) == (date(2026, 12, 31), "check")


def test_dir12_within_30_days_but_not_for_first_directors(vault):
    company_id = company(vault)
    first = person(vault, "Asha Rao", "01234567")
    later = person(vault, "Vikram Shah", "07654321")
    vault.save("appointment", {"company_id": company_id, "party_id": first, "role": "director", "date_of_appointment": "2015-06-01"}, USER)
    appointment = vault.save(
        "appointment", {"company_id": company_id, "party_id": later, "role": "additional_director", "date_of_appointment": "2026-10-01"}, USER
    )
    dir12 = [i for i in due_items(vault, TODAY, company_id) if i.form == "DIR-12"]
    assert [(i.trigger, i.due) for i in dir12] == [(f"appointment:{appointment}:in", date(2026, 10, 31))]


def test_a_resignation_gets_its_own_dir12(vault):
    company_id = company(vault)
    director = person(vault, "Vikram Shah", "07654321")
    appointment = vault.save(
        "appointment",
        {"company_id": company_id, "party_id": director, "role": "director", "date_of_appointment": "2015-06-01",
         "date_of_cessation": "2026-09-30", "cessation_reason": "resignation"},
        USER,
    )
    item = only(due_items(vault, TODAY, company_id), "DIR-12")
    assert (item.trigger, item.due) == (f"appointment:{appointment}:out", date(2026, 10, 30))


def test_pas3_is_15_days_for_private_placement_and_30_for_rights(vault):
    company_id = company(vault)
    for kind in ("private_placement", "rights", None):
        fields = {"company_id": company_id, "kind": "allotment", "date": "2026-10-01"}
        if kind:
            fields["allotment_type"] = kind
        vault.save("event", fields, USER)
    pas3 = sorted((i.due, i.certainty, i.title) for i in due_items(vault, TODAY, company_id) if i.form == "PAS-3")
    assert pas3 == [
        (date(2026, 10, 16), "check", "Return of allotment (type not recorded)"),
        (date(2026, 10, 16), "firm", "Return of allotment (private placement)"),
        (date(2026, 10, 31), "firm", "Return of allotment (rights)"),
    ]


def test_inc22_is_30_days_after_the_2017_amendment(vault):
    company_id = company(vault)
    vault.save("event", {"company_id": company_id, "kind": "registered_office_change", "date": "2026-10-01"}, USER)
    item = only(due_items(vault, TODAY, company_id), "INC-22")
    assert (item.due, item.law) == (date(2026, 10, 31), "s.12(4)")


def test_next_board_meeting_within_120_days(vault):
    company_id = company(vault, is_small_company=False)
    vault.save("meeting", {"company_id": company_id, "kind": "board", "date": "2026-08-01"}, USER)
    assert only(due_items(vault, TODAY, company_id), "BOARD MEETING").due == date(2026, 11, 29)


def test_small_company_board_meeting_each_half_year(vault):
    company_id = company(vault, is_small_company=True)
    vault.save("meeting", {"company_id": company_id, "kind": "board", "date": "2026-08-01"}, USER)
    item = only(due_items(vault, TODAY, company_id), "BOARD MEETING")
    assert (item.due, item.law) == (date(2027, 6, 30), "s.173(5)")


def test_adt1_runs_from_the_meeting_that_appointed_the_auditor(vault):
    company_id = company(vault)
    agm = vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26"}, USER)
    firm = vault.save("party", {"kind": "organisation", "name": "Mehta & Co", "org_type": "audit_firm", "frn": "123456W"}, USER)
    vault.save(
        "auditor_appointment",
        {"company_id": company_id, "auditor_id": firm, "audit_type": "statutory", "meeting_id": agm,
         "from_fy": "2026-27", "to_fy": "2030-31"},
        USER,
    )
    assert only(due_items(vault, TODAY, company_id), "ADT-1").due == date(2026, 10, 11)


def test_mgt14_for_special_resolutions_and_flagged_ones(vault):
    company_id = company(vault)
    special = vault.save("resolution", {"company_id": company_id, "kind": "special", "subject": "Alteration of articles", "passed_on": "2026-09-26"}, USER)
    vault.save("resolution", {"company_id": company_id, "kind": "board", "subject": "Open a bank account", "passed_on": "2026-09-20"}, USER)
    flagged = vault.save(
        "resolution",
        {"company_id": company_id, "kind": "board", "subject": "Borrowing", "passed_on": "2026-09-20", "mgt14_required": True},
        USER,
    )
    mgt14 = sorted((i.trigger, i.due) for i in due_items(vault, TODAY, company_id) if i.form == "MGT-14")
    assert mgt14 == sorted([(f"resolution:{special}", date(2026, 10, 26)), (f"resolution:{flagged}", date(2026, 10, 20))])


def test_charge_creation_and_satisfaction(vault):
    company_id = company(vault)
    vault.save("charge", {"company_id": company_id, "amount": "50,00,000", "created_on": "2026-09-20", "satisfied_on": "2026-10-05"}, USER)
    items = due_items(vault, TODAY, company_id)
    assert only(items, "CHG-1").due == date(2026, 10, 20)
    assert only(items, "CHG-4").due == date(2026, 11, 4)


def test_one_person_company_dates(vault):
    company_id = company(vault, cin="U74999MH2015OPC123456")
    items = [i for i in due_items(vault, TODAY, company_id) if i.trigger.endswith("2025-26")]
    aoc4, mgt7a = only(items, "AOC-4"), only(items, "MGT-7A")
    assert aoc4.due == date(2026, 9, 27)
    assert (mgt7a.due, mgt7a.certainty) == (date(2026, 11, 29), "check")
    assert not [i for i in due_items(vault, TODAY, company_id) if i.form == "AGM"]


def test_llp_annual_forms(vault):
    company_id = vault.save("company", {"name": "Rao & Shah LLP", "cin": "AAB-1234"}, USER)
    items = [i for i in due_items(vault, TODAY, company_id) if i.trigger.endswith("2025-26")]
    assert only(items, "LLP FORM 11").due == date(2026, 5, 30)
    assert only(items, "LLP FORM 8").due == date(2026, 10, 30)


def test_a_submitted_filing_closes_its_item_even_for_a_form_variant(vault):
    company_id = company(vault)
    meeting = vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26"}, USER)
    vault.save(
        "filing",
        {"company_id": company_id, "form": "AOC-4 XBRL", "trigger": f"meeting:{meeting}", "status": "submitted", "srn": "AB1234567"},
        USER,
    )
    aoc4 = only(due_items(vault, TODAY, company_id), "AOC-4")
    assert aoc4.state(TODAY) == "done"
    assert "AOC-4" not in [i.form for i in upcoming(vault, TODAY, company_id)]


def test_din_kyc_listed_once_per_person(vault):
    first, second = company(vault), vault.save("company", {"name": "Acme Holdings Private Limited"}, USER)
    director = person(vault, "Asha Rao", "01234567", kyc_next_due="2028-06-30")
    for company_id in (first, second):
        vault.save("appointment", {"company_id": company_id, "party_id": director, "role": "director"}, USER)
    kyc = [i for i in due_items(vault, TODAY) if i.form == "DIR-3 KYC"]
    assert [(i.due, i.title) for i in kyc] == [(date(2028, 6, 30), "DIN KYC for Asha Rao (DIN 01234567)")]


def test_struck_off_companies_are_left_out(vault):
    company(vault, status="struck_off")
    assert due_items(vault, TODAY) == []


def test_upcoming_keeps_the_window(vault):
    company_id = company(vault)
    vault.save("meeting", {"company_id": company_id, "kind": "agm", "date": "2026-09-26"}, USER)
    forms = {i.form for i in upcoming(vault, TODAY, company_id, days_ahead=30)}
    assert "AOC-4" in forms and "MGT-7" not in forms  # MGT-7 is 47 days away
