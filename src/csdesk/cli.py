"""The `csdesk` command.

    csdesk init            set up the data folder, database and sample template; print the Claude config
    csdesk serve           run the MCP server over stdio (Claude Desktop and Claude Code start this)
    csdesk browser         open the CS Desk browser window so she can log in
    csdesk due             print what is overdue and what falls due soon
    csdesk set-sensitive   type a PAN, Aadhaar or passport number locally, so it never passes through a chat
    csdesk claude-config   print the Claude Desktop config entry (--write adds it to Claude Desktop, with a backup)
    csdesk record FORM     record how she fills FORM in the CS Desk browser, then draft a recipe from it
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .config import Settings, load_settings
from .errors import CsDeskError, Invalid
from .vault import Source, Vault


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="csdesk", description="CS Desk: tools for a Company Secretary, for Claude.")
    parser.add_argument("--version", action="version", version=f"csdesk {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="set up the data folder and print the Claude Desktop config")
    commands.add_parser("serve", help="run the MCP server over stdio")
    browser = commands.add_parser("browser", help="open the CS Desk browser window so she can log in")
    browser.add_argument("--url", help="page to open instead of the MCA home page")
    due = commands.add_parser("due", help="print overdue and upcoming filings")
    due.add_argument("--company", help="id, CIN or name; all companies when omitted")
    due.add_argument("--days", type=int, default=60, help="how far ahead to look (default 60)")
    sensitive = commands.add_parser("set-sensitive", help="type a PAN, Aadhaar or passport number locally")
    sensitive.add_argument("--party", type=int, required=True, help="the person's party id")
    sensitive.add_argument("--field", choices=("pan", "aadhaar", "passport_no"), required=True)
    config = commands.add_parser("claude-config", help="print the Claude Desktop config entry")
    config.add_argument("--write", action="store_true", help="add it to Claude Desktop's config file (a backup is kept)")
    config.add_argument("--path", type=Path, help="config file to write (default: Claude Desktop's own)")
    record = commands.add_parser("record", help="record how she fills a form in the CS Desk browser; Enter stops it")
    record.add_argument("form", help="the form being filled, e.g. DIR-12")
    record.add_argument("--company", help="the company it is for (id, CIN or name), to match typed values")
    record.add_argument("--party", type=int, help="the person it is about (party id), to match typed values")
    record.add_argument("--minutes", type=int, default=120, help="stop after this many minutes (default 120)")
    run_recording = commands.add_parser("record-run", help=argparse.SUPPRESS)
    run_recording.add_argument("folder", type=Path)
    args = parser.parse_args(argv)

    settings = load_settings()
    try:
        return COMMANDS[args.command](settings, args)
    except CsDeskError as exc:
        print(f"csdesk: {exc}", file=sys.stderr)
        return 1


def _init(settings: Settings, args: argparse.Namespace) -> int:
    from .drafting import ensure_sample

    settings.ensure_dirs()
    with Vault.open(settings.db_path, actor="user"):
        pass
    sample = ensure_sample(settings.templates_dir)
    print(f"Data folder:  {settings.home}")
    print(f"Inbox:        {settings.inbox_dir}  (drop documents here)")
    print(f"Templates:    {settings.templates_dir}  (her Word templates; sample: {sample.name})")
    print(f"Law folder:   {settings.law_dir}  (Acts, Rules, SS-1/SS-2, circulars)")
    print()
    print("For Claude Desktop, add this under \"mcpServers\" in %APPDATA%\\Claude\\claude_desktop_config.json:")
    print(json.dumps(claude_config(settings), indent=2))
    return 0


def _serve(settings: Settings, args: argparse.Namespace) -> int:
    from .server import build_server

    settings.ensure_dirs()
    handler = logging.FileHandler(settings.logs_dir / "csdesk.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    build_server(settings).run()
    return 0


def _browser(settings: Settings, args: argparse.Namespace) -> int:
    from .browser import chrome

    info = chrome.launch(settings, url=args.url or chrome.MCA_HOME)
    if info["started"]:
        print("The CS Desk browser is open. Log in to MCA there; Claude will work inside that window.")
    else:
        print("The CS Desk browser is already open.")
    return 0


def _due(settings: Settings, args: argparse.Namespace) -> int:
    from .duedates import upcoming

    today = date.today()
    with Vault.open(settings.db_path, actor="user") as vault:
        company_id = vault.resolve_company(args.company) if args.company else None
        items = upcoming(vault, today, company_id, args.days)
    if not items:
        print(f"Nothing overdue, and nothing due in the next {args.days} days.")
        return 0
    labels = {"overdue": "OVERDUE", "due_this_week": "this week", "upcoming": ""}
    for item in items:
        check = "  (rule to confirm)" if item.certainty == "check" else ""
        print(f"{item.due:%d-%m-%Y}  {labels[item.state(today)]:9}  {item.company[:28]:28}  {item.form:12}  {item.title}{check}")
    return 0


def _set_sensitive(settings: Settings, args: argparse.Namespace) -> int:
    label = {"pan": "PAN", "aadhaar": "Aadhaar number", "passport_no": "passport number"}[args.field]
    with Vault.open(settings.db_path, actor="user") as vault:
        party = vault.party(args.party)
        value = getpass.getpass(f"{label} for {party['name']} (what you type stays hidden): ")
        if not value.strip():
            print("Nothing typed; no change.")
            return 1
        vault.save("party", {args.field: value}, Source("user", "user", note="typed locally with csdesk set-sensitive"), args.party)
        print(f"Saved. Shown everywhere as {vault.party(args.party)[args.field]}.")
    return 0


def _claude_config(settings: Settings, args: argparse.Namespace) -> int:
    if not args.write:
        print(json.dumps(claude_config(settings), indent=2))
        return 0
    path = args.path or Path(os.environ.get("APPDATA", Path.home()), "Claude", "claude_desktop_config.json")
    backup = write_claude_config(settings, path)
    print(f"Added CS Desk to {path}." + (f" The previous file is kept as {backup.name}." if backup else ""))
    print("Restart Claude Desktop to load it.")
    return 0


def write_claude_config(settings: Settings, path: Path) -> Path | None:
    """Add the csdesk entry to a Claude Desktop config file, keeping its other servers. Returns the backup path."""
    data: dict[str, Any] = {}
    backup = None
    if path.exists():
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise Invalid(f"{path} isn't valid JSON ({exc.msg}, line {exc.lineno}); fix it first, nothing was changed.") from exc
        backup = path.with_name(f"{path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak")
        backup.write_text(text, encoding="utf-8")
    data.setdefault("mcpServers", {}).update(claude_config(settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return backup


def claude_config(settings: Settings) -> dict[str, Any]:
    """The Claude Desktop "mcpServers" entry that starts this installation's server."""
    return {
        "csdesk": {
            "command": sys.executable,
            "args": ["-m", "csdesk", "serve"],
            "env": {"AAGAM_HOME": str(settings.home)},
        }
    }


