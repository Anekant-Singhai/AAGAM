"""This computer and this copy of AAGAM: health, updates, repairs and uninstalling, for the window's System page.

Updates themselves are in updates.py. Repairs run AAGAM's own setup script (scripts/setup-windows.ps1) with the
part to repair, in the background, each with a log the page can follow. Uninstalling runs scripts/uninstall.ps1
on its own, which closes AAGAM first. Both are for Windows, where AAGAM is installed; elsewhere they say so.
"""

from __future__ import annotations

import itertools
import logging
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from csdesk.errors import Invalid, NotFound

from .. import updates
from ..config import AagamSettings

log = logging.getLogger("aagam.system")
FIRST_CHECK = 30  # seconds after the server starts
TICK = 10 * 60  # how often the watcher looks
CHECK_EVERY = 2 * 3600  # how often it asks GitHub
IDLE_BEFORE_UPDATE = 20 * 60  # an update is put in place only after the window has been left alone this long
_ACTIVITY = {"last": time.monotonic()}


def note_activity() -> None:
    """The window asked for something (app.py's middleware calls this): she may be working, so no update now."""
    _ACTIVITY["last"] = time.monotonic()


def idle_for() -> float:
    """Seconds since the window last asked for anything (a closed or hidden window asks for nothing)."""
    return time.monotonic() - _ACTIVITY["last"]

# What the System page's Repair buttons run (setup-windows.ps1's switches).
REPAIRS: dict[str, list[str]] = {
    "local_ai": ["-RepairOnly", "-LocalAI"],
    "claude": ["-RepairOnly", "-ConfigureClaude"],
    "shortcuts": ["-RepairOnly", "-DesktopShortcut"],
    "reinstall": [],
}
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DETACHED = (0x00000008 | 0x00000200 | 0x08000000) if sys.platform == "win32" else 0


class UpdateSettings(BaseModel):
    auto_update: bool | None = None
    autostart: bool | None = None
    repo: str | None = None
    branch: str | None = None
    token: str | None = None


class UninstallIn(BaseModel):
    remove_data: bool = False
    confirm: str = ""


class PlaceIn(BaseModel):
    into: str | None = None


class PathIn(BaseModel):
    path: str = ""


def _action(check: Any) -> str | None:
    """The repair that fixes a doctor finding, when there is one (and only on Windows, where repairs run)."""
    if sys.platform != "win32" or check.status == "ok":
        return None
    if check.key == "local_ai":
        return "local_ai"
    if check.key == "claude_desktop":
        return "claude"
    if check.key in ("python", "interface") or (check.key == "ocr" and "packages" in check.detail):
        return "reinstall"
    return None


# ------------------------------------------------------------------ starting things that outlive a request


def _powershell(script: Path, args: list[str]) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args]


def launch_apply(app: Path, settings: AagamSettings) -> None:
    updates.launch_apply(app, settings.core.home, settings.web_port)


def launch_uninstall(app: Path, settings: AagamSettings, remove_data: bool) -> None:
    command = _powershell(app / "scripts" / "uninstall.ps1", ["-Quiet", "-Port", str(settings.web_port)])
    if remove_data:
        command += ["-RemoveData", "-Confirm", "REMOVE"]
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=_DETACHED, close_fds=True)


def start_repair(app: Path, settings: AagamSettings, action: str, log_path: Path) -> subprocess.Popen[bytes]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as out:
        return subprocess.Popen(_powershell(app / "scripts" / "setup-windows.ps1", REPAIRS[action]), cwd=str(app),
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, creationflags=_NO_WINDOW)


# Tests replace these; each starts something that carries on after the request has been answered.
LAUNCHERS: dict[str, Callable[..., Any]] = {"apply": launch_apply, "uninstall": launch_uninstall, "repair": start_repair}


def _start_update(app: Path, settings: AagamSettings) -> None:
    updates.save_state(app, status="applying", error=None)
    try:
        LAUNCHERS["apply"](app, settings)
    except OSError as exc:
        updates.save_state(app, status="failed", error=f"The update couldn't start ({exc}).")
        raise Invalid(f"The update couldn't start ({exc}).") from exc


def _tail(path: Path, lines: int = 40) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return [line for line in text.split("\n") if line.strip()][-lines:]


# ------------------------------------------------------------------ the API


