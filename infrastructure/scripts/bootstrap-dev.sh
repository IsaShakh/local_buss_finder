#!/bin/sh
set -eu

docker compose run --rm \
  -e DJANGO_SUPERUSER_USERNAME \
  -e DJANGO_SUPERUSER_PASSWORD \
  backend python manage.py bootstrap_environment "$@"
