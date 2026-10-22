"""Folders brought into the library: what is read and what is left out, where each document came from and whose it
is, passes that read only what is new, stop when asked and pick up where they stopped."""

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import ACME, USER, run, write_notice_pdf, write_pdf
from mcp import Client

from aagam import editing, folders, library
from aagam.cli import main
from aagam.config import AagamSettings
from aagam.db import open_db
from aagam.mcp_server import build
from aagam.web import folders_api
from aagam.web.app import create_app
from csdesk.documents import intake
from csdesk.errors import Invalid, NotFound

CHANGE = {"X-AAGAM": "1"}
BETA = {"name": "Beta Traders Private Limited", "cin": "U51909DL2018PTC334455"}


def vault_of(settings):
    return open_db(settings.db_path, actor="test")


LONG_AGO = 1_700_000_000  # 14 November 2023: undated files last changed then


def build_tree(root: Path) -> Path:
    """A client folder as a CS keeps one, with the things that aren't documents mixed in. Returned as Windows names it."""
    agm = root / "Acme Widgets" / "2025-26" / "AGM"
    agm.mkdir(parents=True)
    write_notice_pdf(agm / "AGM notice.pdf")
    (root / "Acme Widgets" / "2025-26" / "letter.txt").write_text("Date: 15.04.2025\nTo the Board of Directors\nSub: Statutory registers", encoding="utf-8")
    (root / "Beta").mkdir()
    write_pdf(root / "Beta" / "statement.pdf", ["Beta Traders Private Limited\nCIN: U51909DL2018PTC334455\nStatement of stock as on date"])
    (root / "Unsorted").mkdir()
    (root / "Unsorted" / "memo.txt").write_text("A note to self about nothing in particular.", encoding="utf-8")
    for undated in (root / "Beta" / "statement.pdf", root / "Unsorted" / "memo.txt"):
        os.utime(undated, (LONG_AGO, LONG_AGO))
    (root / "broken.pdf").write_bytes(b"%PDF-1.4 this is not really a PDF")
    (root / "old.doc").write_bytes(b"\xd0\xcf\x11\xe0 an old Word file")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "secret.txt").write_text("never read", encoding="utf-8")
    (root / "~$draft.docx").write_bytes(b"owner file")
    (root / "desktop.ini").write_text("[.ShellClassInfo]", encoding="utf-8")
    return Path(os.path.realpath(root))


READABLE = {"Acme Widgets/2025-26/AGM/AGM notice.pdf", "Acme Widgets/2025-26/letter.txt", "Beta/statement.pdf",
            "Unsorted/memo.txt", "broken.pdf"}


def docs_by_name(vault):
    return {d["original_name"]: library.document(vault, d["id"]) for d in library.list_documents(vault, limit=100)["documents"]}


# ------------------------------------------------------------------ walking


def test_the_walk_leaves_out_what_isnt_hers(settings, tmp_path):
    build_tree(tmp_path / "Clients")
    (settings.home / "clients" / "kept-copy.txt").write_text("AAGAM's own copy", encoding="utf-8")
    tree = folders.scan(tmp_path, settings.home)  # AAGAM's data folder (tmp_path/home) sits inside this one
    # A folder's own files first, then the folders inside it, each in name order.
    assert [rel for rel, _, _ in tree.files] == [
        "Clients/broken.pdf", "Clients/Acme Widgets/2025-26/letter.txt", "Clients/Acme Widgets/2025-26/AGM/AGM notice.pdf",
        "Clients/Beta/statement.pdf", "Clients/Unsorted/memo.txt"]
    assert {rel for rel, _, _ in tree.files} == {f"Clients/{r}" for r in READABLE}
    assert tree.skipped == {".doc": 1} and tree.too_big == 0 and tree.folders == 6  # Clients, and the five inside it
    assert all(len(modified) == 19 for _, _, modified in tree.files)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows hidden files and junctions")
def test_hidden_files_and_junctions_are_not_followed(tmp_path):
    root = tmp_path / "Clients"
    root.mkdir()
    (root / "kept.txt").write_text("hers", encoding="utf-8")
    hidden = root / "hidden.txt"
    hidden.write_text("hidden by Windows", encoding="utf-8")
    import ctypes

    ctypes.windll.kernel32.SetFileAttributesW(str(hidden), 0x2)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "far.txt").write_text("not under Clients", encoding="utf-8")
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "link"), str(elsewhere)], capture_output=True)
    tree = folders.scan(root)
    rels = {rel for rel, _, _ in tree.files}
    assert "hidden.txt" not in rels and "kept.txt" in rels
    if made.returncode == 0:
        assert not any(rel.startswith("link/") for rel in rels)