def router(settings: AagamSettings, db: Callable[..., Any]) -> APIRouter:
    api = APIRouter(prefix="/api/system")
    home = settings.core.home
    tasks: dict[str, dict[str, Any]] = {}
    jobs: dict[str, dict[str, Any]] = {}
    numbers = itertools.count(1)

    @api.get("")
    def system() -> dict[str, Any]:
        return updates.info(updates.app_folder(), home)

    @api.post("/updates/check")
    def check() -> dict[str, Any]:
        return updates.check(updates.app_folder())

    @api.post("/updates/apply")
    def apply() -> dict[str, Any]:
        app = updates.app_folder()
        if updates.mode(app) == "none":
            raise Invalid("Updates aren't set up for this copy of AAGAM. Install it with install.cmd to get them.")
        if (updates.updates_dir(app) / "apply.lock").exists():
            raise Invalid("An update is already under way.")
        _start_update(app, settings)
        return {"started": True}

    @api.put("/updates/settings")
    def update_settings(body: UpdateSettings) -> dict[str, Any]:
        app = updates.app_folder()
        given = body.model_fields_set
        changes: dict[str, Any] = {}
        if "repo" in given and body.repo is not None:
            repo = body.repo.strip().removeprefix("https://github.com/").strip("/").removesuffix(".git")
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
                raise Invalid("Give the repository as owner/name, e.g. Anekant-Singhai/AAGAM.")
            changes["repo"] = repo
        if "branch" in given and body.branch is not None:
            if not re.fullmatch(r"[\w./-]+", body.branch.strip()):
                raise Invalid("That isn't a branch name.")
            changes["branch"] = body.branch.strip()
        if "auto_update" in given and body.auto_update is not None:
            changes["auto_update"] = body.auto_update
        if changes:
            updates.write_record(app, **changes)
        if "autostart" in given and body.autostart is not None:
            problem = updates.set_autostart(app, body.autostart)
            if problem:
                raise Invalid(problem)
        if "token" in given:
            updates.save_token(app, body.token)
        return updates.info(app, home)

    @api.get("/health")
    def health() -> dict[str, Any]:
        from .. import doctor

        return {"checks": [{"key": c.key, "label": c.label, "status": c.status, "detail": c.detail, "fix": c.fix,
                            "action": _action(c)} for c in doctor.run_checks(settings)]}

    @api.post("/repair/{action}")
    def repair(action: str) -> dict[str, Any]:
        if action not in REPAIRS:
            raise NotFound(f"There is no repair {action!r}; repairs: {', '.join(REPAIRS)}.")
        if sys.platform != "win32":
            raise Invalid("Repairs run on Windows, where AAGAM is installed.")
        running = [t for t in tasks.values() if t["process"].poll() is None]
        if running:
            raise Invalid("A repair is already running; wait for it to finish.")
        task = f"{action}-{next(numbers)}"
        log_path = home / "logs" / f"repair-{task}.log"
        tasks[task] = {"process": LAUNCHERS["repair"](updates.app_folder(), settings, action, log_path), "log": log_path}
        return {"started": True, "task": task}

    @api.get("/tasks/{task}")
    def task_status(task: str) -> dict[str, Any]:
        if task not in tasks:
            raise NotFound(f"There is no task {task!r} (tasks are forgotten when AAGAM closes).")
        code = tasks[task]["process"].poll()
        status = "running" if code is None else "done" if code == 0 else "failed"
        return {"task": task, "status": status, "log": _tail(tasks[task]["log"])}

    @api.post("/shutdown")
    def shutdown(request: Request) -> dict[str, Any]:
        server = getattr(request.app.state, "server", None)
        if server is not None:
            # After this answer has gone: uvicorn finishes the requests in hand, then closes.
            threading.Timer(0.3, lambda: setattr(server, "should_exit", True)).start()
        return {"stopping": True}

    @api.post("/backup")
    def start_backup(body: PlaceIn) -> dict[str, Any]:
        """Copy her data in the background. A large library takes a while; the window asks /jobs for the result."""
        from ..maintain import backup_data

        if any(job["status"] == "running" for job in jobs.values()):
            raise Invalid("A backup is already running.")
        into = Path(body.into).expanduser() if body.into and body.into.strip() else None
        job = f"backup-{next(numbers)}"
        jobs[job] = {"status": "running", "error": None, "path": None, "files": 0, "bytes": 0}

        def run() -> None:
            try:
                done = backup_data(home, into)
                jobs[job].update(status="done", path=done["path"], files=done["files"], bytes=done["bytes"], error=None)
            except Exception as exc:  # noqa: BLE001 - the window shows the sentence; the copy is removed if it was half done
                jobs[job].update(status="failed", error=str(exc) or "The copy didn't finish.")

        threading.Thread(target=run, name=job, daemon=True).start()
        return {"started": True, "task": job}

    @api.get("/jobs/{job}")
    def job_status(job: str) -> dict[str, Any]:
        if job not in jobs:
            raise NotFound(f"There is no job {job!r} (jobs are forgotten when AAGAM closes).")
        return {"task": job, **jobs[job]}

    @api.post("/support")
    def support(body: PlaceIn) -> dict[str, Any]:
        from ..maintain import support_report

        into = Path(body.into).expanduser() if body.into and body.into.strip() else None
        return support_report(settings, into)

    @api.post("/reveal")
    def reveal(body: PathIn) -> dict[str, Any]:
        """Open File Explorer on a file or folder she just made (a backup or a report). Only inside her user folder."""
        if not body.path.strip():
            raise Invalid("Nothing to show.")
        path = Path(body.path).expanduser()
        if not path.exists():
            raise NotFound("That file or folder is not there.")
        if sys.platform != "win32":
            raise Invalid("Showing a folder is for Windows.")
        resolved = path.resolve()
        user = Path.home().resolve()
        if resolved != user and user not in resolved.parents:
            raise Invalid("That is outside your user folder.")
        # explorer has to show a window; CREATE_NO_WINDOW would hide the folder she asked to see.
        if resolved.is_dir():
            subprocess.Popen(["explorer", str(resolved)])
        else:
            subprocess.Popen(["explorer", "/select,", str(resolved)])
        return {"shown": True}

    @api.post("/uninstall")
    def uninstall(body: UninstallIn) -> dict[str, Any]:
        if body.remove_data and body.confirm != "REMOVE":
            raise Invalid("To delete the data folder too, type REMOVE. Nothing was changed.")
        if sys.platform != "win32":
            raise Invalid("Uninstalling is for Windows. Elsewhere, delete the program folder (the data folder is separate).")
        LAUNCHERS["uninstall"](updates.app_folder(), settings, body.remove_data)
        return {"started": True}

    return api


