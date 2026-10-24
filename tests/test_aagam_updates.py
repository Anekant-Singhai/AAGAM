"""The update manager, the System page's API and the installer scripts: without the network, a server or a real install."""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aagam import cli, doctor, updates
from aagam.config import AagamSettings, claude_config_in_use, claude_desktop_config_paths
from aagam.web import system_api
from aagam.web.app import create_app

CHANGE = {"X-AAGAM": "1"}
ROOT = Path(__file__).resolve().parents[1]
REPO = "someone/aagam"
OLD, NEW = "a" * 40, "b" * 40


def pyproject(version: str = "0.2.0", deps: tuple[str, ...] = ("fastapi>=0.115",)) -> str:
    listed = ", ".join(f'"{d}"' for d in deps)
    return (f'[build-system]\nrequires = ["setuptools>=68"]\n\n[project]\nname = "aagam"\nversion = "{version}"\n'
            f'dependencies = [{listed}]\n\n[project.scripts]\naagam = "aagam.cli:main"\n')


def code_files(version: str, deps: tuple[str, ...] = ("fastapi>=0.115",), extra: dict[str, str] | None = None) -> dict[str, str]:
    files = {
        "pyproject.toml": pyproject(version, deps),
        "README.md": f"AAGAM {version}\n",
        "src/aagam/__init__.py": f'__version__ = "{version}"\n',
        "src/aagam/web/static/index.html": "<html></html>",
        "src/aagam/web/static/assets/index.js": f"// {version}",
        "scripts/setup-windows.ps1": "# setup\n",
        "docs/AAGAM.md": "# map\n",
    }
    files.update(extra or {})
    return files


def make_app(tmp_path: Path, version: str = "0.2.0", commit: str | None = OLD, **more: str) -> Path:
    app = tmp_path / "app"
    for name, text in code_files(version, extra=more).items():
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        (app / name).write_text(text, encoding="utf-8")
    (app / "src" / "aagam.egg-info").mkdir(parents=True)
    (app / "src" / "aagam.egg-info" / "PKG-INFO").write_text("Name: aagam\n", encoding="utf-8")
    updates.write_record(app, repo=REPO, branch="main", commit=commit, version=version, installed_at="2026-10-01T10:00:00",
                         auto_update=True)
    return app


def zipball(files: dict[str, str], top: str = "someone-aagam-bbbbbbb") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"{top}/{name}", text)
    return buffer.getvalue()


class FakeGitHub:
    """Answers the few GitHub API calls the updater makes; records what was asked."""

    def __init__(self, head: str = NEW, version: str = "0.3.0", files: dict[str, str] | None = None) -> None:
        self.head, self.calls, self.status = head, [], {}
        self.version = version
        self.files = files or code_files(version)

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, headers.get("Authorization")))
        path = url.removeprefix(updates.API)
        for prefix, answer in self.status.items():
            if path.startswith(prefix):
                return answer
        if path == f"/repos/{REPO}/commits/main":
            return 200, {}, json.dumps(_commit(self.head, "Add LLP forms")).encode()
        if path.startswith(f"/repos/{REPO}/compare/"):
            return 200, {}, json.dumps({"commits": [_commit("c" * 40, "Folders"), _commit(self.head, "Add LLP forms")]}).encode()
        if path.startswith(f"/repos/{REPO}/contents/src/aagam/__init__.py"):
            content = base64.b64encode(f'__version__ = "{self.version}"\n'.encode()).decode()
            return 200, {}, json.dumps({"content": content}).encode()
        if path.startswith(f"/repos/{REPO}/zipball/"):
            return 200, {}, zipball(self.files)
        return 404, {}, b'{"message": "Not Found"}'


def _commit(sha: str, message: str) -> dict:
    return {"sha": sha, "commit": {"message": f"{message}\n\nmore words", "committer": {"date": "2026-10-20T09:00:00Z"}}}


class FakeSteps(updates.Steps):
    """Everything outside the app folder, recorded instead of done."""

    def __init__(self, up: list[bool] | None = None, stops: bool = True, mcp: int = 0) -> None:
        self.done: list[tuple] = []
        self.up = list(up or [True])

        def stop_server(port: int) -> bool:
            self.done.append(("stop", port))
            return stops

        def start_server(app: Path, port: int, home: Path | None) -> None:
            self.done.append(("start", port))

        def wait_until_up(port: int, timeout: float) -> dict | None:
            return {"ok": True} if (self.up.pop(0) if self.up else True) else None

        def run_python(app: Path, args: list[str]) -> tuple[int, str]:
            self.done.append(("python", tuple(args)))
            return 0, "AAGAM is ready."

        super().__init__(stop_server=stop_server, start_server=start_server, wait_until_up=wait_until_up, run_python=run_python,
                         mcp_running=lambda app: mcp, stop_mcp=lambda app: self.done.append(("stop-mcp",)) or mcp,
                         open_browser=lambda port: self.done.append(("open", port)))

    def pythons(self) -> list[tuple[str, ...]]:
        return [d[1] for d in self.done if d[0] == "python"]


