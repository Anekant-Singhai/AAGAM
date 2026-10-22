"""Keeping AAGAM up to date: what is installed, what GitHub has, and putting a new version in place.

scripts/install.ps1 writes install.json in the app folder: the GitHub repository, the branch and the commit
installed. Updates come one of two ways:

- archive (her laptop): GitHub's API says which commit the branch is at and what changed since hers. The new
  version is downloaded as a zip, unpacked into .update/ and checked before anything else is touched.
- git (a developer's checkout): `git fetch`, then `git pull --ff-only`. Never automatic.

The new version is put in place by a process of its own (`python -m aagam.updates apply`), because a running
server can't replace the files it runs from. It asks the server to close, keeps a copy of the current code in
.update/backup-<commit>, puts the new files in, reinstalls the Python packages only when pyproject.toml's
dependencies or commands changed, sets up the data folder (`aagam init`) and starts the server again. If a step
fails, the copy goes back and the old version is started again. What happened is kept in .update/status.json for
the window to show after the restart, and step by step in logs/aagam-update.log.

This module uses only the standard library, so the update process holds no package files open while it replaces
them, and it never imports the rest of AAGAM: new code runs in new processes.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# The GitHub repository AAGAM is installed and updated from (scripts/install.ps1 has the same default).
DEFAULT_REPO = "Anekant-Singhai/AAGAM"
DEFAULT_BRANCH = "main"
API = "https://api.github.com"
# What an update replaces. Everything else in the app folder (.venv, .update, install.json) stays.
CODE = ("src", "scripts", "docs", "pyproject.toml", "README.md", "START-HERE.txt", "install.cmd", "manage.cmd", "LICENSE")
TASK_NAME = "AAGAM Update"
RECORD = "install.json"
KEEP_BACKUPS = 2
MAX_CHANGES = 50
STATE_KEYS = ("checked_at", "available", "latest", "changes", "status", "error", "needs_token", "last_update")
EMPTY_STATE: dict[str, Any] = {
    "checked_at": None, "available": False, "latest": None, "changes": [], "status": "idle", "error": None,
    "needs_token": False, "last_update": None,
}
_LOCK = threading.Lock()


class UpdateError(Exception):
    """An update step that couldn't be done, in words she can act on."""

    def __init__(self, message: str, needs_token: bool = False) -> None:
        super().__init__(message)
        self.needs_token = needs_token


# ------------------------------------------------------------------ where things are


def app_folder() -> Path:
    """The folder AAGAM runs from: pyproject.toml, src/, scripts/ and .venv/. AAGAM_APP_DIR points elsewhere (tests)."""
    override = os.environ.get("AAGAM_APP_DIR")
    return Path(override) if override else Path(__file__).resolve().parents[2]


def updates_dir(app: Path) -> Path:
    return app / ".update"


def venv_python(app: Path, windowless: bool = False) -> Path:
    """The app's own Python (pythonw on Windows when no console is wanted); this one when there is no .venv."""
    if sys.platform == "win32":
        candidate = app / ".venv" / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    else:
        candidate = app / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else Path(sys.executable)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))  # PowerShell 5.1 writes a BOM
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# ------------------------------------------------------------------ the install record


def read_record(app: Path) -> dict[str, Any]:
    return _read_json(app / RECORD)


def write_record(app: Path, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        record = {**read_record(app), **changes}
        _write_json(app / RECORD, record)
    return record


def version_of(app: Path) -> str | None:
    try:
        text = (app / "src" / "aagam" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text)
    return m.group(1) if m else None


def _git(app: Path, *args: str, timeout: float = 120) -> str:
    try:
        done = subprocess.run(["git", "-C", str(app), *args], capture_output=True, text=True, timeout=timeout,
                              creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"git didn't answer ({exc}).") from exc
    if done.returncode != 0:
        raise UpdateError((done.stderr or done.stdout).strip().splitlines()[-1] if (done.stderr or done.stdout).strip() else f"git {args[0]} failed.")
    return done.stdout.strip()


def mode(app: Path) -> str:
    """How this copy is updated: "git" (a checkout, by git pull), "archive" (installed from GitHub) or "none"."""
    if (app / ".git").exists() and shutil.which("git"):
        return "git"
    if (app / "pyproject.toml").is_file() and (app / "src" / "aagam").is_dir() and read_record(app).get("repo"):
        return "archive"
    return "none"


def _repo_from_url(url: str) -> str | None:
    m = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url.strip())
    return m.group(1) if m else None


def current_commit(app: Path, how: str | None = None) -> str | None:
    how = how or mode(app)
    if how == "git":
        try:
            return _git(app, "rev-parse", "HEAD", timeout=20)
        except UpdateError:
            return None
    return read_record(app).get("commit") or None


_RUNNING: dict[str, str | None] = {}


