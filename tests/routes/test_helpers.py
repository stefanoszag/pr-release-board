"""Unit tests for route helpers (resolve_repo)."""

from typing import Any

from app.models.pull_request import PullRequestCache
from app.models.queue_event import QueueEvent
from app.models.queue_item import QueueItem
from app.models.repo import Repo
from app.routes._helpers import resolve_repo
from tests.services.test_queue_service import make_repo


def _delete_all_repos(db_session: Any) -> None:
    """Delete all repos and dependent rows (FK order)."""
    db_session.query(QueueEvent).delete()
    db_session.query(QueueItem).delete()
    db_session.query(PullRequestCache).delete()
    db_session.query(Repo).delete()
    db_session.commit()


def test_resolve_repo_none_returns_first_repo(app: Any, db_session: Any) -> None:
    """resolve_repo(None) → (first repo by id, None)."""
    _delete_all_repos(db_session)
    repo = make_repo(db_session)
    db_session.commit()
    with app.app_context():
        result_repo, err = resolve_repo(None)
    assert err is None
    assert result_repo is not None
    assert result_repo.id == repo.id
    assert result_repo.name == repo.name


def test_resolve_repo_valid_id_returns_that_repo(app: Any, db_session: Any) -> None:
    """resolve_repo(valid_id) → (Repo, None)."""
    repo = make_repo(db_session)
    db_session.commit()
    with app.app_context():
        result_repo, err = resolve_repo(repo.id)
    assert err is None
    assert result_repo is not None
    assert result_repo.id == repo.id


def test_resolve_repo_invalid_id_returns_404(app: Any, db_session: Any) -> None:
    """resolve_repo(99999) when not in DB → (None, 404)."""
    make_repo(db_session)
    db_session.commit()
    with app.app_context():
        result_repo, err = resolve_repo(99999)
    assert result_repo is None
    assert err == 404


def test_resolve_repo_none_no_repos_returns_404(app: Any, db_session: Any) -> None:
    """resolve_repo(None) when no repos in DB → (None, 404)."""
    _delete_all_repos(db_session)
    with app.app_context():
        result_repo, err = resolve_repo(None)
    assert result_repo is None
    assert err == 404
