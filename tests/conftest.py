"""Pytest fixtures for test isolation and app context."""

import os
import subprocess
import sys

import pytest

from app import create_app
from app.extensions import db

# Default test DB URL when neither TEST_DATABASE_URL nor DATABASE_URL is set.
_TEST_DATABASE_URL = "postgresql://test:test@localhost:5432/test_pr_board"


def _ensure_test_database_url() -> None:
    """
    Set DATABASE_URL to the test database for this process.

    Uses TEST_DATABASE_URL if set, otherwise DATABASE_URL, otherwise
    a default local Postgres URL. Ensures alembic and create_app use the same DB.
    """
    url = os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", _TEST_DATABASE_URL),
    )
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
