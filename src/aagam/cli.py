"""The `aagam` command.

    aagam                  open AAGAM (starts the server if needed, then the browser)
    aagam serve            run the server without opening a browser
    aagam mcp              run the MCP server over stdio (Claude Desktop starts this)
    aagam init             set up the data folder and print the Claude Desktop entry
    aagam claude-config    print it, or --write it into Claude Desktop's config (with a backup)
    aagam add FILE...      bring files into the library from a terminal
    aagam reindex          rebuild facts, resolutions and tags for every document
    aagam ai               run queued local-AI summaries now
    aagam build-ui         build the web interface from frontend/ (needs Node.js; developers only)
    aagam version          this copy's version and commit, and where it updates from
    aagam update           check GitHub for a newer version; --apply puts it in place (AAGAM closes and comes back)
    aagam backup           copy documents and records to Documents\\AAGAM backups
    aagam support          save a report on the Desktop (health check and logs, no documents)
    aagam uninstall        remove AAGAM from this computer (the data folder stays unless --remove-data --confirm REMOVE)
    aagam doctor           check this computer has everything AAGAM needs, with a fix for each problem

Everything else (record, set-sensitive, due, browser) is the core's: `csdesk --help`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from csdesk.errors import CsDeskError, Invalid

from . import __version__
from .config import AagamSettings, claude_desktop_config_paths, load

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="aagam", description="AAGAM: a Company Secretary's workbench.")
    parser.add_argument("--version", action="version", version=f"aagam {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("open", help="open AAGAM in the browser (the default)")
    commands.add_parser("serve", help="run the server without opening a browser")
    commands.add_parser("mcp", help="run the MCP server over stdio for Claude Desktop")
    commands.add_parser("init", help="set up the data folder")
    config = commands.add_parser("claude-config", help="print or write the Claude Desktop entry")
    config.add_argument("--write", action="store_true")
    config.add_argument("--path", type=Path)
    add = commands.add_parser("add", help="bring files, or whole folders with the folders inside them, into the library")
    add.add_argument("paths", nargs="+", type=Path, metavar="PATH")
    add.add_argument("--company", help="the client they belong to (otherwise worked out from each document)")
    add.add_argument("--tag", action="append", default=[])
    add.add_argument("--precedent", action="store_true", help="other companies' documents, for the precedent library")
    add.add_argument("--watch", action="store_true", help="for a folder: bring in new files while AAGAM is open")
    commands.add_parser("reindex", help="rebuild facts, resolutions and tags for every document")
    commands.add_parser("ai", help="run queued local-AI summaries now")
    commands.add_parser("build-ui", help="build the web interface (developers only)")
    commands.add_parser("version", help="this copy's version, commit and where it updates from")
    update = commands.add_parser("update", help="check for a newer version, or put it in place")
    update.add_argument("--check", action="store_true", help="only check and say what changed (the default)")
    update.add_argument("--apply", action="store_true", help="put the newest version in place; AAGAM closes and starts again")
    update.add_argument("--apply-if-idle", action="store_true", help="install an update only when AAGAM is closed and idle (the daily task)")
    update.add_argument("--open", action="store_true", help="with --apply: open AAGAM in the browser afterwards")
    update.add_argument("--set-token", action="store_true", help="store a GitHub token for a private repository (typed, not shown)")
    update.add_argument("--clear-token", action="store_true", help="forget the stored token")
    update.add_argument("--auto", choices=("on", "off"), help="install updates by itself when AAGAM is idle")
    update.add_argument("--repo", help="the GitHub repository to update from, owner/name")
    update.add_argument("--branch", help="its branch (main)")
    uninstall = commands.add_parser("uninstall", help="remove AAGAM from this computer (Windows)")
    uninstall.add_argument("--remove-data", action="store_true", help="also delete the data folder: every document and record")
    uninstall.add_argument("--confirm", default="", help='with --remove-data: type REMOVE to say you mean it')
    commands.add_parser("doctor", help="check this computer has everything AAGAM needs")
    backup = commands.add_parser("backup", help="copy your documents and records to Documents\\AAGAM backups")
    backup.add_argument("--to", type=Path, help="the folder to put the copy in")
    support = commands.add_parser("support", help="save a report you can send when you need help (no documents in it)")
    support.add_argument("--to", type=Path, help="the folder to put the report in")
    args = parser.parse_args(argv)
    settings = load()
    try:
        return COMMANDS[args.command or "open"](settings, args)
    except CsDeskError as exc:
        print(f"aagam: {exc}", file=sys.stderr)
        return 1


def _open(settings: AagamSettings, args: argparse.Namespace) -> int:
    from .web.app import wait_until_up

    url = f"http://127.0.0.1:{settings.web_port}/"
    if not wait_until_up(settings.web_port, timeout=0.5):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        log = (settings.core.logs_dir / "aagam-web.log")
        settings.core.ensure_dirs()
        with log.open("ab") as out:
            subprocess.Popen([sys.executable, "-m", "aagam", "serve"], stdin=subprocess.DEVNULL, stdout=out, stderr=out, creationflags=flags, close_fds=True)
        if not wait_until_up(settings.web_port, timeout=30):
            _tell(
                "AAGAM didn't open.\n\n"
                "Press the Windows key, type AAGAM Manager, and press Enter. "
                "Choose 4 (Health check), then 5 (Repair) if it finds a problem. Your documents are kept.\n\n"
                f"Details are in:\n{log}"
            )
            return 1
    webbrowser.open(url)
    print(f"AAGAM is open at {url}")
    return 0


def _serve(settings: AagamSettings, args: argparse.Namespace) -> int:
    import uvicorn

    from .web.app import create_app

    _log_to_file(settings, "aagam-web.log")
    app = create_app(settings)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.bind, port=settings.web_port, log_level="warning"))
    app.state.server = server  # POST /api/system/shutdown closes it gracefully; the updater asks for that
    server.run()
    return 0


def _mcp(settings: AagamSettings, args: argparse.Namespace) -> int:
    from .mcp_server import build

    _log_to_file(settings, "aagam-mcp.log")
    build(settings).run()
    return 0


def _tell(message: str) -> None:
    """A desktop shortcut uses pythonw, which has no window, so on Windows this is also a dialog."""
    print(message, file=sys.stderr)
    if sys.platform != "win32" or os.environ.get("AAGAM_NO_DIALOG"):
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "AAGAM", 0x00000010)  # MB_OK | MB_ICONERROR
    except (AttributeError, OSError):
        pass


def _log_to_file(settings: AagamSettings, name: str) -> None:
    settings.core.ensure_dirs()
    handler = RotatingFileHandler(settings.core.logs_dir / name, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def _init(settings: AagamSettings, args: argparse.Namespace) -> int:
    from csdesk.drafting import ensure_sample

    from .db import open_db

    settings.core.ensure_dirs()
    with open_db(settings.core.db_path):
        pass
    ensure_sample(settings.core.templates_dir)
    print(f"Data folder:  {settings.core.home}")
    print(f"Inbox:        {settings.core.inbox_dir}  (files dropped here are brought in automatically while AAGAM is open)")
    print(f"Templates:    {settings.core.templates_dir}")
    print(f"Law folder:   {settings.core.law_dir}")
    print(f"Local AI:     {'on, model ' + settings.local_ai_model if settings.local_ai else 'off'}")
    print()
    print("Claude Desktop entry (aagam claude-config --write adds it for you):")
    print(json.dumps(claude_entry(settings), indent=2))
    return 0


def claude_entry(settings: AagamSettings) -> dict[str, Any]:
    return {"aagam": {"command": sys.executable, "args": ["-m", "aagam", "mcp"], "env": {"AAGAM_HOME": str(settings.core.home)}}}


def _claude_config(settings: AagamSettings, args: argparse.Namespace) -> int:
    if not args.write:
        print(json.dumps(claude_entry(settings), indent=2))
        return 0
    # Every config Claude Desktop may read (the Microsoft Store build reads its own copy). All are read first, so a
    # broken one stops the lot and nothing is half done.
    found: list[tuple[Path, str | None, dict[str, Any]]] = []
    for path in [args.path] if args.path else claude_desktop_config_paths():
        text, data = None, {}
        if path.exists():
            text = path.read_text(encoding="utf-8")
            try:
                data = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError as exc:
                raise Invalid(f"{path} isn't valid JSON ({exc.msg}, line {exc.lineno}); fix it first, nothing was changed.") from exc
            if not isinstance(data, dict):
                raise Invalid(f"{path} isn't a JSON object; fix it first, nothing was changed.")
        found.append((path, text, data))
    for path, text, data in found:
        if text is not None:
            path.with_name(f"{path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak").write_text(text, encoding="utf-8")
        servers = data.setdefault("mcpServers", {})
        servers.pop("csdesk", None)  # AAGAM's server includes every CS Desk tool
        servers.update(claude_entry(settings))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Added AAGAM to {path}.")
    print("Restart Claude Desktop to load it.")
    return 0


def _add(settings: AagamSettings, args: argparse.Namespace) -> int:
    """Files are read one by one; a folder is read with the folders inside it, a line for each file."""
    from . import folders, library
    from .db import open_db

    tags = [*args.tag, *(["precedent"] if args.precedent and "precedent" not in args.tag else [])]
    with open_db(settings.core.db_path, actor="her") as vault:
        company_id = vault.resolve_company(args.company) if args.company else None
    failed = 0
    for path in args.paths:
        if path.is_dir():
            with open_db(settings.core.db_path, actor="her") as vault:
                folder = folders.add_folder(vault, settings.core.home, path, "one" if company_id else "auto", company_id, None,
                                            args.tag, args.precedent, args.watch)
            print(f"Reading {folder['path']}")

            def note(rel: str, status: str, error: str | None) -> None:
                print(f"  {rel}: {error}" if error else f"  {rel}: {'already in the library' if status == 'already' else status}")

            if not folders.run_queue(settings.core, f"cli:{os.getpid()}", folder_id=folder["id"], on_file=note):
                print("  AAGAM is already reading this folder in the background; see Library > Folders.")
                continue
            with open_db(settings.core.db_path, actor="her") as vault:
                folder = folders.get(vault, folder["id"])
            left_out = ", ".join(f"{n} {kind}" for kind, n in folder["skipped"].items())
            print(f"{folder['added']} added, {folder['already']} already in the library, {folder['failed']} couldn't be read"
                  + (f"; left out: {left_out}" if left_out else ""))
            failed += folder["failed"]
            continue
        try:
            origin = library.Origin.of_file(path) if path.is_file() else None
            with open_db(settings.core.db_path, actor="her") as vault:
                info = library.add_document(vault, settings.core, path, company_id, tags=tags, origin=origin,
                                            work_out_client=company_id is None)
        except CsDeskError as exc:
            print(f"{path.name}: {exc}", file=sys.stderr)
            failed += 1
            continue
        client = f", client {info['client']}" if info.get("client") else ""
        print(f"{path.name}: document {info['document_id']}, {info['doc_type']}, {len(info['tags'])} tags{client}")
    return 1 if failed else 0


def _reindex(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import library
    from .db import open_db

    with open_db(settings.core.db_path, actor="her") as vault:
        print(f"Reindexed {library.reindex_all(vault, settings.core.home)} documents.")
    return 0


def _ai(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import ai

    local = ai.LocalAI.from_settings(settings)
    status = local.status()
    if not status.get("model_installed"):
        print(status["message"], file=sys.stderr)
        return 1
    print(f"Summarised {ai.run_queue(settings, local)} document(s) with {local.model}.")
    return 0


def _build_ui(settings: AagamSettings, args: argparse.Namespace) -> int:
    frontend = ROOT / "frontend"
    node_dir = ROOT / ".tools" / "node"
    npm = node_dir / "npm.cmd" if (node_dir / "npm.cmd").exists() else Path("npm")
    env = {**os.environ, "PATH": f"{node_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    for step in (["install", "--no-audit", "--no-fund"], ["run", "build"]):
        result = subprocess.run([str(npm), *step], cwd=frontend, env=env, shell=sys.platform == "win32")
        if result.returncode != 0:
            return result.returncode
    print(f"Built into {Path(__file__).parent / 'web' / 'static'}")
    return 0


def _version(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import updates

    app = updates.app_folder()
    about = updates.info(app, settings.core.home)
    commit = f", commit {about['commit'][:7]}" if about["commit"] else ""
    print(f"AAGAM {__version__}{commit}")
    print(f"Program folder: {about['app_folder']}")
    print(f"Data folder:    {about['data_folder']}")
    if about["mode"] == "archive":
        auto = "installed by themselves when AAGAM is idle" if about["auto_update"] else "installed when you choose"
        print(f"Updates:        from github.com/{about['repo']} ({about['branch']}), {auto}")
    elif about["mode"] == "git":
        print(f"Updates:        a developer's git checkout of {about['repo'] or 'a repository'}: `aagam update --apply` pulls")
    else:
        print("Updates:        not set up for this copy (install it with install.cmd to get them)")
    return 0


def _update(settings: AagamSettings, args: argparse.Namespace) -> int:
    import re

    from . import updates

    app = updates.app_folder()
    if args.set_token:
        import getpass

        updates.save_token(app, getpass.getpass("Paste the GitHub token (it isn't shown): "))
        print("The update key is stored for this Windows user." if updates.load_token(app) else "No key was given; nothing changed.")
        return 0
    if args.clear_token:
        updates.save_token(app, None)
        print("The update key is forgotten.")
        return 0
    changes: dict[str, Any] = {}
    if args.repo:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
            raise Invalid("Give the repository as owner/name, e.g. Anekant-Singhai/AAGAM.")
        changes["repo"] = args.repo
    if args.branch:
        changes["branch"] = args.branch
    if args.auto:
        changes["auto_update"] = args.auto == "on"
    if changes:
        updates.write_record(app, **changes)
        print("Saved: " + ", ".join(f"{k} = {v}" for k, v in changes.items()))
        if not (args.apply or args.check):
            return 0
    if args.apply_if_idle and not args.apply:
        try:
            outcome = updates.apply_if_idle(app, settings.core.home, settings.web_port)
        except updates.UpdateError as exc:
            print(f"The update didn't go through: {exc}", file=sys.stderr)
            return 1
        print(outcome["reason"])
        return 0
    if args.apply:
        try:
            result = updates.apply(app, settings.core.home, settings.web_port, open_browser=args.open)
        except updates.UpdateError as exc:
            print(f"The update didn't go through: {exc}", file=sys.stderr)
            return 1
        print(f"AAGAM is up to date ({(result['to'] or '?')[:7]}).")
        for note in result["notes"]:
            print(f"  {note}")
        return 0
    found = updates.check(app)
    if found["error"]:
        print(found["error"], file=sys.stderr)
        return 1
    latest = found["latest"] or {}
    if not found["available"]:
        print(f"AAGAM is up to date ({(latest.get('commit') or '?')[:7]}).")
        return 0
    version = f" {latest['version']}" if latest.get("version") else ""
    print(f"A newer version{version} is ready ({len(found['changes'])} change(s)):")
    for change in found["changes"][:20]:
        print(f"  {(change.get('date') or '')[:10]}  {change.get('message')}")
    print("Put it in place with: aagam update --apply")
    return 0


def _uninstall(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import updates

    if args.remove_data and args.confirm != "REMOVE":
        raise Invalid("To delete the data folder too, add --confirm REMOVE. Nothing was changed.")
    if sys.platform != "win32":
        raise Invalid("Uninstalling is for Windows. Elsewhere, delete the program folder (the data folder is separate).")
    script = updates.app_folder() / "scripts" / "uninstall.ps1"
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Quiet", "-Port", str(settings.web_port)]
    if args.remove_data:
        command += ["-RemoveData", "-Confirm", "REMOVE"]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    kept = "is deleted too" if args.remove_data else f"stays in {settings.core.home}"
    print(f"AAGAM is being removed from this computer; your data {kept}.")
    return 0


def _backup(settings: AagamSettings, args: argparse.Namespace) -> int:
    from .maintain import backup_data

    print("Copying your data. This can take a while if there are many documents. AAGAM can stay open.")
    try:
        done = backup_data(Path(settings.core.home), args.to)
    except Invalid as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"A copy of your data is in:\n  {done['path']}")
    print(f"  {done['files']} files. AAGAM itself was not changed.")
    print("On a new laptop: install AAGAM, close it, then replace the AAGAM data folder with this copy.")
    return 0


def _support(settings: AagamSettings, args: argparse.Namespace) -> int:
    from .maintain import support_report

    try:
        done = support_report(settings, args.to)
    except Invalid as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"A report is saved here:\n  {done['path']}")
    print("It has the health check and recent logs. It does not contain your documents or your update key.")
    print("Send that file if you need help.")
    return 0


def _doctor(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import doctor

    checks = doctor.run_checks(settings)
    print(f"AAGAM {__version__} on this computer:\n")
    print(doctor.report(checks, getattr(sys.stdout, "encoding", None)))
    return doctor.exit_code(checks)


COMMANDS = {
    "open": _open,
    "serve": _serve,
    "mcp": _mcp,
    "init": _init,
    "claude-config": _claude_config,
    "add": _add,
    "reindex": _reindex,
    "ai": _ai,
    "build-ui": _build_ui,
    "version": _version,
    "update": _update,
    "uninstall": _uninstall,
    "doctor": _doctor,
    "backup": _backup,
    "support": _support,
}
