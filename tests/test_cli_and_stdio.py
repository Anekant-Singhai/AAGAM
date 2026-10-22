import getpass
import json
import os
import sys

from helpers import ACME, USER, run
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from csdesk.cli import main
from csdesk.config import load_settings
from csdesk.vault import Vault


def test_init_sets_up_and_prints_the_claude_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    assert '"csdesk"' in out and '"serve"' in out
    assert (tmp_path / "home" / "templates" / "sample-board-resolution-additional-director.docx").is_file()


def test_due_prints_the_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    with Vault.open(load_settings().db_path) as vault:
        vault.save("company", ACME, USER)
    assert main(["due"]) == 0
    assert "Acme Widgets" in capsys.readouterr().out


def test_errors_are_one_plain_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    assert main(["due", "--company", "Nobody"]) == 1
    assert "No company matches 'Nobody'" in capsys.readouterr().err


def test_set_sensitive_keeps_the_number_out_of_sight(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    with Vault.open(load_settings().db_path) as vault:
        party_id = vault.save("party", {"kind": "individual", "name": "Asha Rao"}, USER)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "abcpe1234f")
    assert main(["set-sensitive", "--party", str(party_id), "--field", "pan"]) == 0
    out = capsys.readouterr().out
    assert "XXXXXX234F" in out and "ABCPE1234F" not in out
    with Vault.open(load_settings().db_path) as vault:
        assert vault.party(party_id, reveal=True)["pan"] == "ABCPE1234F"
        assert vault.field_history("party", party_id, "pan")[-1]["recorded_by"] == "user"


def test_claude_config_is_merged_with_a_backup(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    path = tmp_path / "claude_desktop_config.json"
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    assert main(["claude-config", "--write", "--path", str(path)]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["mcpServers"]) == {"other", "csdesk"} and data["theme"] == "dark"
    assert data["mcpServers"]["csdesk"]["env"]["AAGAM_HOME"] == str(tmp_path / "home")
    assert len(list(tmp_path.glob("claude_desktop_config.json.*.bak"))) == 1


def test_a_broken_claude_config_is_left_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    path = tmp_path / "claude_desktop_config.json"
    path.write_text("{ not json", encoding="utf-8")
    assert main(["claude-config", "--write", "--path", str(path)]) == 1
    assert path.read_text(encoding="utf-8") == "{ not json"
    assert "isn't valid JSON" in capsys.readouterr().err


def test_serve_speaks_mcp_over_stdio_like_claude_desktop_starts_it(tmp_path):
    home = tmp_path / "home"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "csdesk", "serve"], env={**os.environ, "AAGAM_HOME": str(home)}
    )

    async def steps():
        async with Client(params) as client:
            return await client.list_tools(), await client.call_tool("csdesk_info", {})

    tools, info = run(steps())
    assert len(tools.tools) >= 30
    assert info.structured_content["data_folder"] == str(home)
    assert (home / "logs" / "csdesk.log").exists()
