.PHONY: up down infra-up infra-ps infra-test compose-check backend-test backend-check

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
	docker compose run --rm backend pytest

backend-check:
	docker compose run --rm backend ruff check .
	docker compose run --rm backend python manage.py check
