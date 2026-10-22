"""LLPs: their forms are recognised, their documents filed under them, their dates worked out, their jobs listed."""

from datetime import date

import pytest
from helpers import ACME, USER, run, write_pdf
from mcp import Client

from aagam import checklists, classify, entities, everything, library, workbook
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.mcp_server import build
from csdesk.duedates import due_items, form_family

LLP = {"name": "Rao & Shah Advisors LLP", "cin": "AAB-1234"}

FORM_11 = (
    "FORM 11\n"
    "[Pursuant to section 35 of the Limited Liability Partnership Act, 2008 and rule 25(1) of the Limited Liability\n"
    "Partnership Rules, 2009]\n"
    "Annual Return of Limited Liability Partnership (LLP)\n"
    "1. (a) LLPIN: AAB-1234\n"
    "(b) Name of the limited liability partnership: RAO & SHAH ADVISORS LLP\n"
    "2. Address of the registered office: 12 Marine Lines, Mumbai 400002"
)
FORM_8 = (
    "FORM 8\n"
    "[Pursuant to section 34 of the Limited Liability Partnership Act, 2008 and rule 24 of the Limited Liability Partnership\n"
    "Rules, 2009]\n"
    "Statement of Account & Solvency\n"
    "Part A - Statement of Solvency\n"
    "LLPIN AAB-1234"
)
FORM_3 = (
    "FORM 3\n"
    "Information with regard to limited liability partnership agreement and changes, if any, made therein\n"
    "[Pursuant to section 23(2) and 23(5) of the Limited Liability Partnership Act, 2008 and rule 21 of the Limited\n"
    "Liability Partnership Rules, 2009]"
)
FORM_4 = (
    "FORM 4\n"
    "Notice of appointment, cessation, change in name/ address/designation of a designated partner or partner, and\n"
    "consent to become a partner/designated partner\n"
    "[Pursuant to sections 7(3), 25(1), 25(2) of the Limited Liability Partnership Act, 2008 and rule 22 of the Limited\n"
    "Liability Partnership Rules, 2009]"
)
FILLIP = (
    "FORM FiLLiP\n"
    "Form for incorporation of Limited Liability Partnership (LLP)\n"
    "[Pursuant to section 11 of the Limited Liability Partnership Act, 2008 and rule 11 of the Limited Liability Partnership\n"
    "Rules, 2009]"
)
RUN_LLP = (
    "Reserve Unique Name-Limited Liability Partnership (RUN-LLP)\n"
    "[Pursuant to sections 15 and 16 of the Limited Liability Partnership Act, 2008 and rules 18 and 20 of the Limited\n"
    "Liability Partnership Rules, 2009]\n"
    "1. Purpose of application: Incorporation of new LLP"
)
AGREEMENT = (
    "LIMITED LIABILITY PARTNERSHIP AGREEMENT\n"
    "OF RAO & SHAH ADVISORS LLP\n"
    "THIS LIMITED LIABILITY PARTNERSHIP AGREEMENT is made at Mumbai on this 5th day of June, 2025\n"
    "BETWEEN\n"
    "1. Ms. Asha Rao, residing at Mumbai (hereinafter called the First Partner)\n"
    "2. Mr. Vikram Shah, residing at Pune (hereinafter called the Second Partner)\n"
    "WHEREAS the parties have consented to act as designated partners, the LLP was registered vide its\n"
    "Certificate of Incorporation dated 1st June, 2025, and no act shall be done without the consent of the\n"
    "designated partner named for it."
)
SUPPLEMENTARY = (
    "SUPPLEMENTARY AGREEMENT\n"
    "This Supplementary Agreement is made on 1st April, 2026 between the partners of Rao & Shah Advisors LLP\n"
    "(LLPIN: AAB-1234) to amend the LLP Agreement dated 5th June, 2025, as to the contribution of each partner."
)
PARTNERS_CTC = (
    "CERTIFIED TRUE COPY OF THE RESOLUTION PASSED BY THE PARTNERS OF RAO & SHAH ADVISORS LLP AT THE MEETING OF THE\n"
    "PARTNERS HELD ON 10TH APRIL, 2026 AT MUMBAI\n"
    "RESOLVED THAT the registered office of the LLP be shifted to 14 Marine Lines, Mumbai."
)
CONSENT = (
    "CONSENT TO ACT AS DESIGNATED PARTNER\n"
    "To, The Partners, Rao & Shah Advisors LLP\n"
    "I, Asha Rao, hereby give my consent to act as a Designated Partner of Rao & Shah Advisors LLP."
)


