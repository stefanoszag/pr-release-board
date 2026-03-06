"""Pytest fixtures for test isolation and app context."""

import os
import subprocess
import sys

# Set test DB URL before any app import. Config reads os.environ at import time,
# so DATABASE_URL must be set now or the app would use SQLite.
_TEST_DATABASE_URL = "postgresql://test:test@127.0.0.1:5432/test_pr_board"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _TEST_DATABASE_URL)

import pytest  # type: ignore[import-untyped]  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.repo import Repo  # noqa: E402


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


@pytest.fixture(scope="session", autouse=True)
def truncate_tables(run_migrations: None) -> None:
    """
    Truncate all app tables at the start of each test run so reruns start clean.

    Runs after migrations, before the app fixture. create_app() then runs
    seed_repo() and adds the single repo row. Postgres only; no-op for SQLite.
    """
    from sqlalchemy import create_engine, text

    url = os.environ.get("DATABASE_URL", "")
    if not url or "sqlite" in url:
        return
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE repos RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.fixture(scope="session")
def app(truncate_tables):
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


@pytest.fixture(scope="function")
def repo_1(db_session):
    """
    Ensure repo with id=1 exists (for API/page routes that use repo_id=1 or first repo).
    Create it if missing so tests can seed PRs/queue for it.
    """
    repo = db_session.get(Repo, 1)
    if repo is not None:
        return repo
    repo = Repo(
        id=1,
        owner="test-org",
        name="test-repo",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()
    # Keep sequence in sync for other tests that insert repos without id
    db_session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('repos', 'id'), "
            "(SELECT COALESCE(MAX(id), 1) FROM repos))"
        )
    )
    db_session.commit()
    return repo