def test_preview_counts_and_refuses_what_it_cant_take(settings, tmp_path):
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        seen = folders.preview(vault, settings.home, f'"{root}"')  # as Explorer's "Copy as path" gives it
        assert (seen["exists"], seen["files"], seen["folders"], seen["skipped"], seen["truncated"]) == (True, 5, 5, {".doc": 1}, False)
        assert seen["by_kind"] == {"pdf": 3, "text": 2} and seen["already_added"] is None
        assert seen["bytes"] == sum((root / r).stat().st_size for r in READABLE)
        assert set(seen["sample"]) <= READABLE
        assert folders.preview(vault, settings.home, str(tmp_path / "nowhere"))["exists"] is False
        for bad in (str(root / "Unsorted" / "memo.txt"), str(settings.home / "clients"), "Clients", "  "):
            with pytest.raises(Invalid):
                folders.preview(vault, settings.home, bad)
        with pytest.raises(NotFound):
            folders.add_folder(vault, settings.home, tmp_path / "nowhere")


# ------------------------------------------------------------------- passes


def test_a_folder_is_read_with_where_each_document_came_from_and_whose_it_is(settings, tmp_path):
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        acme = vault.save("company", ACME, USER)
        beta = vault.save("company", BETA, USER)
        folder = folders.add_folder(vault, settings.home, root, tags=["Imported 2026"])
    assert folder["status"] == "queued" and folder["tags"] == ["imported 2026"] and folder["exists"]
    assert folders.run_queue(settings, "test") == 1
    with vault_of(settings) as vault:
        done = folders.get(vault, folder["id"], details=True)
        assert (done["status"], done["found"], done["done"], done["added"], done["already"], done["failed"]) == ("done", 5, 5, 4, 0, 1)
        assert done["skipped"] == {".doc": 1} and done["documents"] == 4 and done["finished_at"]
        assert [f["rel_path"] for f in done["failures"]] == ["broken.pdf"] and "Couldn't open" in done["failures"][0]["error"]
        docs = docs_by_name(vault)
        notice = docs["AGM notice.pdf"]
        assert notice["source_path"] == str(root / "Acme Widgets" / "2025-26" / "AGM" / "AGM notice.pdf")
        assert (notice["source_folder"], notice["folder_id"], notice["folder_path"]) == ("Acme Widgets/2025-26/AGM", folder["id"], str(root))
        assert notice["file_modified"] and notice["doc_date"] == "2026-09-30" and notice["fy"] == "2026-27"
        assert notice["company_id"] == acme and notice["client_why"] == "the folder “Acme Widgets”"
        assert "imported 2026" in {t["name"] for t in notice["tags"]}
        letter = docs["letter.txt"]
        assert (letter["doc_date"], letter["doc_date_basis"], letter["company_id"]) == ("2025-04-15", "“Date: 15.04.2025”", acme)
        statement = docs["statement.pdf"]
        assert statement["company_id"] == beta and statement["client_why"] == "its CIN U51909DL2018PTC334455"
        memo = docs["memo.txt"]
        assert memo["company_id"] is None and memo["doc_date_basis"] == "the day the file was last changed"
        assert library.list_documents(vault, folder_id=folder["id"], within="Acme Widgets")["total"] == 2
        assert library.list_documents(vault, folder_id=folder["id"], within="Acme Widgets/2025-26/AGM")["total"] == 1


def test_one_client_no_client_and_other_companies_documents(settings, tmp_path):
    with vault_of(settings) as vault:
        acme = vault.save("company", ACME, USER)
        vault.save("company", BETA, USER)
    made = {}
    for name in ("one", "none", "precedent"):
        root = tmp_path / name / "Beta"
        root.mkdir(parents=True)
        write_pdf(root / f"{name}.pdf", [f"Beta Traders Private Limited\nCIN: U51909DL2018PTC334455\nFile {name}"])
        made[name] = root.parent
    with vault_of(settings) as vault:
        folders.add_folder(vault, settings.home, made["one"], "one", acme)
        folders.add_folder(vault, settings.home, made["none"], "none")
        folders.add_folder(vault, settings.home, made["precedent"], precedent=True)
        with pytest.raises(Invalid):
            folders.add_folder(vault, settings.home, made["one"], "one", None)
        with pytest.raises(Invalid):
            folders.add_folder(vault, settings.home, made["one"], "sometimes")
    assert folders.run_queue(settings, "test") == 3
    with vault_of(settings) as vault:
        docs = docs_by_name(vault)
        assert docs["one.pdf"]["company_id"] == acme  # every file is that client's, whatever it says
        assert docs["none.pdf"]["company_id"] is None
        assert docs["precedent.pdf"]["company_id"] is None and "precedent" in {t["name"] for t in docs["precedent.pdf"]["tags"]}


