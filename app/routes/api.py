"""JSON API routes."""

from flask import Blueprint, current_app, jsonify

from app.services.github_service import sync_repo

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health() -> dict:
    """Health check for smoke tests and load balancers."""
    return {"status": "ok"}


@api_bp.route("/sync", methods=["POST"])
def sync() -> tuple[dict, int]:
    """
    Sync open PRs from GitHub into the cache for the configured repo (repo_id=1).

    Returns:
        200 with {"updated": N, "repo": "..."} on success.
        400 if GITHUB_TOKEN, GITHUB_OWNER, or GITHUB_REPO are not set.
        404 if the repo row is not found.
    """
    token = current_app.config.get("GITHUB_TOKEN", "")
    owner = current_app.config.get("GITHUB_OWNER", "")
    repo_name = current_app.config.get("GITHUB_REPO", "")
    if not token or not owner or not repo_name:
        return (
            jsonify(
                {
                    "error": "GitHub credentials not configured",
                    "required": ["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"],
                }
            ),
            400,
        )
    try:
        result = sync_repo(repo_id=1)
        return jsonify(result), 200
    except ValueError as e:
        if "not found" in str(e).lower():
            return jsonify({"error": str(e)}), 404
        return jsonify({"error": str(e)}), 400
