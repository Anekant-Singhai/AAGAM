"""Starting, finding and stopping recordings.

A recording started from Claude runs in its own background process
(`csdesk record-run <folder>`), because it has to stay attached to the browser
while she fills the form, long after the tool call that started it has
returned. The folder is the only channel between the two: the recorder keeps a
heartbeat file fresh, and a STOP file asks it to finish.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import Invalid, NotFound
from ..vault import Vault

STALE_AFTER_SECONDS = 15


def new_recording(
    settings: Settings, form: str, company: str | None = None, party_id: int | None = None, max_minutes: int = 120
) -> Path:
    form = " ".join(form.upper().split())
    if not form:
        raise Invalid("Say which form is being recorded, e.g. DIR-12.")
    meta: dict[str, Any] = {"form": form, "max_minutes": max_minutes, "started_at": datetime.now().isoformat(timespec="seconds")}
    with Vault.open(settings.db_path, actor="recorder") as vault:
        if company:
            company_id = vault.resolve_company(company)
            row = vault.company_row(company_id)
            meta |= {"company_id": company_id, "company_name": row["name"], "cin": row["cin"]}
        if party_id is not None:
            meta |= {"party_id": party_id, "party_name": vault.party(party_id)["name"]}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = settings.recordings_dir / f"{stamp}-{re.sub(r'[^A-Za-z0-9]+', '-', form).strip('-')}"
    folder.mkdir(parents=True, exist_ok=False)
    meta["id"] = folder.name
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return folder


def is_running(folder: Path) -> bool:
    if (folder / "done.json").exists() or (folder / "error.json").exists():
        return False
    beat = folder / "heartbeat"
    return beat.exists() and time.time() - beat.stat().st_mtime < STALE_AFTER_SECONDS


def active(settings: Settings) -> Path | None:
    if not settings.recordings_dir.exists():
        return None
    running = [folder for folder in settings.recordings_dir.iterdir() if folder.is_dir() and is_running(folder)]
    return max(running, key=lambda f: f.name) if running else None


def find(settings: Settings, recording: str | None) -> Path:
    if recording:
        folder = settings.recordings_dir / recording
        if not folder.is_dir():
            raise NotFound(f"There is no recording called {recording}.")
        return folder
    folder = active(settings)
    if folder is None:
        raise NotFound("No recording is running.")
    return folder


def spawn(settings: Settings, folder: Path) -> int:
    """Start the recorder for `folder` as a background process that outlives this call."""
    env = {
        **os.environ,
        "AAGAM_HOME": str(settings.home),
        "CSDESK_CDP_PORT": str(settings.cdp_port),
        "CSDESK_BROWSER": settings.browser,
    }
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    log = (folder / "recorder.log").open("ab")
    process = subprocess.Popen(
        [sys.executable, "-m", "csdesk", "record-run", str(folder)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        creationflags=flags,
        close_fds=True,
    )
    log.close()
    return process.pid


async def wait_for(folder: Path, names: tuple[str, ...], timeout: float) -> str | None:
    """Wait until one of the files appears in the folder; return its name, or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name in names:
            if (folder / name).exists():
                return name
        await asyncio.sleep(0.25)
    return None


def read_error(folder: Path) -> str:
    try:
        return json.loads((folder / "error.json").read_text(encoding="utf-8"))["message"]
    except (OSError, ValueError, KeyError):
        return "The recorder stopped unexpectedly; see recorder.log in the recording folder."


def counts(folder: Path) -> dict[str, int]:
    """How much has been recorded so far, by event type."""
    tally: dict[str, int] = {}
    path = folder / "events.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.search(r'"type": "(\w+)"', line)
            if match:
                tally[match.group(1)] = tally.get(match.group(1), 0) + 1
    return tally
