"""HTML page routes."""

from flask import Blueprint, render_template

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.repo import Repo
from app.services.queue_service import get_queue

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def board() -> str:
    """
    Render the release queue board with three sections: Queued, Ready, Other.

    Passes queued_prs (from get_queue), ready_prs (approved, not in queue),
    other_prs (not approved, not in queue), plus repo and last_sync.
    """
    repo = db.session.get(Repo, 1)
    queued_prs = []
    ready_prs = []
    other_prs = []
    last_sync = None

    if repo:
        queued_prs = get_queue(repo_id=repo.id)
        queued_numbers = {q["pr_number"] for q in queued_prs}

        ready_prs = (
            db.session.query(PullRequestCache)
            .filter(
                PullRequestCache.repo_id == repo.id,
                PullRequestCache.is_open.is_(True),
                PullRequestCache.approved.is_(True),
                PullRequestCache.number.notin_(queued_numbers),
            )
            .order_by(PullRequestCache.number.asc())
            .all()
        )
        other_prs = (
            db.session.query(PullRequestCache)
            .filter(
                PullRequestCache.repo_id == repo.id,
                PullRequestCache.is_open.is_(True),
                PullRequestCache.approved.is_(False),
                PullRequestCache.number.notin_(queued_numbers),
            )
            .order_by(PullRequestCache.number.asc())
            .all()
        )

        open_prs = (
            db.session.query(PullRequestCache)
            .filter(
                PullRequestCache.repo_id == repo.id,
                PullRequestCache.is_open.is_(True),
            )
            .all()
        )
        if open_prs:
            last_sync = max(
                (p.synced_at for p in open_prs if p.synced_at),
                default=None,
            )

    return render_template(
        "board.html",
        repo=repo,
        queued_prs=queued_prs,
        ready_prs=ready_prs,
        other_prs=other_prs,
        last_sync=last_sync,
    )
