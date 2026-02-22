# pr-release-board
A lightweight visual board for prioritising and coordinating pull request releases

## Setup

This project uses [Poetry](https://python-poetry.org/) for dependency and environment management.

```bash
# Install dependencies and create the virtual environment
poetry install

# Run the Flask app (use Poetry so dependencies are available)
FLASK_APP=app poetry run flask run

# Or activate the shell and run from there
poetry shell
FLASK_APP=app flask run
```

## Run with Docker

```bash
# Build the image
docker build -t pr-release-board .

# Run and publish port 5000 (app listens on 0.0.0.0:5000 inside the container)
docker run -p 5000:5000 --name prb pr-release-board

# If port 5000 is in use on the host, use e.g. 5001:5000 and open http://127.0.0.1:5001/
docker run -p 5001:5000 --name prb pr-release-board
```

Then open **http://127.0.0.1:5000/** (or **http://127.0.0.1:5001/** if you mapped 5001).

If you get connection refused or 403:

1. **Check the container is running:** `docker ps` — you should see `prb` (or the container ID) with status Up.
2. **Check Flask is listening on 0.0.0.0:** `docker logs prb` — you should see `Running on http://0.0.0.0:5000/`. If it shows `127.0.0.1`, the image was built before adding `--host=0.0.0.0`; rebuild with `docker build -t pr-release-board .`.
3. **Try 127.0.0.1:** Some setups (e.g. Rancher Desktop) behave better with **http://127.0.0.1:5000/** than localhost.
4. **Stop and remove before re-run:** `docker rm -f prb` then run the `docker run` command again.

## Run with Docker Compose (app + Postgres)

Starts the app and a Postgres 16 database; the app waits for the DB to be ready.

```bash
docker-compose up --build
```

Then open **http://127.0.0.1:5000/** (or **http://127.0.0.1:5001/** if you changed the port in `docker-compose.yml`). Set `GITHUB_TOKEN`, `GITHUB_OWNER`, and `GITHUB_REPO` in the `web` service environment when you use GitHub features. There are no database models yet (Phase 1); once you add models and a migration in Phase 2, run `docker-compose exec web alembic upgrade head` to create tables.
