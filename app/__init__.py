"""Application factory."""

import os

from flask import Flask

from app.config import Config
from app.extensions import db, scheduler
from app.routes.api import api_bp
from app.routes.pages import pages_bp


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns:
        The configured Flask application instance.
    """
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    app = Flask(__name__, template_folder=template_dir)
    Config.init_app(app)
    database_url = app.config["DATABASE_URL"]
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        database_url if database_url else "sqlite:///app.db"
    )

    db.init_app(app)

    with app.app_context():
        from app.models.repo import seed_repo

        seed_repo()

    scheduler.start()

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(pages_bp)

    return app