def running_commit(app: Path) -> str | None:
    """The commit this process started with (it can't change under a running server: an update restarts it)."""
    key = str(app)
    if key not in _RUNNING:
        _RUNNING[key] = current_commit(app)
    return _RUNNING[key]


def repo_of(app: Path, how: str | None = None) -> str | None:
    how = how or mode(app)
    record = read_record(app)
    if how == "git":
        try:
            return _repo_from_url(_git(app, "remote", "get-url", "origin", timeout=20)) or record.get("repo")
        except UpdateError:
            return record.get("repo")
    return record.get("repo")


def branch_of(app: Path, how: str | None = None) -> str | None:
    how = how or mode(app)
    record = read_record(app)
    if record.get("branch"):
        return record["branch"]
    if how == "git":
        try:
            return _git(app, "rev-parse", "--abbrev-ref", "HEAD", timeout=20)
        except UpdateError:
            return None
    return DEFAULT_BRANCH if how == "archive" else None


def info(app: Path, home: Path) -> dict[str, Any]:
    """What the window's System page shows about this copy."""
    how = mode(app)
    record = read_record(app)
    return {
        "version": version_of(app),
        "commit": current_commit(app, how),
        "installed_at": record.get("installed_at"),
        "app_folder": str(app),
        "data_folder": str(home),
        "mode": how,
        "auto_update": bool(record.get("auto_update", True)) if how == "archive" else False,
        "repo": repo_of(app, how),
        "branch": branch_of(app, how),
        "has_token": token_path(app).is_file(),
        "updates": state(app),
    }


# ------------------------------------------------------------------ what the last check and update found


def state(app: Path) -> dict[str, Any]:
    saved = _read_json(updates_dir(app) / "status.json")
    return {**EMPTY_STATE, **{k: v for k, v in saved.items() if k in STATE_KEYS}}


def save_state(app: Path, **changes: Any) -> dict[str, Any]:
    with _LOCK:
        current = {**state(app), **{k: v for k, v in changes.items() if k in STATE_KEYS}}
        _write_json(updates_dir(app) / "status.json", current)
    return current


# ------------------------------------------------------------------ the update key (a GitHub token, for a private repository)


