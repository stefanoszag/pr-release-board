"""QueueEvent model for logging queue mutations (add, remove, move, note update)."""

from datetime import datetime, timezone

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db

# Valid event_type values for queue_events
QUEUE_EVENT_TYPES = frozenset(
    {
        "added",
        "removed",
        "moved",
        "note_updated",
        "sync_removed",
    }
)


class QueueEvent(db.Model):
    """
    A single logged event for a queue mutation (add, remove, move, note update).

    Used for the activity log; payload stores context per event type.

    Attributes:
        id: Primary key.
        repo_id: Foreign key to repos.id.
        pr_number: GitHub PR number (matches PullRequestCache.number).
        event_type: One of added, removed, moved, note_updated, sync_removed.
        payload: Optional JSON context (e.g. position, from_position, note).
        created_at: When the event occurred (timezone-aware).
    """

    __tablename__ = "queue_events"

    __table_args__ = (
        Index(
            "ix_queue_events_repo_id_created_at",
            "repo_id",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey("repos.id"), nullable=False)
    pr_number = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.Text, nullable=False)
    payload = db.Column(JSONB, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<QueueEvent id={self.id} repo_id={self.repo_id} "
            f"pr_number={self.pr_number} event_type={self.event_type}>"
        )