# ------------------------------------------------------------------ the record and checking


def test_the_install_record_and_what_the_system_page_shows(tmp_path):
    app = make_app(tmp_path)
    assert updates.mode(app) == "archive"
    about = updates.info(app, tmp_path / "data")
    assert (about["version"], about["commit"], about["repo"], about["branch"]) == ("0.2.0", OLD, REPO, "main")
    assert about["auto_update"] is True and about["has_token"] is False
    assert about["updates"]["status"] == "idle" and about["updates"]["available"] is False
    updates.write_record(app, auto_update=False)
    assert updates.info(app, tmp_path)["auto_update"] is False
    (app / updates.RECORD).unlink()
    assert updates.mode(app) == "none"


def test_a_check_says_whether_there_is_something_new_and_what_changed(tmp_path):
    app = make_app(tmp_path)
    github = FakeGitHub()
    found = updates.check(app, github)
    assert found["available"] and found["error"] is None
    assert found["latest"] == {"commit": NEW, "date": "2026-10-20T09:00:00Z", "version": "0.3.0"}
    assert [c["message"] for c in found["changes"]] == ["Add LLP forms", "Folders"]  # newest first, first lines only
    assert updates.state(app)["checked_at"]

    updates.write_record(app, commit=NEW)
    assert updates.check(app, github)["available"] is False

    updates.write_record(app, commit=None)  # a copy whose commit wasn't recorded is brought to a known one
    assert updates.check(app, github)["changes"][0]["commit"] == NEW


def test_a_private_repository_asks_for_an_update_key_and_limits_are_explained(tmp_path):
    app = make_app(tmp_path)
    github = FakeGitHub()
    github.status = {f"/repos/{REPO}/commits": (404, {}, b'{"message": "Not Found"}')}
    found = updates.check(app, github)
    assert found["status"] == "failed" and found["needs_token"] and "update key" in found["error"]

    github.status = {f"/repos/{REPO}/commits": (401, {}, b'{"message": "Bad credentials"}')}
    assert "refused" in updates.check(app, github)["error"]

    github.status = {f"/repos/{REPO}/commits": (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 600)}, b"{}")}
    found = updates.check(app, github)
    assert "limit" in found["error"] and not found["needs_token"]

    def offline(url, headers):
        raise updates.UpdateError("Couldn't reach GitHub (no route). Check the internet connection and try again.")

    assert "internet" in updates.check(app, offline)["error"]


def test_the_token_is_sent_only_to_github_and_never_shown(tmp_path):
    app = make_app(tmp_path)
    updates.save_token(app, "  github_pat_123  ")
    github = FakeGitHub()
    updates.check(app, github)
    assert {auth for _, auth in github.calls} == {"Bearer github_pat_123"}
    assert "github_pat_123" not in json.dumps(updates.info(app, tmp_path))
    assert updates.info(app, tmp_path)["has_token"] is True
    updates.save_token(app, None)
    assert updates.load_token(app) is None and not updates.token_path(app).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows'")
def test_the_update_key_is_encrypted_for_this_windows_user(tmp_path):
    app = make_app(tmp_path)
    updates.save_token(app, "github_pat_secret")
    assert b"github_pat_secret" not in updates.token_path(app).read_bytes()
    assert updates.load_token(app) == "github_pat_secret"


def test_http_get_keeps_the_token_off_redirects(monkeypatch):
    seen = {}

    class Answer:
        status, headers = 200, {"X-Test": "1"}

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        seen["redirected"] = dict(request.header_items())
        seen["unredirected"] = dict(request.unredirected_hdrs)
        return Answer()

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    status, headers, _ = updates.http_get("https://api.github.com/x", {"Authorization": "Bearer t", "User-Agent": "u"})
    assert status == 200 and headers == {"x-test": "1"}
    assert seen["unredirected"] == {"Authorization": "Bearer t"}


# ------------------------------------------------------------------ getting a version ready


