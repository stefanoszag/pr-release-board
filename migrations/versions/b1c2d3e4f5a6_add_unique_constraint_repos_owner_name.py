"""add unique constraint repos owner name

Revision ID: b1c2d3e4f5a6
Revises: a446322e70dd
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a446322e70dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint on (owner, name) to repos table."""
    op.create_unique_constraint(
        "uq_repos_owner_name", "repos", ["owner", "name"]
    )


def downgrade() -> None:
    """Remove unique constraint uq_repos_owner_name from repos table."""
    op.drop_constraint("uq_repos_owner_name", "repos", type_="unique")