def token_path(app: Path) -> Path:
    return updates_dir(app) / ("token.bin" if sys.platform == "win32" else "token.txt")


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows' own encryption for this user (DPAPI): only she, on this computer, can read the key back."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buffer = ctypes.create_string_buffer(data, len(data))
    given = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = Blob()
    description = ctypes.c_wchar_p("AAGAM update key") if protect else None
    if not function(ctypes.byref(given), description, None, None, None, 0x01, ctypes.byref(result)):  # 0x01: no prompts
        raise OSError(ctypes.get_last_error(), "Windows couldn't protect or read the update key.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def save_token(app: Path, token: str | None) -> None:
    path = token_path(app)
    if not token or not token.strip():
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = token.strip().encode("utf-8")
    if sys.platform == "win32":
        path.write_bytes(_dpapi(data, protect=True))
    else:
        path.write_bytes(data)
        path.chmod(0o600)


def load_token(app: Path) -> str | None:
    path = token_path(app)
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
        return (_dpapi(data, protect=False) if sys.platform == "win32" else data).decode("utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


# ------------------------------------------------------------------ GitHub

Fetch = Callable[[str, dict[str, str]], tuple[int, dict[str, str], bytes]]


def http_get(url: str, headers: dict[str, str], timeout: float = 30) -> tuple[int, dict[str, str], bytes]:
    """GET a URL: (status, headers with lower-case names, body). The token is never sent on to a redirect (GitHub's
    download links carry their own)."""
    request = urllib.request.Request(url, headers={k: v for k, v in headers.items() if k.lower() != "authorization"})
    for key, value in headers.items():
        if key.lower() == "authorization":
            request.add_unredirected_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"Couldn't reach GitHub ({reason}). Check the internet connection and try again.") from exc


@dataclass
class GitHub:
    repo: str
    token: str | None = None
    fetch: Fetch | None = None  # None: http_get (looked up when called, so tests can stand in for GitHub)

    def headers(self) -> dict[str, str]:
        out = {"Accept": "application/vnd.github+json", "User-Agent": "AAGAM-updater", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            out["Authorization"] = f"Bearer {self.token}"
        return out

    def get(self, path: str) -> Any:
        status, headers, body = (self.fetch or http_get)(f"{API}{path}", self.headers())
        if status == 200:
            return json.loads(body.decode("utf-8"))
        raise self.error(status, headers, body)

    def error(self, status: int, headers: dict[str, str], body: bytes) -> UpdateError:
        try:
            message = json.loads(body.decode("utf-8")).get("message", "")
        except (ValueError, UnicodeDecodeError, AttributeError):
            message = ""
        if status in (403, 429) and headers.get("x-ratelimit-remaining") == "0":
            reset = headers.get("x-ratelimit-reset")
            when = datetime.fromtimestamp(int(reset)).strftime("%H:%M") if reset and reset.isdigit() else "within the hour"
            return UpdateError(f"GitHub's limit on update checks was reached; it resets at {when}. AAGAM will try again later.")
        if status == 401:
            return UpdateError("GitHub refused the update key. Paste a new one on the System page.", needs_token=True)
        if status == 404:
            if self.token:
                return UpdateError(f"GitHub can't find {self.repo} with this update key: check the repository's name and the "
                                   "key's access to it.", needs_token=True)
            return UpdateError(f"GitHub can't find {self.repo}. If the repository is private, AAGAM needs an update key "
                               "(a read-only GitHub token).", needs_token=True)
        return UpdateError(f"GitHub answered {status}{': ' + message if message else ''}.")

    def head(self, branch: str) -> dict[str, Any]:
        data = self.get(f"/repos/{self.repo}/commits/{branch}")
        return _commit(data)

    def changes(self, base: str, head: str) -> list[dict[str, Any]]:
        data = self.get(f"/repos/{self.repo}/compare/{base}...{head}")
        commits = [_commit(c) for c in data.get("commits", [])]
        return list(reversed(commits))[:MAX_CHANGES]  # newest first

    def version_at(self, commit: str) -> str | None:
        try:
            data = self.get(f"/repos/{self.repo}/contents/src/aagam/__init__.py?ref={commit}")
            text = base64.b64decode(data.get("content", "")).decode("utf-8")
        except (UpdateError, ValueError, UnicodeDecodeError):
            return None
        m = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text)
        return m.group(1) if m else None

    def zipball(self, commit: str) -> bytes:
        status, headers, body = (self.fetch or http_get)(f"{API}/repos/{self.repo}/zipball/{commit}", self.headers())
        if status != 200:
            raise self.error(status, headers, body)
        return body


def _commit(data: dict[str, Any]) -> dict[str, Any]:
    commit = data.get("commit") or {}
    when = (commit.get("committer") or {}).get("date") or (commit.get("author") or {}).get("date")
    return {"commit": data.get("sha"), "date": when, "message": (commit.get("message") or "").strip().split("\n")[0]}


# ------------------------------------------------------------------ checking


def check(app: Path | None = None, fetch: Fetch | None = None) -> dict[str, Any]:
    """Ask GitHub (or git) whether there is a newer version, and what changed. Returns the update state."""
    app = app or app_folder()
    how = mode(app)
    save_state(app, status="checking", error=None)
    try:
        if how == "git":
            found = _check_git(app)
        elif how == "archive":
            found = _check_archive(app, fetch)
        else:
            raise UpdateError("Updates aren't set up for this copy of AAGAM. Install it with install.cmd to get them.")
    except UpdateError as exc:
        return save_state(app, status="failed", error=str(exc), needs_token=exc.needs_token, checked_at=_now())
    return save_state(app, status="idle", error=None, needs_token=False, checked_at=_now(), **found)


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _check_archive(app: Path, fetch: Fetch | None) -> dict[str, Any]:
    record = read_record(app)
    github = GitHub(record["repo"], load_token(app), fetch)
    latest = github.head(record.get("branch") or DEFAULT_BRANCH)
    installed = record.get("commit")
    if _same(installed, latest["commit"]):
        changes: list[dict[str, Any]] = []
    elif installed:
        try:
            changes = github.changes(installed, latest["commit"])
        except UpdateError:
            changes = [latest]  # her commit isn't on GitHub any more: the latest is still the one to have
        changes = changes or [latest]
    else:
        changes = [latest]  # this copy's commit wasn't recorded: bring it to a known one
    latest_out = {"commit": latest["commit"], "date": latest["date"], "version": github.version_at(latest["commit"])}
    return {"available": bool(changes), "latest": latest_out, "changes": changes}


def _check_git(app: Path) -> dict[str, Any]:
    branch = branch_of(app, "git") or DEFAULT_BRANCH
    try:
        _git(app, "remote", "get-url", "origin", timeout=20)
    except UpdateError as exc:
        raise UpdateError("This checkout has no GitHub remote ('origin'), so there is nothing to compare with.") from exc
    _git(app, "fetch", "--quiet", "origin", branch)
    remote = f"origin/{branch}"
    log = _git(app, "log", f"--max-count={MAX_CHANGES}", "--format=%H%x1f%cI%x1f%s", f"HEAD..{remote}")
    changes = [dict(zip(("commit", "date", "message"), line.split("\x1f"), strict=False)) for line in log.splitlines() if line]
    try:
        text = _git(app, "show", f"{remote}:src/aagam/__init__.py")
        m = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text)
        version = m.group(1) if m else None
    except UpdateError:
        version = None
    latest = {"commit": _git(app, "rev-parse", remote), "date": _git(app, "log", "-1", "--format=%cI", remote), "version": version}
    return {"available": bool(changes), "latest": latest, "changes": changes}


