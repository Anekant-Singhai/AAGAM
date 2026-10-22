"""AAGAM's MCP server as Claude Desktop sees it."""

import os
import sys

from helpers import ACME, run, write_notice_pdf
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from aagam.config import AagamSettings
from aagam.mcp_server import build


def test_claude_can_bring_in_find_and_summarise(settings, tmp_path):
    server = build(AagamSettings(core=settings, local_ai=False))
    pdf = write_notice_pdf(tmp_path / "Acme AGM notice.pdf")

    async def steps():
        async with Client(server) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            await client.call_tool("save_company", {"fields": ACME, "source": {"kind": "user"}})
            added = await client.call_tool("ingest_document", {"path": str(pdf), "tags": ["precedent"]})
            found = await client.call_tool("library_search", {"query": "principal business activities"})
            precedents = await client.call_tool("precedent_search", {"section": "186", "resolution_kind": "special", "min_crore": 50})
            full = await client.call_tool("precedent_get", {"resolution_id": precedents.structured_content["resolutions"][0]["id"]})
            summary = await client.call_tool("library_save_summary", {"document_id": 1, "summary": "AGM notice with s.185/186 resolutions."})
            limits = await client.call_tool(
                "loan_limits",
                {"paid_up_capital": 100_000_000, "free_reserves": 500_000_000, "securities_premium": 200_000_000,
                 "proposed_loans_investments": 1_000_000_000, "company": "Acme"},
            )
            read = await client.call_tool("read_document", {"document_id": 1, "pages": "4"})
            status = await client.call_tool("local_ai_status", {})
            return tools, added, found, precedents, full, summary, limits, read, status

    tools, added, found, precedents, full, summary, limits, read, status = run(steps())
    assert {"due_dates", "fill_form", "record_start", "save_company", "library_search", "precedent_search", "loan_limits"} <= tools
    assert added.structured_content["doc_type"] == "notice"
    assert found.structured_content["documents"][0]["pages"] == [2, 4]
    assert precedents.structured_content["count"] == 1 and "section 186(2)" in full.structured_content["statement"]
    assert summary.structured_content["summary"].startswith("AGM notice")
    assert limits.structured_content["s186"]["status"] == "special_resolution"
    assert "ITEM NO: 1" in read.content[1].text
    assert status.structured_content["message"] == "Local AI is turned off."


def test_aagam_mcp_over_stdio_as_claude_desktop_starts_it(tmp_path):
    home = tmp_path / "home"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aagam", "mcp"], env={**os.environ, "AAGAM_HOME": str(home), "AAGAM_LOCAL_AI": "off"}
    )

    async def steps():
        async with Client(params) as client:
            return await client.list_tools(), await client.call_tool("library_list", {})

    tools, listed = run(steps())
    assert len(tools.tools) >= 44
    assert listed.structured_content == {"total": 0, "documents": []}
    assert (home / "logs" / "aagam-mcp.log").exists()
