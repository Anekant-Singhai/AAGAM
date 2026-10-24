from collections.abc import Iterator

import pytest

from csdesk.config import Settings
from csdesk.vault import Vault


@pytest.fixture(autouse=True)
def nothing_outside_the_test(monkeypatch, tmp_path_factory):
    """No test changes this computer: no scheduled task, start-up entry or registry value (updates.py checks
    AAGAM_NO_SYSTEM_CHANGES), and no data folder in the real user folder. A test that needs AAGAM_HOME sets its own."""
    monkeypatch.setenv("AAGAM_NO_SYSTEM_CHANGES", "1")
    monkeypatch.setenv("AAGAM_HOME", str(tmp_path_factory.mktemp("default-home")))


@pytest.fixture
def settings(tmp_path) -> Settings:
    home = Settings(home=tmp_path / "home", cdp_port=9333)
    home.ensure_dirs()
    return home


@pytest.fixture
def vault(settings: Settings) -> Iterator[Vault]:
    with Vault.open(settings.db_path, actor="test") as opened:
        yield opened
