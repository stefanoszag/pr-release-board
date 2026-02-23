"""Queue operations: add, remove, reorder, and list queued PRs."""

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_item import QueueItem


def add_to_queue(repo_id: int, pr_number: int, note: str = "") -> QueueItem:
    """
    Add a PR to the queue for the given repo.

    The PR must exist in PullRequestCache, be open, and be approved. It is
    appended at the end of the queue (position max(current) + 1, or 1 if empty).

    Args:
        repo_id: Primary key of the Repo.
        pr_number: GitHub PR number.
        note: Optional free-text note for the queued PR.

    Returns:
        The created QueueItem.

    Raises:
        ValueError: If the PR is not in cache, not open, not approved, or already in queue.
    """
    pr_cache = (
        db.session.query(PullRequestCache)
        .filter_by(repo_id=repo_id, number=pr_number)
        .first()
    )
    if pr_cache is None or not pr_cache.is_open:
        raise ValueError("PR not found or not open")
    if not pr_cache.approved:
        raise ValueError("PR must be approved to add to queue")

    existing = (
        db.session.query(QueueItem)
        .filter_by(repo_id=repo_id, pr_number=pr_number)
        .first()
    )
    if existing is not None:
        raise ValueError("already in queue")

    max_position = (
        db.session.query(db.func.coalesce(db.func.max(QueueItem.position), 0))
        .filter_by(repo_id=repo_id)
        .scalar()
    )
    next_position = int(max_position) + 1

    item = QueueItem(
        repo_id=repo_id,
        pr_number=pr_number,
        position=next_position,
        note=note.strip() if note else None,
    )
    db.session.add(item)
    db.session.commit()
    db.session.refresh(item)
    return item


def remove_from_queue(repo_id: int, pr_number: int) -> None:
    """
    Remove a PR from the queue and renumber remaining items.

    Args:
        repo_id: Primary key of the Repo.
        pr_number: GitHub PR number.

    Raises:
        ValueError: If no QueueItem exists for (repo_id, pr_number).
    """
    item = (
        db.session.query(QueueItem)
        .filter_by(repo_id=repo_id, pr_number=pr_number)
        .first()
    )
    if item is None:
        raise ValueError("PR not in queue")

    old_position = item.position
    db.session.delete(item)
    db.session.commit()

    # Renumber: assign 1..N by current position order
    remaining = (
        db.session.query(QueueItem)
        .filter_by(repo_id=repo_id)
        .order_by(QueueItem.position.asc())
        .all()
    )
    for idx, qi in enumerate(remaining, start=1):
        if qi.position != idx:
            qi.position = idx
    db.session.commit()


def update_note(repo_id: int, pr_number: int, note: str) -> QueueItem:
    """
    Update the note for a queued PR.

    Args:
        repo_id: Primary key of the Repo.
        pr_number: GitHub PR number.
        note: New note text.

    Returns:
        The updated QueueItem.

    Raises:
        ValueError: If no QueueItem exists for (repo_id, pr_number).
    """
    item = (
        db.session.query(QueueItem)
        .filter_by(repo_id=repo_id, pr_number=pr_number)
        .first()
    )
    if item is None:
        raise ValueError("PR not in queue")

    item.note = note.strip() if note else None
    db.session.commit()
    db.session.refresh(item)
    return item


def get_queue(repo_id: int) -> list[dict]:
    """
    Return the queue for the given repo with PR metadata.

    QueueItem is joined to PullRequestCache on (repo_id, pr_number/number).
    Results are ordered by position ASC.

    Args:
        repo_id: Primary key of the Repo.

    Returns:
        List of dicts with keys: position, pr_number, note, title, url,
        author, approved, synced_at. synced_at is ISO format string.
    """
    rows = (
        db.session.query(QueueItem, PullRequestCache)
        .join(
            PullRequestCache,
            db.and_(
                PullRequestCache.repo_id == QueueItem.repo_id,
                PullRequestCache.number == QueueItem.pr_number,
            ),
        )
        .filter(QueueItem.repo_id == repo_id)
        .order_by(QueueItem.position.asc())
        .all()
    )

    result: list[dict] = []
    for qi, pr in rows:
        synced_at = pr.synced_at.isoformat() if pr.synced_at else None
        result.append(
            {
                "position": qi.position,
                "pr_number": qi.pr_number,
                "note": qi.note or "",
                "title": pr.title or "",
                "url": pr.url or "",
                "author": pr.author or "",
                "approved": pr.approved,
                "synced_at": synced_at,
            }
        )
    return result
