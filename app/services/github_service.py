"""GitHub API integration for syncing pull request data."""

from datetime import datetime, timezone

from flask import current_app
from github import Github

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.repo import Repo


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

    gh = Github(token)
    full_name = f"{repo.owner}/{repo.name}"
    github_repo = gh.get_repo(full_name)
    open_pulls = github_repo.get_pulls(state="open", base=repo.default_branch)

    now_utc = datetime.now(timezone.utc)
    seen_numbers: set[int] = set()
    updated = 0

    for pr in open_pulls:
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

    # Mark PRs that were open but not in this fetch as closed
    closed_query = db.session.query(PullRequestCache).filter(
        PullRequestCache.repo_id == repo_id,
        PullRequestCache.is_open.is_(True),
    )
    if seen_numbers:
        closed_query = closed_query.filter(
            PullRequestCache.number.notin_(seen_numbers)
        )
    closed_query.update(
        {PullRequestCache.is_open: False}, synchronize_session=False
    )

    db.session.commit()
    return {"updated": updated, "repo": repo.name}
