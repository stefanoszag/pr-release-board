"""Application factory."""

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
    app = Flask(__name__)
    Config.init_app(app)
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["DATABASE_URL"]

    db.init_app(app)

    scheduler.start()

    app.register_blueprint(api_bp)
    app.register_blueprint(pages_bp)

    @app.route("/health")
    def health() -> dict:
        """Health check for smoke tests and load balancers."""
        return {"status": "ok"}

    return app
