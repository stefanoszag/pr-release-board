"""JSON API routes."""

import time

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.services.github_service import sync_repo

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health() -> dict:
    """Health check for smoke tests and load balancers."""
    return {"status": "ok"}


@api_bp.route("/prs")
def list_prs() -> tuple[list, int]:
    """
    Return open cached PRs as JSON.

    Optional query params:
      approved: "true" or "false" to filter by approval status.
      in_queue: ignored in Phase 2 (no queue table yet).

    Returns:
      200 with list of PR objects: number, title, url, author, base_branch,
      approved, synced_at (ISO 8601).
    """
    start = time.perf_counter()
    approved_param = request.args.get("approved", "").lower()
    in_queue_param = request.args.get("in_queue", "").lower()
    if in_queue_param:
        current_app.logger.debug(
            "GET /api/prs: in_queue=%s ignored (Phase 2)", in_queue_param
        )

    query = db.session.query(PullRequestCache).filter(
        PullRequestCache.is_open.is_(True)
    )
    if approved_param == "true":
        query = query.filter(PullRequestCache.approved.is_(True))
    elif approved_param == "false":
        query = query.filter(PullRequestCache.approved.is_(False))
    query = query.order_by(
        PullRequestCache.approved.desc(), PullRequestCache.number.asc()
    )
    rows = query.all()

    out = []
    for pr in rows:
        synced_at = pr.synced_at
        if synced_at is not None:
            synced_at_str = synced_at.isoformat().replace("+00:00", "Z")
        else:
            synced_at_str = None
        out.append(
            {
                "number": pr.number,
                "title": pr.title or "",
                "url": pr.url or "",
                "author": pr.author or "",
                "base_branch": pr.base_branch or "",
                "approved": pr.approved,
                "synced_at": synced_at_str,
            }
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    current_app.logger.info(
        "GET /api/prs: count=%s, approved_filter=%s, elapsed_ms=%.0f",
        len(out),
        approved_param or "none",
        elapsed_ms,
    )
    return jsonify(out), 200


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
        current_app.logger.warning(
            "POST /api/sync rejected: GitHub credentials not configured"
        )
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
        start = time.perf_counter()
        result = sync_repo(repo_id=1)
        elapsed_ms = (time.perf_counter() - start) * 1000
        current_app.logger.info(
            "POST /api/sync completed: repo=%s, prs_updated=%s, elapsed_ms=%.0f",
            result["repo"],
            result["updated"],
            elapsed_ms,
        )
        return jsonify(result), 200
    except ValueError as e:
        current_app.logger.warning("POST /api/sync failed: %s", e)
        if "not found" in str(e).lower():
            return jsonify({"error": str(e)}), 404
        return jsonify({"error": str(e)}), 400
