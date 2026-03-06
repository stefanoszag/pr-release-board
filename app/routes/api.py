"""JSON API routes."""

import time

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models.pull_request import PullRequestCache
from app.models.queue_item import QueueItem
from app.models.repo import Repo
from app.routes._helpers import resolve_repo
from app.services.github_service import sync_repo
from app.services.queue_service import (
    add_to_queue,
    get_queue,
    remove_from_queue,
    reorder_queue,
    update_note,
)

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health() -> dict:
    """Health check for smoke tests and load balancers."""
    return {"status": "ok"}


@api_bp.route("/repos")
def list_repos() -> tuple[list, int]:
    """
    Return all tracked repos as JSON (id, owner, name, default_branch).

    Returns:
        200 with list of repo dicts; empty list when no repos.
    """
    repos = db.session.query(Repo).order_by(Repo.id).all()
    out = [
        {
            "id": r.id,
            "owner": r.owner,
            "name": r.name,
            "default_branch": r.default_branch,
        }
        for r in repos
    ]
    return jsonify(out), 200


@api_bp.route("/last-sync")
def last_sync() -> tuple[dict, int]:
    """
    Return the most recent sync timestamp for the board.

    Query param: repo_id (optional; defaults to first repo).
    Used by the board page to refresh the "Last sync" label when background
    sync runs, without a full page reload.

    Returns:
        200 with {"last_sync": "ISO8601" | null}. 404 if repo not found.
    """
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err
    open_prs = (
        db.session.query(PullRequestCache)
        .filter(
            PullRequestCache.repo_id == repo.id,
            PullRequestCache.is_open.is_(True),
        )
        .all()
    )
    last = None
    if open_prs:
        last = max(
            (p.synced_at for p in open_prs if p.synced_at),
            default=None,
        )
    last_str = last.isoformat().replace("+00:00", "Z") if last else None
    return jsonify({"last_sync": last_str}), 200


@api_bp.route("/prs")
def list_prs() -> tuple[list, int]:
    """
    Return open cached PRs as JSON.

    Query params: repo_id (optional; defaults to first repo).
    Optional: approved, in_queue (true/false) to filter.

    Returns:
      200 with list of PR objects. 404 if repo not found.
    """
    start = time.perf_counter()
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    approved_param = request.args.get("approved", "").lower()
    in_queue_param = request.args.get("in_queue", "").lower()

    query = db.session.query(PullRequestCache).filter(
        PullRequestCache.repo_id == repo.id,
        PullRequestCache.is_open.is_(True),
    )
    if approved_param == "true":
        query = query.filter(PullRequestCache.approved.is_(True))
    elif approved_param == "false":
        query = query.filter(PullRequestCache.approved.is_(False))

    if in_queue_param == "true":
        queue_pr_numbers = db.session.query(QueueItem.pr_number).filter(
            QueueItem.repo_id == repo.id
        )
        query = query.filter(
            PullRequestCache.number.in_(queue_pr_numbers),
        )
    elif in_queue_param == "false":
        queue_pr_numbers = db.session.query(QueueItem.pr_number).filter(
            QueueItem.repo_id == repo.id
        )
        query = query.filter(
            PullRequestCache.number.notin_(queue_pr_numbers),
        )

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
        "GET /api/prs: count=%s, approved=%s, in_queue=%s, elapsed_ms=%.0f",
        len(out),
        approved_param or "none",
        in_queue_param or "none",
        elapsed_ms,
    )
    return jsonify(out), 200


@api_bp.route("/queue")
def queue_list() -> tuple[list, int]:
    """
    Return the queue for the given repo with PR metadata.

    Query param: repo_id (optional; defaults to first repo).
    Returns 404 if repo not found.
    """
    start = time.perf_counter()
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err
    items = get_queue(repo_id=repo.id)
    elapsed_ms = (time.perf_counter() - start) * 1000
    current_app.logger.info(
        "GET /api/queue: count=%s, elapsed_ms=%.0f", len(items), elapsed_ms
    )
    return jsonify(items), 200


@api_bp.route("/queue/add", methods=["POST"])
def queue_add() -> tuple[dict, int]:
    """
    Add a PR to the queue. Body: repo_id (required), pr_number, note (optional).
    Returns 201 with new queue item; 400 if invalid; 404 if repo not found.
    """
    data = request.get_json(silent=True) or {}
    repo_id = data.get("repo_id")
    if repo_id is None:
        return jsonify({"error": "repo_id is required"}), 400
    try:
        repo_id = int(repo_id)
    except (TypeError, ValueError):
        return jsonify({"error": "repo_id must be an integer"}), 400

    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    pr_number = data.get("pr_number")
    if pr_number is None:
        return jsonify({"error": "pr_number is required"}), 400
    try:
        pr_number = int(pr_number)
    except (TypeError, ValueError):
        return jsonify({"error": "pr_number must be an integer"}), 400
    note = data.get("note", "") or ""
    if not isinstance(note, str):
        note = str(note)

    try:
        add_to_queue(repo_id=repo.id, pr_number=pr_number, note=note)
    except ValueError as e:
        current_app.logger.warning("POST /api/queue/add failed: %s", e)
        return jsonify({"error": str(e)}), 400

    items = get_queue(repo_id=repo.id)
    added = next((q for q in items if q["pr_number"] == pr_number), None)
    if not added:
        return jsonify({"error": "Queue item not found after add"}), 500
    current_app.logger.info(
        "POST /api/queue/add: pr_number=%s, new_position=%s",
        pr_number,
        added["position"],
    )
    return jsonify(added), 201


