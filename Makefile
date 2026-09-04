STORAGE_TEST_COMPOSE := docker compose -p local-business-intelligence-storage-test -f docker-compose.yml -f docker-compose.e2e.yml

.PHONY: up down infra-up infra-ps infra-test compose-check backend-test backend-check frontend-install frontend-test frontend-check storage-integration workers-up workers-inspect

up:
	docker compose up -d --build

down:
	docker compose down

infra-up:
	docker compose up -d --build --wait --wait-timeout 90 postgres redis garage

infra-ps:
	docker compose ps -a

infra-test:
	python3 -m unittest tests/infra/test_compose_contract.py -v

compose-check:
	docker compose config --quiet
	docker compose -f docker-compose.yml -f docker-compose.e2e.yml config --quiet

backend-test:
	docker compose run --rm backend pytest -m "not integration" -q

backend-check:
	docker compose run --rm backend ruff check .
	docker compose run --rm backend ruff format --check .
	docker compose run --rm backend python manage.py check
	docker compose run --rm backend python manage.py makemigrations --check --dry-run

frontend-test:
	docker compose run --rm frontend npm run test:run

frontend-install:
	docker compose build frontend
	docker compose run --rm frontend npm ci

frontend-check:
	docker compose run --rm frontend npm run lint
	docker compose run --rm frontend npm run typecheck
	docker compose run --rm frontend npm run build

storage-integration:
	@set -eu; trap '$(STORAGE_TEST_COMPOSE) down -v' EXIT INT TERM; \
	$(STORAGE_TEST_COMPOSE) up -d --wait --wait-timeout 90 postgres redis garage; \
	$(STORAGE_TEST_COMPOSE) run --rm -e STORAGE_INTEGRATION_PROJECT=1 backend \
	  pytest apps/sources/tests/integration/test_s3_raw_payload_storage.py -q

workers-up:
	docker compose build backend
	docker compose up -d --wait --wait-timeout 90 celery-discovery celery-normalization

workers-inspect:
	docker compose exec celery-discovery celery -A config inspect active_queues -d discovery@celery-discovery
	docker compose exec celery-normalization celery -A config inspect active_queues -d normalization@celery-normalization
