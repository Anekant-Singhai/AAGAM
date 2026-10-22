"""Backups and the report she can send: her documents stay in the backup, and out of the report."""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from aagam import cli
from aagam.config import AagamSettings
from aagam.maintain import backup_data, redact, support_report
from csdesk.errors import Invalid

TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"


def test_a_token_in_a_log_is_not_left_in_the_clear():
    assert TOKEN not in redact(f"GitHub said {TOKEN} and Bearer {TOKEN}")
    assert "[removed]" in redact(TOKEN)


def test_backup_copies_records_and_leaves_out_the_browser_and_logs(tmp_path):
    home = tmp_path / "home"
    (home / "clients").mkdir(parents=True)
    (home / "clients" / "a.txt").write_text("hello", encoding="utf-8")
    (home / "bin").mkdir()
    (home / "bin" / "gone.pdf").write_bytes(b"%PDF")
    (home / "browser-profile" / "Cookies").parent.mkdir(parents=True)
    (home / "browser-profile" / "Cookies").write_text("secret", encoding="utf-8")
    (home / "logs").mkdir()
    (home / "logs" / "aagam-web.log").write_text("log", encoding="utf-8")
    (home / "csdesk.db-wal").write_bytes(b"wal")
    with sqlite3.connect(home / "csdesk.db") as conn:
        conn.execute("CREATE TABLE t (n)")
        conn.execute("INSERT INTO t VALUES (1)")

    done = backup_data(home, tmp_path / "out")
    dest = Path(done["path"])
    assert (dest / "clients" / "a.txt").read_text(encoding="utf-8") == "hello"
    assert (dest / "bin" / "gone.pdf").read_bytes() == b"%PDF"
    assert not (dest / "browser-profile").exists()
    assert not (dest / "logs").exists()
    assert not (dest / "csdesk.db-wal").exists()
    assert "put your documents and records back" in (dest / "READ ME.txt").read_text(encoding="utf-8")
    with sqlite3.connect(dest / "csdesk.db") as copy:
        assert copy.execute("SELECT n FROM t").fetchone()[0] == 1

    with pytest.raises(Invalid, match="outside"):
        backup_data(home, home / "clients")
    assert not list((home / "clients").glob("AAGAM *")), "a refused backup leaves nothing inside the data folder"


def test_support_report_has_logs_and_not_the_database(settings, tmp_path):
    (settings.home / "logs" / "aagam-web.log").write_text(f"failed with {TOKEN}\n", encoding="utf-8")
    (settings.home / "csdesk.db").write_bytes(b"not a real database and must not be zipped")
    done = support_report(AagamSettings(core=settings, local_ai=False, local_ai_url="http://127.0.0.1:1"), tmp_path)

    with zipfile.ZipFile(done["path"]) as archive:
        names = archive.namelist()
        assert "report.txt" in names and "logs/aagam-web.log" in names
        assert not any(name.endswith(".db") for name in names)
        log = archive.read("logs/aagam-web.log").decode()
        report = archive.read("report.txt").decode()
    assert TOKEN not in log and "[removed]" in log
    assert "not a real database" not in report
    assert TOKEN not in report


def test_backup_and_support_from_the_command(settings, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(settings.home))
    (settings.home / "clients" / "a.txt").write_text("x", encoding="utf-8")
    assert cli.main(["backup", "--to", str(tmp_path / "backups")]) == 0
    assert "A copy of your data is in" in capsys.readouterr().out
    assert cli.main(["support", "--to", str(tmp_path / "reports")]) == 0
    assert "A report is saved here" in capsys.readouterr().out
    assert list((tmp_path / "reports").glob("*.zip")), "the report is a zip she can send"
