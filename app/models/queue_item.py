"""QueueItem model for persisted PR queue state."""

from datetime import datetime, timezone

from app.extensions import db


class QueueItem(db.Model):
    """
    A single PR in the release queue for a repo.

    Position is 1-based; ordering is by position ASC. A PR can appear at most
    once per repo (unique on repo_id, pr_number).

    Attributes:
        id: Primary key.
        repo_id: Foreign key to repos.id.
        pr_number: GitHub PR number (matches PullRequestCache.number).
        position: 1-based display order in the queue.
        note: Optional free-text note for this queued PR.
        added_at: When the PR was added to the queue (timezone-aware).
    """

    __tablename__ = "queue_items"

    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey("repos.id"), nullable=False)
    pr_number = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text, nullable=True)
    added_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("repo_id", "pr_number", name="uq_queue_items_repo_pr"),
    )

    def __repr__(self) -> str:
        return (
            f"<QueueItem repo_id={self.repo_id} pr_number={self.pr_number} "
            f"position={self.position}>"
        )