def kind_of(text: str) -> str | None:
    return classify.detect([(1, text)], "scan.pdf").doc_type


@pytest.mark.parametrize("text", [FORM_11, FORM_8, FORM_3, FORM_4, FILLIP, RUN_LLP], ids=["11", "8", "3", "4", "fillip", "run-llp"])
def test_llp_forms_are_filed_mca_forms(text):
    assert kind_of(text) == "mca_form"


def test_llp_documents_get_their_own_types():
    assert kind_of(AGREEMENT) == "llp_agreement"
    assert kind_of(SUPPLEMENTARY) == "llp_agreement"
    assert kind_of(PARTNERS_CTC) == "partners_resolution"
    assert kind_of(CONSENT) == "partner_consent"
    assert classify.detect([(1, AGREEMENT)], "x.pdf").title == "LIMITED LIABILITY PARTNERSHIP AGREEMENT"


def test_look_alikes_stay_what_they_are():
    tax_audit = (
        "FORM NO. 3CD\n[See rule 6G(2)]\nStatement of particulars required to be furnished under section 44AB of the\n"
        "Income-tax Act, 1961, pursuant to section 44AB\nName of the assessee: Rao & Shah Advisors LLP"
    )
    assert kind_of(tax_audit) != "mca_form"
    minutes = (
        "MINUTES OF THE MEETING OF THE PARTNERS OF RAO & SHAH ADVISORS LLP HELD ON 10TH APRIL, 2026 AT MUMBAI\n"
        "The partners noted that, as provided in clause 12 of the\n"
        "LLP Agreement, the accounts are to be audited every year."
    )
    assert kind_of(minutes) == "minutes"
    board_ctc = (
        "CERTIFIED TRUE COPY OF THE RESOLUTION PASSED BY THE BOARD OF DIRECTORS OF ACME WIDGETS PRIVATE LIMITED AT ITS\n"
        "MEETING HELD ON 10TH APRIL, 2026\nRESOLVED THAT M/s Rao & Co., Chartered Accountants, of which Ms. Asha Rao is one\n"
        "of the partners, be appointed as internal auditors."
    )
    assert kind_of(board_ctc) == "board_resolution"
    loan = (
        "SUPPLEMENTARY AGREEMENT\nThis Supplementary Agreement is made on 1st April, 2026 between Acme Widgets Private Limited\n"
        "and State Bank of India, the parties to the loan agreement, witnesseth as follows."
    )
    assert kind_of(loan) != "llp_agreement"  # no LLP in it
    dir2 = "FORM DIR-2\nConsent to act as a director of a company\n[Pursuant to section 152(5)]"
    assert kind_of(dir2) in ("mca_form", "consent_dir2")


def test_its_llpin_heads_it_and_files_it_under_the_llp(settings, tmp_path):
    with open_db(settings.db_path, actor="test") as db:
        llp_id = db.save("company", {**LLP, "date_of_incorporation": "2025-06-01"}, USER)
        db.save("company", ACME, USER)
        info = library.add_document(db, settings, write_pdf(tmp_path / "form 11.pdf", [FORM_11]), queue_ai=False, work_out_client=True)
        doc = library.document(db, info["document_id"])
        assert (doc["doc_type"], doc["company_cin"], doc["company_id"]) == ("mca_form", "AAB-1234", llp_id)
        assert doc["client_why"] == "its LLPIN AAB-1234"
        assert library.client_for(db, info["document_id"]) == (llp_id, "its LLPIN AAB-1234")

        found = entities.browse(db, "llpin")["entities"]
        assert [(e["key"], e["documents"]) for e in found] == [("AAB-1234", 1)]
        dossier = entities.dossier(db, "llpin", entities.key_of("llpin", "aab-1234"))
        assert [(f["type"], f["id"], f["entity_type"]) for f in dossier["company_file"]] == [("company", llp_id, "llp")]
        assert dossier["documents"][0]["document_id"] == info["document_id"]
        assert everything.search_all(db, "AAB-1234")["looks_like"] == "llpin"
        assert everything.search_all(db, "U74999MH2015PTC123456")["looks_like"] == "cin"


# ----------------------------------------------------------------- due dates


