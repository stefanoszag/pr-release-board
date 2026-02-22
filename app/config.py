"""Application configuration loaded from environment variables."""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


class Config:
    """
    Flask and application configuration.

    All credentials and settings are read directly from environment variables
    via os.environ. No .env file is used; variables are injected at runtime
    (e.g. via docker-compose environment block or the host shell).
    """

    # GitHub
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_OWNER: str = os.environ.get("GITHUB_OWNER", "")
    GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "")
    DEFAULT_BRANCH: str = os.environ.get("DEFAULT_BRANCH", "main")

    # Database
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

    # Sync
    SYNC_INTERVAL_MINUTES: int = int(
        os.environ.get("SYNC_INTERVAL_MINUTES", "5")
    )

    @classmethod
    def init_app(cls, app: "Flask") -> None:
        """
        Load this config into the Flask app.

        Args:
            app: The Flask application instance.
        """
        app.config.from_object(cls)