def _record(settings: Settings, args: argparse.Namespace) -> int:
    import asyncio

    from . import recorder

    settings.ensure_dirs()
    if recorder.active(settings):
        print("A recording is already running; stop it first.", file=sys.stderr)
        return 1
    folder = recorder.new_recording(settings, args.form, args.company, args.party, args.minutes)

    async def go() -> dict[str, Any]:
        stop = asyncio.Event()
        task = asyncio.create_task(recorder.run(settings, folder, stop))
        while not task.done() and not (folder / "started.json").exists():
            await asyncio.sleep(0.25)
        if task.done():
            return await task  # raises the recorder's error, e.g. the browser isn't open
        print(f"Recording {args.form} in the CS Desk browser. She fills the form as usual (no need to submit).")
        print("Press Enter here when she is done.")
        waiting = asyncio.create_task(asyncio.to_thread(sys.stdin.readline))
        await asyncio.wait({task, waiting}, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        return await task

    try:
        summary = asyncio.run(go())
    except KeyboardInterrupt:
        (folder / "STOP").touch()
        print("Stopped.")
        return 1
    print(f"Recorded {summary['fields_filled']} field(s) over {summary['steps']} step(s); {summary['matched']} matched the company file.")
    print(f"Flow:   {summary['flow']}")
    if summary["recipe_draft"]:
        print(f"Recipe: {summary['recipe_draft']}")
    for item in summary["to_review"]:
        print(f"  - {item}")
    return 0


def _record_run(settings: Settings, args: argparse.Namespace) -> int:
    """The background recorder started by the record_start tool."""
    import asyncio
    import traceback

    from . import recorder

    folder: Path = args.folder
    try:
        asyncio.run(recorder.run(settings, folder))
    except Exception as exc:  # the tool reads error.json to tell Claude what went wrong
        message = str(exc) if isinstance(exc, CsDeskError) else f"The recorder failed: {exc}"
        (folder / "error.json").write_text(json.dumps({"message": message, "trace": traceback.format_exc()}), encoding="utf-8")
        return 1
    return 0


COMMANDS: dict[str, Callable[[Settings, argparse.Namespace], int]] = {
    "init": _init,
    "serve": _serve,
    "browser": _browser,
    "due": _due,
    "set-sensitive": _set_sensitive,
    "claude-config": _claude_config,
    "record": _record,
    "record-run": _record_run,
}
