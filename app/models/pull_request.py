"""PullRequestCache model for cached GitHub PR data."""

from app.extensions import db


class PullRequestCache(db.Model):
    """
    Cached pull request data synced from GitHub.

    One row per PR per repo; (repo_id, number) is unique. Updated on each sync.

    Attributes:
        id: Primary key.
        repo_id: Foreign key to repos.id.
        number: GitHub PR number, unique per repo.
        title: PR title.
        url: PR HTML URL.
        author: GitHub username of the author.
        base_branch: Branch the PR targets.
        head_sha: SHA of the head commit at last sync.
        is_open: True if the PR is open on GitHub.
        is_merged: True if the PR has been merged.
        updated_at_github: Last update time from GitHub (timezone-aware).
        approved: True if the PR has at least one APPROVED review.
        synced_at: When this row was last upserted by our sync.
    """

    __tablename__ = "pull_request_cache"

    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey("repos.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.Text, nullable=True)
    url = db.Column(db.Text, nullable=True)
    author = db.Column(db.Text, nullable=True)
    base_branch = db.Column(db.Text, nullable=True)
    head_sha = db.Column(db.Text, nullable=True)
    is_open = db.Column(db.Boolean, nullable=False, default=True)
    is_merged = db.Column(db.Boolean, nullable=False, default=False)
    updated_at_github = db.Column(db.DateTime(timezone=True), nullable=True)
    approved = db.Column(db.Boolean, nullable=False, default=False)
    synced_at = db.Column(db.DateTime(timezone=True), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "repo_id", "number", name="uq_pull_request_cache_repo_number"
        ),
    )

    def __repr__(self) -> str:
        return f"<PullRequestCache repo_id={self.repo_id} number={self.number}>"
