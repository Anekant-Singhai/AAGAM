import json
import socket
import sys

from aagam import cli, doctor
from aagam.config import AagamSettings


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aagam(settings, **changes) -> AagamSettings:
    # Port 1 refuses at once, so the Ollama check doesn't wait on a real Ollama.
    return AagamSettings(core=settings, web_port=_free_port(), local_ai_url="http://127.0.0.1:1", **changes)


def test_checks_cover_everything_and_say_how_to_fix(settings, tmp_path):
    checks = doctor.run_checks(_aagam(settings), claude_config=tmp_path / "claude_desktop_config.json")

    assert [c.key for c in checks] == [
        "python", "data_folder", "database", "interface", "port", "ocr", "browser", "local_ai", "claude_desktop", "disk",
    ]
    for c in checks:
        assert c.status in (doctor.OK, doctor.WARN, doctor.FAIL)
        assert c.label and c.detail
        if c.status != doctor.OK:
            assert c.fix, c
    by_key = {c.key: c for c in checks}
    assert by_key["python"].status == doctor.OK
    assert by_key["data_folder"].status == doctor.OK
    assert by_key["database"].status == doctor.OK
    assert by_key["port"].status == doctor.OK
    # Optional parts are warnings, never failures.
    assert by_key["local_ai"].status == doctor.WARN
    assert by_key["claude_desktop"].status == doctor.WARN
    assert not list(settings.home.glob(".aagam-doctor-*")), "the write probe is cleaned up"


def test_missing_data_folder_fails_with_a_fix(settings, tmp_path):
    from csdesk.config import Settings

    missing = AagamSettings(core=Settings(home=tmp_path / "nowhere"), web_port=_free_port(), local_ai=False)
    checks = {c.key: c for c in doctor.run_checks(missing, claude_config=tmp_path / "none.json")}

    assert checks["data_folder"].status == doctor.FAIL
    assert "aagam init" in checks["data_folder"].fix
    assert checks["local_ai"].status == doctor.OK  # turned off is fine
    assert doctor.exit_code(list(checks.values())) == 1
    assert not (tmp_path / "nowhere").exists(), "doctor doesn't create the data folder"


def test_claude_desktop_entry_is_recognised(settings, tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    entry = {"command": sys.executable, "args": ["-m", "aagam", "mcp"], "env": {"AAGAM_HOME": str(settings.home)}}
    config.write_text(json.dumps({"mcpServers": {"aagam": entry}}), encoding="utf-8")
    assert doctor.check_claude_desktop(_aagam(settings), config).status == doctor.OK

    entry["env"]["AAGAM_HOME"] = str(tmp_path / "elsewhere")
    config.write_text(json.dumps({"mcpServers": {"aagam": entry}}), encoding="utf-8")
    assert doctor.check_claude_desktop(_aagam(settings), config).status == doctor.WARN

    config.write_text("{not json", encoding="utf-8")
    assert doctor.check_claude_desktop(_aagam(settings), config).status == doctor.WARN


def test_report_marks_and_exit_code():
    checks = [
        doctor.Check("a", "First", doctor.OK, "fine"),
        doctor.Check("b", "Second", doctor.WARN, "meh", "do this"),
        doctor.Check("c", "Third", doctor.FAIL, "broken", "do that"),
    ]
    text = doctor.report(checks, "utf-8")
    assert "✓ First" in text and "! Second" in text and "✗ Third" in text
    assert "-> do that" in text and "-> do this" in text
    assert doctor.exit_code(checks) == 1
    assert doctor.exit_code(checks[:2]) == 0
    assert "X  Third" in doctor.report(checks, "cp1252"), "falls back to plain marks on a console that can't show them"


def test_cli_doctor(settings, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("AAGAM_HOME", str(settings.home))
    monkeypatch.setenv("AAGAM_PORT", str(_free_port()))
    monkeypatch.setenv("AAGAM_LOCAL_AI", "off")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "Data folder" in out and str(settings.home) in out
    assert code in (0, 1)  # depends on this computer's browser; the structure is what's tested