# ------------------------------------------------------------------ getting a version ready


def unpack(zip_path: Path, target: Path) -> Path:
    """Unpack a downloaded version into `target`; returns the folder holding its pyproject.toml."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    root = target.resolve()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                if not (root / member.filename).resolve().is_relative_to(root):
                    raise UpdateError("The download has a file outside its own folder, so it wasn't used.")
            archive.extractall(target)
    except zipfile.BadZipFile as exc:
        raise UpdateError("The download is damaged (not a zip file). Try again.") from exc
    for candidate in [target, *sorted(p for p in target.iterdir() if p.is_dir())]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise UpdateError("The download doesn't look like AAGAM (it has no pyproject.toml).")


def validate(root: Path) -> None:
    """Refuse a version that couldn't run: it must have AAGAM's code and its built interface."""
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UpdateError(f"The new version's pyproject.toml can't be read ({exc}).") from exc
    if project.get("name") != "aagam":
        raise UpdateError("The download isn't AAGAM (pyproject.toml names another project).")
    static = root / "src" / "aagam" / "web" / "static"
    missing = [str(p.relative_to(root)) for p in (root / "src" / "aagam" / "__init__.py", static / "index.html") if not p.is_file()]
    if not missing and not list((static / "assets").glob("*.js")):
        missing.append("src/aagam/web/static/assets/*.js")
    if missing:
        raise UpdateError(f"The new version is incomplete ({', '.join(missing)} missing), so it wasn't installed.")


def stage(app: Path, commit: str, fetch: Fetch | None = None) -> Path:
    """Download that commit and unpack it into .update/stage-<commit>, checked. Returns the unpacked folder."""
    record = read_record(app)
    github = GitHub(record.get("repo") or DEFAULT_REPO, load_token(app), fetch)
    save_state(app, status="downloading", error=None)
    folder = updates_dir(app)
    folder.mkdir(parents=True, exist_ok=True)
    download = folder / f"download-{commit[:12]}.zip"
    download.write_bytes(github.zipball(commit))
    root = unpack(download, folder / f"stage-{commit[:12]}")
    validate(root)
    save_state(app, status="ready")
    return root


def install_facts(pyproject: str) -> tuple[Any, ...]:
    """What in pyproject.toml needs pip when it changes: the packages, the commands, the build. (The code itself
    is picked up from src/ without pip: AAGAM is installed in editable mode.)"""
    try:
        data = tomllib.loads(pyproject)
    except tomllib.TOMLDecodeError:
        return ("unreadable", pyproject)
    project = data.get("project", {})
    return (
        sorted(project.get("dependencies", [])),
        sorted((k, sorted(v)) for k, v in project.get("optional-dependencies", {}).items()),
        sorted(project.get("scripts", {}).items()),
        sorted(data.get("build-system", {}).get("requires", [])),
        project.get("requires-python"),
    )


def dependencies_changed(old: str, new: str) -> bool:
    try:
        before, after = tomllib.loads(old).get("project", {}), tomllib.loads(new).get("project", {})
    except tomllib.TOMLDecodeError:
        return True
    return sorted(before.get("dependencies", [])) != sorted(after.get("dependencies", []))


# ------------------------------------------------------------------ putting it in place


def _skipped(rel: Path) -> bool:
    return any(part == "__pycache__" or part.endswith(".egg-info") for part in rel.parts)


def _mirror(source: Path, target: Path) -> None:
    """Make `target` hold exactly what `source` holds (leaving __pycache__ and pip's *.egg-info alone)."""
    target.mkdir(parents=True, exist_ok=True)
    wanted = {p.relative_to(source) for p in source.rglob("*") if not _skipped(p.relative_to(source))}
    for path in sorted(target.rglob("*"), reverse=True):  # children before their folders
        rel = path.relative_to(target)
        if _skipped(rel) or rel in wanted:
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    for rel in sorted(wanted):
        src, dst = source / rel, target / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def put_in_place(source: Path, app: Path) -> None:
    """Replace the app's code (CODE) with `source`'s. A part the new version no longer has is removed."""
    for name in CODE:
        src, dst = source / name, app / name
        if src.is_dir():
            _mirror(src, dst)
        elif src.is_file():
            if dst.is_dir():
                shutil.rmtree(dst)
            shutil.copy2(src, dst)
        elif dst.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
        elif dst.exists():
            dst.unlink()


def backup_code(app: Path, commit: str | None) -> Path:
    """A copy of the code as it is now, in .update/backup-<commit>, to put back if the update fails."""
    target = updates_dir(app) / f"backup-{(commit or datetime.now().strftime('%Y%m%d-%H%M%S'))[:12]}"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for name in CODE:
        src = app / name
        if src.is_dir():
            shutil.copytree(src, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        elif src.is_file():
            shutil.copy2(src, target / name)
    _write_json(target / "backup.json", {"commit": commit, "version": version_of(app), "at": _now()})
    return target


def prune(app: Path, keep: int = KEEP_BACKUPS) -> None:
    """Keep the newest `keep` backups; remove downloads and unpacked versions."""
    folder = updates_dir(app)
    if not folder.is_dir():
        return
    backups = sorted((p for p in folder.glob("backup-*") if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep:]:
        shutil.rmtree(old, ignore_errors=True)
    for leftover in [*folder.glob("stage-*"), *folder.glob("download-*.zip")]:
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)
        else:
            leftover.unlink(missing_ok=True)


# ------------------------------------------------------------------ the steps that touch the rest of the computer

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
_DETACHED = (0x00000008 | 0x00000200 | 0x08000000) if sys.platform == "win32" else 0  # DETACHED_PROCESS, NEW_PROCESS_GROUP, NO_WINDOW


def work_in_progress(home: Path) -> bool:
    """True when a folder or a long scan is being read, or the database can't be asked. An update waits."""
    if not (home / "csdesk.db").is_file():
        return False
    try:
        from .db import open_db

        with open_db(home / "csdesk.db", actor="updates") as vault:
            reading = vault.conn.execute("SELECT 1 FROM ai_jobs WHERE task = 'ocr' AND status = 'running' LIMIT 1").fetchone()
            try:  # a folder waiting its turn picks up where it was; one being read is left to finish
                folder = vault.conn.execute("SELECT 1 FROM folders WHERE status = 'running' LIMIT 1").fetchone()
            except Exception:  # noqa: BLE001 - a database from before folders existed
                folder = None
            return bool(reading or folder)
    except Exception:  # noqa: BLE001 - when in doubt, don't update now
        return True


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def note_installed_version(app: Path) -> None:
    """Windows Settings > Apps shows the version after an update, when this folder is the one that was installed.

    A test's temporary copy does not match that folder, so it never writes the registry.
    """
    if sys.platform != "win32" or mode(app) != "archive":
        return
    version = version_of(app)
    if not version:
        return
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AAGAM",
                             0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except OSError:
        return
    with key:
        try:
            location, _ = winreg.QueryValueEx(key, "InstallLocation")
        except OSError:
            return
        try:
            same = Path(location).resolve() == app.resolve()
        except OSError:
            return
        if not same:
            return
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)


def register_daily_update(app: Path) -> str | None:
    """On Windows, a daily 08:00 task that installs a GitHub update when AAGAM is closed.

    None when it was added, or when this copy shouldn't have one (not Windows, a git checkout, no Python yet).
    A sentence when it was tried and failed. Never raises: a failed task must not fail an update.
    """
    if sys.platform != "win32" or mode(app) != "archive":
        return None
    pythonw = venv_python(app, windowless=True)
    if not pythonw.is_file():
        return None
    script = "\n".join([
        f"$action = New-ScheduledTaskAction -Execute {_ps_quote(str(pythonw))} -Argument '-m aagam update --apply-if-idle' -WorkingDirectory {_ps_quote(str(app))}",
        "$trigger = New-ScheduledTaskTrigger -Daily -At '08:00'",
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)",
        f"Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $action -Trigger $trigger -Settings $settings "
        "-Description 'Installs a new AAGAM version from GitHub when AAGAM is not open.' -Force | Out-Null",
    ])
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                              timeout=60, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if done.returncode != 0:
        return (done.stderr or done.stdout or "could not add the daily check").strip()
    return None


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def health(port: int, timeout: float = 2) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as response:
            data = json.load(response)
            return data if isinstance(data, dict) and data.get("ok") else None
    except (OSError, ValueError):
        return None


