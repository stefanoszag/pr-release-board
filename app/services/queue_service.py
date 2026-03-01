"""Queue operations: add, remove, reorder, and list queued PRs."""

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_event import QueueEvent
from app.models.queue_item import QueueItem


def _log_event(
    repo_id: int,
    pr_number: int,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """
    Append a queue event to the session and flush (no commit).

    Caller is responsible for committing so the event is written atomically
    with the corresponding data change.

    Args:
        repo_id: Primary key of the Repo.
        pr_number: GitHub PR number.
        event_type: One of added, removed, moved, note_updated, sync_removed.
        payload: Optional JSON context for the event.
    """
    event = QueueEvent(
        repo_id=repo_id,
        pr_number=pr_number,
        event_type=event_type,
        payload=payload,
    )
    db.session.add(event)
    db.session.flush()


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
    _log_event(repo_id, pr_number, "added", {"position": next_position})
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
    _log_event(repo_id, pr_number, "removed", {"position": old_position})
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

    note_value = note.strip() if note else None
    item.note = note_value
    _log_event(repo_id, pr_number, "note_updated", {"note": note_value})
    db.session.commit()
    db.session.refresh(item)
    return item


def reorder_queue(repo_id: int, ordered_pr_numbers: list[int]) -> None:
    """
    Reorder the queue to match the given list of PR numbers.

    The submitted list must contain exactly the same set of PR numbers as
    currently in the queue (no missing or extra items).

    Args:
        repo_id: Primary key of the Repo.
        ordered_pr_numbers: PR numbers in the desired order (positions 1..N).

    Raises:
        ValueError: If the list does not match the current set of queued PRs.
    """
    items = (
        db.session.query(QueueItem)
        .filter_by(repo_id=repo_id)
        .order_by(QueueItem.position.asc())
        .all()
    )
    current_prs = {item.pr_number for item in items}
    submitted = set(ordered_pr_numbers)
    if current_prs != submitted:
        raise ValueError("ordered_pr_numbers must match current queue (no missing or extra items)")

    before_positions = {item.pr_number: item.position for item in items}
    pr_to_item = {item.pr_number: item for item in items}

    for new_position, pr_number in enumerate(ordered_pr_numbers, start=1):
        item = pr_to_item[pr_number]
        old_position = before_positions[pr_number]
        if old_position != new_position:
            _log_event(
                repo_id,
                pr_number,
                "moved",
                {"from_position": old_position, "to_position": new_position},
            )
        item.position = new_position

    db.session.commit()


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
