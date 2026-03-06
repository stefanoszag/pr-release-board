"""API endpoint tests using Flask test client; sync_repo mocked where needed."""

from typing import Any
from unittest.mock import MagicMock

import pytest  # type: ignore[import-untyped]

from app.models.repo import Repo
from app.services import queue_service
from tests.services.test_queue_service import make_pr, make_repo


# ---- GET /api/repos ----
def test_get_repos_returns_list(client: Any, repo_1: Repo) -> None:
    """GET /api/repos → 200 with list of repo dicts (id, owner, name,
    default_branch)."""
    r = client.get("/api/repos")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = next(d for d in data if d["id"] == repo_1.id)
    assert first["owner"] == repo_1.owner
    assert first["name"] == repo_1.name
    assert first["default_branch"] == repo_1.default_branch


def test_get_repos_empty_when_no_repos(client: Any, db_session: Any, app: Any) -> None:
    """GET /api/repos when no repos in DB → 200 with empty list."""
    from app.models.pull_request import PullRequestCache
    from app.models.queue_event import QueueEvent
    from app.models.queue_item import QueueItem

    db_session.query(QueueEvent).delete()
    db_session.query(QueueItem).delete()
    db_session.query(PullRequestCache).delete()
    db_session.query(Repo).delete()
    db_session.commit()
    r = client.get("/api/repos")
    assert r.status_code == 200
    assert r.get_json() == []