def stop_server(port: int, wait: float = 30) -> bool:
    """Ask the AAGAM server on this port to close, and wait for it to. True once nothing is listening."""
    if not port_in_use(port):
        return True
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/shutdown", data=b"", method="POST",
                                     headers={"X-AAGAM": "1", "Content-Type": "application/json"})
    with contextlib.suppress(OSError):  # an older AAGAM has no shutdown; it may be closing anyway
        urllib.request.urlopen(request, timeout=5).close()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if not port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def start_server(app: Path, port: int, home: Path | None = None) -> None:
    env = {**os.environ, "AAGAM_PORT": str(port)}
    if home:
        env["AAGAM_HOME"] = str(home)
    log = (home or Path.home()) / "logs" / "aagam-web.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as out:
        subprocess.Popen([str(venv_python(app, windowless=True)), "-m", "aagam", "serve"], cwd=str(app), env=env,
                         stdin=subprocess.DEVNULL, stdout=out, stderr=out, creationflags=_DETACHED, close_fds=True)


def wait_until_up(port: int, timeout: float = 60) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        answer = health(port)
        if answer:
            return answer
        time.sleep(0.5)
    return None


def run_python(app: Path, args: list[str], timeout: float = 1800) -> tuple[int, str]:
    try:
        done = subprocess.run([str(venv_python(app)), *args], cwd=str(app), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def aagam_processes(app: Path) -> list[dict[str, Any]]:
    """AAGAM's other processes from this app's Python (Claude Desktop's `aagam mcp`, a `serve`), on Windows."""
    if sys.platform != "win32":
        return []
    scripts = str((app / ".venv" / "Scripts").resolve()).replace("'", "''")
    command = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | "
        f"Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith('{scripts}', 'OrdinalIgnoreCase') -and "
        f"$_.ProcessId -ne {os.getpid()} }} | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress"
    )
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=60,
                              creationflags=_NO_WINDOW)
        data = json.loads(done.stdout) if done.stdout.strip() else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    return [{"pid": p.get("ProcessId"), "command": p.get("CommandLine") or ""} for p in ([data] if isinstance(data, dict) else data)]


