"""Tests for queue_service: add, remove, reorder, update_note, cleanup, get_queue."""

from datetime import datetime, timezone
from typing import Any

import pytest  # type: ignore[import-untyped]

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_event import QueueEvent
from app.models.queue_item import QueueItem
from app.models.repo import Repo
from app.services import queue_service


def make_repo(db_session: Any) -> Repo:
    """Insert a Repo row and return it."""
    repo = Repo(owner="test-org", name="test-repo", default_branch="main")
    db_session.add(repo)
    db_session.flush()
    return repo


def make_pr(
    db_session: Any,
    repo: Repo,
    *,
    pr_number: int = 101,
    approved: bool = True,
    is_open: bool = True,
    title: str = "PR title",
    url: str = "https://github.com/test/pull/101",
    author: str = "author",
) -> PullRequestCache:
    """Insert a PullRequestCache row and return it."""
    pr = PullRequestCache(
        repo_id=repo.id,
        number=pr_number,
        title=title,
        url=url,
        author=author,
        is_open=is_open,
        approved=approved,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(pr)
    db_session.flush()
    return pr


# ---- add_to_queue ----


def test_add_to_queue_happy_path_creates_position_one(db_session: Any) -> None:
    """First add creates QueueItem at position 1 and logs added event."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    item = queue_service.add_to_queue(repo.id, 1, note="")
    assert item.position == 1
    assert item.pr_number == 1
    assert item.repo_id == repo.id
    assert item.note is None
    events = db_session.query(QueueEvent).filter_by(event_type="added").all()
    assert len(events) == 1
    assert events[0].payload == {"position": 1}


def test_add_to_queue_second_add_position_two(db_session: Any) -> None:
    """Second add gets position 2."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    make_pr(db_session, repo, pr_number=2)
    queue_service.add_to_queue(repo.id, 1)
    item2 = queue_service.add_to_queue(repo.id, 2)
    assert item2.position == 2


def test_add_to_queue_pr_not_in_cache_raises(db_session: Any) -> None:
    """PR not in PullRequestCache raises ValueError."""
    repo = make_repo(db_session)
    with pytest.raises(ValueError, match="PR not found or not open"):
        queue_service.add_to_queue(repo.id, 999)


def test_add_to_queue_pr_not_open_raises(db_session: Any) -> None:
    """PR with is_open=False raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1, is_open=False)
    with pytest.raises(ValueError, match="PR not found or not open"):
        queue_service.add_to_queue(repo.id, 1)


def test_add_to_queue_pr_not_approved_raises(db_session: Any) -> None:
    """PR not approved raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1, approved=False)
    with pytest.raises(ValueError, match="PR must be approved"):
        queue_service.add_to_queue(repo.id, 1)


def test_add_to_queue_already_in_queue_raises(db_session: Any) -> None:
    """PR already in queue raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    queue_service.add_to_queue(repo.id, 1)
    with pytest.raises(ValueError, match="already in queue"):
        queue_service.add_to_queue(repo.id, 1)


# ---- remove_from_queue ----


def test_remove_from_queue_happy_path(db_session: Any) -> None:
    """Item deleted, remaining renumbered, removed event logged."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    make_pr(db_session, repo, pr_number=2)
    queue_service.add_to_queue(repo.id, 1)
    queue_service.add_to_queue(repo.id, 2)
    queue_service.remove_from_queue(repo.id, 1)
    remaining = (
        db_session.query(QueueItem)
        .filter_by(repo_id=repo.id)
        .order_by(QueueItem.position.asc())
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].pr_number == 2
    assert remaining[0].position == 1
    events = db_session.query(QueueEvent).filter_by(event_type="removed").all()
    assert len(events) == 1
    assert events[0].payload == {"position": 1}


def test_remove_from_queue_not_in_queue_raises(db_session: Any) -> None:
    """Removing PR not in queue raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    with pytest.raises(ValueError, match="PR not in queue"):
        queue_service.remove_from_queue(repo.id, 1)


# ---- reorder_queue ----


def test_reorder_queue_happy_path(db_session: Any) -> None:
    """Positions updated; moved events only for changed items."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    make_pr(db_session, repo, pr_number=2)
    make_pr(db_session, repo, pr_number=3)
    queue_service.add_to_queue(repo.id, 1)
    queue_service.add_to_queue(repo.id, 2)
    queue_service.add_to_queue(repo.id, 3)
    queue_service.reorder_queue(repo.id, [3, 1, 2])
    items = (
        db_session.query(QueueItem)
        .filter_by(repo_id=repo.id)
        .order_by(QueueItem.position.asc())
        .all()
    )
    assert [i.pr_number for i in items] == [3, 1, 2]
    assert [i.position for i in items] == [1, 2, 3]
    moved = db_session.query(QueueEvent).filter_by(event_type="moved").all()
    assert len(moved) >= 1


