"""The loop as she will use it: a real browser window with a debugging port, driven only through the MCP tools."""

from pathlib import Path

import pytest
from helpers import ACME, browser_or_skip, close_browser, run
from mcp import Client

from csdesk.browser import chrome
from csdesk.server import build_server
from csdesk.vault import Vault

pytestmark = pytest.mark.browser
USER = {"kind": "user"}


def test_fill_the_practice_form_through_the_tools(settings):
    browser_or_skip()
    chrome.launch(settings, url="about:blank", headless=True)
    try:

        async def steps():
            async with Client(build_server(settings)) as client:
                await client.call_tool("save_company", {"fields": ACME, "source": USER})
                party = await client.call_tool(
                    "save_party",
                    {"fields": {"kind": "individual", "name": "Asha Rao", "din": "01234567", "pan": "ABCPE1234F"}, "source": USER},
                )
                filing = await client.call_tool("start_filing", {"company": "Acme", "form": "DEMO-1"})
                opened = await client.call_tool("browser_open", {"url": "practice"})
                status = await client.call_tool("browser_status", {})
                filled = await client.call_tool(
                    "fill_form",
                    {
                        "filing_id": filing.structured_content["id"],
                        "party_id": party.structured_content["party_id"],
                        "extra": {"date_of_appointment": "2026-10-01", "designation": "Additional Director"},
                    },
                )
                refused = await client.call_tool("browser_open", {"url": "https://example.com/"})
                shot = await client.call_tool("browser_screenshot", {"filing_id": filing.structured_content["id"]})
                return filing, opened, status, filled, refused, shot

        filing, opened, status, filled, refused, shot = run(steps())
        assert not opened.is_error, opened.content
        assert any("demo_form.html" in tab["url"] for tab in status.structured_content["tabs"])
        assert not filled.is_error, filled.content
        summary = filled.content[0].text
        assert '"status": "ready_for_review"' in summary and "XXXXXX234F" in summary
        assert "ABCPE1234F" not in summary
        assert [block.type for block in filled.content] == ["text", "image"]
        assert refused.is_error and "only opens" in refused.content[0].text
        assert shot.content[-1].type == "image", shot.content
        folder = settings.home / filing.structured_content["folder"]
        assert list(folder.glob("*-DEMO-1-fill-log.json")) and list(folder.glob("*-screen.png"))
        with Vault.open(settings.db_path) as vault:
            assert vault.filing(filing.structured_content["id"])["status"] == "ready_for_review"
        # The tools detached without closing her window.
        assert chrome.debug_info(settings.cdp_port) is not None
    finally:
        run(close_browser(settings.cdp_port))


def test_tools_say_plainly_when_the_window_is_closed(settings):
    async def steps():
        async with Client(build_server(settings)) as client:
            return await client.call_tool("browser_status", {}), await client.call_tool("browser_open", {"url": "practice"})

    status, opened = run(steps())
    assert status.structured_content["open"] is False
    assert opened.is_error and "isn't open" in opened.content[0].text
    assert not Path(settings.browser_profile_dir, "Default").exists()  # nothing was launched behind her back