def test_a_download_is_unpacked_and_checked_before_use(tmp_path):
    app = make_app(tmp_path)
    root = updates.stage(app, NEW, FakeGitHub())
    assert (root / "src" / "aagam" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.3.0"\n'
    assert updates.state(app)["status"] == "ready"

    incomplete = {k: v for k, v in code_files("0.3.0").items() if "static" not in k}
    with pytest.raises(updates.UpdateError, match="incomplete"):
        updates.stage(app, NEW, FakeGitHub(files=incomplete))
    other = {**code_files("0.3.0"), "pyproject.toml": pyproject().replace('name = "aagam"', 'name = "other"')}
    with pytest.raises(updates.UpdateError, match="isn't AAGAM"):
        updates.stage(app, NEW, FakeGitHub(files=other))

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.txt", "x")
    with pytest.raises(updates.UpdateError, match="outside"):
        updates.unpack(unsafe, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_pip_runs_only_when_packages_or_commands_change():
    base = pyproject("0.2.0")
    assert updates.install_facts(base) == updates.install_facts(pyproject("0.3.0"))  # a new version number alone: no pip
    assert updates.install_facts(base) != updates.install_facts(pyproject("0.2.0", ("fastapi>=0.115", "httpx")))
    assert updates.dependencies_changed(base, pyproject("0.2.0", ("fastapi>=0.120",)))
    assert not updates.dependencies_changed(base, pyproject("0.9.0"))
    scripts = base.replace('aagam = "aagam.cli:main"', 'aagam = "aagam.cli:main"\naagam-manager = "aagam.updates:main"')
    assert updates.install_facts(base) != updates.install_facts(scripts)


# ------------------------------------------------------------------ putting it in place


def test_an_update_replaces_the_code_keeps_a_copy_and_starts_aagam_again(tmp_path):
    app = make_app(tmp_path, **{"src/aagam/old_module.py": "gone = True\n", "src/aagam/__pycache__/x.pyc": "cache"})
    (app / ".venv").mkdir()
    (app / ".venv" / "marker").write_text("my environment", encoding="utf-8")
    new_files = code_files("0.3.0", extra={"src/aagam/folders.py": "new = True\n"})
    steps = FakeSteps()
    result = updates.apply(app, tmp_path / "data", 8799, steps=steps, fetch=FakeGitHub(files=new_files))

    assert result["ok"] and (result["from"], result["to"]) == (OLD, NEW)
    assert (app / "src" / "aagam" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.3.0"\n'
    assert (app / "src" / "aagam" / "folders.py").is_file()
    assert not (app / "src" / "aagam" / "old_module.py").exists(), "a file the new version dropped goes"
    assert (app / "src" / "aagam.egg-info" / "PKG-INFO").is_file(), "pip's record of the editable install stays"
    assert (app / ".venv" / "marker").is_file(), "the Python environment is never touched"
    record = updates.read_record(app)
    assert (record["commit"], record["version"], record["previous_commit"]) == (NEW, "0.3.0", OLD)
    backup = app / ".update" / f"backup-{OLD[:12]}"
    assert (backup / "src" / "aagam" / "old_module.py").is_file()
    assert [d[0] for d in steps.done] == ["stop", "python", "start", "python"]
    assert steps.pythons() == [("-m", "aagam", "init"), ("-m", "aagam", "doctor")], "same packages: no pip"
    saved = updates.state(app)
    assert saved["status"] == "done" and saved["last_update"]["ok"] and not saved["available"]
    assert not list((app / ".update").glob("stage-*")) and not list((app / ".update").glob("download-*"))
    assert (tmp_path / "data" / "logs" / "aagam-update.log").read_text(encoding="utf-8").count("update finished") == 1


def test_new_packages_are_installed_and_claude_desktop_is_told_to_restart(tmp_path):
    app = make_app(tmp_path)
    new_files = code_files("0.3.0", deps=("fastapi>=0.115", "httpx>=0.27"))
    steps = FakeSteps(mcp=1)
    result = updates.apply(app, tmp_path / "data", 8799, steps=steps, fetch=FakeGitHub(files=new_files))
    pip = steps.pythons()[0]
    assert pip[:3] == ("-m", "pip", "install") and pip[-2:] == ("-e", str(app))
    assert ("stop-mcp",) in steps.done
    assert any("Restart Claude Desktop" in note for note in result["notes"])


def test_a_new_version_that_doesnt_start_is_taken_back_out(tmp_path):
    app = make_app(tmp_path)
    steps = FakeSteps(up=[False, True])  # the new version doesn't answer; the old one, put back, does
    with pytest.raises(updates.UpdateError, match="didn't start"):
        updates.apply(app, tmp_path / "data", 8799, steps=steps, fetch=FakeGitHub())
    assert (app / "src" / "aagam" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.2.0"\n'
    assert updates.read_record(app)["commit"] == OLD
    assert [d[0] for d in steps.done].count("start") == 2
    saved = updates.state(app)
    assert saved["status"] == "failed" and saved["last_update"]["ok"] is False and "didn't start" in saved["error"]
    assert not (app / ".update" / "apply.lock").exists()


def test_nothing_changes_when_aagam_wont_close_or_the_download_fails(tmp_path):
    app = make_app(tmp_path)
    steps = FakeSteps(stops=False)
    with pytest.raises(updates.UpdateError, match="didn't close"):
        updates.apply(app, tmp_path / "data", 8799, steps=steps, fetch=FakeGitHub())
    assert updates.version_of(app) == "0.2.0" and [d[0] for d in steps.done] == ["stop"]

    github = FakeGitHub()
    github.status = {f"/repos/{REPO}/zipball": (502, {}, b"{}")}
    steps = FakeSteps()
    with pytest.raises(updates.UpdateError):
        updates.apply(app, tmp_path / "data", 8799, steps=steps, fetch=github)
    assert steps.done == [], "AAGAM wasn't even asked to close"


def test_only_the_two_newest_copies_are_kept(tmp_path):
    app = make_app(tmp_path)
    for n, commit in enumerate(("b" * 40, "c" * 40, "d" * 40)):
        updates.apply(app, tmp_path / "data", 8799, commit=commit, steps=FakeSteps(), fetch=FakeGitHub(head=commit, version=f"0.{3 + n}.0"))
        time.sleep(0.05)
    backups = sorted(p.name for p in (app / ".update").glob("backup-*"))
    assert len(backups) == 2 and f"backup-{'a' * 12}" not in backups
    assert updates.version_of(app) == "0.5.0"


def test_one_update_at_a_time(tmp_path):
    app = make_app(tmp_path)
    (app / ".update").mkdir(exist_ok=True)
    (app / ".update" / "apply.lock").write_text("123", encoding="utf-8")
    with pytest.raises(updates.UpdateError, match="already running"):
        updates.apply(app, tmp_path / "data", 8799, steps=FakeSteps(), fetch=FakeGitHub())


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_a_developer_checkout_updates_by_git_pull(tmp_path):
    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    origin, work, app = tmp_path / "origin.git", tmp_path / "work", tmp_path / "checkout"
    git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    git("clone", str(origin), str(work), cwd=tmp_path)
    for name, text in code_files("0.2.0").items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text, encoding="utf-8")
    for args in (("config", "user.email", "t@example.com"), ("config", "user.name", "T"), ("add", "-A"), ("commit", "-m", "First"),
                 ("push", "origin", "HEAD:main")):
        git(*args, cwd=work)
    git("clone", "-b", "main", str(origin), str(app), cwd=tmp_path)
    assert updates.mode(app) == "git" and updates.check(app)["available"] is False

    (work / "src" / "aagam" / "__init__.py").write_text('__version__ = "0.3.0"\n', encoding="utf-8")
    for args in (("commit", "-am", "Bump to 0.3.0"), ("push", "origin", "HEAD:main")):
        git(*args, cwd=work)
    found = updates.check(app)
    assert found["available"] and [c["message"] for c in found["changes"]] == ["Bump to 0.3.0"]
    assert found["latest"]["version"] == "0.3.0"
    assert updates.info(app, tmp_path)["auto_update"] is False, "a checkout never updates by itself"

    steps = FakeSteps()
    result = updates.apply(app, tmp_path / "data", 8799, steps=steps)
    assert result["ok"] and updates.version_of(app) == "0.3.0" and result["to"] == updates.current_commit(app)


def test_mirroring_leaves_caches_and_pips_record_alone(tmp_path):
    source, target = tmp_path / "new", tmp_path / "old"
    (source / "pkg").mkdir(parents=True)
    (source / "pkg" / "a.py").write_text("a", encoding="utf-8")
    (target / "pkg" / "__pycache__").mkdir(parents=True)
    (target / "pkg" / "__pycache__" / "a.pyc").write_text("c", encoding="utf-8")
    (target / "pkg" / "b.py").write_text("b", encoding="utf-8")
    (target / "x.egg-info").mkdir()
    updates._mirror(source, target)
    assert (target / "pkg" / "a.py").is_file() and not (target / "pkg" / "b.py").exists()
    assert (target / "pkg" / "__pycache__" / "a.pyc").is_file() and (target / "x.egg-info").is_dir()


def test_claude_desktop_entry_is_taken_out_on_uninstall(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    config.write_text(json.dumps({"mcpServers": {"aagam": {"command": "x"}, "other": {"command": "y"}}, "theme": "dark"}), encoding="utf-8")
    assert updates.remove_claude_entry([config, tmp_path / "missing.json"]) == [str(config)]
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data == {"mcpServers": {"other": {"command": "y"}}, "theme": "dark"}
    assert len(list(tmp_path.glob("claude_desktop_config.json.*.bak"))) == 1
    assert updates.remove_claude_entry([config]) == [], "nothing to take out the second time"

    # Uninstalling one copy leaves another copy's entry (a developer's, say) alone.
    app = tmp_path / "app"
    mine = {"command": str(app / ".venv" / "Scripts" / "python.exe"), "args": ["-m", "aagam", "mcp"]}
    config.write_text(json.dumps({"mcpServers": {"aagam": {"command": "I:\\dev\\.venv\\Scripts\\python.exe"}}}), encoding="utf-8")
    assert updates.remove_claude_entry([config], app) == []
    config.write_text(json.dumps({"mcpServers": {"aagam": mine}}), encoding="utf-8")
    assert updates.remove_claude_entry([config], app) == [str(config)]


def test_the_updater_records_an_installation(tmp_path, capsys):
    app = make_app(tmp_path)
    (app / updates.RECORD).unlink()
    assert updates.main(["record", "--app", str(app), "--repo", REPO, "--branch", "main", "--commit", NEW, "--source", "zip",
                         "--auto-update", "on"]) == 0
    record = updates.read_record(app)
    assert (record["repo"], record["commit"], record["source"], record["auto_update"], record["version"]) == (REPO, NEW, "zip", True, "0.2.0")
    assert record["installed_at"]

    # Installed again from a ZIP, whose commit isn't known: the old commit mustn't stay in the record.
    assert updates.main(["record", "--app", str(app), "--repo", REPO, "--commit", "none", "--source", "zip"]) == 0
    assert updates.read_record(app)["commit"] is None and updates.read_record(app)["installed_at"] == record["installed_at"]

    # Start at sign-in is offered once per copy: a reinstall keeps her choice (the tests never touch the registry).
    assert updates.main(["autostart", "--app", str(app), "on", "--once"]) == 0
    assert updates.read_record(app)["autostart_offered"] is True


# ------------------------------------------------------------------ the System page's API


@pytest.fixture
def system(settings, tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setenv("AAGAM_APP_DIR", str(app))
    started = []
    monkeypatch.setitem(system_api.LAUNCHERS, "apply", lambda app_dir, s: started.append(("apply", app_dir)))
    monkeypatch.setitem(system_api.LAUNCHERS, "uninstall", lambda app_dir, s, remove: started.append(("uninstall", remove)))
    # Port 1 refuses at once, so the local-AI check is a warning with a Repair button, and never a real Ollama.
    web = create_app(AagamSettings(core=settings, local_ai=True, local_ai_url="http://127.0.0.1:1"), background=False)
    with TestClient(web, base_url="http://127.0.0.1") as client:
        yield client, app, started


def test_the_system_page_shows_this_copy_and_changes_its_update_settings(system, settings):
    client, app, _ = system
    about = client.get("/api/system").json()
    assert set(about) == {"version", "commit", "installed_at", "app_folder", "data_folder", "mode", "auto_update", "repo", "branch",
                          "has_token", "autostart", "updates"}
    assert about["autostart"] is False  # a test's copy has no Python of its own, so it never starts with Windows
    assert (about["mode"], about["commit"], about["data_folder"]) == ("archive", OLD, str(settings.home))
    assert set(about["updates"]) == set(updates.STATE_KEYS)
    assert client.get("/api/health").json()["commit"] == OLD

    changed = client.put("/api/system/updates/settings", json={"auto_update": False, "repo": "https://github.com/me/aagam.git",
                                                               "token": "github_pat_x"}, headers=CHANGE).json()
    assert (changed["auto_update"], changed["repo"], changed["has_token"]) == (False, "me/aagam", True)
    assert client.put("/api/system/updates/settings", json={"branch": "main"}, headers=CHANGE).json()["has_token"] is True
    assert client.put("/api/system/updates/settings", json={"token": None}, headers=CHANGE).json()["has_token"] is False
    assert client.put("/api/system/updates/settings", json={"repo": "not a repo"}, headers=CHANGE).status_code == 400
    assert client.put("/api/system/updates/settings", json={"auto_update": True}).status_code == 403, "changes need the window's header"


def test_checking_and_updating_from_the_window(system, monkeypatch):
    client, app, started = system
    monkeypatch.setattr(updates, "http_get", FakeGitHub())
    found = client.post("/api/system/updates/check", headers=CHANGE).json()
    assert found["available"] and found["latest"]["version"] == "0.3.0"
    assert client.post("/api/system/updates/apply", headers=CHANGE).json() == {"started": True}
    assert started == [("apply", app)] and updates.state(app)["status"] == "applying"

    (app / updates.RECORD).unlink()
    assert client.post("/api/system/updates/apply", headers=CHANGE).status_code == 400  # not set up for updates


def test_health_with_repairs_and_uninstalling(system, monkeypatch, tmp_path):
    client, app, started = system
    checks = client.get("/api/system/health").json()["checks"]
    assert {c["key"] for c in checks} >= {"python", "database", "local_ai", "claude_desktop"}
    assert all(set(c) == {"key", "label", "status", "detail", "fix", "action"} for c in checks)
    assert client.post("/api/system/repair/nonsense", headers=CHANGE).status_code == 404

    class Process:
        polls = [None, 0]

        def poll(self):
            return self.polls.pop(0) if self.polls else 0

    def repair(app_dir, s, action, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("== Downloading the local AI\nAAGAM is set up.\n", encoding="utf-8")
        return Process()

    monkeypatch.setitem(system_api.LAUNCHERS, "repair", repair)
    if sys.platform == "win32":
        assert next(c for c in checks if c["key"] == "local_ai")["action"] == "local_ai"
        task = client.post("/api/system/repair/local_ai", headers=CHANGE).json()
        assert task["started"] and task["task"].startswith("local_ai-")
        assert client.post("/api/system/repair/claude", headers=CHANGE).status_code == 400, "one repair at a time"
        status = client.get(f"/api/system/tasks/{task['task']}").json()
        assert status["status"] == "done" and status["log"][-1] == "AAGAM is set up."
        assert client.post("/api/system/uninstall", json={"remove_data": False}, headers=CHANGE).json() == {"started": True}
        assert started[-1] == ("uninstall", False)
    else:
        assert client.post("/api/system/repair/local_ai", headers=CHANGE).status_code == 400
    assert client.get("/api/system/tasks/nothing").status_code == 404
    refused = client.post("/api/system/uninstall", json={"remove_data": True, "confirm": "yes"}, headers=CHANGE)
    assert refused.status_code == 400 and "REMOVE" in refused.json()["detail"]


def test_shutdown_closes_the_server_after_answering(system):
    client, _, _ = system

    class Server:
        should_exit = False

    server = Server()
    client.app.state.server = server
    assert client.post("/api/system/shutdown", headers=CHANGE).json() == {"stopping": True}
    time.sleep(0.6)
    assert server.should_exit is True


def test_the_watcher_updates_by_itself_only_when_allowed_and_idle(settings, tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setenv("AAGAM_APP_DIR", str(app))
    monkeypatch.setattr(updates, "http_get", FakeGitHub())
    started = []
    monkeypatch.setitem(system_api.LAUNCHERS, "apply", lambda app_dir, s: started.append(app_dir))
    aagam_settings = AagamSettings(core=settings, local_ai=False)
    watcher = system_api.UpdateWatcher(aagam_settings)
    monkeypatch.setattr(system_api, "idle_for", lambda: system_api.IDLE_BEFORE_UPDATE + 1)  # nobody has used the window

    monkeypatch.setattr(system_api, "_busy", lambda s: True)
    assert watcher.tick() is False and not started  # reading something: wait
    monkeypatch.setattr(system_api, "_busy", lambda s: False)
    updates.write_record(app, auto_update=False)
    assert watcher.tick() is False and not started  # she chose to update by hand
    updates.write_record(app, auto_update=True)
    monkeypatch.setattr(system_api, "idle_for", lambda: 60.0)
    assert watcher.tick() is False and not started, "she used the window a minute ago: the update waits"
    assert updates.state(app)["available"] is True  # meanwhile the window offers Update now
    monkeypatch.setattr(system_api, "idle_for", lambda: system_api.IDLE_BEFORE_UPDATE + 1)
    assert watcher.tick() is True and started == [app]
    assert updates.state(app)["status"] == "applying"


def test_using_the_window_counts_as_activity_but_its_health_checks_dont(system):
    client, _, _ = system
    client.get("/api/overview")
    assert system_api.idle_for() < 5
    system_api._ACTIVITY["last"] -= 3600
    client.get("/api/health")
    assert system_api.idle_for() > 3000, "the window asking whether AAGAM is still there isn't her working"
    client.get("/api/documents")
    assert system_api.idle_for() < 5


def test_a_watcher_asks_github_only_every_so_often(settings, tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setenv("AAGAM_APP_DIR", str(app))
    github = FakeGitHub(head=OLD)  # nothing new
    monkeypatch.setattr(updates, "http_get", github)
    watcher = system_api.UpdateWatcher(AagamSettings(core=settings, local_ai=False))
    watcher.tick()
    asked = len(github.calls)
    watcher.tick()
    assert len(github.calls) == asked, "checked a moment ago: no need to ask GitHub again"
    updates.save_state(app, checked_at="2026-01-01T09:00:00")
    watcher.tick()
    assert len(github.calls) > asked


def test_a_record_naming_a_missing_branch_follows_the_repository_s_default(tmp_path):
    app = make_app(tmp_path)  # recorded as "main"
    github = FakeGitHub()
    github.status = {f"/repos/{REPO}/commits/main": (404, {}, b'{"message": "No commit found for SHA: main"}')}

    def answers(url, headers):
        if url.endswith(f"/repos/{REPO}"):
            return 200, {}, json.dumps({"default_branch": "master"}).encode()
        if url.endswith(f"/repos/{REPO}/commits/master"):
            return 200, {}, json.dumps(_commit(NEW, "On master")).encode()
        return github(url, headers)

    found = updates.check(app, answers)
    assert found["error"] is None and found["available"] and found["latest"]["commit"] == NEW
    assert updates.read_record(app)["branch"] == "master"


def test_a_copy_installed_from_a_zip_takes_github_s_commit_when_the_versions_match(tmp_path):
    app = make_app(tmp_path, version="0.3.0", commit=None)
    found = updates.check(app, FakeGitHub(version="0.3.0"))
    assert found["available"] is False, "the same version as GitHub's newest: no update to itself straight after installing"
    assert updates.read_record(app)["commit"] == NEW
    older = make_app(tmp_path / "older", version="0.2.0", commit=None)
    assert updates.check(older, FakeGitHub(version="0.3.0"))["available"] is True
    newer = make_app(tmp_path / "newer", version="0.3.1", commit=None)
    assert updates.check(newer, FakeGitHub(version="0.3.0"))["available"] is False, "never back to an older version"


def test_starting_with_windows_is_never_set_by_tests(tmp_path):
    app = make_app(tmp_path)
    (app / ".venv" / "Scripts").mkdir(parents=True)
    (app / ".venv" / "Scripts" / "pythonw.exe").write_bytes(b"")
    assert updates.set_autostart(app, True) is None
    assert updates.autostart(app) is False, "AAGAM_NO_SYSTEM_CHANGES keeps the registry untouched"
    assert updates.register_daily_update(app) is None


# ------------------------------------------------------------------ Claude Desktop's config, the command line


def test_claude_desktop_from_the_store_reads_its_own_config(settings, tmp_path, monkeypatch, capsys):
    local, roaming = tmp_path / "local", tmp_path / "roaming"
    (local / "Packages" / "Claude_pzs8sxrjxfjjc").mkdir(parents=True)
    (local / "Packages" / "ClaudeOther").mkdir(parents=True)  # not Claude's: no underscore
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    store = local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert claude_desktop_config_paths() == [store, roaming / "Claude" / "claude_desktop_config.json"]
    assert claude_config_in_use() == store

    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "preferences": {"a": 1}}), encoding="utf-8")
    monkeypatch.setenv("AAGAM_HOME", str(settings.home))
    assert cli.main(["claude-config", "--write"]) == 0
    for path in claude_desktop_config_paths():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["mcpServers"]["aagam"]["env"]["AAGAM_HOME"] == str(settings.home)
    assert json.loads(store.read_text(encoding="utf-8"))["preferences"] == {"a": 1}
    assert len(list(store.parent.glob("*.bak"))) == 1
    assert doctor.check_claude_desktop(AagamSettings(core=settings), claude_config_in_use()).status == doctor.OK

    (roaming / "Claude" / "claude_desktop_config.json").write_text("{broken", encoding="utf-8")
    store_before = store.read_text(encoding="utf-8")
    assert cli.main(["claude-config", "--write"]) == 1
    assert store.read_text(encoding="utf-8") == store_before, "a broken config stops the lot; nothing is half done"


def test_without_claude_desktop_the_doctor_says_to_install_it(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    check = doctor.check_claude_desktop(AagamSettings(core=settings), claude_config_in_use())
    assert check.status == doctor.WARN and "claude.ai/download" in check.fix


def test_a_closed_copy_is_updated_without_being_started(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(updates, "health", lambda port, timeout=2: None)
    monkeypatch.setattr(updates, "work_in_progress", lambda home: False)
    steps = FakeSteps()
    outcome = updates.apply_if_idle(app, tmp_path / "data", 8799, steps=steps, fetch=FakeGitHub())
    assert outcome["applied"] is True
    assert updates.version_of(app) == "0.3.0"
    assert "start" not in [step[0] for step in steps.done], "she had AAGAM closed, so it stays closed"
    assert ("python", ("-m", "aagam", "doctor")) in [(step[0], step[1]) for step in steps.done if step[0] == "python"]


def test_the_daily_check_leaves_an_open_or_git_copy_alone(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    monkeypatch.setattr(updates, "health", lambda port, timeout=2: {"ok": True})
    outcome = updates.apply_if_idle(app, tmp_path / "data", 8799, fetch=FakeGitHub())
    assert outcome["applied"] is False and "open" in outcome["reason"].lower()
    assert updates.version_of(app) == "0.2.0"

    (app / ".git").mkdir()
    monkeypatch.setattr(updates.shutil, "which", lambda name: "git" if name == "git" else None)
    assert updates.apply_if_idle(app, tmp_path / "data", 8799)["applied"] is False
    assert updates.register_daily_update(app) is None, "a git checkout must not grow a scheduled task"


def test_the_daily_task_is_not_registered_without_the_apps_python(tmp_path):
    assert updates.register_daily_update(make_app(tmp_path)) is None


def test_backup_and_a_report_from_the_window(system, settings, tmp_path):
    client, _, _ = system
    (settings.home / "clients" / "a.txt").write_text("hello", encoding="utf-8")
    (settings.home / "logs" / "aagam-web.log").write_text("ghp_abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")
    started = client.post("/api/system/backup", json={"into": str(tmp_path / "backups")}, headers=CHANGE)
    assert started.status_code == 200, started.text
    task = started.json()["task"]
    job = {"status": "running"}
    for _ in range(50):
        job = client.get(f"/api/system/jobs/{task}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert (Path(job["path"]) / "clients" / "a.txt").read_text(encoding="utf-8") == "hello"

    started = client.post("/api/system/backup", json={"into": str(settings.home / "inside")}, headers=CHANGE)
    assert started.status_code == 200
    task = started.json()["task"]
    for _ in range(50):
        job = client.get(f"/api/system/jobs/{task}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "failed" and "outside" in job["error"]
    assert client.get("/api/system/jobs/missing").status_code == 404
    assert client.post("/api/system/backup", json={}).status_code == 403

    report = client.post("/api/system/support", json={"into": str(tmp_path / "reports")}, headers=CHANGE)
    assert report.status_code == 200, report.text
    blob = zipfile.ZipFile(report.json()["path"]).read("logs/aagam-web.log").decode()
    assert "ghp_" not in blob and "[removed]" in blob
    outside = Path("C:/Windows") if sys.platform == "win32" else Path("/usr")
    assert client.post("/api/system/reveal", json={"path": str(outside)}, headers=CHANGE).status_code == 400


def test_version_and_update_on_the_command_line(settings, tmp_path, monkeypatch, capsys):
    app = make_app(tmp_path)
    monkeypatch.setenv("AAGAM_APP_DIR", str(app))
    monkeypatch.setenv("AAGAM_HOME", str(settings.home))
    monkeypatch.setattr(updates, "http_get", FakeGitHub())
    assert cli.main(["version"]) == 0
    out = capsys.readouterr().out
    assert f"commit {OLD[:7]}" in out and f"github.com/{REPO}" in out
    assert cli.main(["update", "--check"]) == 0
    out = capsys.readouterr().out
    assert "A newer version 0.3.0 is ready (2 change(s))" in out and "Add LLP forms" in out
    assert cli.main(["update", "--auto", "off"]) == 0 and updates.read_record(app)["auto_update"] is False
    assert cli.main(["update", "--repo", "bad repo"]) == 1
    assert cli.main(["uninstall", "--remove-data"]) == 1
    assert "--confirm REMOVE" in capsys.readouterr().err


# ------------------------------------------------------------------ the installer scripts


SCRIPTS = sorted((ROOT / "scripts").glob("*.ps1"))
BATCH = [ROOT / "install.cmd", ROOT / "manage.cmd", ROOT / "scripts" / "setup-windows.cmd"]


def test_the_scripts_are_plain_ascii_for_windows_powershell():
    # Windows PowerShell 5.1 reads a .ps1 without a BOM in the ANSI code page: one curly quote can break a script.
    for path in [*SCRIPTS, *BATCH]:
        data = path.read_bytes()
        assert all(b < 128 for b in data), f"{path.name} has non-ASCII characters"
    for path in BATCH:
        assert b"\r\n" in path.read_bytes(), f"{path.name} needs Windows line endings"
    assert {p.name for p in SCRIPTS} >= {"install.ps1", "setup-windows.ps1", "manage.ps1", "uninstall.ps1"}


@pytest.mark.skipif(shutil.which("powershell") is None, reason="needs Windows PowerShell")
def test_the_powershell_scripts_parse():
    paths = ",".join(f"'{p}'" for p in SCRIPTS)
    command = (f"$bad = 0; foreach ($f in @({paths})) {{ $t = $null; $e = $null; "
               "[System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$t, [ref]$e) | Out-Null; "
               "foreach ($x in $e) { Write-Output (\"$f line \" + $x.Extent.StartLineNumber + ': ' + $x.Message); $bad++ } }; exit $bad")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


def test_install_record_constants_agree():
    text = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    assert f"$DefaultRepo = '{updates.DEFAULT_REPO}'" in text
    for part in updates.CODE:
        assert f"'{part}'" in text, f"install.ps1 doesn't copy {part}, which updates replace"