def only(items, form, trigger=None):
    found = [i for i in items if i.form == form and (trigger is None or i.trigger == trigger)]
    assert len(found) == 1, [(i.form, i.trigger) for i in items]
    return found[0]


def test_an_llp_incorporated_after_september_may_run_its_first_year_on(vault):
    llp = vault.save("company", {**LLP, "date_of_incorporation": "2025-11-15"}, USER)
    items = due_items(vault, date(2026, 10, 22), llp)
    assert not [i for i in items if i.trigger.endswith("2024-25")]  # it didn't exist yet
    first11, first8 = only(items, "LLP FORM 11", "form11:2025-26"), only(items, "LLP FORM 8", "form8:2025-26")
    assert (first11.due, first11.certainty, first11.law) == (date(2026, 5, 30), "check", "LLP Act s.35(1); rule 25(1)")
    assert (first8.due, first8.certainty, first8.law) == (date(2026, 10, 30), "check", "LLP Act s.34(3); rule 24(4)")
    assert "31-03-2027" in first11.basis
    second = only(items, "LLP FORM 11", "form11:2026-27")
    assert (second.due, second.certainty) == (date(2027, 5, 30), "firm")
    form3 = only(items, "LLP FORM 3", "form3:incorporation")
    assert (form3.due, form3.law) == (date(2025, 12, 15), "LLP Act s.23(2); rule 21(1)")


def test_an_llp_incorporated_by_september_has_a_firm_first_year(vault):
    llp = vault.save("company", {**LLP, "date_of_incorporation": "2025-06-10"}, USER)
    items = due_items(vault, date(2026, 10, 22), llp)
    assert only(items, "LLP FORM 11", "form11:2025-26").certainty == "firm"
    assert only(items, "LLP FORM 8", "form8:2025-26").certainty == "firm"
    # Incorporated between January and March, it is in the second half of its first year too.
    early = vault.save("company", {"name": "Early Start LLP", "cin": "AAC-1234", "date_of_incorporation": "2026-02-10"}, USER)
    assert only(due_items(vault, date(2026, 10, 22), early), "LLP FORM 11", "form11:2025-26").certainty == "check"


def test_llp_events_start_their_own_forms(vault):
    llp = vault.save("company", LLP, USER)
    events = {}
    for kind, day in (("registered_office_change", "2026-10-01"), ("name_change", "2026-10-05"),
                      ("llp_agreement_change", "2026-10-10"), ("sbo_declaration", "2026-10-12"), ("allotment", "2026-10-12")):
        events[kind] = vault.save("event", {"company_id": llp, "kind": kind, "date": day}, USER)
    items = due_items(vault, date(2026, 10, 22), llp)
    form15 = only(items, "LLP FORM 15")
    assert (form15.due, form15.law, form15.trigger, form15.certainty) == (
        date(2026, 10, 31), "LLP Act s.13(3); rule 17", f"event:{events['registered_office_change']}", "firm")
    form5 = only(items, "LLP FORM 5")
    assert (form5.due, form5.certainty) == (date(2026, 11, 4), "check")
    assert only(items, "LLP FORM 3", f"event:{events['llp_agreement_change']}").due == date(2026, 11, 9)
    ben2 = only(items, "LLP BEN-2")
    assert (ben2.due, ben2.certainty, ben2.law) == (date(2026, 11, 11), "check", "LLP (Significant Beneficial Owners) Rules, 2023")
    assert not {"INC-22", "PAS-3", "BEN-2", "AGM", "MGT-7", "AOC-4"} & {i.form for i in items}


def test_partners_and_their_din_kyc(vault):
    llp = vault.save("company", {**LLP, "date_of_incorporation": "2025-06-01"}, USER)
    first = vault.save("party", {"kind": "individual", "name": "Asha Rao", "din": "01234567", "kyc_next_due": "2027-06-30"}, USER)
    later = vault.save("party", {"kind": "individual", "name": "Vikram Shah", "din": "07654321"}, USER)
    vault.save("appointment", {"company_id": llp, "party_id": first, "role": "designated_partner", "date_of_appointment": "2025-06-01"}, USER)
    joined = vault.save("appointment", {"company_id": llp, "party_id": later, "role": "designated_partner",
                                        "date_of_appointment": "2026-10-01"}, USER)
    items = due_items(vault, date(2026, 10, 22), llp)
    form4 = only(items, "LLP FORM 4")
    assert (form4.due, form4.trigger) == (date(2026, 10, 31), f"appointment:{joined}:in")  # not for the first partners
    kyc = only(items, "DIR-3 KYC")
    assert (kyc.due, kyc.company_id) == (date(2027, 6, 30), llp)