def stop_mcp(app: Path) -> int:
    """Stop Claude Desktop's AAGAM servers from this app (they hold package files pip must replace). How many."""
    stopped = 0
    for process in aagam_processes(app):
        if re.search(r"-m\s+(?:aagam\s+mcp|csdesk\s+serve)", process["command"]):
            subprocess.run(["taskkill", "/PID", str(process["pid"]), "/F"], capture_output=True, timeout=30, creationflags=_NO_WINDOW)
            stopped += 1
    return stopped


@dataclass
class Steps:
    """The parts of an update that reach outside the app folder. Tests replace them."""

    stop_server: Callable[[int], bool] = stop_server
    start_server: Callable[[Path, int, Path | None], None] = start_server
    wait_until_up: Callable[[int, float], dict[str, Any] | None] = wait_until_up
    run_python: Callable[[Path, list[str]], tuple[int, str]] = run_python
    mcp_running: Callable[[Path], int] = lambda app: sum(  # noqa: E731
        bool(re.search(r"-m\s+(?:aagam\s+mcp|csdesk\s+serve)", p["command"])) for p in aagam_processes(app))
    stop_mcp: Callable[[Path], int] = stop_mcp
    open_browser: Callable[[int], None] = lambda port: webbrowser.open(f"http://127.0.0.1:{port}/")  # noqa: E731


class Log:
    """The update's own log, a line per step, in logs/aagam-update.log."""

    def __init__(self, home: Path | None) -> None:
        self.path = (home / "logs" / "aagam-update.log") if home else None

    def __call__(self, line: str) -> None:
        text = f"{_now()} {line}"
        if sys.stdout is not None and sys.stdout.isatty():
            print(text, flush=True)  # in the AAGAM Manager's window; a detached update writes only the log
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as out:
                out.write(text + "\n")


def _take_lock(app: Path) -> Path:
    lock = updates_dir(app) / "apply.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime > 1800:
        lock.unlink(missing_ok=True)  # left by an update that died half an hour ago
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise UpdateError("An update is already running. Wait for it to finish.") from exc
    os.write(handle, str(os.getpid()).encode())
    os.close(handle)
    return lock


