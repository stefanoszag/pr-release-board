"""Shared route helpers for repo resolution and common patterns."""

from app.extensions import db
from app.models.repo import Repo


def resolve_repo(repo_id: int | None) -> tuple[Repo | None, int | None]:
    """
    Fetch Repo by id; return (None, 404) if not found.

    If repo_id is None, falls back to the first repo row (ordered by id).
    Callers can use the second value as the HTTP status to return when
    the first is None.

    Args:
        repo_id: Optional repo primary key from query/body.

    Returns:
        (Repo, None) on success; (None, 404) when no repo found.
    """
    if repo_id is None:
        repo = db.session.query(Repo).order_by(Repo.id).first()
    else:
        repo = db.session.get(Repo, repo_id)
    if repo is None:
        return None, 404
    return repo, None