# ---- GET /api/health ----
def test_get_health_returns_ok(client: Any) -> None:
    """GET /api/health → 200 {"status": "ok"}."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


# ---- GET /api/prs ----
def test_get_prs_returns_list(client: Any, db_session: Any, repo_1: Repo) -> None:
    """GET /api/prs with PRs in cache → 200 list."""
    make_pr(db_session, repo_1, pr_number=201, title="First PR")
    make_pr(db_session, repo_1, pr_number=202, title="Second PR")
    db_session.commit()
    r = client.get("/api/prs")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 2
    numbers = {p["number"] for p in data}
    assert 201 in numbers and 202 in numbers


def test_get_prs_approved_filter(client: Any, db_session: Any, repo_1: Repo) -> None:
    """GET /api/prs?approved=true → only approved rows."""
    make_pr(db_session, repo_1, pr_number=101, approved=True)
    make_pr(db_session, repo_1, pr_number=102, approved=False)
    db_session.commit()
    r = client.get("/api/prs?approved=true")
    assert r.status_code == 200
    data = r.get_json()
    assert all(p["approved"] for p in data)
    assert any(p["number"] == 101 for p in data)


def test_get_prs_invalid_repo_id_404(client: Any, repo_1: Repo) -> None:
    """GET /api/prs?repo_id=99999 when repo not in DB → 404."""
    r = client.get("/api/prs?repo_id=99999")
    assert r.status_code == 404
    assert (r.get_json() or {}).get("error") == "Repo not found"


def test_get_queue_invalid_repo_id_404(client: Any) -> None:
    """GET /api/queue?repo_id=99999 when repo not in DB → 404."""
    r = client.get("/api/queue?repo_id=99999")
    assert r.status_code == 404
    assert (r.get_json() or {}).get("error") == "Repo not found"


def test_get_last_sync_invalid_repo_id_404(client: Any) -> None:
    """GET /api/last-sync?repo_id=99999 when repo not in DB → 404."""
    r = client.get("/api/last-sync?repo_id=99999")
    assert r.status_code == 404
    assert (r.get_json() or {}).get("error") == "Repo not found"


# ---- GET /api/queue ----
def test_get_queue_returns_ordered(client: Any, db_session: Any, repo_1: Repo) -> None:
    """GET /api/queue with items in queue → 200 ordered list."""
    make_pr(db_session, repo_1, pr_number=301)
    make_pr(db_session, repo_1, pr_number=302)
    db_session.commit()
    queue_service.add_to_queue(repo_1.id, 301)
    queue_service.add_to_queue(repo_1.id, 302)
    db_session.commit()
    r = client.get("/api/queue")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 2
    by_num = {q["pr_number"]: q for q in data}
    assert 301 in by_num and 302 in by_num
    assert by_num[301]["position"] < by_num[302]["position"]


def test_get_prs_scoped_by_repo_id(client: Any, db_session: Any, repo_1: Repo) -> None:
    """GET /api/prs?repo_id=X returns only PRs for that repo (multi-repo scoping)."""
    repo2 = make_repo(db_session)
    make_pr(db_session, repo_1, pr_number=9011, title="PR in repo 1")
    make_pr(db_session, repo2, pr_number=9012, title="PR in repo 2")
    db_session.commit()
    r = client.get(f"/api/prs?repo_id={repo_1.id}")
    assert r.status_code == 200
    data = r.get_json()
    numbers = [p["number"] for p in data]
    assert 9011 in numbers
    assert 9012 not in numbers
    r2 = client.get(f"/api/prs?repo_id={repo2.id}")
    assert r2.status_code == 200
    data2 = r2.get_json()
    numbers2 = [p["number"] for p in data2]
    assert 9012 in numbers2
    assert 9011 not in numbers2


# ---- GET /api/last-sync ----
def test_get_last_sync_returns_timestamp(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """GET /api/last-sync with PRs synced → 200 with ISO timestamp."""
    make_pr(db_session, repo_1, pr_number=401, title="PR")
    db_session.commit()
    r = client.get("/api/last-sync")
    assert r.status_code == 200
    data = r.get_json()
    assert "last_sync" in data
    assert data["last_sync"] is None or isinstance(data["last_sync"], str)


# ---- POST /api/queue/add ----
def test_post_queue_add_approved_pr_201(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/add with approved PR → 201 item dict."""
    make_pr(db_session, repo_1, pr_number=501)
    db_session.commit()
    r = client.post(
        "/api/queue/add",
        json={"repo_id": repo_1.id, "pr_number": 501, "note": "ready"},
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["pr_number"] == 501
    assert data["position"] >= 1
    assert data.get("note") == "ready"


def test_post_queue_add_missing_repo_id_400(client: Any) -> None:
    """POST /api/queue/add without repo_id in body → 400."""
    r = client.post(
        "/api/queue/add",
        json={"pr_number": 1},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "repo_id" in (r.get_json() or {}).get("error", "").lower()


def test_post_queue_add_missing_pr_number_400(client: Any, repo_1: Repo) -> None:
    """POST /api/queue/add without pr_number → 400."""
    r = client.post(
        "/api/queue/add",
        json={"repo_id": repo_1.id},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "pr_number" in (r.get_json() or {}).get("error", "").lower()


def test_post_queue_add_invalid_repo_id_404(client: Any) -> None:
    """POST /api/queue/add with repo_id not in DB → 404 (before checking PR)."""
    r = client.post(
        "/api/queue/add",
        json={"repo_id": 99999, "pr_number": 1},
        content_type="application/json",
    )
    assert r.status_code == 404
    assert (r.get_json() or {}).get("error") == "Repo not found"


def test_post_queue_add_not_approved_400(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/add with PR not approved → 400."""
    make_pr(db_session, repo_1, pr_number=502, approved=False)
    db_session.commit()
    r = client.post(
        "/api/queue/add",
        json={"repo_id": repo_1.id, "pr_number": 502},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "approved" in (r.get_json() or {}).get("error", "").lower()


# ---- POST /api/queue/remove ----
def test_post_queue_remove_exists_200(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/remove when item exists → 200 {"removed": true}."""
    make_pr(db_session, repo_1, pr_number=601)
    db_session.commit()
    queue_service.add_to_queue(repo_1.id, 601)
    db_session.commit()
    r = client.post(
        "/api/queue/remove",
        json={"repo_id": repo_1.id, "pr_number": 601},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json() == {"removed": True}


def test_post_queue_remove_not_in_queue_404(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/remove when not in queue → 404."""
    make_pr(db_session, repo_1, pr_number=602)
    db_session.commit()
    r = client.post(
        "/api/queue/remove",
        json={"repo_id": repo_1.id, "pr_number": 602},
        content_type="application/json",
    )
    assert r.status_code == 404


# ---- POST /api/queue/note ----
def test_post_queue_note_exists_200(client: Any, db_session: Any, repo_1: Repo) -> None:
    """POST /api/queue/note when item exists → 200 updated item."""
    make_pr(db_session, repo_1, pr_number=701)
    db_session.commit()
    queue_service.add_to_queue(repo_1.id, 701, note="old")
    db_session.commit()
    r = client.post(
        "/api/queue/note",
        json={"repo_id": repo_1.id, "pr_number": 701, "note": "new note"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["pr_number"] == 701
    assert data.get("note") == "new note"


# ---- POST /api/queue/reorder ----
def test_post_queue_reorder_valid_200(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/reorder with valid order → 200 {"reordered": true}."""
    make_pr(db_session, repo_1, pr_number=801)
    make_pr(db_session, repo_1, pr_number=802)
    db_session.commit()
    queue_service.add_to_queue(repo_1.id, 801)
    queue_service.add_to_queue(repo_1.id, 802)
    db_session.commit()
    # Build order that matches current queue (may contain items from other tests)
    current = client.get("/api/queue").get_json()
    all_nums = [q["pr_number"] for q in current]
    ordered = [802, 801] + [n for n in all_nums if n not in (801, 802)]
    r = client.post(
        "/api/queue/reorder",
        json={"repo_id": repo_1.id, "ordered_pr_numbers": ordered},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json() == {"reordered": True}


def test_post_queue_reorder_set_mismatch_400(
    client: Any, db_session: Any, repo_1: Repo
) -> None:
    """POST /api/queue/reorder when set mismatch → 400."""
    make_pr(db_session, repo_1, pr_number=901)
    db_session.commit()
    queue_service.add_to_queue(repo_1.id, 901)
    db_session.commit()
    r = client.post(
        "/api/queue/reorder",
        json={"repo_id": repo_1.id, "ordered_pr_numbers": [901, 999]},
        content_type="application/json",
    )
    assert r.status_code == 400


# ---- POST /api/sync ----
def test_post_sync_token_set_mocked_200(
    client: Any, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/sync with token set (mocked sync_repo) → 200 {"updated": N}."""
    app.config["GITHUB_TOKEN"] = "fake"
    app.config["GITHUB_OWNER"] = "org"
    app.config["GITHUB_REPO"] = "repo"
    mock_sync = MagicMock(return_value={"updated": 3, "repo": "repo"})
    monkeypatch.setattr(
        "app.routes.api.sync_repo",
        mock_sync,
    )
    r = client.post("/api/sync")
    assert r.status_code == 200
    data = r.get_json()
    assert data["updated"] == 3
    assert data["repo"] == "repo"
    mock_sync.assert_called_once_with(repo_id=1)


def test_post_sync_no_token_400(client: Any, app: Any) -> None:
    """POST /api/sync with no token → 400."""
    app.config["GITHUB_TOKEN"] = ""
    app.config["GITHUB_OWNER"] = ""
    app.config["GITHUB_REPO"] = ""
    r = client.post("/api/sync")
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data