def apply(
    app: Path | None = None,
    home: Path | None = None,
    port: int = 8765,
    commit: str | None = None,
    open_browser: bool = False,
    start_afterwards: bool = True,
    steps: Steps | None = None,
    fetch: Fetch | None = None,
) -> dict[str, Any]:
    """Put the newest version (or `commit`) in place, as the module docstring says. Returns what happened (also kept as
    the state's last_update). Raises UpdateError with what went wrong, after putting the old version back.

    `start_afterwards` is False for the daily check, which only runs when AAGAM is already closed and leaves it closed.
    """
    app = app or app_folder()
    steps = steps or Steps()
    log = Log(home)
    how = mode(app)
    old_commit = current_commit(app, how)
    old_record = read_record(app)
    notes: list[str] = []
    started = _now()
    lock = _take_lock(app)
    save_state(app, status="applying", error=None)
    log(f"update started ({how}; this copy is at {(old_commit or 'an unrecorded commit')[:12]})")
    stopped = replaced = pip = False
    backup: Path | None = None
    new_commit = old_commit
    try:
        if how == "archive":
            target = commit or (state(app).get("latest") or {}).get("commit")
            if not target:
                found = check(app, fetch)
                if found["error"]:
                    raise UpdateError(found["error"], needs_token=bool(found.get("needs_token")))
                target = (found.get("latest") or {}).get("commit")
            if not target:
                raise UpdateError("GitHub didn't say which version is the newest.")
            log(f"downloading {target[:12]}")
            source = stage(app, target, fetch)  # before anything stops: a failed download leaves AAGAM as it was
            new_pyproject = (source / "pyproject.toml").read_text(encoding="utf-8")
            new_commit = target
        elif how == "git":
            source = None
            new_pyproject = None
        else:
            raise UpdateError("Updates aren't set up for this copy of AAGAM. Install it with install.cmd to get them.")
        old_pyproject = (app / "pyproject.toml").read_text(encoding="utf-8")

        log("closing AAGAM")
        save_state(app, status="applying")
        if not steps.stop_server(port):
            raise UpdateError("AAGAM didn't close, so nothing was changed. Close it and try again.")
        stopped = True
        backup = backup_code(app, old_commit)
        log(f"kept a copy of the current version in {backup.name}")

        if how == "archive":
            pip = install_facts(old_pyproject) != install_facts(new_pyproject or "")
            if pip and dependencies_changed(old_pyproject, new_pyproject or ""):
                n = steps.stop_mcp(app)
                if n:
                    notes.append("Restart Claude Desktop to use the new version (its AAGAM tools were closed for the update).")
                    log(f"closed {n} AAGAM server(s) started by Claude Desktop")
            replaced = True  # from here on, files may have changed: a failure puts the copy back
            put_in_place(source, app)  # type: ignore[arg-type]
        else:
            branch = branch_of(app, "git") or DEFAULT_BRANCH
            replaced = True
            _git(app, "pull", "--ff-only", "origin", branch, timeout=300)
            new_commit = current_commit(app, "git")
            new_pyproject = (app / "pyproject.toml").read_text(encoding="utf-8")
            pip = install_facts(old_pyproject) != install_facts(new_pyproject)
        log(f"new files in place ({(new_commit or '?')[:12]})")

        if pip:
            log("installing the Python packages the new version needs")
            code, out = steps.run_python(app, ["-m", "pip", "install", "--quiet", "--timeout", "60", "--retries", "10", "-e", str(app)])
            if code:
                raise UpdateError("Installing the new version's Python packages failed: " + _last_lines(out))
        code, out = steps.run_python(app, ["-m", "aagam", "init"])
        if code:
            raise UpdateError("Setting up the data folder with the new version failed: " + _last_lines(out))
        write_record(app, commit=new_commit, version=version_of(app), updated_at=_now(), previous_commit=old_commit)

        if start_afterwards:
            log("starting AAGAM again")
            steps.start_server(app, port, home)
            if not steps.wait_until_up(port, 90):
                raise UpdateError("The new version didn't start.")
        else:
            log("AAGAM stays closed until you open it")
        code, out = steps.run_python(app, ["-m", "aagam", "doctor"])
        summary = [line for line in out.splitlines() if line.strip()][-1:] if out else []
        log(f"health check: {summary[0] if summary else 'no answer'}")
        if code:
            notes.append(f"The health check found something to fix: {summary[0] if summary else 'see the System page'}")
        if steps.mcp_running(app):
            notes.append("Restart Claude Desktop to give it the new version's tools.")
    except Exception as exc:
        message = str(exc) if isinstance(exc, UpdateError) else f"{type(exc).__name__}: {exc}"
        log(f"update failed: {message}")
        if replaced and backup is not None:
            log("putting the previous version back")
            try:
                if how == "git":
                    _git(app, "reset", "--keep", old_commit or "HEAD@{1}")
                else:
                    put_in_place(backup, app)
                if old_record:
                    _write_json(app / RECORD, old_record)
                else:
                    (app / RECORD).unlink(missing_ok=True)
                if pip:
                    steps.run_python(app, ["-m", "pip", "install", "--quiet", "-e", str(app)])
            except Exception as again:  # noqa: BLE001 - say so, and still try to start AAGAM
                log(f"putting the previous version back failed too: {again}")
                message += f" Putting the previous version back also failed ({again}); run Repair in the AAGAM Manager."
        if stopped and start_afterwards:
            try:
                steps.start_server(app, port, home)
                steps.wait_until_up(port, 60)
            except Exception as again:  # noqa: BLE001
                log(f"couldn't start AAGAM again: {again}")
        result = {"at": started, "from": old_commit, "to": old_commit, "ok": False, "error": message, "notes": notes}
        save_state(app, status="failed", error=message, last_update=result,
                   needs_token=bool(getattr(exc, "needs_token", False)))
        raise UpdateError(message, needs_token=bool(getattr(exc, "needs_token", False))) from exc
    finally:
        lock.unlink(missing_ok=True)
        prune(app)

    if how == "archive":
        note_installed_version(app)
        problem = register_daily_update(app)
        if problem:
            notes.append("The daily update check could not be added. AAGAM still updates itself while it is open.")
            log(f"daily update check: {problem}")
    result = {"at": started, "from": old_commit, "to": new_commit, "ok": True, "error": None, "notes": notes}
    save_state(app, status="done", available=False, changes=[], error=None, needs_token=False, last_update=result)
    log("update finished")
    if open_browser:
        steps.open_browser(port)
    return result


