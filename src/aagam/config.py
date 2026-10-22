"""AAGAM's settings: the core's (data folder, browser) plus the web interface and local AI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from csdesk.config import Settings, load_settings


@dataclass(frozen=True)
class AagamSettings:
    core: Settings
    web_port: int = 8765
    # The address `aagam serve` listens on. Only a container sets 0.0.0.0 (its port is then
    # published on the host's 127.0.0.1); on her laptop it stays on this computer.
    bind: str = "127.0.0.1"
    local_ai: bool = True
    local_ai_url: str = "http://127.0.0.1:11434"
    local_ai_model: str = "qwen3:4b"
    local_ai_context: int = 8192

    @property
    def home(self):  # noqa: ANN201 - a Path, as the core's
        return self.core.home


def load() -> AagamSettings:
    return AagamSettings(
        core=load_settings(),
        web_port=int(os.environ.get("AAGAM_PORT", "8765")),
        bind=os.environ.get("AAGAM_BIND", "127.0.0.1").strip() or "127.0.0.1",
        local_ai=os.environ.get("AAGAM_LOCAL_AI", "on").lower() not in ("off", "0", "no", "false"),
        local_ai_url=os.environ.get("AAGAM_LOCAL_AI_URL", "http://127.0.0.1:11434").rstrip("/"),
        local_ai_model=os.environ.get("AAGAM_LOCAL_AI_MODEL", "qwen3:4b"),
        local_ai_context=int(os.environ.get("AAGAM_LOCAL_AI_CONTEXT", "8192")),
    )


def claude_desktop_config_path() -> Path:
    """Where Claude Desktop keeps its config on Windows (%APPDATA%\\Claude)."""
    return Path(os.environ.get("APPDATA", Path.home()), "Claude", "claude_desktop_config.json")
