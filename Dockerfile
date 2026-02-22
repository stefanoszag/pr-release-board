# Phase 1: app scaffold — run with docker-compose (Step 9)
FROM python:3.12-slim

# Install Poetry and configure to install into system Python (no venv in container)
RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi

# Copy application code and migrations
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

ENV FLASK_APP=app
EXPOSE 5000

# Run migrations then start the app (migrations use DATABASE_URL from env)
CMD ["sh", "-c", "alembic upgrade head && exec flask run --host=0.0.0.0 --port=5000"]
