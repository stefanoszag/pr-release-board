"""GitHub API integration for syncing pull request data."""

from datetime import datetime, timezone

from flask import current_app
from github import Github

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.repo import Repo
from app.services.queue_service import cleanup_closed_prs


def sync_repo(repo_id: int) -> dict:
    """
    Sync open PRs from GitHub for the given repo into PullRequestCache.

    Fetches open PRs targeting the repo's default branch, computes approved
    status from reviews, upserts into the cache, and marks PRs no longer
    returned as is_open=False.

    Args:
        repo_id: Primary key of the Repo row to sync.

    Returns:
        Dict with "updated" (int, number of PRs upserted) and "repo" (str, repo name).

    Raises:
        ValueError: If repo_id is not found or GitHub credentials are missing.
    """
    repo = db.session.get(Repo, repo_id)
    if repo is None:
        raise ValueError(f"Repo with id {repo_id} not found")

    token = current_app.config.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is not set")

    full_name = f"{repo.owner}/{repo.name}"
    current_app.logger.info(
        "Sync starting: repo_id=%s, target=%s, default_branch=%s",
        repo_id,
        full_name,
        repo.default_branch,
    )

    gh = Github(token)
    github_repo = gh.get_repo(full_name)
    open_pulls = github_repo.get_pulls(state="open", base=repo.default_branch)
    pr_list = list(open_pulls)
    current_app.logger.info(
        "GitHub API: found %s open PR(s) for %s", len(pr_list), full_name
    )

    now_utc = datetime.now(timezone.utc)
    seen_numbers: set[int] = set()
    updated = 0

    for pr in pr_list:
        seen_numbers.add(pr.number)
        reviews = list(pr.get_reviews())
        approved = any(getattr(r, "state", None) == "APPROVED" for r in reviews)

        updated_at_github = pr.updated_at
        if updated_at_github is not None and updated_at_github.tzinfo is None:
            updated_at_github = updated_at_github.replace(tzinfo=timezone.utc)

        cached = (
            db.session.query(PullRequestCache)
            .filter_by(repo_id=repo_id, number=pr.number)
            .first()
        )
        if cached:
            cached.title = pr.title
            cached.url = pr.html_url
            cached.author = pr.user.login if pr.user else None
            cached.base_branch = pr.base.ref if pr.base else None
            cached.head_sha = pr.head.sha if pr.head else None
            cached.is_open = True
            cached.is_merged = pr.merged
            cached.updated_at_github = updated_at_github
            cached.approved = approved
            cached.synced_at = now_utc
        else:
            cached = PullRequestCache(
                repo_id=repo_id,
                number=pr.number,
                title=pr.title,
                url=pr.html_url,
                author=pr.user.login if pr.user else None,
                base_branch=pr.base.ref if pr.base else None,
                head_sha=pr.head.sha if pr.head else None,
                is_open=True,
                is_merged=pr.merged,
                updated_at_github=updated_at_github,
                approved=approved,
                synced_at=now_utc,
            )
            db.session.add(cached)
        updated += 1

    # Mark PRs that were open but not in this fetch as closed; set is_merged from GitHub
    to_close = (
        db.session.query(PullRequestCache)
        .filter(
            PullRequestCache.repo_id == repo_id,
            PullRequestCache.is_open.is_(True),
        )
    )
    if seen_numbers:
        to_close = to_close.filter(
            PullRequestCache.number.notin_(seen_numbers)
        )
    to_close_list = to_close.all()
    for cached in to_close_list:
        try:
            gh_pr = github_repo.get_pull(cached.number)
            cached.is_merged = bool(gh_pr.merged)
        except Exception as e:
            current_app.logger.warning(
                "Could not fetch PR #%s for merged status: %s",
                cached.number,
                e,
            )
        cached.is_open = False

    db.session.commit()
    current_app.logger.info(
        "Sync completed: repo=%s, prs_upserted=%s",
        repo.name,
        updated,
    )

    removed = cleanup_closed_prs(repo_id=repo_id, open_pr_numbers=seen_numbers)
    if removed:
        current_app.logger.info(
            "Sync cleanup: removed %s PR(s) from queue: %s", len(removed), removed
        )

    return {"updated": updated, "repo": repo.name}
