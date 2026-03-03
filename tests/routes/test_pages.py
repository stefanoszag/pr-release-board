"""Smoke tests for HTML page routes."""

from typing import Any

import pytest  # type: ignore[import-untyped]

from app.models.repo import Repo
from app.extensions import db


def test_get_board_200_contains_board_and_queued(client: Any) -> None:
    """GET / → 200, response contains 'board' and 'Queued' (template rendered)."""
    r = client.get("/")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "board" in text.lower()
    assert "Queued" in text


def test_get_activity_200_contains_activity(client: Any) -> None:
    """GET /activity → 200, response contains 'Activity'."""
    r = client.get("/activity")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "Activity" in text


def test_get_board_no_repo_200(
    client: Any, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET / with no repo seeded → 200 (graceful empty state, no 500)."""
    real_get = db.session.get

    def mock_get(self: Any, entity: type, ident: int) -> Any:
        if entity is Repo and ident == 1:
            return None
        return real_get(entity, ident)

    monkeypatch.setattr(type(db.session), "get", mock_get)
    r = client.get("/")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "No repo configured" in text or "board" in text.lower()


def test_get_activity_no_repo_200(
    client: Any, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /activity with no repo seeded → 200 (graceful empty state, no 500)."""
    real_get = db.session.get

    def mock_get(self: Any, entity: type, ident: int) -> Any:
        if entity is Repo and ident == 1:
            return None
        return real_get(entity, ident)

    monkeypatch.setattr(type(db.session), "get", mock_get)
    r = client.get("/activity")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert "Activity" in text
