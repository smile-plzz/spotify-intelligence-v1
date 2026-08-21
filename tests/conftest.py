import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fixture_db import build_fixture_db  # noqa: E402


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory):
    return build_fixture_db(str(tmp_path_factory.mktemp("warehouse") / "spotify_data.db"))


@pytest.fixture()
def client(fixture_db, monkeypatch):
    import dashboard

    monkeypatch.setattr(dashboard, "DB_PATH", fixture_db)
    dashboard.app.config["TESTING"] = True
    with dashboard.app.test_client() as c:
        yield c
