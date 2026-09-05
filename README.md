# Local Business Intelligence

Внутренний single-user инструмент для сбора и нормализации публичных данных о
локальных бизнесах. Первый вертикальный срез начинается с Türkiye → Antalya →
Alanya и остаётся географически настраиваемым.

Согласованный дизайн находится в
[`docs/superpowers/specs/2026-09-04-local-business-intelligence-v1-design.md`](docs/superpowers/specs/2026-09-04-local-business-intelligence-v1-design.md),
а пошаговый план — в
[`docs/superpowers/plans/2026-09-04-v1-foundation-discovery-vertical-slice.md`](docs/superpowers/plans/2026-09-04-v1-foundation-discovery-vertical-slice.md).

## Требования

- Git;
- Docker Engine или Docker Desktop с запущенным daemon;
- Docker Compose `2.24.0` или новее;
- Node.js `24.x` и bundled npm для локального Playwright E2E;
- Python 3 для infrastructure contract test.

Проверка prerequisites:

```bash
git --version
docker version
docker compose version --short
node --version
npm --version
```

Backend, frontend и их runtime-зависимости собираются в контейнерах. Локальный
Node.js нужен только для Playwright, а локальный Python — только для
`tests/infra`.

## Первый запуск

```bash
cp .env.example .env
make compose-check
make infra-test
make infra-up
```

Создайте владельца, не помещая пароль в shell history или `.env`:

```zsh
export DJANGO_SUPERUSER_USERNAME=owner
read -r -s "DJANGO_SUPERUSER_PASSWORD?Пароль локального владельца: "
export DJANGO_SUPERUSER_PASSWORD
./infrastructure/scripts/bootstrap-dev.sh --require-owner
unset DJANGO_SUPERUSER_PASSWORD DJANGO_SUPERUSER_USERNAME
make up
```

`bootstrap_environment` применяет migrations, идемпотентно загружает географию,
источники и таксономию, затем создаёт или обновляет owner. Публичная пара
`owner` / `e2e-password` разрешена только в изолированном fixture E2E и запрещена
для development/production.

Локальные адреса:

- dashboard через production nginx: `http://127.0.0.1:8080`;
- Django API: `http://127.0.0.1:8000/api/v1/`;
- frontend dev server: `http://127.0.0.1:5173`;
- Garage S3 API: `http://127.0.0.1:3900`;
- Garage admin API: `http://127.0.0.1:3903`;
- PostgreSQL/PostGIS: `127.0.0.1:5432`;
- Redis: `127.0.0.1:6379`.

Garage не предоставляет MinIO Console: для локальной диагностики используйте
S3-compatible client и `docker compose logs garage`. Bucket закрыт и доступен
только по credentials из локального `.env`.

## Проверки

```bash
make compose-check infra-test
make backend-check backend-test
make frontend-check frontend-test
make storage-integration
make verify
make e2e
```

`make e2e` создаёт отдельный Compose project
`local-business-intelligence-e2e`, использует отдельные PostGIS/Redis/Garage
volumes, fixture adapters и публичного fixture owner. После успеха или ошибки
контейнеры и volumes только этого E2E project удаляются; development data не
затрагиваются.

## Live Overture и OpenStreetMap

Fixture adapters доступны только с `config.settings.testing` и не могут быть
включены в development/production. Обычный запуск использует live Overture и
OSM adapters, но bootstrap и проверки к провайдерам не обращаются. Live-запрос
начинается только после осознанного выбора Overture Maps и/или OpenStreetMap при
создании кампании и нажатия «Запустить кампанию».

Перед любым разрешённым live OSM sample задайте в локальном `.env`:

- `OVERPASS_URL` — HTTPS endpoint, которым вы вправе пользоваться;
- `SOURCE_USER_AGENT` — product/version и реальный контакт.

В production дополнительно обязателен `OSM_DATASET_VERSION` — стабильный
идентификатор снимка/набора данных. В development без него сохраняется
временный retrieval marker, поэтому для воспроизводимого sample значение лучше
задавать явно. Overture не требует локального credential, но его live download
также выполняйте только после проверки лицензии, attribution и допустимого
объёма данных.

Не используйте публичные community Overpass endpoints как bulk dependency.
Поднимите собственный endpoint или используйте сервис с подходящими лимитами и
условиями. Перед live-запуском проверьте attribution, лицензии, request limits и
операционный бюджет источников.

## Raw storage и резервное копирование

Raw payload сохраняется до строки `SourceRecord` в закрытом S3 bucket по ключу:

```text
raw/{source}/{campaign_id}/{sha256(external_id)}/{sha256(payload)}.json.gz
```

Приоритет резервного копирования — согласованная пара PostgreSQL + S3 bucket:
база содержит provenance, checksum и object key, а Garage — исходный gzip JSON.
Redis является очередью, а не системой долговременного хранения. Для локальной
разработки данные находятся в named volumes `postgres_data`, `garage_meta` и
`garage_data`.

## Пилотная география

Bootstrap создаёт `Türkiye → Antalya → Alanya` и область поиска
«Аланья — пилот» с bbox `(31.70, 36.30, 32.65, 36.75)`. Это operational AOI
первого сбора, а не юридически точная административная граница Аланьи.

## Диагностика

```bash
docker compose ps -a
docker compose logs postgres
docker compose logs redis
docker compose logs garage
docker compose logs backend celery-discovery celery-normalization nginx
make workers-inspect
```

- PostGIS: проверьте `DATABASE_URL`, healthcheck и свободный порт 5432.
- Redis: проверьте `REDIS_URL`, `CELERY_BROKER_URL` и обе worker queues.
- Garage/S3: проверьте endpoint, bucket, access key/secret и healthcheck.
- Если справочники или owner отсутствуют, повторите bootstrap — он идемпотентен.

## Остановка

```bash
make down
```

Обычная остановка сохраняет development named volumes. `docker compose down -v`
удаляет локальную базу, очередь и object storage, поэтому намеренно не включён в
`make down`.

## Канонические бизнесы и проверка дубликатов

Раздел «Бизнесы» использует `/api/v1/businesses/` и показывает канонические
компании, число уникальных источников и исходных записей. Provenance исходных
записей остаётся доступен через `/api/v1/source-records/`.

При обновлении существующей локальной установки выполните:

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py deduplicate_businesses --dry-run
docker compose run --rm backend python manage.py deduplicate_businesses
```

Dry-run рассчитывает результат в транзакции и откатывает изменения. Реальный
запуск создаёт производные компании, memberships и кандидатов на проверку;
исходные записи не удаляются. Команда допускает повторный запуск. После неё
число normalized records должно совпадать с числом memberships, а unresolved
для каждого owner должно быть равно нулю. Новые нормализованные записи
привязываются к компаниям в ходе обработки кампании.

В разделе «Дубликаты» (`/businesses/duplicates`) представлены две сводки,
степень совпадения и причины. «Объединить» переносит исходные записи в одну
компанию; сохраняемую компанию детерминированно выбирает сервер. «Это разные
компании» закрывает кандидатуру без слияния. Оба действия требуют подтверждения.
После решения обновляются очередь, список бизнесов и показатели обзора.
Если другой запрос уже обработал пару, обновите список.

Discovery запускается только кнопкой «Запустить кампанию». Этот срез не добавляет
scheduler, AI, платные API, crawler, audit, scoring бизнесов или export.
Баллы совпадения служат только для проверки дубликатов.
