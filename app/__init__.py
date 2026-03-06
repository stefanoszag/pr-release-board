"""Application factory."""

import logging
import os
import sys

from flask import Flask

from app.config import Config
from app.extensions import db, scheduler
from app.routes.api import api_bp
from app.routes.pages import pages_bp


def _background_sync(flask_app: Flask) -> None:
    """
    Run a single sync cycle inside a pushed application context.

    Intended to be called by APScheduler on an interval. Errors are caught
    and logged so a failed sync never crashes the scheduler.

    Args:
        flask_app: The Flask application instance to push context for.
    """
    with flask_app.app_context():
        try:
            from app.services.github_service import sync_repo

            sync_repo(repo_id=1)
        except Exception as e:
            flask_app.logger.error("Background sync failed: %s", e)


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        The configured Flask application instance.
    """
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    app = Flask(__name__, template_folder=template_dir)
    Config.init_app(app)

    # Ensure app and request logs at INFO are visible (e.g. sync logs, timing)
    app.logger.setLevel(logging.INFO)
    if not app.logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
    database_url = app.config["DATABASE_URL"]
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        database_url if database_url else "sqlite:///app.db"
    )

    db.init_app(app)

    with app.app_context():
        if app.config.get("GITHUB_TOKEN") and app.config.get("GITHUB_OWNER"):
            from app.services.github_service import sync_repos_from_github

            names = sync_repos_from_github(owner=app.config["GITHUB_OWNER"])
            if names:
                app.logger.info("Synced %s repo(s) from GitHub: %s", len(names), names)

    scheduler.start()

    if app.config.get("GITHUB_TOKEN"):
        scheduler.add_job(
            func=_background_sync,
            args=[app],
            trigger="interval",
            minutes=app.config["SYNC_INTERVAL_MINUTES"],
            id="background_sync",
            replace_existing=True,
        )
        app.logger.info(
            "Background sync scheduled every %s minute(s).",
            app.config["SYNC_INTERVAL_MINUTES"],
        )

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(pages_bp)

    return app