@api_bp.route("/queue/remove", methods=["POST"])
def queue_remove() -> tuple[dict, int]:
    """
    Remove a PR from the queue. Body: repo_id (required), pr_number.
    Returns 200 with {"removed": true}; 404 if repo or PR not in queue.
    """
    data = request.get_json(silent=True) or {}
    repo_id = data.get("repo_id")
    if repo_id is None:
        return jsonify({"error": "repo_id is required"}), 400
    try:
        repo_id = int(repo_id)
    except (TypeError, ValueError):
        return jsonify({"error": "repo_id must be an integer"}), 400

    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    pr_number = data.get("pr_number")
    if pr_number is None:
        return jsonify({"error": "pr_number is required"}), 400
    try:
        pr_number = int(pr_number)
    except (TypeError, ValueError):
        return jsonify({"error": "pr_number must be an integer"}), 400

    try:
        remove_from_queue(repo_id=repo.id, pr_number=pr_number)
    except ValueError as e:
        current_app.logger.warning("POST /api/queue/remove failed: %s", e)
        return jsonify({"error": str(e)}), 404

    current_app.logger.info("POST /api/queue/remove: pr_number=%s", pr_number)
    return jsonify({"removed": True}), 200


@api_bp.route("/queue/note", methods=["POST"])
def queue_note() -> tuple[dict, int]:
    """
    Update the note for a queued PR. Body: repo_id (required), pr_number, note.
    Returns 200 with updated queue item; 404 if repo or PR not in queue.
    """
    data = request.get_json(silent=True) or {}
    repo_id = data.get("repo_id")
    if repo_id is None:
        return jsonify({"error": "repo_id is required"}), 400
    try:
        repo_id = int(repo_id)
    except (TypeError, ValueError):
        return jsonify({"error": "repo_id must be an integer"}), 400

    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    pr_number = data.get("pr_number")
    if pr_number is None:
        return jsonify({"error": "pr_number is required"}), 400
    try:
        pr_number = int(pr_number)
    except (TypeError, ValueError):
        return jsonify({"error": "pr_number must be an integer"}), 400
    note = data.get("note", "") or ""
    if not isinstance(note, str):
        note = str(note)

    try:
        update_note(repo_id=repo.id, pr_number=pr_number, note=note)
    except ValueError as e:
        current_app.logger.warning("POST /api/queue/note failed: %s", e)
        return jsonify({"error": str(e)}), 404

    items = get_queue(repo_id=repo.id)
    updated = next((q for q in items if q["pr_number"] == pr_number), None)
    if not updated:
        return jsonify({"error": "Queue item not found after update"}), 500
    current_app.logger.info(
        "POST /api/queue/note: pr_number=%s, note=%s", pr_number, note[:50]
    )
    return jsonify(updated), 200


@api_bp.route("/queue/reorder", methods=["POST"])
def queue_reorder() -> tuple[dict, int]:
    """
    Reorder the queue. Body: repo_id (required), ordered_pr_numbers (list).
    Returns 200 with {"reordered": true}; 400 if invalid; 404 if repo not found.
    """
    start = time.perf_counter()
    data = request.get_json(silent=True) or {}
    repo_id = data.get("repo_id")
    if repo_id is None:
        return jsonify({"error": "repo_id is required"}), 400
    try:
        repo_id = int(repo_id)
    except (TypeError, ValueError):
        return jsonify({"error": "repo_id must be an integer"}), 400

    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    ordered_pr_numbers = data.get("ordered_pr_numbers")
    if ordered_pr_numbers is None:
        return jsonify({"error": "ordered_pr_numbers is required"}), 400
    if not isinstance(ordered_pr_numbers, list):
        return jsonify({"error": "ordered_pr_numbers must be a list"}), 400
    if not all(isinstance(x, int) for x in ordered_pr_numbers):
        return jsonify({"error": "ordered_pr_numbers must contain only integers"}), 400

    try:
        reorder_queue(repo_id=repo.id, ordered_pr_numbers=ordered_pr_numbers)
    except ValueError as e:
        current_app.logger.warning("POST /api/queue/reorder failed: %s", e)
        return jsonify({"error": str(e)}), 400

    elapsed_ms = (time.perf_counter() - start) * 1000
    current_app.logger.info(
        "POST /api/queue/reorder: count=%s, elapsed_ms=%.0f",
        len(ordered_pr_numbers),
        elapsed_ms,
    )
    return jsonify({"reordered": True}), 200


@api_bp.route("/sync", methods=["POST"])
def sync() -> tuple[dict, int]:
    """
    Sync open PRs from GitHub into the cache for the given repo.

    Query param: repo_id (optional; defaults to first repo).
    Returns 200 with {"updated": N, "repo": "..."}; 400 if no token;
    404 if repo not found.
    """
    repo_id = request.args.get("repo_id", type=int)
    repo, err = resolve_repo(repo_id)
    if err is not None:
        return jsonify({"error": "Repo not found"}), err

    token = current_app.config.get("GITHUB_TOKEN", "")
    if not token:
        current_app.logger.warning(
            "POST /api/sync rejected: GITHUB_TOKEN not configured"
        )
        return (
            jsonify(
                {
                    "error": "GITHUB_TOKEN is not set",
                    "required": ["GITHUB_TOKEN"],
                }
            ),
            400,
        )
    try:
        start = time.perf_counter()
        result = sync_repo(repo_id=repo.id)
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
