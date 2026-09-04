# Local Business Intelligence

Внутренний single-user инструмент для сбора и нормализации публичных данных о
локальных бизнесах. Первый вертикальный срез начинается с Türkiye → Antalya →
Alanya и остаётся географически настраиваемым.

Согласованный дизайн находится в
[`docs/superpowers/specs/2026-09-04-local-business-intelligence-v1-design.md`](docs/superpowers/specs/2026-09-04-local-business-intelligence-v1-design.md),
а пошаговый план — в
[`docs/superpowers/plans/2026-09-04-v1-foundation-discovery-vertical-slice.md`](docs/superpowers/plans/2026-09-04-v1-foundation-discovery-vertical-slice.md).

## Требования

- Docker Engine или Docker Desktop с запущенным daemon;
- Docker Compose 2.24.4 или новее;
- Python 3 для запуска локального infrastructure contract test.

Приложение и его зависимости будут собираться в контейнерах, поэтому системные
Python и Node.js не используются как production runtime.

## Первый запуск инфраструктуры

```bash
cp .env.example .env
make compose-check
make infra-test
make infra-up
make infra-ps
```

Локальные адреса первого этапа:

- PostgreSQL/PostGIS: `127.0.0.1:5432`;
- Redis: `127.0.0.1:6379`;
- Garage S3 API: `http://127.0.0.1:3900`;
- Garage admin API: `http://127.0.0.1:3903`.

Garage запускается в single-node режиме только для разработки и E2E. Backend
использует общий S3-compatible contract, поэтому production storage выбирается
отдельно и не зависит от локального Garage.

PostgreSQL/PostGIS image собирается локально для текущей архитектуры из
официального PostgreSQL 17.11 и multi-arch PostGIS 3.6 layer. Оба исходных
manifest закреплены digest-ами; сценарий одинаково работает на `amd64` и
Apple Silicon без эмуляции.

## Остановка

```bash
make down
```

Обычная остановка сохраняет named volumes. Команда
`docker compose down -v` удаляет локальную базу, очередь и object storage и
потому намеренно не включена в Makefile.