def test_a_company_files_ben2_on_a_ben1_declaration(vault):
    company_id = vault.save("company", ACME, USER)
    event = vault.save("event", {"company_id": company_id, "kind": "sbo_declaration", "date": "2026-10-01"}, USER)
    ben2 = only(due_items(vault, date(2026, 10, 9), company_id), "BEN-2")
    assert (ben2.due, ben2.trigger) == (date(2026, 10, 31), f"event:{event}")
    assert "rule 5" in ben2.law and ben2.certainty == "firm"


def test_an_llp_filing_closes_its_item_however_the_form_is_written(vault):
    llp = vault.save("company", LLP, USER)
    vault.save("filing", {"company_id": llp, "form": "Form 11", "trigger": "form11:2025-26", "status": "submitted", "srn": "AB1234567"}, USER)
    form11 = only(due_items(vault, date(2026, 10, 22), llp), "LLP FORM 11", "form11:2025-26")
    assert form11.state(date(2026, 10, 22)) == "done"
    assert {form_family(f) for f in ("Form 11", "FORM-11", "LLP Form No. 11", "LLP FORM 11", "llp-11")} == {"LLP FORM 11"}
    assert form_family("llp ben 2") == "LLP BEN-2" and form_family("Form 3CD") == "FORM 3CD" and form_family("AOC-4 XBRL") == "AOC-4"


# --------------------------------------------------------------- work, Claude


def test_llp_jobs_have_checklists(vault):
    llp_kinds = [k for k in checklists.KINDS if k.startswith("llp_")]
    assert llp_kinds == ["llp_incorporation", "llp_annual_filing", "llp_partner_change", "llp_agreement_change",
                         "llp_office_change", "llp_name_change", "llp_strike_off"]
    for kind in llp_kinds:
        assert checklists.KINDS[kind]["label"].startswith("LLP: ") and checklists.KINDS[kind]["steps"]
    annual = checklists.KINDS["llp_annual_filing"]["steps"]
    assert ("Form 11 (annual return) by 30 May, within 60 days of the year end", "s.35(1); rule 25(1)") in annual
    assert list(checklists.KINDS)[-1] == "other"


def test_claude_opens_llp_work_and_llpin_dossiers(settings, tmp_path):
    with open_db(settings.db_path, actor="test") as db:
        llp_id = db.save("company", LLP, USER)
        library.add_document(db, settings, write_pdf(tmp_path / "form 8.pdf", [FORM_8]), queue_ai=False)
        work = workbook.create_work(db, "Annual filings FY 2025-26", "llp_annual_filing", llp_id)
        assert work["kind_label"] == "LLP: Annual filings (Form 8 and Form 11)"
    server = build(AagamSettings(core=settings, local_ai=False))

    async def steps():
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            created = await client.call_tool("work_create", {"title": "Agreement change", "kind": "llp_agreement_change", "company": "AAB-1234"})
            dossier = await client.call_tool("entity_dossier", {"kind": "llpin", "name": "aab-1234"})
            return tools, created, dossier

    tools, created, dossier = run(steps())
    assert "llp_strike_off" in str(tools["work_create"].input_schema) and "llpin" in str(tools["entity_list"].input_schema)
    assert created.structured_content["kind"] == "llp_agreement_change" and created.structured_content["checklist"]
    assert dossier.structured_content["company_file"][0]["name"] == LLP["name"]


def test_an_llp_dossier_names_what_is_missing(vault, settings):
    from csdesk.dossier.build import build as build_dossier

    llp = vault.save("company", {**LLP, "date_of_incorporation": "2025-06-01"}, USER)
    partner = vault.save("party", {"kind": "individual", "name": "Asha Rao"}, USER)
    vault.save("appointment", {"company_id": llp, "party_id": partner, "role": "designated_partner"}, USER)
    text = build_dossier(vault, settings, llp, date(2026, 10, 22))["markdown"]
    assert "1 designated partner(s) on file; an LLP needs at least two (LLP Act s.7)." in text
    assert "Asha Rao is a designated partner but has no DIN on file (LLP Act s.7(6))." in text
    assert "## Partners" in text and "LLP FORM 8" in text
