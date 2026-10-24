"""Starting AAGAM the way Windows does: from a shortcut or at sign-in, with no console; once, even when clicked twice;
and the AAGAM Manager's window, which works without AAGAM's Python."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from aagam import cli
from aagam.config import load

ROOT = Path(__file__).resolve().parents[1]
windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_without_a_console_output_goes_to_a_log(monkeypatch, tmp_path):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    cli._without_a_console()
    try:
        print("hello from pythonw")
        assert sys.stdout.isatty() is False, "uvicorn's logging asks this; with no console it used to stop AAGAM"
    finally:
        sys.stdout.close()
    assert "hello from pythonw" in (tmp_path / "home" / "logs" / "aagam-console.log").read_text(encoding="utf-8")


def test_a_second_click_waits_for_the_first_start(monkeypatch, tmp_path):
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path / "home"))
    settings = load()
    settings.core.ensure_dirs()
    assert cli._claim_start(settings) is True
    assert cli._claim_start(settings) is False, "a start is under way: wait for it rather than start a second server"
    long_ago = time.time() - cli.START_TIMEOUT - 1
    os.utime(settings.core.logs_dir / "aagam-starting", (long_ago, long_ago))
    assert cli._claim_start(settings) is True, "a start that never came up doesn't block the next one"


def test_a_quick_start_shows_no_window(monkeypatch):
    import aagam.web.app as web

    monkeypatch.setattr(web, "wait_until_up", lambda port, timeout=20: True)
    assert cli._wait_while_showing(8799, 10) is True


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@windows
def test_the_server_runs_without_a_console(tmp_path):
    """What the desktop shortcut and the start at sign-in do: pythonw, no console and no handles at all."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pytest.skip("this Python has no pythonw.exe")
    port = _free_port()
    env = {**os.environ, "AAGAM_HOME": str(tmp_path / "home"), "AAGAM_PORT": str(port), "AAGAM_LOCAL_AI": "off"}
    detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP
    server = subprocess.Popen([str(pythonw), "-m", "aagam", "serve"], env=env, creationflags=detached, close_fds=True)
    try:
        answer = None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and server.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                    answer = json.load(response)
                break
            except OSError:
                time.sleep(0.3)
        log = tmp_path / "home" / "logs" / "aagam-console.log"
        assert answer and answer["ok"], f"it stopped before answering: {log.read_text(encoding='utf-8') if log.exists() else 'no log'}"
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/shutdown", data=b"", method="POST", headers={"X-AAGAM": "1"})
        urllib.request.urlopen(request, timeout=5).close()
        server.wait(30)
    finally:
        if server.poll() is None:
            server.kill()


@windows
def test_the_manager_window_builds(tmp_path):
    env = {**os.environ, "AAGAM_PORT": str(_free_port()), "AAGAM_MANAGER_SNAPSHOT": str(tmp_path / "manager.png")}
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "manager.ps1"), "-SelfTest"],
                          capture_output=True, text=True, timeout=120, env=env)
    assert done.returncode == 0, done.stderr
    assert "buttons=12" in done.stdout and "AAGAM is not running" in done.stdout
    assert (tmp_path / "manager.png").stat().st_size > 10_000
