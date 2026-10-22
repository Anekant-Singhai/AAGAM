"""The CS Desk browser window: Chrome (or Edge) with a profile of its own and a local debugging port.

She opens it and logs in to the portal herself, captcha and OTP included. The
tools then attach to that same window over the Chrome DevTools Protocol, so
they work inside her session without ever handling her password. The
debugging port listens on 127.0.0.1 only, and the separate profile keeps her
everyday browsing out of it. (Chrome ignores the debugging port on its default
profile, which is one more reason for the separate one.)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import NotFound

MCA_HOME = "https://www.mca.gov.in/content/mca/global/en/home.html"


def _candidates(preference: str) -> list[Path]:
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    chrome = [
        Path(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        Path(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        Path(local, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    edge = [
        Path(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        Path(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    found_on_path = [
        Path(p) for p in (shutil.which(name) for name in ("chrome", "google-chrome", "chromium", "msedge")) if p
    ]
    return (edge + chrome if preference == "edge" else chrome + edge) + found_on_path


def find_browser(preference: str = "chrome") -> Path:
    """`preference` is "chrome", "edge", or the full path to a Chromium-based browser."""
    if preference.lower() not in ("chrome", "edge"):
        path = Path(preference)
        if path.is_file():
            return path
        raise NotFound(f"There is no browser at {preference}.")
    for path in _candidates(preference.lower()):
        if path.is_file():
            return path
    raise NotFound("Neither Chrome nor Edge was found. Set CSDESK_BROWSER to the browser's full .exe path.")


def debug_info(port: int) -> dict[str, Any] | None:
    """The browser's /json/version answer, or None when nothing is listening on the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def launch(settings: Settings, url: str = MCA_HOME, headless: bool = False, wait_seconds: float = 20) -> dict[str, Any]:
    """Open the CS Desk browser window (or report the one already open)."""
    info = debug_info(settings.cdp_port)
    if info:
        return {"started": False, "browser": info.get("Browser"), "port": settings.cdp_port}
    executable = find_browser(settings.browser)
    settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(executable),
        f"--remote-debugging-port={settings.cdp_port}",
        f"--user-data-dir={settings.browser_profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    args.append(url)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    process = subprocess.Popen(
        args,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        info = debug_info(settings.cdp_port)
        if info:
            return {"started": True, "pid": process.pid, "browser": info.get("Browser"), "port": settings.cdp_port}
        time.sleep(0.25)
    raise NotFound(
        "The browser started but its debugging port never opened. If a CS Desk browser window is already open "
        "(started some other way), close it and try again."
    )
