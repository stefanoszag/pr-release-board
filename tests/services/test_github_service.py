"""Tests for github_service.sync_repo with mocked PyGithub."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest  # type: ignore[import-untyped]

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_item import QueueItem
from app.models.repo import Repo
from app.services import github_service
from app.services.queue_service import add_to_queue

from tests.services.test_queue_service import make_repo, make_pr


def _make_mock_pr(
    *,
    number: int = 1,
    title: str = "PR title",
    html_url: str = "https://github.com/org/repo/pull/1",
    author_login: str = "author",
    base_ref: str = "main",
    head_sha: str = "abc123",
    merged: bool = False,
    approved: bool = True,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Build a MagicMock that looks like a PyGithub PullRequest."""
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.html_url = html_url
    pr.user = MagicMock(login=author_login) if author_login else None
    pr.base = MagicMock(ref=base_ref)
    pr.head = MagicMock(sha=head_sha)
    pr.merged = merged
    pr.updated_at = updated_at or datetime.now(timezone.utc)
    review = MagicMock(state="APPROVED" if approved else "CHANGES_REQUESTED")
    pr.get_reviews.return_value = [review] if approved else []
    return pr


@pytest.fixture
def mock_github(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Return a MagicMock wired up as the Github() client."""
    mock_gh = MagicMock()
    monkeypatch.setattr(
        "app.services.github_service.Github",
        lambda token: mock_gh,
    )
    return mock_gh


@pytest.fixture
def app_with_token(app: Any) -> Any:
    """Ensure GITHUB_TOKEN is set so sync_repo can run."""
    app.config["GITHUB_TOKEN"] = "fake-token"
    return app


def test_sync_repo_upsert_new_pr(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """GitHub returns one open PR → PullRequestCache row created with correct fields."""
    repo = make_repo(db_session)
    db_session.commit()
    mock_repo = MagicMock()
    mock_pr = _make_mock_pr(
        number=42,
        title="New feature",
        html_url="https://github.com/test-org/test-repo/pull/42",
        author_login="dev",
        approved=True,
    )
    mock_repo.get_pulls.return_value = [mock_pr]
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        result = github_service.sync_repo(repo.id)

    assert result["updated"] == 1
    assert result["repo"] == "test-repo"
    cached = (
        db_session.query(PullRequestCache)
        .filter_by(repo_id=repo.id, number=42)
        .first()
    )
    assert cached is not None
    assert cached.title == "New feature"
    assert cached.url == "https://github.com/test-org/test-repo/pull/42"
    assert cached.author == "dev"
    assert cached.approved is True
    assert cached.is_open is True
    assert cached.synced_at is not None


def test_sync_repo_update_existing_pr(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """Row already in cache → fields updated, synced_at refreshed."""
    repo = make_repo(db_session)
    make_pr(
        db_session,
        repo,
        pr_number=1,
        title="Old title",
        author="oldauthor",
        approved=False,
    )
    db_session.commit()
    mock_repo = MagicMock()
    mock_pr = _make_mock_pr(
        number=1,
        title="Updated title",
        author_login="newauthor",
        approved=True,
    )
    mock_repo.get_pulls.return_value = [mock_pr]
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        result = github_service.sync_repo(repo.id)

    assert result["updated"] == 1
    cached = (
        db_session.query(PullRequestCache)
        .filter_by(repo_id=repo.id, number=1)
        .first()
    )
    assert cached.title == "Updated title"
    assert cached.author == "newauthor"
    assert cached.approved is True
    assert cached.synced_at is not None


def test_sync_repo_approved_flag_true(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """Review with state=APPROVED → approved=True."""
    repo = make_repo(db_session)
    db_session.commit()
    mock_repo = MagicMock()
    mock_pr = _make_mock_pr(number=1, approved=True)
    mock_repo.get_pulls.return_value = [mock_pr]
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        github_service.sync_repo(repo.id)

    cached = (
        db_session.query(PullRequestCache)
        .filter_by(repo_id=repo.id, number=1)
        .first()
    )
    assert cached.approved is True


def test_sync_repo_approved_flag_false(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """No approved review → approved=False."""
    repo = make_repo(db_session)
    db_session.commit()
    mock_repo = MagicMock()
    mock_pr = _make_mock_pr(number=1, approved=False)
    mock_repo.get_pulls.return_value = [mock_pr]
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        github_service.sync_repo(repo.id)

    cached = (
        db_session.query(PullRequestCache)
        .filter_by(repo_id=repo.id, number=1)
        .first()
    )
    assert cached.approved is False


def test_sync_repo_close_stale_pr(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """Row with is_open=True not returned by GitHub → is_open=False after sync."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=99, is_open=True)
    db_session.commit()
    mock_repo = MagicMock()
    mock_repo.get_pulls.return_value = []  # No open PRs from GitHub
    mock_gh_pr = MagicMock(merged=False)
    mock_repo.get_pull.return_value = mock_gh_pr
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        github_service.sync_repo(repo.id)

    db_session.expire_all()  # Reload from DB
    cached = (
        db_session.query(PullRequestCache)
        .filter_by(repo_id=repo.id, number=99)
        .first()
    )
    assert cached is not None
    assert cached.is_open is False


def test_sync_repo_cleanup_triggered(
    db_session: Any,
    app_with_token: Any,
    mock_github: MagicMock,
) -> None:
    """Closed PR that was in queue → QueueItem deleted after sync."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1, is_open=True)
    db_session.commit()
    add_to_queue(repo.id, 1)
    db_session.commit()
    mock_repo = MagicMock()
    mock_repo.get_pulls.return_value = []  # PR 1 no longer open
    mock_gh_pr = MagicMock(merged=False)
    mock_repo.get_pull.return_value = mock_gh_pr
    mock_github.get_repo.return_value = mock_repo

    with app_with_token.app_context():
        github_service.sync_repo(repo.id)

    item = (
        db_session.query(QueueItem)
        .filter_by(repo_id=repo.id, pr_number=1)
        .first()
    )
    assert item is None


def test_sync_repo_no_repo_found(db_session: Any, app_with_token: Any) -> None:
    """repo_id not in DB → ValueError."""
    with app_with_token.app_context():
        with pytest.raises(ValueError, match="not found"):
            github_service.sync_repo(99999)


def test_sync_repo_no_token(db_session: Any, app: Any, mock_github: MagicMock) -> None:
    """GITHUB_TOKEN empty → ValueError."""
    repo = make_repo(db_session)
    db_session.commit()
    app.config["GITHUB_TOKEN"] = ""

    with app.app_context():
        with pytest.raises(ValueError, match="GITHUB_TOKEN is not set"):
            github_service.sync_repo(repo.id)
