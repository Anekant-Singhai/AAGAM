from collections.abc import Iterator

import pytest

from csdesk.config import Settings
from csdesk.vault import Vault


@pytest.fixture
def settings(tmp_path) -> Settings:
    home = Settings(home=tmp_path / "home", cdp_port=9333)
    home.ensure_dirs()
    return home


@pytest.fixture
def vault(settings: Settings) -> Iterator[Vault]:
    with Vault.open(settings.db_path, actor="test") as opened:
        yield opened
