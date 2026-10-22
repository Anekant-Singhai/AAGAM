"""Folders on her computer brought into the library: once, or watched for new files.

She points AAGAM at a folder (say D:\\Clients). Every file in it, and in the folders inside it, that AAGAM can read
is copied in and read like any other document; her own files stay where they are. Each document keeps where it
came from, so the library can be narrowed to a folder, and is filed under the client its CIN or LLPIN, its folder's
name or its company name points to (library.client_for). A second look reads only what is new or changed (a changed
file comes in as a new document; the earlier one stays), and a document she deleted isn't brought back.

A pass runs in the background, file by file. A few threads read the next files ahead (their fingerprint and their
text; PDFium takes one PDF at a time, under intake.PDFIUM) while each file is filed in a transaction of its own,
so a long folder never holds the database for long. Progress is kept in the `folders` table: a pass stopped by a
closed AAGAM is taken up again where it stopped, and she can stop one herself.
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import stat as stat_flags
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from csdesk.config import Settings
from csdesk.documents.intake import DOC_TYPES, MAX_BYTES, MEDIA_TYPES, Prepared, prepare
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from . import editing, library
from .db import open_db

log = logging.getLogger("aagam.folders")

CLIENT_MODES = ("auto", "one", "none")  # worked out per file, all one client's, or no client's
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "$recycle.bin", "system volume information"}
TOO_BIG = f"over {MAX_BYTES // (1024 * 1024)} MB"
PREVIEW_FILES = 50_000  # a preview stops counting here...
PREVIEW_SECONDS = 10  # ...or after this long
STALE_MINUTES = 10  # a pass not heard from for this long was left by an AAGAM that closed
WATCH_MINUTES = 10  # how often a watched folder is looked at again
READ_AHEAD_THREADS = 3
READ_AHEAD_FILES = 6
# When a pass started and when a file was read, to the millisecond, so a file that failed in an earlier pass is
# told apart from one that failed in this one (only the first is tried again).
NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"
# Starting a new pass over a folder clears the last one's counts.
NEW_PASS = ("status = 'queued', found = 0, done = 0, added = 0, already = 0, failed = 0, skipped = NULL, error = NULL, "
            "current = NULL, started_at = NULL, finished_at = NULL")


# -------------------------------------------------------------------- walking


@dataclass
class Tree:
    """What a folder holds: the files AAGAM can read, as (path inside it, size, last changed), and what it can't."""

    root: Path
    files: list[tuple[str, int, str]] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)  # by extension, files AAGAM can't read yet
    too_big: int = 0
    folders: int = 0
    unreadable: list[str] = field(default_factory=list)  # folders it wasn't allowed to open
    truncated: bool = False


def _key(path: str | Path) -> str:
    """A path as Windows compares paths: whole, resolved, and without regard to case."""
    return os.path.normcase(os.path.realpath(str(path)))


def inside(path: str | Path, folder: str | Path) -> bool:
    child, parent = _key(path), _key(folder)
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def _modified(seconds: float) -> str:
    return datetime.fromtimestamp(seconds).isoformat(timespec="seconds")


def _hidden(entry: os.DirEntry[str]) -> bool:
    """Names that are never her documents, and (on Windows) anything marked hidden or system."""
    name = entry.name
    if name.startswith((".", "~$")) or name.lower() in SKIP_NAMES:
        return True
    try:
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & (getattr(stat_flags, "FILE_ATTRIBUTE_HIDDEN", 0) | getattr(stat_flags, "FILE_ATTRIBUTE_SYSTEM", 0)))


LINK_TAGS = {getattr(stat_flags, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003), getattr(stat_flags, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)}