def _last_lines(text: str, n: int = 3) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " / ".join(lines[-n:]) or "no details"


def apply_if_idle(
    app: Path,
    home: Path,
    port: int,
    steps: Steps | None = None,
    fetch: Fetch | None = None,
) -> dict[str, Any]:
    """Install a GitHub update only when this is an installed copy, automatic updates are on, AAGAM is closed
    and nothing is being read. Leaves AAGAM closed. The daily task runs this; it never interrupts her."""
    log = Log(home)
    how = mode(app)
    if how != "archive":
        reason = "This copy updates another way, so the daily check left it alone."
    elif not read_record(app).get("auto_update", True):
        reason = "Automatic updates are off."
    elif health(port):
        reason = "AAGAM is open, so this check left it alone. It updates itself from the window."
    elif work_in_progress(home):
        reason = "AAGAM is reading documents, so this check waited."
    else:
        found = check(app, fetch)
        if found.get("error"):
            reason = str(found["error"])
        elif not found.get("available"):
            return {"applied": False, "reason": "Already up to date."}
        else:
            result = apply(app, home, port, start_afterwards=False, steps=steps, fetch=fetch)
            reason = "A new version is in place. Open AAGAM from the desktop."
            log(f"daily check: {reason}")
            return {"applied": True, "reason": reason, "to": result.get("to")}
    log(f"daily check: {reason}")
    return {"applied": False, "reason": reason}


def launch_apply(app: Path, home: Path, port: int, open_browser: bool = False) -> None:
    """Start `python -m aagam.updates apply` on its own, so it carries on after the server closes."""
    args = [sys.executable, "-m", "aagam.updates", "apply", "--app", str(app), "--home", str(home), "--port", str(port)]
    if open_browser:
        args.append("--open")
    log = home / "logs" / "aagam-update.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "AAGAM_HOME": str(home), "AAGAM_PORT": str(port), "PYTHONPATH": str(app / "src")}
    with log.open("ab") as out:
        subprocess.Popen(args, cwd=str(app), env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                         creationflags=_DETACHED, close_fds=True)


# ------------------------------------------------------------------ Claude Desktop, when AAGAM is removed


def remove_claude_entry(paths: list[Path]) -> list[str]:
    """Take AAGAM out of each Claude Desktop config (each backed up first). Returns the files changed."""
    changed = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            continue
        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if not isinstance(servers, dict) or "aagam" not in servers:
            continue
        path.with_name(f"{path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak").write_text(text, encoding="utf-8")
        del servers["aagam"]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        changed.append(str(path))
    return changed


# ------------------------------------------------------------------ python -m aagam.updates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aagam.updates", description="AAGAM's updater (the AAGAM Manager and install.ps1 use this).")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("apply", help="put the newest version in place")
    run.add_argument("--app", type=Path)
    run.add_argument("--home", type=Path)
    run.add_argument("--port", type=int, default=int(os.environ.get("AAGAM_PORT", "8765")))
    run.add_argument("--commit")
    run.add_argument("--open", action="store_true", help="open AAGAM in the browser afterwards")
    commands.add_parser("schedule", help="add the daily update check (Windows, an installed copy)").add_argument("--app", type=Path)
    record = commands.add_parser("record", help="write the install record (install.ps1)")
    record.add_argument("--app", type=Path)
    record.add_argument("--repo")
    record.add_argument("--branch")
    record.add_argument("--commit")
    record.add_argument("--source", choices=("download", "zip", "git", "local"))
    record.add_argument("--auto-update", choices=("on", "off"))
    unclaude = commands.add_parser("claude-remove", help="take AAGAM out of Claude Desktop's config")
    unclaude.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)

    if args.command == "apply":
        home = args.home or Path(os.environ.get("AAGAM_HOME") or Path.home() / "AAGAM")
        try:
            apply(args.app or app_folder(), home, args.port, args.commit, args.open)
        except UpdateError as exc:
            print(f"The update didn't go through: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "schedule":
        problem = register_daily_update(args.app or app_folder())
        if problem:
            print(problem, file=sys.stderr)
            return 1
        return 0
    if args.command == "record":
        app = args.app or app_folder()
        changes: dict[str, Any] = {"version": version_of(app)}
        for key in ("repo", "branch", "commit", "source"):
            if getattr(args, key):
                changes[key] = getattr(args, key)
        if args.auto_update:
            changes["auto_update"] = args.auto_update == "on"
        if not read_record(app).get("installed_at"):
            changes["installed_at"] = _now()
        changes["updated_at"] = _now()
        print(json.dumps(write_record(app, **changes), indent=2))
        return 0
    if args.command == "claude-remove":
        for changed in remove_claude_entry(args.paths):
            print(f"Took AAGAM out of {changed}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
