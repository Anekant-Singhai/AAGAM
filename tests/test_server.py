"""The MCP tools as Claude sees them, through an in-process MCP client."""

from datetime import date, timedelta
from pathlib import Path

import docx
from helpers import ACME, run, write_pdf
from mcp import Client

from csdesk.server import build_server

USER = {"kind": "user"}


async def _session(settings, steps):
    async with Client(build_server(settings)) as client:
        return await steps(client)


def call(settings, name, arguments):
    async def steps(client):
        return await client.call_tool(name, arguments)

    return run(_session(settings, steps))


def text_of(result):
    return "\n".join(block.text for block in result.content if block.type == "text")


def test_the_tools_claude_needs_are_listed(settings):
    names = {tool.name for tool in run(build_server(settings).list_tools())}
    assert {"save_company", "read_document", "due_dates", "fill_form", "law_search", "build_dossier"} <= names


def test_errors_reach_claude_as_plain_sentences(settings):
    result = call(settings, "save_company", {"fields": {"name": "X", "pan": "ABCPE1234F"}, "source": USER})
    assert result.is_error and "director's PAN" in text_of(result)
    result = call(settings, "save_company", {"fields": {"name": "X", "cin": "U123"}, "source": USER})
    assert result.is_error and "neither a CIN" in text_of(result)


def test_a_document_is_read_and_cited(settings, tmp_path):
    pdf = write_pdf(tmp_path / "coi.pdf", ["Certificate of Incorporation\nRegistrar of Companies, Mumbai", ""])

    async def steps(client):
        await client.call_tool("save_company", {"fields": ACME, "source": USER})
        ingested = await client.call_tool(
            "ingest_document", {"path": str(pdf), "company": "Acme", "doc_type": "certificate_of_incorporation"}
        )
        document_id = ingested.structured_content["document_id"]
        read = await client.call_tool("read_document", {"document_id": document_id, "pages": "all"})
        saved = await client.call_tool(
            "save_company",
            {
                "company": "Acme",
                "fields": {"roc": "RoC-Mumbai"},
                "source": {"kind": "document", "document_id": document_id, "page": 1, "quote": "Registrar of Companies, Mumbai"},
            },
        )
        history = await client.call_tool("field_history", {"entity": "company", "record_id": saved.structured_content["company_id"], "field": "roc"})
        return read, history

    read, history = run(_session(settings, steps))
    assert "Registrar of Companies, Mumbai" in text_of(read)
    assert [block.type for block in read.content].count("image") == 1  # page 2 has no text layer
    entry = history.structured_content["history"][0]
    assert (entry["source_kind"], entry["page"], entry["quote"]) == ("document", 1, "Registrar of Companies, Mumbai")


def test_a_filing_closes_its_due_date(settings):
    agm = (date.today() - timedelta(days=5)).isoformat()

    async def steps(client):
        saved = await client.call_tool("save_company", {"fields": ACME, "source": USER})
        company_id = saved.structured_content["company_id"]
        await client.call_tool("save_meeting", {"fields": {"company_id": company_id, "kind": "agm", "date": agm}, "source": USER})
        before = await client.call_tool("due_dates", {"company": "Acme"})
        aoc4 = next(i for i in before.structured_content["items"] if i["form"] == "AOC-4")
        filing = await client.call_tool("start_filing", {"company": "Acme", "form": "AOC-4", "trigger": aoc4["trigger"]})
        filed = await client.call_tool(
            "update_filing", {"filing_id": filing.structured_content["id"], "status": "submitted", "srn": "AB1234567", "filed_on": date.today().isoformat()}
        )
        after = await client.call_tool("due_dates", {"company": "Acme"})
        return filing, filed, after

    filing, filed, after = run(_session(settings, steps))
    assert filing.structured_content["folder"].startswith(f"clients/{ACME['cin']}/filings/")
    assert (settings.home / filing.structured_content["folder"]).is_dir()
    assert filed.structured_content["srn"] == "AB1234567"
    assert "AOC-4" not in [i["form"] for i in after.structured_content["items"]]


def test_draft_from_the_sample_template(settings):
    async def steps(client):
        await client.call_tool("save_company", {"fields": ACME, "source": USER})
        templates = await client.call_tool("list_templates", {})
        sample = templates.structured_content["templates"][0]
        missing = await client.call_tool("render_draft", {"company": "Acme", "template": sample["template"]})
        extra = {key: "x" for key in sample["extra"]} | {"meeting_date": "2026-10-01", "appointee_name": "Vikram Shah"}
        drafted = await client.call_tool("render_draft", {"company": "Acme", "template": sample["template"], "extra": extra})
        return missing, drafted

    missing, drafted = run(_session(settings, steps))
    assert missing.is_error and "also needs these extra values" in text_of(missing)
    text = "\n".join(p.text for p in docx.Document(drafted.structured_content["path"]).paragraphs)
    assert "ACME WIDGETS PRIVATE LIMITED" in text and "01-10-2026" in text and "VIKRAM SHAH" in text


def test_law_search_points_to_the_section(settings):
    sections = {
        "92": "Annual return. (1) Every company shall prepare a return in the prescribed form containing the particulars "
        "as they stood on the close of the financial year regarding its registered office and members.",
        "137": "Copy of financial statement to be filed with Registrar. (1) A copy of the financial statements, including "
        "consolidated financial statement, if any, along with all the documents which are required to be or attached to "
        "such financial statements under this Act, duly adopted at the annual general meeting of the company, shall be "
        "filed with the Registrar within thirty days of the date of annual general meeting.",
        "139": "Appointment of auditors. (1) Every company shall, at the first annual general meeting, appoint an "
        "individual or a firm as an auditor who shall hold office till the conclusion of its sixth annual general meeting.",
    }
    (settings.law_dir / "Companies_Act_2013_extract.txt").write_text(
        "\n".join(f"{number}. {body}" for number, body in sections.items()), encoding="utf-8"
    )
    result = call(settings, "law_search", {"query": "financial statements filed within thirty days"})
    top = result.structured_content["results"][0]
    assert top["locator"].startswith("s.137") and top["title"] == "Companies Act 2013 extract"


def test_empty_law_folder_says_so(settings):
    result = call(settings, "law_search", {"query": "annual return"})
    assert result.structured_content["results"] == [] and "law folder is empty" in result.structured_content["message"]


def test_dossier_lists_people_dates_and_gaps(settings):
    async def steps(client):
        saved = await client.call_tool("save_company", {"fields": {**ACME, "roc": "RoC-Mumbai"}, "source": USER})
        company_id = saved.structured_content["company_id"]
        party = await client.call_tool(
            "save_party", {"fields": {"kind": "individual", "name": "Asha Rao", "din": "01234567", "pan": "ABCPE1234F"}, "source": USER}
        )
        await client.call_tool(
            "save_appointment",
            {"fields": {"company_id": company_id, "party_id": party.structured_content["party_id"], "role": "director",
                        "date_of_appointment": "2015-06-01"}, "source": USER},
        )
        return await client.call_tool("build_dossier", {"company": "Acme"})

    result = run(_session(settings, steps))
    markdown = result.structured_content["markdown"]
    assert "| Asha Rao | 01234567 | Director |" in markdown
    assert "1 director(s) on file; a private company needs at least 2 (s.149(1))." in markdown
    assert "No current statutory auditor on file." in markdown
    assert "ABCPE1234F" not in markdown
    assert Path(result.structured_content["path"]).is_file()