def _link(entry: os.DirEntry[str]) -> bool:
    """A shortcut to somewhere else (a symbolic link or a junction): never followed, so nothing is walked twice.
    OneDrive's files are reparse points too, but of another kind, and are read like any other."""
    try:
        if entry.is_symlink() or getattr(entry, "is_junction", lambda: False)():
            return True
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        if not attributes & getattr(stat_flags, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            return False
        return getattr(os.lstat(entry.path), "st_reparse_tag", 0) in LINK_TAGS
    except OSError:
        return True


def scan(root: str | Path, home: Path | None = None, limit: int | None = None, seconds: float | None = None) -> Tree:
    """Every file under `root` that AAGAM can read, folder by folder in name order. Links and junctions aren't
    followed, and AAGAM's own data folder is left out if it is inside. `limit` and `seconds` cut a preview short."""
    root = Path(root)
    tree = Tree(root)
    stop_at = time.monotonic() + seconds if seconds else None
    stack: list[tuple[Path, str]] = [(root, "")]
    while stack:
        folder, rel = stack.pop()
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
        except OSError:
            tree.unreadable.append(rel or ".")
            continue
        below: list[tuple[Path, str]] = []
        for entry in entries:
            if _hidden(entry) or _link(entry):
                continue
            name = entry.name
            path_in = f"{rel}/{name}" if rel else name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if home is not None and inside(entry.path, home):
                        continue
                    below.append((Path(entry.path), path_in))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in MEDIA_TYPES:
                kind = suffix or "(no extension)"
                tree.skipped[kind] = tree.skipped.get(kind, 0) + 1
            elif info.st_size > MAX_BYTES:
                tree.too_big += 1
            else:
                tree.files.append((path_in, info.st_size, _modified(info.st_mtime)))
                if (limit and len(tree.files) >= limit) or (stop_at and time.monotonic() > stop_at):
                    tree.truncated = True
                    return tree
        tree.folders += len(below)
        stack.extend(reversed(below))  # the first by name is walked next
    return tree


def _folder_path(path: str | Path, home: Path, must_exist: bool = True) -> Path:
    """Her folder as a whole path. Quotes from Explorer's "Copy as path" and %VARIABLES% are allowed."""
    text = os.path.expandvars(str(path).strip().strip('"').strip())
    if not text:
        raise Invalid("Choose a folder first.")
    folder = Path(text).expanduser()
    if not folder.is_absolute():
        raise Invalid(f"Give the whole path of the folder, such as D:\\Clients (not {text!r}).")
    folder = Path(os.path.realpath(folder))
    if folder.exists() and not folder.is_dir():
        raise Invalid(f"{folder} is a file, not a folder. Choose the folder it is in, or add the file on its own.")
    if inside(folder, home):
        raise Invalid(f"{folder} is inside AAGAM's own data folder ({home}); choose one of your own folders.")
    if must_exist and not folder.is_dir():
        raise NotFound(f"There is no folder at {folder}. Is the drive connected?")
    return folder


def _kind(name: str) -> str:
    suffix = os.path.splitext(name)[1].lower()
    return next((kind for kind, (_, suffixes) in library.FILE_KINDS.items() if suffix in suffixes), "other")


def preview(vault: Vault, home: Path, path: str | Path) -> dict[str, Any]:
    """What bringing in a folder would mean: how many files AAGAM can read (by kind), their size, how many folders,
    what it would leave out and why. Counting stops after PREVIEW_FILES files or PREVIEW_SECONDS seconds."""
    folder = _folder_path(path, home, must_exist=False)
    empty = {"path": str(folder), "files": 0, "by_kind": {}, "bytes": 0, "folders": 0, "skipped": {}, "too_big": 0, "sample": [],
             "truncated": False, "unreadable": 0}
    row = vault.conn.execute("SELECT id FROM folders WHERE path = ?", (str(folder),)).fetchone()
    if not folder.is_dir():
        return {**empty, "exists": False, "already_added": row["id"] if row else None}
    tree = scan(folder, home, limit=PREVIEW_FILES, seconds=PREVIEW_SECONDS)
    by_kind: dict[str, int] = {}
    for rel, _, _ in tree.files:
        kind = _kind(rel)
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        **empty,
        "exists": True,
        "files": len(tree.files),
        "by_kind": by_kind,
        "bytes": sum(size for _, size, _ in tree.files),
        "folders": tree.folders,
        "skipped": dict(sorted(tree.skipped.items(), key=lambda kv: -kv[1])),
        "too_big": tree.too_big,
        "sample": [rel for rel, _, _ in tree.files[:8]],
        "truncated": tree.truncated,
        "unreadable": len(tree.unreadable),
        "already_added": row["id"] if row else None,
    }


# ------------------------------------------------------------------- folders


