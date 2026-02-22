"""HTML page routes."""

from flask import Blueprint, render_template

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.repo import Repo

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def board() -> str:
    """
    Render the release queue board with open cached PRs.

    Shows repo info, Sync now button, last sync time, and PR list
    (approved first, then by number). Empty state if no PRs cached.
    """
    repo = db.session.get(Repo, 1)
    prs = []
    last_sync = None
    if repo:
        prs = (
            db.session.query(PullRequestCache)
            .filter(PullRequestCache.repo_id == repo.id, PullRequestCache.is_open.is_(True))
            .order_by(
                PullRequestCache.approved.desc(),
                PullRequestCache.number.asc(),
            )
            .all()
        )
        if prs:
            last_sync = max(p.synced_at for p in prs)
    return render_template(
        "board.html",
        repo=repo,
        prs=prs,
        last_sync=last_sync,
    )
