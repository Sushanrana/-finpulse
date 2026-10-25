import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402
import db as fdb  # noqa: E402
from helpers import register  # noqa: E402


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-not-for-production",
        "DATABASE": str(tmp_path / "test.db"),
        "SESSION_COOKIE_SECURE": False,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "FRAME_ANCESTORS": "'none'",
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def alice(app):
    c = app.test_client()
    resp = register(c, "alice@example.com")
    assert resp.status_code == 302
    return c


@pytest.fixture
def bob(app):
    c = app.test_client()
    resp = register(c, "bob@example.com")
    assert resp.status_code == 302
    return c


@pytest.fixture
def query(app):
    """Run a read-only SQL query against the test DB."""
    def _query(sql, params=()):
        with app.app_context():
            return fdb.query_all(sql, params)
    return _query