# ------------------------------------------------------------------ checking by itself


def _busy(settings: AagamSettings) -> bool:
    """Is AAGAM reading something just now (a folder, a long scan)? An update waits for it."""
    return updates.work_in_progress(Path(settings.core.home))


class UpdateWatcher(threading.Thread):
    """Asks GitHub a little after AAGAM starts and every two hours. An installed copy with automatic updates on puts a
    new version in place only once the window has been left alone for IDLE_BEFORE_UPDATE and nothing is being read,
    so an update never cuts into her work; until then the window offers "Update now". A developer's checkout is only
    ever checked."""

    def __init__(self, settings: AagamSettings, first: float = FIRST_CHECK, every: float = TICK, check_every: float = CHECK_EVERY,
                 idle: float = IDLE_BEFORE_UPDATE) -> None:
        super().__init__(name="aagam-updates", daemon=True)
        self.settings, self.first, self.every, self.check_every, self.idle = settings, first, every, check_every, idle
        self.stopping = threading.Event()

    def run(self) -> None:
        if self.stopping.wait(self.first):
            return
        while True:
            try:
                self.tick()
            except Exception:
                log.exception("update check")
            if self.stopping.wait(self.every):
                return

    def tick(self) -> bool:
        """One look; True when it started an update."""
        app = updates.app_folder()
        how = updates.mode(app)
        if how == "none":
            return False
        found = updates.state(app)
        if self._time_to_ask(found):
            found = updates.check(app)
        if how != "archive" or not found["available"] or not updates.read_record(app).get("auto_update", True):
            return False
        if idle_for() < self.idle or _busy(self.settings) or (updates.updates_dir(app) / "apply.lock").exists():
            return False  # she is using AAGAM, or it is reading: a later look tries again
        _start_update(app, self.settings)
        return True

    def _time_to_ask(self, found: dict[str, Any]) -> bool:
        from datetime import datetime

        if found.get("status") in ("checking", "downloading", "applying") or not found.get("checked_at"):
            return True
        try:
            asked = datetime.fromisoformat(found["checked_at"])
        except ValueError:
            return True
        return (datetime.now() - asked).total_seconds() >= self.check_every

    def stop(self) -> None:
        self.stopping.set()


def helpers(settings: AagamSettings) -> list[threading.Thread]:
    """Background threads to start with the server."""
    return [UpdateWatcher(settings)]
