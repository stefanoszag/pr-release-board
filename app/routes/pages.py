"""HTML page routes."""

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_event import QueueEvent
from app.models.repo import Repo
from app.routes._helpers import resolve_repo
from app.services.queue_service import get_queue

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def board() -> str:
    """
    Render the release queue board with three sections: Queued, Ready, Other.

    Passes queued_prs (from get_queue), ready_prs (approved, not in queue),
    other_prs (not approved, not in queue), plus repo, repos, selected_repo_id,
    and last_sync. repo_id from query (defaults to first repo); 404 if invalid.
    """
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        abort(err)
    all_repos = db.session.query(Repo).order_by(Repo.id).all()

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
        repos=all_repos,
        selected_repo_id=repo.id,
        queued_prs=queued_prs,
        ready_prs=ready_prs,
        other_prs=other_prs,
        last_sync=last_sync,
    )


@pages_bp.route("/activity")
def activity() -> str:
    """
    Render the activity log: last 50 queue events with PR metadata.

    repo_id from query (defaults to first repo); 404 if invalid.
    QueueEvent is left-outer-joined to PullRequestCache for title/url.
    """
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        abort(err)
    all_repos = db.session.query(Repo).order_by(Repo.id).all()

    events: list[dict] = []

    if repo:
        rows = (
            db.session.query(QueueEvent, PullRequestCache)
            .outerjoin(
                PullRequestCache,
                db.and_(
                    PullRequestCache.repo_id == QueueEvent.repo_id,
                    PullRequestCache.number == QueueEvent.pr_number,
                ),
            )
            .filter(QueueEvent.repo_id == repo.id)
            .order_by(QueueEvent.created_at.desc())
            .limit(50)
            .all()
        )
        for qe, pr in rows:
            events.append(
                {
                    "event_type": qe.event_type,
                    "pr_number": qe.pr_number,
                    "payload": qe.payload or {},
                    "created_at": qe.created_at,
                    "pr_title": pr.title if pr else None,
                    "pr_url": pr.url if pr else None,
                }
            )

    return render_template(
        "activity.html",
        events=events,
        repo=repo,
        repos=all_repos,
        selected_repo_id=repo.id,
    )
