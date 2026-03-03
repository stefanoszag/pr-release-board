"""Pytest fixtures for test isolation and app context."""

import os
import subprocess
import sys

# Set test DB URL before any app import. Config reads os.environ at import time,
# so DATABASE_URL must be set now or the app would use SQLite.
_TEST_DATABASE_URL = "postgresql://test:test@127.0.0.1:5432/test_pr_board"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _TEST_DATABASE_URL)

import pytest  # type: ignore[import-untyped]

from app import create_app
from app.extensions import db


def _ensure_test_database_url() -> None:
    """
    Re-apply test DB URL (e.g. before subprocess calls that need it).

    Uses TEST_DATABASE_URL if set, otherwise the default. Already set at
    conftest load time so Config sees it; this keeps alembic subprocess in sync.
    """
    url = os.environ.get("TEST_DATABASE_URL", _TEST_DATABASE_URL)
    os.environ["DATABASE_URL"] = url


@pytest.fixture(scope="session", autouse=True)
def run_migrations() -> None:
    """
    Run alembic upgrade head once per test session before any test.

    Uses the same DATABASE_URL as the app fixture so the test database
    schema is up to date.
    """
    _ensure_test_database_url()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


@pytest.fixture(scope="session")
def app():
    """Create app once per session pointing at TEST_DATABASE_URL."""
    _ensure_test_database_url()
    _app = create_app()
    with _app.app_context():
        yield _app


@pytest.fixture(scope="function")
def db_session(app):
    """
    Each test gets its own connection + transaction; rolled back after.

    Keeps DB clean without re-running migrations.
    """
    with app.app_context():
        connection = db.engine.connect()
        trans = connection.begin()
        db.session.configure(bind=connection)
        yield db.session
        db.session.remove()
        trans.rollback()
        connection.close()


@pytest.fixture(scope="function")
def client(app, db_session):
    """Flask test client, tied to the same rolled-back session."""
    return app.test_client()
