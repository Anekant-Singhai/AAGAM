import json

from helpers import ACME, USER

from csdesk.recorder.draft import build
from csdesk.recorder.values import Matcher, describe_value, shape


def test_shapes_describe_without_keeping_the_value():
    assert shape("U74999MH2015PTC123456") == {"shape": "CIN"}
    assert shape("abcpe1234f") == {"shape": "PAN"}
    assert shape("01/10/2026") == {"shape": "date DD/MM/YYYY", "date_format": "%d/%m/%Y"}
    assert shape("01-Oct-2026") == {"shape": "date DD-Mon-YYYY", "date_format": "%d-%b-%Y"}
    assert shape("1,00,000") == {"shape": "number"}
    assert shape("01234567") == {"shape": "8 digits (a DIN?)"}
    assert shape("Acme Widgets") == {"shape": "text, 12 characters"}
    assert shape("  ") == {"shape": "empty"}


def test_typed_values_are_matched_to_the_company_file(vault):
    company_id = vault.save("company", {**ACME, "paid_up_capital": 100000}, USER)
    asha = vault.save("party", {"kind": "individual", "name": "Asha Rao", "din": "01234567", "pan": "ABCPE1234F"}, USER)
    vault.save("appointment", {"company_id": company_id, "party_id": asha, "role": "director"}, USER)

    for_her = Matcher.from_vault(vault, company_id, asha)
    assert for_her.match("u74999mh2015ptc123456") == ["company.cin"]
    assert for_her.match("01/06/2015") == ["company.date_of_incorporation"]  # typed DD/MM/YYYY, stored ISO
    assert for_her.match("1,00,000") == ["company.paid_up_capital"]
    assert for_her.match("abcpe1234f") == ["party.pan"]
    assert for_her.match("Someone else") == []

    # Without a chosen person, every director on file is a candidate, named so the draft can be checked.
    anyone = Matcher.from_vault(vault, company_id)
    assert anyone.match("01234567") == ["party.din (Asha Rao)"]


def test_the_recording_keeps_shape_and_match_only(vault):
    company_id = vault.save("company", ACME, USER)
    kept = describe_value({"kind": "text", "text": ACME["cin"]}, Matcher.from_vault(vault, company_id))
    assert kept == {"kind": "text", "shape": "CIN", "matches": ["company.cin"]}
    assert describe_value({"kind": "secret", "text": "hunter2"}, Matcher.empty()) == {"kind": "secret"}


def _event(seq, kind, step=1, **data):
    return json.dumps({"seq": seq, "t": f"2026-10-10T11:00:{seq:02d}.000", "step": step, "type": kind, **data})


def test_draft_marks_what_needs_review(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"id": "rec", "form": "INC-22", "started_at": "2026-10-10T11:00:00"}), encoding="utf-8")
    page = "https://www.mca.gov.in/mcafoportal/inc22.do"
    unlabelled = {"tag": "input", "type": "text", "label": "", "label_source": "none", "selector": "#addr1", "required": True}
    in_frame = {"tag": "input", "type": "text", "label": "PIN code", "label_source": "label", "selector": "#pin"}
    login = {"tag": "input", "type": "password", "label": "Password", "label_source": "label", "selector": "#pw", "secret": True}
    lines = [
        _event(1, "step", reason="recording started"),
        _event(2, "snapshot", heading="Form INC-22", page_url=page, frame_url=page, in_frame=False,
               fields=[unlabelled, {**in_frame}, login, {"label": "Registered office email", "label_source": "label",
                                                          "selector": "#email", "required": True, "has_value": False}]),
        _event(3, "change", page_url=page, frame_url=page, in_frame=False, field=unlabelled,
               value={"kind": "text", "shape": "text, 30 characters", "matches": []}),
        _event(4, "change", page_url=page, frame_url="https://www.mca.gov.in/frame", in_frame=True, field=in_frame,
               value={"kind": "text", "shape": "6 digits (a PIN code?)", "matches": ["company.ro_pin"]}),
        _event(5, "change", page_url=page, frame_url=page, in_frame=False, field=login, value={"kind": "secret"}),
        _event(6, "click", page_url=page, name="Proceed", guard="not_listed"),
        _event(7, "click", page_url=page, name="Submit", guard="hers"),
        _event(8, "request", method="POST", url="https://www.mca.gov.in/bin/validate", query_keys=["cin"], status=200,
               resource_type="xhr", ms=310),
        _event(9, "stopped", reason="stopped"),
    ]
    (folder / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = build(folder)
    assert summary["fields_filled"] == 2 and summary["matched"] == 1  # the password field is left out
    review = "\n".join(summary["to_review"])
    assert "no match in the company file" in review
    assert "no label; found by CSS selector" in review
    assert "inside a frame" in review
    assert '"Proceed"' in review

    flow = (folder / "flow.md").read_text(encoding="utf-8")
    assert "`POST https://www.mca.gov.in/bin/validate ?cin` → 200 (xhr, 310 ms)" in flow
    assert "pressed **Submit** (hers; CS Desk never presses it)" in flow
    assert "Marked required but left empty: Registered office email." in flow
    assert "| Password |" not in flow and "typed into a password, OTP or captcha field (not recorded)" in flow

    source = (folder / "recipe_draft.py").read_text(encoding="utf-8")
    namespace: dict = {}
    exec(compile(source, "recipe_draft.py", "exec"), namespace)  # the draft must at least be valid Python
    recipe = namespace["INC_22"]
    assert recipe.code == "INC-22" and recipe.url_contains == "/mcafoportal/inc22.do"
    assert [f.key for f in recipe.fields] == ["extra.addr1", "company.ro_pin"]
    assert recipe.fields[0].selector == "#addr1"