def test_a_second_look_reads_only_what_is_new_or_changed(settings, tmp_path):
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        folder_id = folders.add_folder(vault, settings.home, root)["id"]
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        docs = docs_by_name(vault)
        editing.delete_document(vault, settings.home, docs["letter.txt"]["id"])  # she deletes one: it stays deleted
        folders.queue_scan(vault, folder_id)
    (root / "Unsorted" / "new.txt").write_text("Date: 01.10.2026\nA new note.", encoding="utf-8")
    memo = root / "Unsorted" / "memo.txt"
    memo.write_text("A note to self, rewritten.", encoding="utf-8")
    os.utime(memo, (memo.stat().st_atime, memo.stat().st_mtime + 120))
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        again = folders.get(vault, folder_id, details=True)
        # new.txt and the changed memo come in; broken.pdf, failed last time, is tried again.
        assert (again["found"], again["added"], again["already"], again["failed"]) == (3, 2, 0, 1)
        names = sorted(d["original_name"] for d in library.list_documents(vault, limit=50)["documents"])
        assert names == ["AGM notice.pdf", "memo.txt", "memo.txt", "new.txt", "statement.pdf"]  # the earlier memo stays
        folders.queue_scan(vault, folder_id)
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        assert folders.get(vault, folder_id)["found"] == 1  # only the broken file, still failing