def test_reorder_queue_set_mismatch_extra_pr_raises(db_session: Any) -> None:
    """Order with extra PR number raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    queue_service.add_to_queue(repo.id, 1)
    with pytest.raises(ValueError, match="ordered_pr_numbers must match current queue"):
        queue_service.reorder_queue(repo.id, [1, 999])


def test_reorder_queue_set_mismatch_missing_pr_raises(db_session: Any) -> None:
    """Order with missing PR number raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    make_pr(db_session, repo, pr_number=2)
    queue_service.add_to_queue(repo.id, 1)
    queue_service.add_to_queue(repo.id, 2)
    with pytest.raises(ValueError, match="ordered_pr_numbers must match current queue"):
        queue_service.reorder_queue(repo.id, [1])


# ---- update_note ----


def test_update_note_happy_path(db_session: Any) -> None:
    """Note updated and note_updated event logged."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    queue_service.add_to_queue(repo.id, 1, note="old")
    item = queue_service.update_note(repo.id, 1, " new note ")
    assert item.note == "new note"
    events = db_session.query(QueueEvent).filter_by(event_type="note_updated").all()
    assert len(events) == 1
    assert events[0].payload == {"note": "new note"}


def test_update_note_not_in_queue_raises(db_session: Any) -> None:
    """Updating note for PR not in queue raises ValueError."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    with pytest.raises(ValueError, match="PR not in queue"):
        queue_service.update_note(repo.id, 1, "x")


# ---- cleanup_closed_prs ----


def test_cleanup_closed_prs_removes_and_renumbers(db_session: Any) -> None:
    """Removes items whose pr_number not in open set; logs sync_removed; renumbers."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    make_pr(db_session, repo, pr_number=2)
    make_pr(db_session, repo, pr_number=3)
    queue_service.add_to_queue(repo.id, 1)
    queue_service.add_to_queue(repo.id, 2)
    queue_service.add_to_queue(repo.id, 3)
    removed = queue_service.cleanup_closed_prs(repo.id, {1, 3})
    assert set(removed) == {2}
    remaining = (
        db_session.query(QueueItem)
        .filter_by(repo_id=repo.id)
        .order_by(QueueItem.position.asc())
        .all()
    )
    assert [r.pr_number for r in remaining] == [1, 3]
    assert [r.position for r in remaining] == [1, 2]
    events = db_session.query(QueueEvent).filter_by(event_type="sync_removed").all()
    assert len(events) == 1
    assert events[0].pr_number == 2


def test_cleanup_closed_prs_no_op_when_all_open(db_session: Any) -> None:
    """No-op when all queued PR numbers are in open_pr_numbers."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1)
    queue_service.add_to_queue(repo.id, 1)
    removed = queue_service.cleanup_closed_prs(repo.id, {1})
    assert removed == []
    count = db_session.query(QueueItem).filter_by(repo_id=repo.id).count()
    assert count == 1


def test_cleanup_closed_prs_returns_removed_list(db_session: Any) -> None:
    """Returns correct list of removed PR numbers."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=10)
    make_pr(db_session, repo, pr_number=20)
    queue_service.add_to_queue(repo.id, 10)
    queue_service.add_to_queue(repo.id, 20)
    removed = queue_service.cleanup_closed_prs(repo.id, set())
    assert set(removed) == {10, 20}


# ---- get_queue ----


def test_get_queue_returns_ordered_with_metadata(db_session: Any) -> None:
    """Returns items ordered by position with joined PR metadata."""
    repo = make_repo(db_session)
    make_pr(db_session, repo, pr_number=1, title="First", author="a1")
    make_pr(db_session, repo, pr_number=2, title="Second", author="a2")
    queue_service.add_to_queue(repo.id, 1, note="n1")
    queue_service.add_to_queue(repo.id, 2, note="n2")
    rows = queue_service.get_queue(repo.id)
    assert len(rows) == 2
    assert rows[0]["position"] == 1
    assert rows[0]["pr_number"] == 1
    assert rows[0]["note"] == "n1"
    assert rows[0]["title"] == "First"
    assert rows[0]["author"] == "a1"
    assert rows[0]["approved"] is True
    assert "synced_at" in rows[0]
    assert rows[1]["position"] == 2
    assert rows[1]["title"] == "Second"