_exists_cache: dict[str, tuple[float, bool]] = {}


def _exists(path: str) -> bool:
    """Whether her folder is still there, asked at most every 30 seconds (an unplugged network drive is slow to say)."""
    now = time.monotonic()
    known = _exists_cache.get(path)
    if known and now - known[0] < 30:
        return known[1]
    there = Path(path).is_dir()
    _exists_cache[path] = (now, there)
    return there


def _shape(row: Any) -> dict[str, Any]:
    out = dict(row)
    out["tags"] = json.loads(out["tags"] or "[]")
    out["skipped"] = json.loads(out["skipped"]) if out["skipped"] else {}
    out["precedent"], out["watch"] = bool(out["precedent"]), bool(out["watch"])
    out["exists"] = _exists(out["path"])
    return out


FOLDER_SQL = """SELECT f.*, c.name AS client, (SELECT COUNT(*) FROM doc_meta m WHERE m.folder_id = f.id) AS documents
                FROM folders f LEFT JOIN companies c ON c.id = f.company_id"""


def listing(vault: Vault) -> list[dict[str, Any]]:
    return [_shape(r) for r in vault.conn.execute(f"{FOLDER_SQL} ORDER BY f.path")]


def get(vault: Vault, folder_id: int, details: bool = False) -> dict[str, Any]:
    """One folder and its pass; with `details`, the files that couldn't be read and the ones read last."""
    row = vault.conn.execute(f"{FOLDER_SQL} WHERE f.id = ?", (folder_id,)).fetchone()
    if row is None:
        raise NotFound(f"There is no folder {folder_id} in the library's list of folders.")
    out = _shape(row)
    if details:
        out["failures"] = vault._rows(
            "SELECT rel_path, error FROM folder_files WHERE folder_id = ? AND status = 'failed' ORDER BY rel_path LIMIT 200", (folder_id,)
        )
        out["recent"] = vault._rows(
            "SELECT rel_path, status, document_id FROM folder_files WHERE folder_id = ? ORDER BY seen_at DESC, rowid DESC LIMIT 20",
            (folder_id,),
        )
    return out


