"""Where AAGAM keeps things.

Code lives in the project folder. Client data lives in one data folder,
AAGAM_HOME (default ~/AAGAM; CSDESK_HOME is still read for older setups), so
the code can be copied or shared without ever carrying client documents or
PAN/Aadhaar numbers along with it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    home: Path
    cdp_port: int = 9222
    browser: str = "chrome"  # "chrome", "edge", or a full path to a Chromium-based browser

    @property
    def db_path(self) -> Path:
        return self.home / "csdesk.db"

    @property
    def law_db_path(self) -> Path:
        return self.home / "law.db"

    @property
    def clients_dir(self) -> Path:
        return self.home / "clients"

    @property
    def inbox_dir(self) -> Path:
        return self.home / "inbox"

    @property
    def templates_dir(self) -> Path:
        return self.home / "templates"

    @property
    def law_dir(self) -> Path:
        return self.home / "law"

    @property
    def browser_profile_dir(self) -> Path:
        return self.home / "browser-profile"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def recordings_dir(self) -> Path:
        return self.home / "recordings"

    def ensure_dirs(self) -> None:
        for folder in (
            self.home,
            self.clients_dir,
            self.inbox_dir,
            self.templates_dir,
            self.law_dir,
            self.browser_profile_dir,
            self.logs_dir,
            self.recordings_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    home = Path(os.environ.get("AAGAM_HOME") or os.environ.get("CSDESK_HOME") or Path.home() / "AAGAM").expanduser()
    return Settings(
        home=home,
        cdp_port=int(os.environ.get("CSDESK_CDP_PORT", "9222")),
        browser=os.environ.get("CSDESK_BROWSER", "chrome"),
    )
