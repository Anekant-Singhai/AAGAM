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
from pathlib import Path
from typing import Any

from csdesk.errors import CsDeskError, Invalid

from . import __version__
from .config import AagamSettings, claude_desktop_config_path, load

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
    add = commands.add_parser("add", help="bring files into the library")
    add.add_argument("files", nargs="+", type=Path)
    add.add_argument("--company")
    add.add_argument("--tag", action="append", default=[])
    commands.add_parser("reindex", help="rebuild facts, resolutions and tags for every document")
    commands.add_parser("ai", help="run queued local-AI summaries now")
    commands.add_parser("build-ui", help="build the web interface (developers only)")
    commands.add_parser("doctor", help="check this computer has everything AAGAM needs")
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
            print(f"AAGAM didn't start; see {log}.", file=sys.stderr)
            return 1
    webbrowser.open(url)
    print(f"AAGAM is open at {url}")
    return 0


def _serve(settings: AagamSettings, args: argparse.Namespace) -> int:
    import uvicorn

    from .web.app import create_app

    _log_to_file(settings, "aagam-web.log")
    uvicorn.run(create_app(settings), host=settings.bind, port=settings.web_port, log_level="warning")
    return 0


def _mcp(settings: AagamSettings, args: argparse.Namespace) -> int:
    from .mcp_server import build

    _log_to_file(settings, "aagam-mcp.log")
    build(settings).run()
    return 0


def _log_to_file(settings: AagamSettings, name: str) -> None:
    settings.core.ensure_dirs()
    handler = logging.FileHandler(settings.core.logs_dir / name, encoding="utf-8")
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
    path = args.path or claude_desktop_config_path()
    data: dict[str, Any] = {}
    if path.exists():
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise Invalid(f"{path} isn't valid JSON ({exc.msg}, line {exc.lineno}); fix it first, nothing was changed.") from exc
        path.with_name(f"{path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak").write_text(text, encoding="utf-8")
    servers = data.setdefault("mcpServers", {})
    servers.pop("csdesk", None)  # AAGAM's server includes every CS Desk tool
    servers.update(claude_entry(settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Added AAGAM to {path}. Restart Claude Desktop to load it.")
    return 0


def _add(settings: AagamSettings, args: argparse.Namespace) -> int:
    from . import library
    from .db import open_db

    failed = 0
    with open_db(settings.core.db_path, actor="her") as vault:
        company_id = vault.resolve_company(args.company) if args.company else None
        for path in args.files:
            try:
                info = library.add_document(vault, settings.core, path, company_id, tags=args.tag)
            except CsDeskError as exc:
                print(f"{path.name}: {exc}", file=sys.stderr)
                failed += 1
                continue
            print(f"{path.name}: document {info['document_id']}, {info['doc_type']}, {len(info['tags'])} tags")
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
    "doctor": _doctor,
}
