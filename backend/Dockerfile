# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgdal32 libgeos-c1v5 libproj25 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

FROM runtime AS development
COPY requirements/base.txt requirements/development.txt requirements/
RUN pip install --require-hashes --requirement requirements/development.txt
COPY . .
USER app
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM runtime AS production
COPY requirements/base.txt requirements/production.txt requirements/
RUN pip install --require-hashes --requirement requirements/production.txt
COPY . .
USER app
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
