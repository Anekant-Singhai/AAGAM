"""Copies of her data, and a small report she can send when she needs help.

A backup is a copy of the data folder (documents, records, templates, the law folder, the Trash)
outside that folder. Putting the copy back is how a new laptop, or a damaged one, gets her work again.
The browser she uses for MCA is left out: it is large, and she logs in again.

The report is a zip of the health check and the recent logs. It has no documents and no update key.
Tokens that happen to be in a log are removed before the zip is written.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from csdesk.errors import Invalid

from .config import AagamSettings

# Chrome's profile for the MCA window, and logs: neither is needed to put her work back.
SKIP_DIRS = {"browser-profile", "logs"}
_SECRET = re.compile(
    r"ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+",
    re.IGNORECASE,
)
_LOG_TAIL = 200_000


def redact(text: str) -> str:
    """Take out GitHub tokens and the like. What is left can be sent to someone who is helping."""
    return _SECRET.sub("[removed]", text)


def desktop_dir() -> Path | None:
    """Her real Desktop, including one redirected by OneDrive."""
    if sys.platform == "win32":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            # CSIDL_DESKTOPDIRECTORY: the folder, not the virtual desktop.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer) == 0 and buffer.value:
                found = Path(buffer.value)
                if found.is_dir():
                    return found
        except (AttributeError, OSError):
            pass
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.is_dir():
            return candidate
    return None


def documents_dir() -> Path:
    """Her Documents folder, or her home folder when there isn't one."""
    if sys.platform == "win32":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buffer) == 0 and buffer.value:
                found = Path(buffer.value)
                if found.is_dir():
                    return found
        except (AttributeError, OSError):
            pass
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def _fresh_dir(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for suffix in ("", *(f" ({n})" for n in range(2, 100))):
        candidate = root / f"{name}{suffix}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise Invalid("There are already many copies from this minute. Nothing new was made.")


def _fresh_file(root: Path, name: str, suffix: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for extra in ("", *(f" ({n})" for n in range(2, 100))):
        candidate = root / f"{name}{extra}{suffix}"
        if not candidate.exists():
            return candidate
    raise Invalid("There are already many reports from this minute. Nothing new was made.")


def _files(home: Path):
    """Files under home, not following links, skipping the folders a backup doesn't keep."""
    for dirpath, dirnames, filenames in os.walk(home, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink() and not (current == home and name in SKIP_DIRS)]
        if current != home and current.relative_to(home).parts[0] in SKIP_DIRS:
            dirnames.clear()
            continue
        for name in filenames:
            path = current / name
            if path.is_symlink():
                continue
            if path.name.endswith(("-wal", "-shm")):
                continue
            yield path


def _copy_db(src: Path, dst: Path) -> None:
    """A consistent copy even while AAGAM has the database open."""
    source = sqlite3.connect(src, timeout=30)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _note(home: Path) -> str:
    return (
        "This is a copy of an AAGAM data folder.\r\n"
        "It was made so you can put your documents and records back.\r\n"
        "\r\n"
        "To put them back on this computer:\r\n"
        "1. Close AAGAM (close the browser tab, then the AAGAM window if one is open).\r\n"
        f"2. Rename the current data folder to AAGAM-old. It is:\r\n   {home}\r\n"
        "3. Copy THIS folder to that same place and name it the way the old one was named.\r\n"
        "4. Open AAGAM from the desktop shortcut.\r\n"
        "\r\n"
        "The browser you use to log in to MCA is not in this copy. Log in again.\r\n"
        "An update of AAGAM never changes this copy.\r\n"
    )


def backup_data(home: Path, into: Path | None = None) -> dict[str, Any]:
    """Copy the data folder to Documents\\AAGAM backups (or `into`). Raises Invalid when it shouldn't try."""
    home = home.resolve()
    if not home.is_dir() or not ((home / "csdesk.db").is_file() or (home / "clients").is_dir()):
        raise Invalid(f"{home} doesn't look like AAGAM's data folder, so nothing was copied.")
    root = (into if into is not None else documents_dir() / "AAGAM backups").resolve()
    if root == home or _inside(root, home) or _inside(home, root):
        raise Invalid("Choose a folder outside your AAGAM data folder. Nothing was copied.")
    dest: Path | None = None
    try:
        dest = _fresh_dir(root, datetime.now().strftime("AAGAM %Y-%m-%d %H%M"))
        files = 0
        total = 0
        for src in _files(home):
            target = dest / src.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix == ".db":
                _copy_db(src, target)
            else:
                shutil.copy2(src, target, follow_symlinks=False)
            files += 1
            total += target.stat().st_size
        (dest / "READ ME.txt").write_text(_note(home), encoding="utf-8")
    except Invalid:
        if dest is not None and dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        raise
    except Exception as exc:
        if dest is not None and dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        raise Invalid(f"The copy didn't finish ({exc}). Nothing was left half-done.") from exc
    return {"path": str(dest), "files": files, "bytes": total}


def _tail(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-_LOG_TAIL:].decode("utf-8", errors="replace")


def support_report(settings: AagamSettings, into: Path | None = None) -> dict[str, Any]:
    """A zip on the Desktop: version, health check, recent logs. No documents, no update key."""
    from . import __version__, doctor, updates

    home = Path(settings.core.home)
    app = updates.app_folder()
    folder = into if into is not None else desktop_dir() or documents_dir()
    path = _fresh_file(folder, datetime.now().strftime("AAGAM support %Y-%m-%d %H%M"), ".zip")
    about = updates.info(app, home)
    record = {k: v for k, v in updates.read_record(app).items() if k != "token"}
    lines = [
        f"AAGAM {__version__}",
        f"Python {sys.version}",
        f"Program folder: {app}",
        f"Data folder: {home}",
        "",
        "This copy",
        json.dumps({k: about[k] for k in about if k != "updates"}, indent=2, default=str),
        "",
        doctor.report(doctor.run_checks(settings), "utf-8"),
        "",
        "Install record (the update key is not included)",
        json.dumps(record, indent=2, default=str),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.txt", redact("\n".join(lines)))
        logs = home / "logs"
        if logs.is_dir():
            for log in sorted(logs.glob("*.log")):
                archive.writestr(f"logs/{log.name}", redact(_tail(log)))
    return {"path": str(path), "bytes": path.stat().st_size}
