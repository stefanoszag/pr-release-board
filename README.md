# pr-release-board

A lightweight visual board for prioritising and coordinating pull request releases. Sync open PRs from GitHub, see approval status, and manage them in one place.

## What it does

- **Board** (`/`) — Shows the configured repo, a “Sync now” button, and a table of open PRs with title (link), author, approved/not-approved badge, and last sync time.
- **Sync** — Fetches open PRs from GitHub (for the repo’s default branch), stores them in Postgres, and updates approval status from reviews. Merged or closed PRs are marked accordingly.
- **API** — `GET /api/health`, `POST /api/sync`, `GET /api/prs` (optional `?approved=true` or `?approved=false`).

Migrations run automatically when the app starts; the repo row is seeded from env if the table is empty.

## Setup (local)

This project uses [Poetry](https://python-poetry.org/) for dependency and environment management.

```bash
poetry install
export FLASK_APP=app
poetry run flask run
```

Then open **http://127.0.0.1:5000/** (Flask’s default port when run locally).

## Run with Docker (single container)

Build and run the image. The app listens on port **5001** inside the container.

```bash
docker build -t pr-release-board .
docker run -p 5001:5001 --name prb pr-release-board
```

Then open **http://127.0.0.1:5001/**.

For GitHub sync you must pass env vars, e.g.:

```bash
docker run -p 5001:5001 -e DATABASE_URL=sqlite:///app.db \
  -e GITHUB_TOKEN=ghp_xxx -e GITHUB_OWNER=your-org -e GITHUB_REPO=your-repo \
  --name prb pr-release-board
```

(Without Postgres you get SQLite; for production use Postgres as in Docker Compose below.)

## Run with Docker Compose (app + Postgres)

Starts the app and a Postgres 16 database. The app waits for the DB to be ready, runs migrations, then starts. One repo is seeded from env if the `repos` table is empty.

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

**Required for sync:** `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`. Optional: `DEFAULT_BRANCH` (default `main`).

### Troubleshooting

- **Connection refused or 403:** Try **http://127.0.0.1:5001/** (not localhost). Ensure the container is up: `docker ps`; check logs: `docker-compose logs web`.
- **Re-run:** `docker-compose down` then `docker-compose up --build`.
- **Single-container Docker:** After `docker run`, stop with `docker rm -f prb` before running again.
