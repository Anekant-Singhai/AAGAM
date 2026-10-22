"""`aagam doctor`: is everything AAGAM needs in place on this computer?

Each check says ok, warn (works, but something is missing) or fail (AAGAM, or that part
of it, won't work), with one line on how to fix it. It reads settings and asks local
services; it never prints anything from the library itself.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .config import AagamSettings, claude_desktop_config_path

OK, WARN, FAIL = "ok", "warn", "fail"
GB = 1024**3


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    status: str  # OK, WARN or FAIL
    detail: str
    fix: str = ""


def run_checks(settings: AagamSettings, claude_config: Path | None = None) -> list[Check]:
    steps: list[tuple[str, Callable[[], Check]]] = [
        ("python", check_python),
        ("data_folder", lambda: check_data_folder(settings)),
        ("database", lambda: check_database(settings)),
        ("interface", check_interface),
        ("port", lambda: check_port(settings)),
        ("ocr", check_ocr),
        ("browser", lambda: check_browser(settings)),
        ("local_ai", lambda: check_local_ai(settings)),
        ("claude_desktop", lambda: check_claude_desktop(settings, claude_config or claude_desktop_config_path())),
        ("disk", lambda: check_disk_space(settings)),
    ]
    results = []
    for key, step in steps:
        try:
            results.append(step())
        except Exception as exc:  # a check that breaks is itself a finding, not a crash
            results.append(Check(key, key, FAIL, f"the check itself failed: {exc}", "Send this output to whoever set AAGAM up."))
    return results


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == FAIL for c in checks) else 0


def report(checks: list[Check], encoding: str | None = None) -> str:
    marks = {OK: "✓", WARN: "!", FAIL: "✗"}
    try:
        "".join(marks.values()).encode(encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        marks = {OK: "ok", WARN: "! ", FAIL: "X "}
    width = max(len(c.label) for c in checks)
    indent = " " * (len(marks[OK]) + 1 + width + 2)
    lines = []
    for c in checks:
        lines.append(f"{marks[c.status]} {c.label.ljust(width)}  {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"{indent}-> {c.fix}")
    failed = sum(c.status == FAIL for c in checks)
    warned = sum(c.status == WARN for c in checks)
    lines.append("")
    if failed:
        lines.append(f"{failed} problem(s) to fix before AAGAM will work properly; see the -> lines above.")
    elif warned:
        lines.append(f"AAGAM is ready. {warned} optional item(s) above are worth a look.")
    else:
        lines.append("AAGAM is ready.")
    return "\n".join(lines)


# ------------------------------------------------------------------ checks


def check_python() -> Check:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 11):  # noqa: UP036 - deliberate: says so plainly if an old Python runs this
        return Check("python", "Python", OK, f"{version} ({sys.executable})")
    return Check("python", "Python", FAIL, f"{version} is too old", "Install Python 3.11 or newer from python.org, then run setup-windows.cmd again.")


def check_data_folder(settings: AagamSettings) -> Check:
    home = Path(settings.core.home)
    label = "Data folder"
    if not home.is_dir():
        return Check("data_folder", label, FAIL, f"{home} doesn't exist yet", "Run `aagam init` to create it (or set AAGAM_HOME to the right folder).")
    try:
        handle, probe = tempfile.mkstemp(dir=home, prefix=".aagam-doctor-")
        os.close(handle)
        os.remove(probe)
    except OSError as exc:
        return Check("data_folder", label, FAIL, f"{home} can't be written to ({exc.strerror or exc})", "Check the folder's permissions, or that its drive is connected and not full.")
    return Check("data_folder", label, OK, f"{home} (writable)")


def check_database(settings: AagamSettings) -> Check:
    from .db import SCHEMA_VERSION, open_db

    label = "Database"
    path = settings.core.db_path
    if not Path(settings.core.home).is_dir():
        return Check("database", label, FAIL, "not created yet (no data folder)", "Run `aagam init`.")
    try:
        with open_db(path) as vault:
            row = vault.conn.execute("SELECT value FROM aagam_meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return Check("database", label, WARN, f"{path.name} is busy ({exc})", "Try again in a moment; something is writing to it.")
        return Check("database", label, FAIL, f"{path.name} won't open ({exc})", "Close other programs using it; if it's damaged, restore csdesk.db from a backup.")
    except Exception as exc:
        return Check("database", label, FAIL, f"{path.name} won't open ({exc})", "Close other programs using it; if it's damaged, restore csdesk.db from a backup.")
    version = row[0] if row else "?"
    if version != SCHEMA_VERSION:
        return Check("database", label, FAIL, f"AAGAM tables at version {version}, expected {SCHEMA_VERSION}", "Reinstall AAGAM (setup-windows.cmd); the update brings the tables up to date.")
    return Check("database", label, OK, f"{path} opens; AAGAM tables at version {version}")


def check_interface() -> Check:
    static = Path(str(resources.files("aagam").joinpath("web", "static")))
    index = static / "index.html"
    scripts = list((static / "assets").glob("*.js")) if (static / "assets").is_dir() else []
    if index.is_file() and scripts:
        return Check("interface", "Interface", OK, f"built ({len(scripts)} script file(s) in {static})")
    missing = "index.html" if not index.is_file() else "assets/*.js"
    return Check("interface", "Interface", FAIL, f"not built ({missing} missing in {static})", "Developers: run `aagam build-ui` (needs Node.js). Otherwise reinstall AAGAM from a copy that includes it.")


def check_port(settings: AagamSettings) -> Check:
    port = settings.web_port
    label = "Web port"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        in_use = probe.connect_ex(("127.0.0.1", port)) == 0
    if not in_use:
        return Check("port", label, OK, f"{port} is free")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            answer = json.load(response)
    except (OSError, ValueError):
        answer = {}
    if isinstance(answer, dict) and answer.get("ok"):
        return Check("port", label, OK, f"{port}: AAGAM {answer.get('version', '?')} is already running there")
    return Check("port", label, FAIL, f"{port} is used by another program", f"Close that program, or set AAGAM_PORT to another port (for example {port + 1}).")


def check_ocr() -> Check:
    label = "Windows OCR"
    if sys.platform != "win32":
        return Check("ocr", label, WARN, "not on Windows: scanned pages won't be read (text PDFs and Office files still are)", "Read scans on a Windows computer, or bring in PDFs that already have text.")
    from . import ocr

    if ocr.available():
        return Check("ocr", label, OK, "available: scanned pages become searchable")
    try:
        import winrt.windows.media.ocr  # noqa: F401
    except ImportError:
        return Check("ocr", label, WARN, "the OCR packages aren't installed", "Run setup-windows.cmd again (it installs them).")
    return Check("ocr", label, WARN, "no OCR language installed: scanned pages won't be read", "Settings > Time & language > Language & region: add English (India) with its optical character recognition feature.")


def check_browser(settings: AagamSettings) -> Check:
    from csdesk.browser.chrome import find_browser
    from csdesk.errors import NotFound

    label = "Chrome or Edge"
    try:
        path = find_browser(settings.core.browser)
    except NotFound as exc:
        # On a server (no desktop) form filling isn't expected; on her laptop it is.
        status = FAIL if sys.platform == "win32" else WARN
        return Check("browser", label, status, f"not found: MCA forms can't be filled ({exc})", "Install Google Chrome, or set CSDESK_BROWSER to the browser's full .exe path.")
    return Check("browser", label, OK, f"{path}")


def check_local_ai(settings: AagamSettings) -> Check:
    from .ai import LocalAI

    label = "Local AI (optional)"
    if not settings.local_ai:
        return Check("local_ai", label, OK, "turned off (AAGAM_LOCAL_AI=off)")
    local = LocalAI.from_settings(settings)
    status = local.status()
    if not status.get("running"):
        return Check("local_ai", label, WARN, f"Ollama isn't answering at {local.url}: no AI summaries until it is", "Install Ollama from ollama.com and start it (everything else works without it).")
    if not status.get("model_installed"):
        return Check("local_ai", label, WARN, f"Ollama is running but {local.model} isn't installed", f"Run: ollama pull {local.model}  (or setup-windows.cmd -LocalAI)")
    return Check("local_ai", label, OK, f"Ollama at {local.url} with {local.model}")


def check_claude_desktop(settings: AagamSettings, path: Path) -> Check:
    label = "Claude Desktop (optional)"
    fix = "Run `aagam claude-config --write` (or setup-windows.cmd -ConfigureClaude), then restart Claude Desktop."
    if not path.is_file():
        return Check("claude_desktop", label, WARN, f"no config at {path}", fix)
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as exc:
        return Check("claude_desktop", label, WARN, f"{path} can't be read ({exc})", "Fix or remove that file (it must be valid JSON), then run `aagam claude-config --write`.")
    entry = (data.get("mcpServers") or {}).get("aagam") if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        return Check("claude_desktop", label, WARN, "AAGAM isn't in Claude Desktop's config", fix)
    command = Path(str(entry.get("command", "")))
    if not command.is_file():
        return Check("claude_desktop", label, WARN, f"the aagam entry points at {command}, which doesn't exist", fix)
    entry_home = (entry.get("env") or {}).get("AAGAM_HOME")
    if entry_home and Path(entry_home).resolve() != Path(settings.core.home).resolve():
        return Check("claude_desktop", label, WARN, f"the aagam entry uses data folder {entry_home}, not {settings.core.home}", fix)
    return Check("claude_desktop", label, OK, f"aagam entry in {path}")


def check_disk_space(settings: AagamSettings) -> Check:
    label = "Disk space"
    folder = Path(settings.core.home)
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    free = shutil.disk_usage(folder).free
    detail = f"{free / GB:.1f} GB free on {folder.anchor or folder}"
    if free < GB // 2:
        return Check("disk", label, FAIL, detail, "Free some space on that drive; AAGAM needs room for documents and the database.")
    if free < 2 * GB:
        return Check("disk", label, WARN, detail, "Space is getting low; free some before bringing in more documents.")
    return Check("disk", label, OK, detail)
