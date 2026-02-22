"""HTML page routes."""

from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def board() -> str:
    """Render the release queue board (placeholder)."""
    return render_template("board.html")
