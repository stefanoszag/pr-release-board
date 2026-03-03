# pr-release-board

[![codecov](https://codecov.io/gh/stefanoszag/pr-release-board/graph/badge.svg?token=SJKDCQ4DYQ)](https://codecov.io/gh/stefanoszag/pr-release-board) [![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/) [![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight visual board for prioritising and coordinating pull request releases. Sync open PRs from GitHub, manage a release queue with drag-and-drop reordering, and track all queue activity in an event log.

## What it does

- **Board** (`/`) — Shows open PRs for the configured repo with title (link), author, and approved / not-approved badge. PRs can be added to, removed from, and reordered in a release queue via drag-and-drop. A "Sync now" button fetches the latest state from GitHub; the last sync timestamp is shown next to the button.
- **Release queue** — Approved PRs can be queued for release. Items are ordered by drag-and-drop (position 1 = next to release). Each queued PR can carry a free-text note. Closed or merged PRs are automatically removed from the queue on the next sync.
- **Activity log** (`/activity`) — Chronological log of all queue events: `added`, `removed`, `moved`, `note_updated`, and `sync_removed` (auto-removed by background sync).
- **Background auto-sync** — APScheduler runs a sync automatically every `SYNC_INTERVAL_MINUTES` minutes (when `GITHUB_TOKEN` is set). No manual action required for the board to stay up-to-date.
- **Sync cleanup** — After each sync, any queued PR that is no longer open on GitHub is removed from the queue and a `sync_removed` event is written to the activity log.

Migrations run automatically when the app starts; the repo row is seeded from env if the table is empty.

## Pages

| Path | Description |
|------|-------------|
| `/` | Board — open PRs, release queue, sync controls |
| `/activity` | Activity log — full event history |

## API surface

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/last-sync` | Current last-sync timestamp (for board label refresh) |
| `POST` | `/api/sync` | Trigger a manual sync |
| `GET` | `/api/prs` | List cached PRs (`?approved=true/false`) |
| `GET` | `/api/queue` | List current queue items |
| `POST` | `/api/queue` | Add a PR to the queue |
| `DELETE` | `/api/queue/<pr_number>` | Remove a PR from the queue |
| `PUT` | `/api/queue/reorder` | Reorder the queue |
| `PUT` | `/api/queue/<pr_number>/note` | Update the note for a queued PR |
| `GET` | `/api/activity` | List queue events |

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes (for sync) | — | GitHub personal access token |
| `GITHUB_OWNER` | Yes (for sync) | — | GitHub organisation or user name |
| `GITHUB_REPO` | Yes (for sync) | — | Repository name (without owner) |
| `DEFAULT_BRANCH` | No | `main` | Base branch to filter open PRs against |
| `DATABASE_URL` | No | `sqlite:///app.db` | SQLAlchemy-compatible database URL |
| `SYNC_INTERVAL_MINUTES` | No | `5` | How often the background sync runs (minutes) |

## Setup (local)

This project uses [Poetry](https://python-poetry.org/) for dependency and environment management.

```bash
poetry install
export FLASK_APP=app
poetry run flask run
```

Then open **http://127.0.0.1:5000/**.

## Testing

Tests use a Postgres database. **You don’t need to set `DATABASE_URL`** — `tests/conftest.py` uses the test DB URL by default (`postgresql://test:test@127.0.0.1:5432/test_pr_board`). Start the test DB with Docker, then run pytest:

```bash
# Easiest: start test DB if needed and run tests
make test
```

Or start the DB once and run pytest yourself:

```bash
make test-db-up
poetry run pytest tests/ -v
# when finished: make test-db-down
```

| Command | Description |
|---------|-------------|
| `make test` | Start test DB if needed, run pytest (no env vars required). |
| `make test-db-up` | Start Postgres 16 container (idempotent). |
| `make test-db-down` | Stop and remove the test DB container. |
| `make test-db-check` | Verify connectivity (if tests fail to connect). |
| `make test-db-logs` | Tail test DB container logs. |
| `make help` | List all targets. |

To use a different test DB (e.g. another port), set `TEST_DATABASE_URL` when running pytest. If port 5432 is in use, change the port in the Makefile and set `TEST_DATABASE_URL` to match.

## Run with Docker Compose (app + Postgres) — recommended

Starts the app and a Postgres 16 database. The app waits for the DB to be ready, runs migrations, then starts. One repo is seeded from env if the `repos` table is empty. Background sync starts automatically.

```bash
# Option A: set env in the shell
export GITHUB_TOKEN=ghp_xxx
export GITHUB_OWNER=your-org
export GITHUB_REPO=your-repo
docker-compose up --build

# Option B: use a .env file in the project root (add .env to .gitignore)
docker-compose up --build
```

Then open **http://127.0.0.1:5001/**.

## Run with Docker (single container)

```bash
docker build -t pr-release-board .
docker run -p 5001:5001 \
  -e GITHUB_TOKEN=ghp_xxx \
  -e GITHUB_OWNER=your-org \
  -e GITHUB_REPO=your-repo \
  --name prb pr-release-board
```

Without a `DATABASE_URL` the app falls back to SQLite inside the container (state is lost on restart).

### Troubleshooting

- **Connection refused or 403:** Try **http://127.0.0.1:5001/** (not `localhost`). Ensure the container is up: `docker ps`; check logs: `docker-compose logs web`.
- **Re-run:** `docker-compose down` then `docker-compose up --build`.
- **Single-container Docker:** After `docker run`, stop with `docker rm -f prb` before running again.