def test_the_same_file_elsewhere_is_already_in_the_library(settings, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    write_pdf(first / "copy.pdf", ["The same letter, kept twice"])
    (second / "copy again.pdf").write_bytes((first / "copy.pdf").read_bytes())
    with vault_of(settings) as vault:
        # Brought in by hand first, with no folder: the folder pass says where it came from.
        loose = library.add_document(vault, settings, first / "copy.pdf", queue_ai=False)["id"]
        folder_id = folders.add_folder(vault, settings.home, second)["id"]
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        seen = folders.get(vault, folder_id, details=True)
        assert (seen["added"], seen["already"]) == (0, 1) and seen["recent"][0]["document_id"] == loose
        assert library.document(vault, loose)["folder_id"] == folder_id


def test_she_can_stop_a_pass_and_a_budget_leaves_the_rest_for_later(settings, tmp_path):
    root = tmp_path / "Many"
    root.mkdir()
    for n in range(5):
        (root / f"note {n}.txt").write_text(f"Note number {n}", encoding="utf-8")
    with vault_of(settings) as vault:
        folder_id = folders.add_folder(vault, settings.home, root)["id"]

    assert folders.run_queue(settings, "test", folder_id=folder_id, budget=0) == 0  # no time at all: nothing is claimed
    with vault_of(settings) as vault:
        assert folders.claim(vault, "test") == folder_id
    left = folders.run_pass(settings, folder_id, budget=0)
    assert (left["status"], left["found"], left["done"]) == ("queued", 5, 0)

    def stop_after_first(rel, status, error):
        with vault_of(settings) as vault:
            folders.stop(vault, folder_id)

    folders.run_queue(settings, "test", on_file=stop_after_first)
    with vault_of(settings) as vault:
        stopped = folders.get(vault, folder_id)
        assert (stopped["status"], stopped["done"], stopped["current"]) == ("stopped", 1, None)
        folders.queue_scan(vault, folder_id)
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        finished = folders.get(vault, folder_id)
        assert (finished["status"], finished["found"], finished["added"]) == ("done", 4, 4)
        assert finished["documents"] == 5


def test_a_file_that_goes_mid_pass_is_passed_over(settings, tmp_path):
    root = tmp_path / "Going"
    root.mkdir()
    for n in range(3):
        (root / f"{n}.txt").write_text(f"file {n}", encoding="utf-8")
    with vault_of(settings) as vault:
        folder_id = folders.add_folder(vault, settings.home, root)["id"]

    def remove_the_last(rel, status, error):
        (root / "2.txt").unlink(missing_ok=True)

    folders.run_queue(settings, "test", on_file=remove_the_last)
    with vault_of(settings) as vault:
        seen = folders.get(vault, folder_id)
        assert (seen["status"], seen["found"], seen["done"], seen["added"], seen["failed"]) == ("done", 2, 2, 2, 0)


def test_claims_are_one_at_a_time_and_dead_passes_are_taken_up(settings, tmp_path):
    root = tmp_path / "Claimed"
    root.mkdir()
    with vault_of(settings) as vault:
        folder_id = folders.add_folder(vault, settings.home, root)["id"]
        assert folders.claim(vault, "mcp:1") == folder_id
        assert folders.claim(vault, "web:2") is None  # someone is reading it
        vault.conn.execute("UPDATE folders SET heartbeat = datetime('now', '-20 minutes') WHERE id = ?", (folder_id,))
        assert folders.claim(vault, "web:2") == folder_id  # not heard from: taken over
        assert folders.get(vault, folder_id)["worker"] == "web:2"
    # A web server starting finds its predecessor's pass, which can't still be running.
    folders_api.helpers(AagamSettings(core=settings, local_ai=False))
    with vault_of(settings) as vault:
        assert folders.get(vault, folder_id)["status"] == "queued"


def test_watched_folders_are_looked_at_again(settings, tmp_path):
    roots = []
    for name in ("watched", "once", "stopped"):
        (tmp_path / name).mkdir()
        roots.append(tmp_path / name)
    with vault_of(settings) as vault:
        ids = [folders.add_folder(vault, settings.home, roots[0], watch=True)["id"],
               folders.add_folder(vault, settings.home, roots[1])["id"],
               folders.add_folder(vault, settings.home, roots[2], watch=True)["id"]]
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        folders.queue_scan(vault, ids[2])
        folders.stop(vault, ids[2])
        assert folders.queue_watched(vault, 10) == 0  # just read
        vault.conn.execute("UPDATE folders SET finished_at = datetime('now', '-11 minutes')")
        assert folders.queue_watched(vault, 10) == 1
        assert [folders.get(vault, i)["status"] for i in ids] == ["queued", "done", "stopped"]
    (roots[0] / "arrived.txt").write_text("Date: 02.10.2026\nArrived later", encoding="utf-8")
    worker = folders.FolderWorker(AagamSettings(core=settings, local_ai=False))
    worker.last_watch = 10**12  # not time to look at watched folders yet; the queued one is read
    assert worker.tick() == 1
    with vault_of(settings) as vault:
        assert folders.get(vault, ids[0])["added"] == 1


def test_the_worker_dates_documents_read_before_dates_were_worked_out(settings, tmp_path):
    (tmp_path / "old.txt").write_text("Date: 05.06.2024\nAn old letter.", encoding="utf-8")
    with vault_of(settings) as vault:
        document_id = library.add_document(vault, settings, tmp_path / "old.txt", queue_ai=False)["id"]
        vault.conn.execute("UPDATE doc_meta SET doc_date = NULL, doc_date_basis = NULL WHERE document_id = ?", (document_id,))
    worker = folders.FolderWorker(AagamSettings(core=settings, local_ai=False))
    worker.last_watch = 10**12
    assert worker.tick() == 0
    with vault_of(settings) as vault:
        assert library.document(vault, document_id)["doc_date"] == "2024-06-05"


def test_forgetting_a_folder_keeps_or_trashes_its_documents(settings, tmp_path):
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        folder_id = folders.add_folder(vault, settings.home, root)["id"]
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        assert folders.forget(vault, settings.home, folder_id) == {"forgotten": folder_id, "documents_trashed": 0}
        kept = library.list_documents(vault, limit=50)["documents"]
        assert len(kept) == 4 and all(d["folder_id"] is None for d in kept) and all(d["source_folder"] is not None for d in kept)
        assert vault.conn.execute("SELECT COUNT(*) FROM folder_files").fetchone()[0] == 0
        with pytest.raises(NotFound):
            folders.get(vault, folder_id)
        again = folders.add_folder(vault, settings.home, root)["id"]
    folders.run_queue(settings, "test")
    with vault_of(settings) as vault:
        assert folders.get(vault, again)["already"] == 4
        assert folders.forget(vault, settings.home, again, trash_documents=True)["documents_trashed"] == 4
        assert library.list_documents(vault)["total"] == 0
    assert (root / "Beta" / "statement.pdf").is_file()  # her own files are never touched


# --------------------------------------------------------------- reading ahead


def test_files_are_read_ahead_in_order_on_other_threads(tmp_path, monkeypatch):
    for name in ("a.txt", "c.txt"):
        (tmp_path / name).write_text(f"text of {name}", encoding="utf-8")
    threads = []

    def noting(path):
        threads.append(threading.current_thread().name)
        return intake.prepare(path)

    monkeypatch.setattr(folders, "prepare", noting)
    items = [("a.txt", 0, ""), ("b.txt", 0, ""), ("c.txt", 0, "")]
    out = list(folders.read_ahead(tmp_path, items, threads=2, window=2))
    assert [item[0] for item, _ in out] == ["a.txt", "b.txt", "c.txt"]
    assert isinstance(out[1][1], FileNotFoundError)
    assert out[0][1].pages[0].text == "text of a.txt" and out[2][1].sha256 == intake._sha256(tmp_path / "c.txt")
    assert all(name.startswith("aagam-read") for name in threads)


def test_prepare_reads_ahead_and_ingest_uses_what_was_read(vault, settings, tmp_path):
    pdf = write_pdf(tmp_path / "letter.pdf", ["A letter of appointment as auditor"])
    assert intake.prepare(pdf).pages[0].text == "A letter of appointment as auditor"
    # PDFs read ahead on several threads at once: PDFium takes them one at a time (intake.PDFIUM).
    pdfs = [write_pdf(tmp_path / f"p{n}.pdf", [f"Page text number {n} " * 5] * 3) for n in range(6)]
    items = [(p.name, p.stat().st_size, "") for p in pdfs]
    out = list(folders.read_ahead(tmp_path, items, threads=3, window=6))
    assert [len(prepared.pages) for _, prepared in out] == [3] * 6
    assert all(prepared.pages[0].text.startswith(f"Page text number {n}") for n, (_, prepared) in enumerate(out))
    text = tmp_path / "note.txt"
    text.write_text("what the file says", encoding="utf-8")
    ready = intake.prepare(text)
    assert ready.size == text.stat().st_size and ready.sha256 == intake._sha256(text)
    read = intake.Prepared(ready.sha256, ready.size, [intake.PageText(1, "what was read ahead", False)])
    info = intake.ingest(vault, settings, text, prepared=read)
    page = vault.conn.execute("SELECT text FROM document_pages WHERE document_id = ?", (info["document_id"],)).fetchone()[0]
    assert page == "what was read ahead"


# ---------------------------------------------------------- web, CLI and MCP


@pytest.fixture
def client(settings):
    app = create_app(AagamSettings(core=settings, local_ai=False), background=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_the_folders_api(client, settings, tmp_path, monkeypatch):
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        acme = vault.save("company", ACME, USER)
    seen = client.post("/api/folders/preview", json={"path": str(root)}, headers=CHANGE).json()
    assert (seen["files"], seen["skipped"]) == (5, {".doc": 1})
    assert client.post("/api/folders", json={"path": str(root)}).status_code == 403  # changes come from the window only

    added = client.post("/api/folders", json={"path": str(root), "company": "auto", "tags": ["imported"], "watch": True}, headers=CHANGE)
    assert added.status_code == 200, added.text
    folder = added.json()
    assert (folder["status"], folder["client_mode"], folder["watch"], folder["documents"], folder["exists"]) == ("queued", "auto", True, 0, True)
    assert [f["id"] for f in client.get("/api/folders").json()["folders"]] == [folder["id"]]
    folders.run_queue(settings, "test")  # what the background worker does
    detail = client.get(f"/api/folders/{folder['id']}").json()
    assert (detail["status"], detail["added"], detail["documents"]) == ("done", 4, 4)
    assert detail["failures"][0]["rel_path"] == "broken.pdf" and len(detail["recent"]) == 5
    listed = client.get("/api/documents", params={"folder": folder["id"], "within": "Acme Widgets"}).json()
    assert listed["total"] == 2

    changed = client.patch(f"/api/folders/{folder['id']}", json={"watch": False, "company": "Acme"}, headers=CHANGE).json()
    assert (changed["watch"], changed["client_mode"], changed["company_id"], changed["client"]) == (False, "one", acme, ACME["name"])
    assert client.patch(f"/api/folders/{folder['id']}", json={"company": "none", "doc_type": ""}, headers=CHANGE).json()["client_mode"] == "none"
    assert client.post(f"/api/folders/{folder['id']}/scan", headers=CHANGE).json()["status"] == "queued"
    assert client.post(f"/api/folders/{folder['id']}/stop", headers=CHANGE).json()["status"] == "stopped"
    assert client.delete(f"/api/folders/{folder['id']}", params={"documents": "bin it"}, headers=CHANGE).status_code == 400
    assert client.delete(f"/api/folders/{folder['id']}", params={"documents": "keep"}, headers=CHANGE).json() == {
        "forgotten": folder["id"], "documents_trashed": 0}
    assert client.get(f"/api/folders/{folder['id']}").status_code == 404
    assert client.post("/api/folders", json={"path": str(settings.home)}, headers=CHANGE).status_code == 400
    assert client.post("/api/folders", json={"path": str(tmp_path / "nowhere")}, headers=CHANGE).status_code == 404

    monkeypatch.setattr(folders, "choose_folder", lambda: str(root))
    assert client.post("/api/folders/browse", headers=CHANGE).json() == {"path": str(root)}


def test_the_folder_dialog_runs_apart_and_says_none_when_it_cant(monkeypatch):
    calls = []

    def answered(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=b"D:/Clients/Acme", stderr=b"")

    monkeypatch.setattr(folders.subprocess, "run", answered)
    assert folders.choose_folder() == str(Path("D:/Clients/Acme"))
    assert calls[0][0] == sys.executable and "askdirectory" in calls[0][2]
    monkeypatch.setattr(folders.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b""))
    assert folders.choose_folder() is None  # she cancelled

    def missing(args, **kwargs):
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(folders.subprocess, "run", missing)
    assert folders.choose_folder() is None


def test_aagam_add_reads_a_folder_in_the_terminal(settings, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AAGAM_HOME", str(settings.home))
    monkeypatch.setenv("AAGAM_LOCAL_AI", "off")
    root = build_tree(tmp_path / "Clients")
    with vault_of(settings) as vault:
        vault.save("company", ACME, USER)
    assert main(["add", str(root)]) == 1  # broken.pdf couldn't be read
    out = capsys.readouterr().out
    single = Path(os.path.realpath(tmp_path)) / "single.txt"
    assert f"Reading {root}" in out and "  Unsorted/memo.txt: added" in out and "  broken.pdf: Couldn't open" in out
    assert "4 added, 0 already in the library, 1 couldn't be read; left out: 1 .doc" in out
    single.write_text("Date: 01.08.2026\nA single letter", encoding="utf-8")
    assert main(["add", str(single), "--company", "Acme"]) == 0
    assert "single.txt: document 5, other" in capsys.readouterr().out
    assert main(["add", str(root)]) == 1  # a second look: only broken.pdf is tried again
    assert "0 added, 0 already in the library, 1 couldn't be read" in capsys.readouterr().out
    with vault_of(settings) as vault:
        doc = library.document(vault, 5)
        assert doc["source_path"] == str(single.resolve()) and doc["doc_date"] == "2026-08-01" and doc["client"] == ACME["name"]


def test_claude_can_bring_in_a_folder_and_follow_it(settings, tmp_path):
    root = build_tree(tmp_path / "Clients")
    server = build(AagamSettings(core=settings, local_ai=False))

    async def steps():
        async with Client(server) as client:
            await client.call_tool("save_company", {"fields": ACME, "source": {"kind": "user"}})
            brought = await client.call_tool("ingest_folder", {"path": str(root), "tags": ["from claude"]})
            status = await client.call_tool("folder_status", {})
            listed = await client.call_tool("library_list", {"fy": "2026-27"})
            single = await client.call_tool("ingest_document", {"path": str(root / "Unsorted" / "memo.txt")})
            return brought, status, listed, single

    brought, status, listed, single = run(steps())
    folder = brought.structured_content
    assert (folder["status"], folder["added"], folder["failed"]) == ("done", 4, 1) and folder["failures"][0]["rel_path"] == "broken.pdf"
    assert [f["path"] for f in status.structured_content["folders"]] == [str(root)]
    assert [d["original_name"] for d in listed.structured_content["documents"]] == ["AGM notice.pdf"]
    assert single.structured_content["already_on_file"] is True
