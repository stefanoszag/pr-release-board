"""Repo model and seed helper for GitHub repository configuration."""

from flask import current_app

from app.extensions import db


class Repo(db.Model):
    """
    Single GitHub repository tracked by the board.

    Attributes:
        id: Primary key.
        owner: GitHub owner (org or user), e.g. "myorg".
        name: Repository name, e.g. "my-repo".
        default_branch: Branch PRs target by default, e.g. "main".
    """

    __tablename__ = "repos"

    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    default_branch = db.Column(db.Text, nullable=False, default="main")

    def __repr__(self) -> str:
        return f"<Repo {self.owner}/{self.name}>"


def seed_repo() -> None:
    """
    Insert one Repo row from config env vars if the repos table is empty.

    Uses GITHUB_OWNER, GITHUB_REPO, and DEFAULT_BRANCH from the Flask app config.
    No-op if the table already has rows or if owner/repo are not set.
    """
    if db.session.query(Repo).count() > 0:
        return

    owner = current_app.config.get("GITHUB_OWNER", "")
    name = current_app.config.get("GITHUB_REPO", "")
    if not owner or not name:
        return

    default_branch = current_app.config.get("DEFAULT_BRANCH", "main")
    repo = Repo(owner=owner, name=name, default_branch=default_branch)
    db.session.add(repo)
    db.session.commit()