def _clean_tags(tags: Iterable[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        clean = " ".join(str(tag).strip().split()).lower()
        if not clean:
            continue
        if len(clean) > 60:
            raise Invalid("A tag is a word or short phrase, up to 60 characters.")
        if clean not in out:
            out.append(clean)
    return out


def _check_options(vault: Vault, client_mode: str, company_id: int | None, doc_type: str | None) -> None:
    if client_mode not in CLIENT_MODES:
        raise Invalid(f"The client is one of: {', '.join(CLIENT_MODES)}.")
    if client_mode == "one":
        if company_id is None:
            raise Invalid("Choose the client these documents belong to.")
        vault.company_row(company_id)
    if doc_type and doc_type not in DOC_TYPES:
        raise Invalid(f"Unknown document type {doc_type!r}.")


def add_folder(
    vault: Vault,
    home: Path,
    path: str | Path,
    client_mode: str = "auto",
    company_id: int | None = None,
    doc_type: str | None = None,
    tags: Iterable[str] = (),
    precedent: bool = False,
    watch: bool = False,
) -> dict[str, Any]:
    """Bring a folder in: it is read in the background (see run_queue). The same folder again takes the new choices
    and is looked at again. `precedent`: other companies' documents, tagged "precedent" and filed under no client."""
    folder = _folder_path(path, home)
    _check_options(vault, client_mode, company_id, doc_type or None)
    values = (client_mode, company_id if client_mode == "one" else None, doc_type or None, json.dumps(_clean_tags(tags)),
              int(precedent), int(watch))
    row = vault.conn.execute("SELECT id, status FROM folders WHERE path = ?", (str(folder),)).fetchone()
    if row:
        folder_id = row["id"]
        vault.conn.execute(
            "UPDATE folders SET client_mode = ?, company_id = ?, doc_type = ?, tags = ?, precedent = ?, watch = ? WHERE id = ?",
            (*values, folder_id),
        )
        if row["status"] != "running":
            vault.conn.execute(f"UPDATE folders SET {NEW_PASS} WHERE id = ?", (folder_id,))
    else:
        folder_id = vault.conn.execute(
            "INSERT INTO folders (path, client_mode, company_id, doc_type, tags, precedent, watch) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(folder), *values),
        ).lastrowid
    _exists_cache.pop(str(folder), None)
    vault.log("add folder", {"id": folder_id, "path": str(folder), "client": client_mode, "watch": watch})
    return get(vault, folder_id)


def change(vault: Vault, folder_id: int, **options: Any) -> dict[str, Any]:
    """Change a folder's choices: watch, client_mode with company_id, doc_type, tags, precedent. They apply to the
    files read from then on; a look again (queue_scan) applies them to new files."""
    current = get(vault, folder_id)
    allowed = {"watch", "client_mode", "company_id", "doc_type", "tags", "precedent"}
    unknown = set(options) - allowed
    if unknown:
        raise Invalid(f"Unknown choice: {', '.join(sorted(unknown))}.")
    merged = {key: options.get(key, current[key]) for key in allowed}
    if "client_mode" in options and options["client_mode"] != "one":
        merged["company_id"] = None
    _check_options(vault, merged["client_mode"], merged["company_id"], merged["doc_type"] or None)
    vault.conn.execute(
        "UPDATE folders SET watch = ?, client_mode = ?, company_id = ?, doc_type = ?, tags = ?, precedent = ? WHERE id = ?",
        (int(bool(merged["watch"])), merged["client_mode"], merged["company_id"], merged["doc_type"] or None,
         json.dumps(_clean_tags(merged["tags"])), int(bool(merged["precedent"])), folder_id),
    )
    vault.log("change folder", {"id": folder_id, **{k: v for k, v in options.items() if k != "tags"}})
    return get(vault, folder_id)


def queue_scan(vault: Vault, folder_id: int) -> dict[str, Any]:
    """Look at the folder again (now, in the background): new and changed files are read, and ones that failed."""
    if get(vault, folder_id)["status"] != "running":
        vault.conn.execute(f"UPDATE folders SET {NEW_PASS} WHERE id = ?", (folder_id,))
    return get(vault, folder_id)


def stop(vault: Vault, folder_id: int) -> dict[str, Any]:
    """Stop reading the folder after the file in hand. What was read stays; a look again carries on."""
    if get(vault, folder_id)["status"] in ("queued", "running"):
        vault.conn.execute("UPDATE folders SET status = 'stopped', current = NULL, finished_at = datetime('now') WHERE id = ?", (folder_id,))
        vault.log("stop folder", {"id": folder_id})
    return get(vault, folder_id)


def forget(vault: Vault, home: Path, folder_id: int, trash_documents: bool = False) -> dict[str, Any]:
    """Take a folder off the list. Its documents stay in the library (still saying where they came from), unless
    `trash_documents`, which moves them to the Trash. Her files on disk are never touched."""
    folder = get(vault, folder_id)
    ids = [r[0] for r in vault.conn.execute("SELECT document_id FROM doc_meta WHERE folder_id = ? ORDER BY document_id", (folder_id,))]
    trashed = 0
    if trash_documents:
        for document_id in ids:
            editing.delete_document(vault, home, document_id)
            trashed += 1
    else:
        vault.conn.execute("UPDATE doc_meta SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
    vault.conn.execute("DELETE FROM folder_files WHERE folder_id = ?", (folder_id,))
    vault.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    vault.log("forget folder", {"id": folder_id, "path": folder["path"], "documents_trashed": trashed})
    return {"forgotten": folder_id, "documents_trashed": trashed}


def queue_watched(vault: Vault, minutes: float = WATCH_MINUTES) -> int:
    """Look again at watched folders whose last pass finished more than `minutes` ago. Stopped ones are left alone."""
    return vault.conn.execute(
        f"""UPDATE folders SET {NEW_PASS} WHERE watch = 1 AND status IN ('done', 'failed')
            AND (finished_at IS NULL OR finished_at <= datetime('now', ?))""",
        (f"-{minutes * 60:.0f} seconds",),
    ).rowcount


def reset_dead(vault: Vault, prefix: str = "web:") -> int:
    """Passes left running by a web server that has gone (only one can hold the port, so any found at its start are
    dead): they wait to be taken up again."""
    return vault.conn.execute(
        "UPDATE folders SET status = 'queued', worker = NULL, current = NULL WHERE status = 'running' AND worker LIKE ?", (f"{prefix}%",)
    ).rowcount


# --------------------------------------------------------------------- passes


def claim(vault: Vault, worker: str, folder_id: int | None = None) -> int | None:
    """Take the next folder waiting to be read (or the given one) for `worker`, unless someone else is reading it.
    A pass not heard from for STALE_MINUTES is taken over. Returns the folder's id, or None."""
    stale = f"-{STALE_MINUTES} minutes"
    waiting = "(status = 'queued' OR (status = 'running' AND (heartbeat IS NULL OR heartbeat < datetime('now', ?))))"
    for row in vault._rows(f"SELECT id FROM folders WHERE {waiting} AND (? IS NULL OR id = ?) ORDER BY id", (stale, folder_id, folder_id)):
        taken = vault.conn.execute(
            f"""UPDATE folders SET status = 'running', worker = ?, heartbeat = datetime('now'), current = NULL, error = NULL,
                   started_at = COALESCE(started_at, {NOW}) WHERE id = ? AND {waiting}""",
            (worker, row["id"], stale),
        ).rowcount
        if taken:
            return row["id"]
    return None


def _wanted(item: tuple[str, int, str], known: dict[str, Any] | None, started: str | None) -> bool:
    """New, changed since it was read, or failed in an earlier pass (a failure in this one isn't tried twice)."""
    _, size, modified = item
    if known is None or known["size"] != size or known["modified"] != modified:
        return True
    return known["status"] == "failed" and (started is None or known["seen_at"] < started)


def _quietly(path: Path) -> Prepared | BaseException:
    try:
        return prepare(path)
    except Exception as exc:  # handed to the filer, which records it against the file
        return exc


def read_ahead(root: Path, items: list[tuple[str, int, str]], threads: int = READ_AHEAD_THREADS,
               window: int = READ_AHEAD_FILES) -> Iterator[tuple[tuple[str, int, str], Prepared | BaseException]]:
    """The files in order, each with what prepare() made of it (or the error), read up to `window` files ahead on
    `threads` threads while the caller files the one in hand."""
    pool = ThreadPoolExecutor(max_workers=max(1, threads), thread_name_prefix="aagam-read")
    pending: deque[tuple[tuple[str, int, str], Any]] = deque()
    upcoming = iter(items)
    try:
        for item in upcoming:
            pending.append((item, pool.submit(_quietly, root / item[0])))
            if len(pending) >= window:
                break
        while pending:
            item, future = pending.popleft()
            following = next(upcoming, None)
            if following is not None:
                pending.append((following, pool.submit(_quietly, root / following[0])))
            yield item, future.result()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _running(vault: Vault, folder_id: int) -> bool:
    row = vault.conn.execute("SELECT status FROM folders WHERE id = ?", (folder_id,)).fetchone()
    return bool(row and row["status"] == "running")


def _record(vault: Vault, folder_id: int, rel: str, size: int, modified: str, status: str, document_id: int | None, error: str | None) -> None:
    vault.conn.execute(
        f"""INSERT INTO folder_files (folder_id, rel_path, size, modified, status, document_id, error, seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, {NOW})
           ON CONFLICT(folder_id, rel_path) DO UPDATE SET size = excluded.size, modified = excluded.modified,
             status = excluded.status, document_id = COALESCE(excluded.document_id, folder_files.document_id),
             error = excluded.error, seen_at = excluded.seen_at""",
        (folder_id, rel, size, modified, status, document_id, error),
    )
    vault.conn.execute(
        f"UPDATE folders SET done = done + 1, {status} = {status} + 1, current = ?, heartbeat = datetime('now') WHERE id = ?",
        (rel, folder_id),
    )


def _file(vault: Vault, settings: Settings, folder: dict[str, Any], path: Path, rel: str, modified: str,
          prepared: Prepared) -> tuple[str, int]:
    """Bring in one file of a folder: ("already", id) when the same file is in the library, else ("added", id)."""
    origin = library.Origin(str(path), folder["id"], posixpath.dirname(rel), modified)
    same = vault.conn.execute("SELECT id FROM documents WHERE sha256 = ? ORDER BY id LIMIT 1", (prepared.sha256,)).fetchone()
    if same:
        meta = vault.conn.execute("SELECT folder_id FROM doc_meta WHERE document_id = ?", (same["id"],)).fetchone()
        if meta is None or meta["folder_id"] is None:
            library.record_origin(vault, same["id"], origin)  # it belongs to no folder yet: now it is this one's
        return "already", same["id"]
    precedent = bool(folder["precedent"])
    tags = json.loads(folder["tags"] or "[]")
    if precedent and "precedent" not in tags:
        tags.append("precedent")
    company_id = folder["company_id"] if folder["client_mode"] == "one" and not precedent else None
    info = library.add_document(vault, settings, path, company_id, folder["doc_type"], tags, origin=origin,
                                work_out_client=folder["client_mode"] == "auto" and not precedent, prepared=prepared)
    return "added", info["document_id"]


def _short(exc: BaseException) -> str:
    text = " ".join(str(exc).split()) or type(exc).__name__
    return text[:300]


FileNote = Callable[[str, str, str | None], None]  # (path inside the folder, added/already/failed, the error)


def run_pass(
    settings: Settings,
    folder_id: int,
    budget: float | None = None,
    stopping: threading.Event | None = None,
    on_file: FileNote | None = None,
) -> dict[str, Any]:
    """One pass over a folder already claimed (see claim): walk it, then file each new or changed file in a
    transaction of its own. A `budget` in seconds, or `stopping` set, leaves the rest for later. She can stop it
    from the window. Returns the folder as it stands."""
    db_path = settings.db_path
    with open_db(db_path, actor="folders") as vault:
        folder = dict(vault.conn.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone())
    root = Path(folder["path"])
    if not root.is_dir():
        with open_db(db_path, actor="folders") as vault:
            vault.conn.execute(
                "UPDATE folders SET status = 'failed', current = NULL, finished_at = datetime('now'), error = ? WHERE id = ?",
                (f"The folder {root} isn't there any more. Is the drive connected?", folder_id),
            )
            return get(vault, folder_id)
    tree = scan(root, settings.home)
    with open_db(db_path, actor="folders") as vault:
        known = {r["rel_path"].lower(): r for r in vault._rows(
            "SELECT rel_path, size, modified, status, seen_at FROM folder_files WHERE folder_id = ?", (folder_id,))}
        to_do = [item for item in tree.files if _wanted(item, known.get(item[0].lower()), folder["started_at"])]
        skipped = dict(sorted(tree.skipped.items(), key=lambda kv: -kv[1]))
        if tree.too_big:
            skipped[TOO_BIG] = tree.too_big
        vault.conn.execute(
            "UPDATE folders SET found = done + ?, skipped = ?, heartbeat = datetime('now') WHERE id = ?",
            (len(to_do), json.dumps(skipped) if skipped else None, folder_id),
        )
    for rel in tree.unreadable:
        log.warning("folder %s: couldn't open %s", folder_id, rel)

    deadline = time.monotonic() + budget if budget is not None else None
    outcome = "done"
    with closing(read_ahead(root, to_do)) as reading:
        for (rel, size, modified), prepared in reading:
            if (stopping is not None and stopping.is_set()) or (deadline is not None and time.monotonic() >= deadline):
                outcome = "later"
                break
            path = root / rel
            if isinstance(prepared, FileNotFoundError) or not path.is_file():
                # It went while the pass was running: nothing to read, nothing to keep.
                with open_db(db_path, actor="folders") as vault:
                    if not _running(vault, folder_id):
                        outcome = "stopped"
                        break
                    vault.conn.execute("UPDATE folders SET found = MAX(found - 1, done), heartbeat = datetime('now') WHERE id = ?", (folder_id,))
                continue
            status, error = "failed", None
            try:
                with open_db(db_path, actor="folders") as vault:
                    if not _running(vault, folder_id):
                        outcome = "stopped"
                        break
                    if isinstance(prepared, BaseException):
                        raise prepared
                    status, document_id = _file(vault, settings, folder, path, rel, modified, prepared)
                    _record(vault, folder_id, rel, size, modified, status, document_id, None)
            except Exception as exc:  # one bad file never stops the pass
                status, error = "failed", _short(exc)
                log.warning("folder %s: %s: %s", folder_id, rel, error)
                with open_db(db_path, actor="folders") as vault:
                    if vault.conn.execute("SELECT 1 FROM folders WHERE id = ?", (folder_id,)).fetchone():
                        _record(vault, folder_id, rel, size, modified, "failed", None, error)
            if on_file:
                on_file(rel, status, error)

    with open_db(db_path, actor="folders") as vault:
        if vault.conn.execute("SELECT 1 FROM folders WHERE id = ?", (folder_id,)).fetchone() is None:
            return {"id": folder_id, "status": "forgotten"}
        if outcome == "done":
            vault.conn.execute(
                "UPDATE folders SET status = 'done', current = NULL, finished_at = datetime('now'), heartbeat = datetime('now') "
                "WHERE id = ? AND status = 'running'",
                (folder_id,),
            )
        elif outcome == "later":
            vault.conn.execute("UPDATE folders SET status = 'queued', current = NULL WHERE id = ? AND status = 'running'", (folder_id,))
        else:
            vault.conn.execute("UPDATE folders SET current = NULL WHERE id = ?", (folder_id,))
        return get(vault, folder_id)


def run_queue(
    settings: Settings,
    worker: str,
    folder_id: int | None = None,
    budget: float | None = None,
    stopping: threading.Event | None = None,
    on_file: FileNote | None = None,
) -> int:
    """Read the folders waiting to be read (or just `folder_id`), one after another, until none is left, the
    `budget` (seconds) is spent or `stopping` is set. Returns how many passes were worked on."""
    started = time.monotonic()
    passes = 0
    while stopping is None or not stopping.is_set():
        left = None if budget is None else budget - (time.monotonic() - started)
        if left is not None and left <= 0:
            break
        with open_db(settings.db_path, actor="folders") as vault:
            taken = claim(vault, worker, folder_id)
        if taken is None:
            break
        passes += 1
        result = run_pass(settings, taken, left, stopping, on_file)
        if folder_id is not None or result.get("status") == "queued":
            break  # just the one, or out of time
    return passes


# ------------------------------------------------------------------- worker


class FolderWorker(threading.Thread):
    """Reads folders in the background while AAGAM is open: passes she asked for, watched folders every
    WATCH_MINUTES, and (when there is nothing else) dates for documents read before dates were worked out."""

    def __init__(self, settings: Any, interval: float = 3, watch_minutes: float = WATCH_MINUTES) -> None:
        super().__init__(name="aagam-folders", daemon=True)
        self.settings, self.interval, self.watch_minutes = settings, interval, watch_minutes
        self.stopping = threading.Event()
        self.worker = f"web:{os.getpid()}"
        self.last_watch = 0.0

    def run(self) -> None:
        while not self.stopping.wait(self.interval):
            try:
                self.tick()
            except Exception:
                log.exception("folder worker")

    def tick(self) -> int:
        core = self.settings.core
        if time.monotonic() - self.last_watch >= self.watch_minutes * 60:
            self.last_watch = time.monotonic()
            with open_db(core.db_path, actor="folders") as vault:
                queue_watched(vault, self.watch_minutes)
        passes = run_queue(core, self.worker, stopping=self.stopping)
        if not passes and not self.stopping.is_set():
            with open_db(core.db_path, actor="folders") as vault:
                library.backfill_dates(vault, 200)
        return passes

    def stop(self) -> None:
        self.stopping.set()


# --------------------------------------------------------- choosing a folder

# Runs in a short-lived Python of its own, so the window's server never waits on Tk.
BROWSE_SCRIPT = """
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
path = filedialog.askdirectory(parent=root, title="Choose a folder to bring into AAGAM", mustexist=True)
root.destroy()
sys.stdout.buffer.write((path or "").encode("utf-8"))
"""


def choose_folder(timeout: float = 300) -> str | None:
    """Her choice in the "choose a folder" dialog on this computer; None if she cancelled or no dialog can be shown."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        done = subprocess.run([sys.executable, "-c", BROWSE_SCRIPT], capture_output=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return None
    chosen = done.stdout.decode("utf-8", errors="replace").strip()
    return str(Path(chosen)) if done.returncode == 0 and chosen else None
