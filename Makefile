# Test database (Docker). URL must match tests/conftest.py default.
# Connection: postgresql://test:test@127.0.0.1:5432/test_pr_board
TEST_DB_IMAGE := postgres:16-alpine
TEST_DB_NAME := pr-release-board-test-db
TEST_DB_USER := test
TEST_DB_PASSWORD := test
TEST_DB_NAME_DB := test_pr_board
TEST_DB_HOST := 127.0.0.1
TEST_DATABASE_URL := postgresql://$(TEST_DB_USER):$(TEST_DB_PASSWORD)@$(TEST_DB_HOST):5432/$(TEST_DB_NAME_DB)

.PHONY: test-db-up test-db-down test-db-logs test-db-check test help

help:
	@echo "Testing (pytest uses test DB by default; no DATABASE_URL needed):"
	@echo "  make test          - Start test DB if needed, run pytest."
	@echo "  make test-db-up    - Start Postgres container (idempotent)."
	@echo "  make test-db-down  - Stop and remove container."
	@echo "  make test-db-check - Verify connectivity from host."
	@echo "  make test-db-logs  - Tail container logs."

## Start Postgres in Docker for testing (port 5432 on host loopback)
test-db-up:
	@if docker ps -q -f name=^$(TEST_DB_NAME)$$ 2>/dev/null | grep -q .; then \
		echo "Test database container already running."; \
	elif docker ps -aq -f name=^$(TEST_DB_NAME)$$ 2>/dev/null | grep -q .; then \
		echo "Starting existing test database container..."; \
		docker start $(TEST_DB_NAME); \
	else \
		docker run -d --name $(TEST_DB_NAME) \
			-e POSTGRES_USER=$(TEST_DB_USER) \
			-e POSTGRES_PASSWORD=$(TEST_DB_PASSWORD) \
			-e POSTGRES_DB=$(TEST_DB_NAME_DB) \
			-p $(TEST_DB_HOST):5432:5432 \
			--health-cmd="pg_isready -U $(TEST_DB_USER) -d $(TEST_DB_NAME_DB)" \
			--health-interval=5s \
			--health-timeout=5s \
			--health-retries=5 \
			$(TEST_DB_IMAGE); \
	fi
	@echo "Waiting for Postgres to be ready..."
	@until docker exec $(TEST_DB_NAME) pg_isready -U $(TEST_DB_USER) -d $(TEST_DB_NAME_DB) 2>/dev/null; do sleep 1; done
	@echo "Test database up: $(TEST_DATABASE_URL)"

## Stop and remove the test database container
test-db-down:
	-docker stop $(TEST_DB_NAME)
	-docker rm $(TEST_DB_NAME)
	@echo "Test database container removed."

## Show logs from the test database container
test-db-logs:
	docker logs -f $(TEST_DB_NAME)

## Verify connectivity: from inside container and from host (requires psycopg2)
test-db-check:
	@echo "Inside container:"
	@docker exec $(TEST_DB_NAME) pg_isready -U $(TEST_DB_USER) -d $(TEST_DB_NAME_DB) || true
	@echo "Port on host:"
	@docker port $(TEST_DB_NAME) 5432 || true
	@echo "From host (Python):"
	@DATABASE_URL=$(TEST_DATABASE_URL) poetry run python -c "\
import os; from sqlalchemy import create_engine; from urllib.parse import urlparse; u=urlparse(os.environ.get('DATABASE_URL','')); print('URL:', u.hostname, u.port, u.path); e=create_engine(os.environ['DATABASE_URL']); e.connect(); print('OK: connected')" 2>/dev/null || echo "Connection from host failed. Ensure DATABASE_URL=$(TEST_DATABASE_URL) and port 5432 is not used by another Postgres."

## Start test DB if needed, then run pytest (conftest uses test DB URL by default)
test:
	$(MAKE) test-db-up 2>/dev/null || true
	@poetry run pytest tests/ -v
