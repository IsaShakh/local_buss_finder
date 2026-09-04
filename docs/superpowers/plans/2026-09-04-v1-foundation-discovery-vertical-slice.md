# Первый вертикальный срез foundation + discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Получить первый рабочий end-to-end срез: пользователь входит в русский React dashboard, создаёт кампанию для Alanya, запускает Overture/OSM discovery, сохраняет raw payload в S3-compatible object storage, нормализует записи в PostgreSQL/PostGIS и видит долговечный прогресс и предварительную таблицу найденных записей.

**Architecture:** Один monorepo и modular Django monolith обслуживают REST API и Celery workers из общего backend image. PostgreSQL/PostGIS хранит domain state и прогресс, Redis используется только как broker, S3-compatible storage хранит deterministic gzip JSON, React polling-ом читает API. Local/E2E использует Garage; production provider остаётся заменяемым за тем же S3 contract. До следующего плана UI показывает `NormalizedSourceRecord`; canonical `Business` и межисточниковая дедупликация намеренно отсутствуют.

**Tech Stack:** Python 3.13, Django 5.2 LTS, DRF 3.16, PostgreSQL 17 + PostGIS 3.6 + `pg_trgm` + `unaccent`, Celery 5.5 + Redis 7.4, Garage/S3, boto3, official `overturemaps` Python client, httpx, React 19.2.8, TypeScript 5.9.3, Vite 8.2.2, React Router, TanStack Query/Table, React Hook Form, Zod, Vitest/Testing Library/MSW, Playwright, Docker Compose, nginx, Gunicorn.

**Spec:** `docs/superpowers/specs/2026-09-04-local-business-intelligence-v1-design.md`

## Approved execution amendments

Эти решения согласованы после первоначального review и имеют приоритет над оставшимися ниже историческими snippets, которые ещё упоминают MinIO:

- repository root: `/Users/vll/VLL/projects/local_buss_finder`;
- PostgreSQL/PostGIS для local/E2E собирается как native multi-arch image из pinned `postgres:17.11-trixie` и `ghcr.io/pglayers/pgx-postgis:17` manifests; это имеет приоритет над историческим `postgis/postgis:17-3.6`, который публикуется только для `amd64`;
- local/E2E object storage: `dxflrs/garage:v2.3.0`, single-node, private default bucket;
- application boundary остаётся provider-neutral через `S3_*` settings и boto3;
- production не использует bundled Garage автоматически: production S3 provider выбирается отдельно;
- Redis не хранит Celery task results; `CELERY_TASK_IGNORE_RESULT=True`, а продуктовый progress хранится только в PostgreSQL;
- Python Redis client закреплён на `redis==5.2.1`: это верхняя совместимая версия для `kombu[redis] 5.5.x`; Redis server остаётся на 7.4;
- общий development backend image имеет одного владельца сборки (`backend`); Celery services переиспользуют тот же image tag без собственного `build`, чтобы параллельный BuildKit export не конфликтовал;
- frontend manifest и lockfile создаются/проверяются в `node:24-bookworm-slim`, даже если host Node новее runtime baseline;
- frontend lint toolchain использует поддерживаемые `eslint==10.9.1` и `@eslint/js==10.0.1`; совместимые peer ranges остальных lint plugins проверены перед обновлением;
- MSW postinstall явно запрещён через `allowScripts`, поскольку первый срез использует Node handlers и не публикует browser service worker;
- root `.dockerignore` передаёт frontend build только `frontend/**` и `infrastructure/nginx/**`, исключая `.git`, `.env`, local `node_modules` и `dist`;
- development requirements lock компилируется с `--allow-unsafe --strip-extras`, чтобы transitive зависимости `pip-tools` (`pip`, `setuptools`) тоже имели exact versions и hashes и принимались `pip install --require-hashes`;
- корректный RED — запустившийся test с ожидаемым assertion failure. `ModuleNotFoundError`, `KeyError` и другие ошибки test harness сначала исправляются и не считаются подтверждённым RED;
- Task 1 использует services `postgres`, `redis`, `garage`, volumes `postgres_data`, `redis_data`, `garage_meta`, `garage_data` и `infrastructure/garage/garage.toml`; отдельные `minio-ready`/`minio-init` не создаются.

## Global Constraints

- Весь видимый UI, validation text и пользовательская документация — на русском; code names, API fields и error codes — на английском.
- Первый operational area — `Türkiye → Antalya → Alanya`, но ни один adapter или query не содержит программной проверки `city == "Alanya"`.
- `SourceRecord` и raw payload сохраняются до normalization; raw lineage не удаляется и не перезаписывается.
- Пустой пользовательский `category_ids` разворачивается в non-empty active mappings отдельно для каждого source; unbounded «все POI» request запрещён.
- PostgreSQL — единственный источник истины для campaign state и counters; Redis state не используется для UI progress.
- Общий порядок row locks: `DiscoveryCampaign → CampaignSourceRun → SourceRecord`.
- Celery messages содержат UUID, а не большие payload.
- Все unsafe HTTP methods защищены session auth + CSRF; JWT не добавляется.
- Runtime baseline: Python 3.13.x, Django 5.2.x LTS, PostgreSQL 17.x, PostGIS 3.6.x, Redis 7.4.x, Celery 5.5.x, Node 24.x LTS, React 19.2.x, Vite 8.x.
- Dependency graphs фиксируются `requirements/*.txt` и `package-lock.json`; floating `latest` не допускается в production artifacts.
- Обязательные extensions: `postgis`, `pg_trgm`, `unaccent`.
- Overture release фиксируется на старте source run; parser поддерживает `taxonomy.primary`/`basic_category` и fallback `categories.primary`.
- Public Overpass не является production dependency: `OVERPASS_URL` обязателен для live OSM run и должен указывать на согласованный self-hosted/paid endpoint.
- UI первого среза говорит «Найдено записей» и предупреждает, что дедупликация не выполнена.
- Не создавать и не реализовывать `deduplication`, canonical `Business`, `enrichment`, `crawling`, `audits`, `scoring`, `opportunities` или exports.
- Каждый behavioral change проходит подтверждённые RED → GREEN → REFACTOR; fixtures/config scaffolding допускаются до первого RED только как test harness без product behavior.

---

## 0. Как выполнять план

Репозиторий на момент написания плана не инициализирован как Git. Перед Task 1:

```bash
cd /Users/vll/VLL/projects/local_buss_finder
test -d .git || git init -b main
```

Для каждой задачи:

1. Не открывать код следующих задач.
2. Написать указанный test и назвать production regression, который он ловит.
3. Запустить test и проверить именно ожидаемую причину RED.
4. Написать минимальную реализацию.
5. Запустить targeted test, затем relevant suite.
6. Сделать refactor только на зелёном состоянии.
7. Выполнить ровно указанный commit либо разделить его только при реально независимых изменениях.

Основные команды после появления Makefile:

```bash
make up
make down
make backend-test
make backend-check
make frontend-test
make frontend-check
make storage-integration
make e2e
make verify
```

## 1. Карта файлов и границ

### Корень и infrastructure

```text
.env.example                         безопасный контракт environment
.editorconfig                        единые line endings/indentation
.gitignore                           secrets, caches, builds, local storage
Makefile                             короткие воспроизводимые команды
docker-compose.yml                   development stack
docker-compose.e2e.yml               test-only overrides/fake adapters
infrastructure/nginx/default.conf    same-origin React + /api proxy
tests/infra/test_compose_contract.py executable Compose contract
README.md                            русский local runbook
```

### Backend

```text
backend/config/settings/*                    dev/test/prod settings
backend/config/api_urls.py                   единый /api/v1 namespace
backend/config/celery.py                     broker, routes, queues
backend/common/models.py                     TimestampedUUIDModel
backend/common/json_types.py                 JSON type aliases
backend/common/observability.py              JSON events, allowlist/redaction
backend/common/celery_signals.py              worker correlation context
backend/apps/system/api/*                    health и session auth
backend/apps/system/middleware.py             correlation ID boundary
backend/apps/geography/*                     hierarchy, SearchArea, seed, API
backend/apps/sources/*                       Source, SourceRecord, raw storage, API
backend/apps/taxonomy/*                      categories/mappings, API
backend/apps/campaigns/*                     models, state machine, progress, API
backend/apps/discovery/domain.py             adapter value objects/protocol
backend/apps/discovery/errors.py             classified provider errors
backend/apps/discovery/registry.py           source code → adapter factory
backend/apps/discovery/adapters/overture.py  Overture integration/parser
backend/apps/discovery/adapters/osm.py       Overpass integration/parser
backend/apps/discovery/tasks.py              campaign/source orchestration
backend/apps/normalization/domain.py         normalized value objects
backend/apps/normalization/rules/*           pure Turkish normalization
backend/apps/normalization/services.py       raw → materialized normalized row
backend/apps/normalization/tasks.py          Celery entry point
backend/apps/businesses/api/*                read API over normalized records
backend/apps/system/management/commands/*    idempotent environment bootstrap
backend/tests/fixtures/sources/*              immutable provider fixtures
```

### Frontend

```text
frontend/src/api/client.ts                   credentials + CSRF + ApiError
frontend/src/app/router.tsx                  public/protected routes
frontend/src/app/providers.tsx               QueryClient/Auth provider
frontend/src/app/observability.ts             optional privacy-safe Sentry init
frontend/src/components/AppShell.tsx         русская navigation/layout
frontend/src/features/auth/*                 session/login/logout
frontend/src/features/dashboard/*            сводные показатели
frontend/src/features/campaigns/*            list/create/detail/progress
frontend/src/features/businesses/*           предварительная paginated таблица
frontend/src/shared/labels.ts                 enum → Russian labels
frontend/e2e/discovery-flow.spec.ts           browser acceptance
```

Route `/businesses` остаётся навигационным именем экрана «Бизнесы», но его queryset/type в этом срезе — только `NormalizedSourceRecord`; model `Business` не создаётся.

### 1.1. Единый контракт test harness

Чтобы шаги можно было выполнять буквально, общие fixtures не объявляются неявно. `backend/conftest.py` создаётся в Task 2 и расширяется только после появления соответствующих models:

```python
# Доступны с Task 2
@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner", password="correct-password", first_name="Владелец"
    )


@pytest.fixture
def auth_client(api_client, owner) -> APIClient:
    api_client.force_authenticate(owner)
    return api_client

# Добавляются в Task 7/8/9/10 соответственно.
# alanya_area: seed_reference_data, затем SearchArea.objects.get(name="Аланья — пилот")
# overture_source/osm_source: seed_sources, затем Source.objects.get(code=...)
# dentist_category: seed_taxonomy, затем BusinessCategory.objects.get(slug="dentist")
# active_source_without_mappings: active Source(code="fixture-empty") без mappings
# other_owner: User(username="other-owner") для ownership/404 tests
# alanya_campaign (и alias campaign): create_campaign(owner, Alanya, Overture+OSM, category_ids=())
# source_run: CampaignSourceRun.objects.get_or_create(alanya_campaign, osm_source)[0]
```

В Task 12 `backend/apps/sources/tests/fakes.py` определяет потокобезопасный `InMemoryRawPayloadStore`: он использует production `canonical_json_bytes`, `gzip.compress(..., mtime=0)`, dual-digest key (`external_id_sha256` + `payload_sha256`) и защищённый `threading.Lock` словарь. Его `put_json` возвращает настоящий `StoredPayload`, `get_json` декодирует сохранённый gzip, а `object_count` считает keys. Fixtures `store` и `thread_safe_store` создают новый instance на каждый test; `payload` всегда имеет `external_id="node/42"`, fixed UTC `fetched_at` и dataset `fixture-2026-09`; `parsed` имеет тот же ID, имя `"Alanya Diş"`, координаты внутри AOI и tuple/dict contact fields. Так concurrency tests не делят mutable state.

В Task 11 integration fixture `minio_store` добавляется именно в root `backend/conftest.py`, а не в sibling app `conftest.py`: тогда она доступна и storage integration tests, и pipeline tests из `apps/discovery/tests/integration/`. Unit-only `fake_s3_client` остаётся в `backend/apps/sources/tests/conftest.py`.

В Task 22 существующий `backend/apps/discovery/tests/conftest.py` расширяется `FixtureAdapterRegistry`:

```python
@dataclass(frozen=True)
class FixtureAdapterRegistry:
    factories: Mapping[str, Callable[[], DiscoveryAdapter]]

    def get(self, source_code: str) -> DiscoveryAdapter:
        return self.factories[source_code]()


@pytest.fixture
def fixture_adapter_registry() -> FixtureAdapterRegistry:
    return FixtureAdapterRegistry(
        {"overture": FixtureOvertureAdapter, "osm": FixtureOsmAdapter}
    )
```

`frontend/src/test/render.tsx` создаётся в Task 6 и является единственной точкой render setup:

```tsx
const OWNER: AuthUser = { id: 1, username: 'owner', display_name: 'Владелец' };

function sessionHandler(user: AuthUser | null) {
  return http.get('/api/v1/auth/session/', () =>
    user
      ? HttpResponse.json(user)
      : HttpResponse.json(
          { error: { code: 'NOT_AUTHENTICATED', detail: 'Требуется вход.', fields: {} } },
          { status: 403 },
        ),
  );
}

function renderAt(path: string, user: AuthUser | null) {
  server.use(sessionHandler(user));
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return { user: userEvent.setup(), ...render(<AppProviders><RouterProvider router={router} /></AppProviders>) };
}

export const renderApp = (path: string) => renderAt(path, null);
export const renderAuthenticatedApp = (path: string) => renderAt(path, OWNER);
```

Каждый frontend test получает `const { user } = renderApp(...)` или `renderAuthenticatedApp(...)`; test с fake timers создаёт `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`. `frontend/src/test/handlers.ts` экспортирует именованные handlers (`invalidCredentialsHandler`, `campaignCreateErrorHandler`, `businessesEmptyHandler`, `businessesServerErrorHandler`) и default happy-path handlers; `setup.ts` делает `server.listen({ onUnhandledRequest: 'error' })`, `server.resetHandlers()` после каждого test и `server.close()` после suite. Новые endpoint handlers добавляются в том же Task, что и consuming feature.

---

### Task 1: Инициализировать repository contract и stateful infrastructure

**Files:**
- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `.env.example`
- Create: `Makefile`
- Create: `docker-compose.yml`
- Create: `docker-compose.e2e.yml`
- Create: `tests/infra/test_compose_contract.py`
- Create: `infrastructure/postgres/Dockerfile`
- Create: `infrastructure/postgres/init/010-extensions.sql`
- Create: `infrastructure/garage/garage.toml`
- Create: `storage/.gitkeep`
- Create: `README.md`

**Interfaces:**
- Consumes: Docker Engine с Compose `>=2.24.0` (нужны override tags `!reset`/`!override` в E2E); design spec из header.
- Produces: services `postgres`, `redis`, `garage`; named volumes `postgres_data`, `redis_data`, `garage_meta`, `garage_data`; shared network `app`; reusable `x-backend-environment`/`x-backend-depends-on` contract.

- [x] **Step 1: Создать executable contract test до Compose файла**

```python
# tests/infra/test_compose_contract.py
import json
import subprocess
import unittest


class ComposeContractTest(unittest.TestCase):
    def load_config(self) -> dict:
        result = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_stateful_services_are_declared_and_isolated(self) -> None:
        config = self.load_config()
        services = config["services"]
        required = {"postgres", "redis", "minio", "minio-ready", "minio-init"}
        self.assertTrue(required.issubset(services))
        self.assertIn("postgis/postgis:17-3.6", services["postgres"]["image"])
        self.assertIn("redis:7.4", services["redis"]["image"])
        self.assertIn("curlimages/curl", services["minio-ready"]["image"])
        self.assertIn("/minio/health/live", services["minio-ready"]["command"][-1])
        for name in ("postgres", "redis", "minio"):
            for port in services[name].get("ports", []):
                self.assertEqual("127.0.0.1", port.get("host_ip"))


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Запустить test и подтвердить RED из-за отсутствующего Compose**

Run:

```bash
python3 -m unittest tests/infra/test_compose_contract.py -v
```

Expected: ERROR/FAIL, `no configuration file provided` или отсутствие ожидаемых services. Это допустимый RED для executable infrastructure contract.

- [x] **Step 3: Создать минимальный Compose и environment contract**

`docker-compose.yml` должен использовать Compose Specification без legacy `version:` и содержать:

```yaml
name: local-business-intelligence

x-backend-environment: &backend-environment
  DJANGO_SETTINGS_MODULE: ${DJANGO_SETTINGS_MODULE:-config.settings.development}
  DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY:-unsafe-dev-only-change-me}
  DJANGO_ALLOWED_HOSTS: ${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1,backend}
  DATABASE_URL: postgis://${POSTGRES_USER:-lbi}:${POSTGRES_PASSWORD:-lbi-dev-only}@postgres:5432/${POSTGRES_DB:-local_business_intelligence}
  REDIS_URL: redis://redis:6379/0
  CELERY_BROKER_URL: redis://redis:6379/0
  CELERY_TASK_IGNORE_RESULT: "true"
  S3_ENDPOINT_URL: http://minio:9000
  S3_ACCESS_KEY_ID: ${S3_ACCESS_KEY_ID:-minioadmin}
  S3_SECRET_ACCESS_KEY: ${S3_SECRET_ACCESS_KEY:-minioadmin}
  S3_BUCKET_NAME: ${S3_BUCKET_NAME:-local-business-intelligence}
  S3_REGION_NAME: ${S3_REGION_NAME:-us-east-1}
  OVERPASS_URL: ${OVERPASS_URL:-}
  OSM_DATASET_VERSION: ${OSM_DATASET_VERSION:-}
  SOURCE_USER_AGENT: "${SOURCE_USER_AGENT:-local-business-intelligence/0.1 (+https://example.invalid/contact)}"
  SENTRY_DSN: ${SENTRY_DSN:-}

x-backend-depends-on: &backend-depends-on
  postgres: {condition: service_healthy}
  redis: {condition: service_healthy}
  minio-init: {condition: service_completed_successfully}

services:
  postgres:
    image: postgis/postgis:17-3.6
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-local_business_intelligence}
      POSTGRES_USER: ${POSTGRES_USER:-lbi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lbi-dev-only}
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks: [app]

  redis:
    image: redis:7.4-alpine
    command: ["redis-server", "--appendonly", "yes"]
    ports:
      - "127.0.0.1:${REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - redis_data:/data
    networks: [app]

  minio:
    image: ${MINIO_IMAGE}
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY_ID:-minioadmin}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_ACCESS_KEY:-minioadmin}
    ports:
      - "127.0.0.1:${MINIO_API_PORT:-9000}:9000"
      - "127.0.0.1:${MINIO_CONSOLE_PORT:-9001}:9001"
    volumes:
      - minio_data:/data
    networks: [app]

  minio-ready:
    image: curlimages/curl:8.12.1
    depends_on:
      minio:
        condition: service_started
    command:
      - /bin/sh
      - -ec
      - 'until curl --fail --silent --show-error http://minio:9000/minio/health/live; do sleep 1; done'
    restart: "no"
    networks: [app]

  minio-init:
    image: ${MINIO_MC_IMAGE}
    depends_on:
      minio-ready:
        condition: service_completed_successfully
    entrypoint: ["/bin/sh", "-c"]
    command:
      - >-
        mc alias set local http://minio:9000 "$${S3_ACCESS_KEY_ID}" "$${S3_SECRET_ACCESS_KEY}" &&
        mc mb --ignore-existing "local/$${S3_BUCKET_NAME}" &&
        mc anonymous set none "local/$${S3_BUCKET_NAME}" &&
        mc ls "local/$${S3_BUCKET_NAME}"
    environment:
      S3_ACCESS_KEY_ID: ${S3_ACCESS_KEY_ID:-minioadmin}
      S3_SECRET_ACCESS_KEY: ${S3_SECRET_ACCESS_KEY:-minioadmin}
      S3_BUCKET_NAME: ${S3_BUCKET_NAME:-local-business-intelligence}
    networks: [app]

networks:
  app: {}

volumes:
  postgres_data: {}
  redis_data: {}
  minio_data: {}
```

Начальная версия `docker-compose.e2e.yml` отключает host ports у stateful services. Начиная с Task 11 этот override используется только с отдельным project name; Task 22 расширит его test-only credentials, application services и fixture adapters:

```yaml
services:
  postgres:
    ports: !reset []
  redis:
    ports: !reset []
  minio:
    ports: !reset []
```

В `.env.example` зафиксировать проверенные immutable release tags:

```dotenv
MINIO_IMAGE=minio/minio:RELEASE.2025-09-07T16-13-09Z
MINIO_MC_IMAGE=minio/mc:RELEASE.2025-08-13T08-35-41Z
DJANGO_SECRET_KEY=unsafe-dev-only-change-me
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend
POSTGRES_DB=local_business_intelligence
POSTGRES_USER=lbi
POSTGRES_PASSWORD=lbi-dev-only
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=local-business-intelligence
OVERPASS_URL=
OSM_DATASET_VERSION=
SOURCE_USER_AGENT=local-business-intelligence/0.1 (+https://example.invalid/contact)
SENTRY_DSN=
```

- [x] **Step 4: Запустить contract и health smoke**

Run:

```bash
cp .env.example .env
docker compose version --short
python3 -m unittest tests/infra/test_compose_contract.py -v
docker compose up -d postgres redis minio minio-init
docker compose ps -a
```

Expected: Compose version `>=2.24.0`; unittest PASS; `postgres` и `redis` healthy; `minio-ready` и `minio-init` exit `0`; `mc ls local/$S3_BUCKET_NAME` внутри `minio-init` succeeds. `minio` server image не использует `mc`/`curl` healthcheck.

- [x] **Step 5: Добавить Make targets и русский runbook**

`Makefile` обязан иметь commands без скрытой очистки volumes:

```make
up:
	docker compose up -d --build

down:
	docker compose down

infra-up:
	docker compose up -d postgres redis minio minio-init
```

README описывает Docker Compose `>=2.24.0`, `docker compose version --short`, `cp .env.example .env`, `make up`, адреса UI/API/MinIO console и подчёркивает, что `docker compose down -v` удаляет local data и не входит в обычный workflow.

- [x] **Step 6: Commit**

```bash
git add .editorconfig .gitignore .env.example Makefile README.md docker-compose.yml docker-compose.e2e.yml tests/infra storage/.gitkeep docs/superpowers
git commit -m "chore: initialize local business intelligence foundation"
```

---

### Task 2: Поднять Django/DRF foundation и health API

**Files:**
- Create: `backend/manage.py`
- Create: `backend/pyproject.toml`
- Create: `backend/requirements/base.in`
- Create: `backend/requirements/development.in`
- Create: `backend/requirements/production.in`
- Create: `backend/requirements/base.txt`
- Create: `backend/requirements/development.txt`
- Create: `backend/requirements/production.txt`
- Create: `backend/Dockerfile`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings/__init__.py`
- Create: `backend/config/settings/base.py`
- Create: `backend/config/settings/development.py`
- Create: `backend/config/settings/testing.py`
- Create: `backend/config/settings/production.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/api_urls.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/common/models.py`
- Create: `backend/apps/system/apps.py`
- Create: `backend/apps/system/api/urls.py`
- Create: `backend/apps/system/api/views.py`
- Create: `backend/apps/system/tests/test_health_api.py`
- Create: `backend/conftest.py`
- Modify: `docker-compose.yml`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `DATABASE_URL`, `REDIS_URL`, `S3_*`, stateful Compose services.
- Produces: `GET /api/v1/health/live/ -> {"status":"ok"}`; `GET /api/v1/health/ready/ -> 200|503` with `database`, `redis`, `object_storage`; abstract `TimestampedUUIDModel`.

- [x] **Step 1: Создать только dependency/test harness**

`backend/requirements/base.in`:

```text
Django==5.2.17
djangorestframework==3.16.1
psycopg[binary]==3.3.5
django-environ==0.14.0
django-cors-headers==4.9.0
boto3==1.43.73
redis==5.2.1
gunicorn==23.0.0
```

`backend/requirements/development.in`:

```text
-r base.in
pytest==9.1.1
pytest-django==4.14.0
pytest-cov==7.1.0
ruff==0.16.6
pip-tools==7.6.1
respx==0.23.1
moto[s3]==5.2.3
freezegun==1.5.5
```

`backend/requirements/production.in` содержит только `-r base.in`. Все direct dependencies exact-pinned; transitive dependencies фиксируются hashes в трёх committed lockfiles. Locks компилируются в Linux/Python 3.13, то есть в той же platform family, что и image:

```bash
docker run --rm -v "$PWD/backend:/app" -w /app python:3.13-slim \
  sh -ec "pip install pip-tools==7.6.1 && \
    pip-compile --allow-unsafe --strip-extras --generate-hashes --resolver=backtracking --output-file requirements/base.txt requirements/base.in && \
    pip-compile --allow-unsafe --strip-extras --generate-hashes --resolver=backtracking --output-file requirements/development.txt requirements/development.in && \
    pip-compile --allow-unsafe --strip-extras --generate-hashes --resolver=backtracking --output-file requirements/production.txt requirements/production.in"
```

Каждый следующий Task, который меняет любой `.in`, повторяет все три `pip-compile` commands из этого шага; CI отклоняет diff, где `.in` изменился без соответствующего `.txt`.

`backend/pyproject.toml` sets pytest `addopts = ["--ds=config.settings.testing"]` (CLI option намеренно имеет приоритет над Compose `DJANGO_SETTINGS_MODULE=config.settings.development`), `python_files = ["test_*.py"]`, marker `integration = "requires isolated real Redis/Garage/PostGIS"`, Ruff target `py313`, line length `100`. Regression test asserts `os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.testing"`, чтобы tests никогда не использовали development/production config случайно.

Создать test harness image до первого RED. `backend/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
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
```

Одновременно добавить Compose harness (он ещё не содержит product URL behavior):

```yaml
  backend:
    build:
      context: ./backend
      target: development
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
    environment: *backend-environment
    depends_on: *backend-depends-on
    volumes:
      - ./backend:/app
    ports:
      - "127.0.0.1:${BACKEND_PORT:-8000}:8000"
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live/', timeout=2)"
      interval: 5s
      timeout: 3s
      retries: 20
    networks: [app]
```

- [x] **Step 2: Написать failing health tests**

```python
# backend/apps/system/tests/test_health_api.py
import pytest

from apps.system.api import views


@pytest.mark.django_db
def test_live_health_does_not_require_auth(api_client):
    response = api_client.get("/api/v1/health/live/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_health_reports_dependency_state(api_client):
    response = api_client.get("/api/v1/health/ready/")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "object_storage": "ok"},
    }


@pytest.mark.django_db
def test_ready_health_returns_503_without_exception_details(api_client, monkeypatch):
    def unavailable_redis() -> None:
        raise ConnectionError("redis://user:secret@redis:6379/0")

    monkeypatch.setattr(views, "check_redis", unavailable_redis)
    response = api_client.get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "ok", "redis": "error", "object_storage": "ok"},
    }
    assert "secret" not in response.content.decode()
```

Добавить первые `api_client`, `owner` и `auth_client` fixtures из §1.1 в `backend/conftest.py`.

- [x] **Step 3: Запустить RED**

Run:

```bash
docker compose build backend
docker compose run --rm backend pytest apps/system/tests/test_health_api.py -q
```

Expected: три assertion failures `404`, потому что health URLs ещё отсутствуют; imports и test harness при этом исправны.

- [x] **Step 4: Реализовать settings, URL namespace и health behavior**

`base.py` использует:

```python
DATABASES = {
    "default": env.db("DATABASE_URL", engine="django.contrib.gis.db.backends.postgis")
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_TZ = True
```

`LiveHealthView` uses `AllowAny`. Module-level functions `check_database() -> None`, `check_redis() -> None` и `check_object_storage() -> None` выполняют соответственно `SELECT 1`, `cache.set/get`, `head_bucket`. `ReadyHealthView` вызывает все три checks, maps success/exception только в `"ok"`/`"error"`, выполняет остальные checks даже после одной ошибки, возвращает 503 if any dependency fails и никогда не возвращает credentials/exception detail.

`common/models.py`:

```python
class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

- [x] **Step 5: Проверить GREEN на development image**

Backend service уже создан как test harness в Step 1; после реализации URL он должен пройти healthcheck без изменения container contract.

Run:

```bash
docker compose run --rm backend pytest apps/system/tests/test_health_api.py -q
docker compose run --rm backend ruff check .
docker compose run --rm backend python manage.py check
```

Expected: tests PASS, Ruff exit 0, Django system check reports no issues.

- [x] **Step 6: Commit**

```bash
git add backend docker-compose.yml Makefile
git commit -m "feat: add Django REST foundation and health checks"
```

---

### Task 3: Настроить Celery/Redis и отдельные очереди

**Files:**
- Create: `backend/config/celery.py`
- Create: `backend/apps/system/tasks.py`
- Create: `backend/apps/system/tests/test_celery_config.py`
- Modify: `backend/config/__init__.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/requirements/base.in`
- Modify: `backend/requirements/base.txt`
- Modify: `backend/requirements/development.txt`
- Modify: `backend/requirements/production.txt`
- Modify: `docker-compose.yml`
- Modify: `tests/infra/test_compose_contract.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `CELERY_BROKER_URL`, `CELERY_TASK_IGNORE_RESULT`.
- Produces: Celery app `config.celery.app`; queues `discovery`, `normalization`; deterministic route patterns for future task names.

- [x] **Step 1: Написать failing Celery configuration test**

```python
# backend/apps/system/tests/test_celery_config.py
from config.celery import app


def test_pipeline_tasks_are_routed_to_separate_queues():
    routes = app.conf.task_routes
    assert routes is not None
    assert routes["apps.discovery.tasks.*"]["queue"] == "discovery"
    assert routes["apps.normalization.tasks.*"]["queue"] == "normalization"
    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_track_started is True
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_publish_retry is True
    assert app.conf.task_publish_retry_policy["max_retries"] == 3


def test_celery_uses_redis_only_as_broker():
    assert app.conf.broker_url == "redis://redis:6379/0"
    assert app.conf.task_ignore_result is True
    assert app.conf.result_backend is None
```

- [x] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/system/tests/test_celery_config.py -q
```

Expected: FAIL только на assertions об отсутствующих routes и `task_ignore_result=False`; import/test harness уже работоспособны.

- [x] **Step 3: Реализовать minimal Celery app**

Добавить `celery[redis]==5.5.3`, закрепить совместимый `redis==5.2.1` в `base.in` и перекомпилировать все три lockfiles exact commands из Task 2. `config/celery.py`:

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("local_business_intelligence")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

В `base.py`:

```python
CELERY_TASK_ROUTES = {
    "apps.discovery.tasks.*": {"queue": "discovery"},
    "apps.normalization.tasks.*": {"queue": "normalization"},
}
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_PUBLISH_RETRY = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=env("REDIS_URL"))
CELERY_TASK_IGNORE_RESULT = env.bool("CELERY_TASK_IGNORE_RESULT", default=True)
CELERY_RESULT_BACKEND = None
```

Publish retry сначала делает три короткие broker attempts. Если публикация `self.retry` всё равно невозможна, wrapper Task 17 явно поднимает `Reject(..., requeue=True)`; глобально переопределять ACK семантику обычных failures не нужно. Идемпотентная reservation не списывает business retry budget повторно при redelivery.

- [x] **Step 4: Добавить worker services без будущих queues**

```yaml
  celery-discovery:
    image: local-business-intelligence/backend:development
    hostname: celery-discovery
    command: celery -A config worker -Q discovery -l INFO --concurrency=1 --hostname=discovery@%h
    environment: *backend-environment
    depends_on: *backend-depends-on
    volumes: ["./backend:/app"]
    networks: [app]
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import os; from config.celery import app;
          name='discovery@'+os.environ['HOSTNAME'];
          data=app.control.inspect(destination=[name], timeout=2).active_queues() or {};
          assert {queue['name'] for queue in data.get(name, [])} == {'discovery'}
      interval: 2s
      timeout: 4s
      retries: 30
      start_period: 5s

  celery-normalization:
    image: local-business-intelligence/backend:development
    hostname: celery-normalization
    command: celery -A config worker -Q normalization -l INFO --concurrency=2 --hostname=normalization@%h
    environment: *backend-environment
    depends_on: *backend-depends-on
    volumes: ["./backend:/app"]
    networks: [app]
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import os; from config.celery import app;
          name='normalization@'+os.environ['HOSTNAME'];
          data=app.control.inspect(destination=[name], timeout=2).active_queues() or {};
          assert {queue['name'] for queue in data.get(name, [])} == {'normalization'}
      interval: 2s
      timeout: 4s
      retries: 30
      start_period: 5s
```

`backend` единолично содержит `build: *backend-build` и публикует `local-business-intelligence/backend:development`; оба worker services только переиспользуют этот image tag. `x-backend-environment` и `x-backend-depends-on` определены в Task 1 и используются без локальных копий в `backend`, `celery-discovery` и `celery-normalization`; все три процесса получают одинаковые `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` и `S3_REGION_NAME`. Не создавать workers для deduplication/enrichment/crawling/audit/scoring.

Healthcheck не ограничивается живым container process: targeted `active_queues()` обязан увидеть worker с ожидаемым именем и нужной queue. Расширить Compose contract test:

```python
def test_celery_workers_become_healthy_only_with_expected_queue(self) -> None:
    services = self.load_config()["services"]
    for service_name, queue_name in (
        ("celery-discovery", "discovery"),
        ("celery-normalization", "normalization"),
    ):
        self.assertIn(service_name, services)
        service = services[service_name]
        self.assertEqual(services["backend"]["image"], service["image"])
        self.assertNotIn("build", service)
        self.assertEqual("true", service["environment"]["CELERY_TASK_IGNORE_RESULT"])
        self.assertNotIn("CELERY_RESULT_BACKEND", service["environment"])
        command = service["command"]
        command_text = command if isinstance(command, str) else " ".join(command)
        self.assertIn(f"--hostname={queue_name}@%h", command_text)
        healthcheck = " ".join(service["healthcheck"]["test"])
        self.assertIn("active_queues", healthcheck)
        self.assertIn(f"== {{'{queue_name}'}}", healthcheck)
```

- [x] **Step 5: Проверить GREEN и worker connectivity**

```bash
docker compose build backend celery-discovery celery-normalization
docker compose run --rm backend pytest apps/system/tests/test_celery_config.py -q
python3 -m unittest tests/infra/test_compose_contract.py -v
docker compose up -d --wait --wait-timeout 90 redis celery-discovery celery-normalization
docker compose exec celery-discovery celery -A config inspect active_queues -d discovery@celery-discovery
docker compose exec celery-normalization celery -A config inspect active_queues -d normalization@celery-normalization
```

Expected: tests PASS; Compose ждёт healthcheck, и каждый targeted worker показывает только свою queue.

- [x] **Step 6: Commit**

```bash
git add backend docker-compose.yml tests/infra/test_compose_contract.py Makefile
git commit -m "feat: configure Celery discovery and normalization queues"
```

---

### Task 4: Создать React/Vite foundation и production proxy

**Files:**
- Create: `.dockerignore`
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/eslint.config.js`
- Create: `frontend/index.html`
- Create: `frontend/Dockerfile`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/App.test.tsx`
- Create: `frontend/src/app/providers.tsx`
- Create: `frontend/src/app/providers.test.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/styles/global.css`
- Create: `infrastructure/nginx/default.conf`
- Modify: `docker-compose.yml`
- Modify: `tests/infra/test_compose_contract.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `/api` same-origin proxy to `backend:8000`; Node 24.
- Produces: Vite app on dev port 5173, nginx on 8080, `AppProviders`, Vitest harness.

- [x] **Step 1: Создать frontend test harness и install locked dependencies**

```bash
mkdir -p frontend
cd frontend
npm init -y
npm install --save-exact react@19.2.8 react-dom@19.2.8 react-router-dom@7.18.3 \
  @tanstack/react-query@5.102.2 @tanstack/react-table@8.21.3 \
  react-hook-form@7.87.0 zod@4.5.4 @hookform/resolvers@5.9.1
npm install --save-dev --save-exact vite@8.2.2 @vitejs/plugin-react@6.1.0 \
  typescript@5.9.3 @types/node@24.1.0 @types/react@19.2.18 \
  @types/react-dom@19.2.5 vitest@5.0.0 jsdom@30.0.1 \
  @testing-library/react@16.3.2 @testing-library/dom@10.4.1 \
  @testing-library/jest-dom@7.0.1 @testing-library/user-event@14.6.7 \
  eslint@10.9.1 @eslint/js@10.0.1 globals@17.11.0 typescript-eslint@8.67.0 \
  eslint-plugin-react-hooks@7.1.1 eslint-plugin-react-refresh@0.5.5 \
  msw@2.15.0 @playwright/test@1.62.1
cd ..
```

`--save-exact` записывает versions без `^`/`~`; commit `package-lock.json`. `package.json` scripts задаются буквально:

```json
{
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "npm run typecheck && vite build",
    "test": "vitest",
    "test:run": "vitest run",
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --project tsconfig.app.json --noEmit --pretty false && tsc --project tsconfig.node.json --noEmit --pretty false",
    "test:e2e": "playwright test"
  }
}
```

`package.json` также содержит `"allowScripts": {"msw": false}`: MSW postinstall копирует browser worker только при настроенном `msw.workerDirectory`, которого в этом срезе нет.

`typecheck` намеренно проверяет оба config напрямую, поэтому `tsconfig.app.json` и `tsconfig.node.json` не обязаны быть composite projects; root `references` остаются для IDE и явного разделения browser/Node environments. Task 4 обязан реально выполнить `npm run typecheck` и `npm run build`, а не только проверить JSON configs.

`frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

`frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "incremental": true,
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`frontend/tsconfig.node.json` включает текущий Vite config и будущий Playwright config через узкий pattern:

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "incremental": true,
    "target": "ES2023",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "resolveJsonModule": true,
    "noEmit": true,
    "strict": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["*.config.ts"]
}
```

`frontend/eslint.config.js` использует ESLint 9 flat config; browser globals разрешены только product/tests, Node globals — только tool configs и E2E:

```js
import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'playwright-report', 'test-results'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
  },
  {
    files: ['*.config.ts', 'e2e/**/*.ts'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.node,
    },
  },
);
```

Первый frontend test уже должен запускаться в browser-like environment. `frontend/vite.config.ts` задаётся буквально:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: false },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    clearMocks: true,
    css: true,
  },
});
```

Начальное содержимое `frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => cleanup());
```

- [x] **Step 2: Написать failing Russian shell test**

```tsx
// frontend/src/app/App.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';

describe('App', () => {
  it('показывает русское название продукта', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Локальные бизнесы' })).toBeInTheDocument();
  });
});
```

- [x] **Step 3: Запустить RED**

```bash
cd frontend
npm run test:run -- src/app/App.test.tsx
```

Expected: FAIL только на assertion: доступный heading `Локальные бизнесы` отсутствует; import/test harness уже работоспособны.

- [x] **Step 4: Реализовать минимальный App и providers**

```tsx
// frontend/src/app/App.tsx
export function App() {
  return (
    <main>
      <h1>Локальные бизнесы</h1>
    </main>
  );
}
```

`AppProviders` создаёт один `QueryClient` с `retry: false` в tests и `retry: 2` в production, затем предоставляет `BrowserRouter`. Отдельный test читает реальные default options через `useQueryClient` и фиксирует детерминированный test policy. `main.tsx` монтирует `App` в `#root`.

- [x] **Step 5: Добавить Dockerfile, Vite proxy и nginx**

`vite.config.ts` уже содержит exact dev proxy `/api` → `http://backend:8000` из Step 1. `default.conf`:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header X-Correlation-ID $request_id;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

`frontend/Dockerfile` использует root build context, чтобы production stage получил nginx config:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS development
COPY frontend/ ./
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM dependencies AS build
ARG VITE_SENTRY_DSN=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS production
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
```

Корневой `.dockerignore` использует allowlist для `frontend/**` и `infrastructure/nginx/**`, после чего повторно исключает `frontend/node_modules/` и `frontend/dist/`; секреты и локальные артефакты не попадают в build context.

Exact development/static services:

```yaml
  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
      target: development
    command: npm run dev -- --host 0.0.0.0
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    ports:
      - "127.0.0.1:${FRONTEND_PORT:-5173}:5173"
    networks: [app]

  nginx:
    build:
      context: .
      dockerfile: frontend/Dockerfile
      target: production
    depends_on:
      backend: {condition: service_healthy}
    ports:
      - "127.0.0.1:${NGINX_PORT:-8080}:80"
    networks: [app]

volumes:
  frontend_node_modules: {}
```

Слить новый volume с уже существующим root `volumes:` block, не создавать второй YAML key.

Расширить `required` в infra test через `required.update({"backend", "celery-discovery", "celery-normalization", "frontend", "nginx"})`; проверка по-прежнему использует `required.issubset(services)`, поэтому последующие test-only services не делают contract test хрупким.

Добавить exact Make targets после появления обоих toolchains:

```make
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
```

`frontend-install` синхронизирует существующий named volume `frontend_node_modules` после изменения lockfile; обычная пересборка image не перезаписывает уже созданный Docker volume.

- [x] **Step 6: Проверить GREEN, typecheck и production build**

```bash
cd frontend
npm run test:run -- src/app/App.test.tsx
npm run lint
npm run typecheck
npm run build
cd ..
python3 -m unittest tests/infra/test_compose_contract.py -v
docker compose build frontend nginx
```

Expected: все commands exit 0; build создаёт `frontend/dist` внутри build stage.

- [x] **Step 7: Commit**

```bash
git add frontend infrastructure/nginx docker-compose.yml tests/infra Makefile
git commit -m "feat: add React Vite application shell"
```

---

### Task 5: Реализовать session authentication API и единый error envelope

**Files:**
- Create: `backend/apps/system/api/auth_serializers.py`
- Create: `backend/apps/system/api/auth_views.py`
- Create: `backend/apps/system/api/exceptions.py`
- Create: `backend/apps/system/tests/test_auth_api.py`
- Create: `backend/apps/system/tests/test_api_errors.py`
- Modify: `backend/apps/system/api/urls.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/settings/development.py`
- Modify: `backend/config/settings/production.py`

**Interfaces:**
- Consumes: Django `User`, session middleware, CSRF middleware.
- Produces: `GET /auth/csrf/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/session/`; `UserResponse`; `ApiErrorResponse`.

```python
class UserResponse(TypedDict):
    id: int
    username: str
    display_name: str


class ApiErrorBody(TypedDict):
    code: str
    detail: str
    fields: dict[str, list[str]]


class ApiException(APIException):
    def __init__(
        self, code: str, detail: str, *, status_code: int = 400,
        fields: dict[str, list[str]] | None = None
    ) -> None: ...
```

- [x] **Step 1: Написать failing API tests**

```python
# backend/apps/system/tests/test_auth_api.py
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_creates_session_and_session_endpoint_returns_user(api_client):
    get_user_model().objects.create_user(
        username="owner", password="correct-password", first_name="Владелец"
    )
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "username": "owner",
        "display_name": "Владелец",
    }
    assert api_client.get("/api/v1/auth/session/").status_code == 200


@pytest.mark.django_db
def test_invalid_login_uses_stable_english_code_and_russian_detail(api_client):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "wrong"},
        format="json",
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "detail": "Неверное имя пользователя или пароль.",
            "fields": {},
        }
    }


@pytest.mark.django_db
def test_session_endpoint_rejects_anonymous_user(api_client):
    response = api_client.get("/api/v1/auth/session/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_login_requires_csrf_cookie_and_matching_header():
    client = APIClient(enforce_csrf_checks=True)
    get_user_model().objects.create_user(username="owner", password="correct-password")
    rejected = client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
    )
    assert rejected.status_code == 403
    assert client.get("/api/v1/auth/csrf/").status_code == 200
    token = client.cookies["csrftoken"].value
    accepted = client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert accepted.status_code == 200
```

Дополнительные tests фиксируют `POST /auth/logout/` → `204` с очисткой session, обязательный CSRF для authenticated logout, единый envelope для serializer validation/405 и одинаковое отображение DRF/Django вариантов `NotFound`/`PermissionDenied`.

- [x] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/system/tests/test_auth_api.py apps/system/tests/test_api_errors.py -q
```

Expected: FAIL с 404 и отсутствующим custom exception handler.

- [x] **Step 3: Реализовать views и exception handler**

Поведение:

```python
@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie установлена."})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            raise ApiException("INVALID_CREDENTIALS", "Неверное имя пользователя или пароль.")
        login(request, user)
        return Response(serialize_user(user))
```

Импортировать `csrf_protect` из `django.views.decorators.csrf`. `LoginView.dispatch` обёрнут `csrf_protect`, потому что DRF `SessionAuthentication` не применяет CSRF к anonymous login самостоятельно. Logout вызывает Django `logout()` и возвращает 204. `SessionView` использует `IsAuthenticated`. Exception handler преобразует DRF auth/validation errors в единый envelope, одинаково классифицирует Django и DRF `Http404`/`PermissionDenied` и не меняет HTTP semantics.

- [x] **Step 4: Зафиксировать cookie/CSRF settings**

В `base.py` добавить `"corsheaders"` в `INSTALLED_APPS` и `"corsheaders.middleware.CorsMiddleware"` в `MIDDLEWARE` непосредственно перед `"django.middleware.common.CommonMiddleware"`; без middleware значения `CORS_*` не применяются.

В `development.py` зафиксировать exact settings:

```python
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:8080"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://localhost:8080"]
```

В `production.py` установить `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `CSRF_COOKIE_SAMESITE="Lax"`, `CORS_ALLOW_CREDENTIALS=True`; `CORS_ALLOWED_ORIGINS=env.list("DJANGO_CORS_ALLOWED_ORIGINS")` и `CSRF_TRUSTED_ORIGINS=env.list("DJANGO_CSRF_TRUSTED_ORIGINS")`. Не включать `CORS_ALLOW_ALL_ORIGINS`.

- [x] **Step 5: Проверить GREEN и CSRF integration**

```bash
docker compose run --rm backend pytest apps/system/tests/test_auth_api.py apps/system/tests/test_api_errors.py -q
docker compose run --rm backend pytest apps/system/tests -q
docker compose run --rm backend ruff check apps/system config
```

Expected: all PASS/exit 0; тест выше фиксирует login без CSRF → 403 и login после `GET /csrf/` с matching header → 200.

- [x] **Step 6: Commit**

```bash
git add backend/apps/system backend/config/settings
git commit -m "feat: add session authentication API"
```

---

### Task 6: Сделать русскую форму входа и protected app shell

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/errors.ts`
- Create: `frontend/src/features/auth/types.ts`
- Create: `frontend/src/features/auth/api.ts`
- Create: `frontend/src/features/auth/AuthProvider.tsx`
- Create: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/features/auth/LoginPage.test.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/app/router.tsx`
- Create: `frontend/src/test/server.ts`
- Create: `frontend/src/test/handlers.ts`
- Create: `frontend/src/test/render.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/providers.tsx`
- Modify: `frontend/src/test/setup.ts`

**Interfaces:**
- Consumes: Task 5 auth endpoints/error envelope.
- Produces:

```ts
export type AuthUser = { id: number; username: string; display_name: string };
export type ApiErrorBody = {
  error: { code: string; detail: string; fields: Record<string, string[]> };
};

export async function getSession(): Promise<AuthUser>;
export async function login(input: { username: string; password: string }): Promise<AuthUser>;
export async function logout(): Promise<void>;
```

- [x] **Step 1: Написать failing behavior tests**

Сначала создать MSW server/default handlers как test harness и заменить `frontend/src/test/setup.ts` на exact lifecycle; это test infrastructure, а не product behavior:

```ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
```

```tsx
// frontend/src/features/auth/LoginPage.test.tsx
it('входит и перенаправляет на обзор', async () => {
  const { user } = renderApp('/login');
  await user.type(screen.getByLabelText('Имя пользователя'), 'owner');
  await user.type(screen.getByLabelText('Пароль'), 'correct-password');
  await user.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByRole('heading', { name: 'Обзор' })).toBeInTheDocument();
});

it('показывает русскую ошибку API', async () => {
  server.use(invalidCredentialsHandler);
  const { user } = renderApp('/login');
  await user.type(screen.getByLabelText('Имя пользователя'), 'owner');
  await user.type(screen.getByLabelText('Пароль'), 'wrong');
  await user.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Неверное имя пользователя или пароль.',
  );
});
```

```tsx
it('защищает корневой route и показывает shell только после входа', async () => {
  const anonymous = renderApp('/');
  expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument();
  anonymous.unmount();
  renderAuthenticatedApp('/');
  expect(await screen.findByRole('navigation')).toHaveTextContent('Обзор');
  expect(screen.getByRole('navigation')).toHaveTextContent('Кампании');
  expect(screen.getByRole('navigation')).toHaveTextContent('Бизнесы');
  expect(screen.queryByText('Дедупликация')).not.toBeInTheDocument();
});
```

- [x] **Step 2: Запустить RED**

```bash
cd frontend
npm run test:run -- src/features/auth/LoginPage.test.tsx
```

Expected: FAIL, потому что routes/provider/pages отсутствуют.

- [x] **Step 3: Реализовать credentialed API client с CSRF**

`request<T>()` всегда передаёт `credentials: 'include'`. Перед первым unsafe request client делает `GET /api/v1/auth/csrf/`, читает `csrftoken` из cookie и устанавливает `X-CSRFToken`. Non-2xx body преобразуется в `ApiClientError` с `code`, `detail`, `fields`; UI не показывает stack trace.

- [x] **Step 4: Реализовать AuthProvider, routes и форму**

`AuthProvider` различает `loading | anonymous | authenticated`; `ProtectedRoute` во время loading показывает «Проверяем сессию…», затем redirect `/login` либо child route. Форма использует Zod:

```ts
const loginSchema = z.object({
  username: z.string().trim().min(1, 'Введите имя пользователя.'),
  password: z.string().min(1, 'Введите пароль.'),
});
```

`AppShell` содержит только доступные в slice ссылки. Не показывать «Дедупликация», «Аудит», «Возможности».

- [x] **Step 5: Проверить GREEN и accessibility basics**

```bash
cd frontend
npm run test:run -- src/features/auth/LoginPage.test.tsx src/app/App.test.tsx
npm run lint
npm run typecheck
```

Expected: tests PASS; labels связаны с inputs; submit доступен по role/name; logout очищает session и возвращает `/login`.

- [x] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: add Russian session login and protected shell"
```

---

### Task 7: Добавить Geography/PostGIS и seed Türkiye → Antalya → Alanya

**Files:**
- Create: `backend/apps/geography/apps.py`
- Create: `backend/apps/geography/models.py`
- Create: `backend/apps/geography/migrations/0001_extensions.py`
- Create: `backend/apps/geography/migrations/0002_initial.py`
- Create: `backend/apps/geography/services.py`
- Create: `backend/apps/geography/api/serializers.py`
- Create: `backend/apps/geography/api/views.py`
- Create: `backend/apps/geography/api/urls.py`
- Create: `backend/apps/geography/management/commands/seed_reference_data.py`
- Create: `backend/apps/geography/tests/test_models.py`
- Create: `backend/apps/geography/tests/test_api.py`
- Create: `backend/apps/geography/tests/test_seed.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/api_urls.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: PostGIS database from Task 1; `TimestampedUUIDModel`.
- Produces: `Country`, `Province`, `District`, `Neighborhood`, `SearchArea`; `GET /geography/search-areas/`.

- [x] **Step 1: Написать failing model/API tests**

```python
# backend/apps/geography/tests/test_models.py
import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from apps.geography.models import Country, Province, District, SearchArea


def alanya_geometry() -> MultiPolygon:
    return MultiPolygon(Polygon.from_bbox((31.70, 36.30, 32.65, 36.75)), srid=4326)


@pytest.mark.django_db
def test_search_area_accepts_consistent_hierarchy_and_4326_geometry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    province = Province.objects.create(country=country, code="07", name="Antalya", name_ru="Анталья")
    district = District.objects.create(province=province, slug="alanya", name="Alanya", name_ru="Аланья")
    area = SearchArea(name="Аланья — пилот", country=country, province=province, district=district, geometry=alanya_geometry())
    area.full_clean()
    area.save()
    assert area.geometry.srid == 4326


@pytest.mark.django_db
def test_search_area_rejects_mismatched_district_ancestry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    antalya = Province.objects.create(country=country, code="07", name="Antalya", name_ru="Анталья")
    mugla = Province.objects.create(country=country, code="48", name="Muğla", name_ru="Мугла")
    mismatched_district = District.objects.create(
        province=mugla, slug="bodrum", name="Bodrum", name_ru="Бодрум"
    )
    area = SearchArea(
        name="Некорректная область",
        country=country,
        province=antalya,
        district=mismatched_district,
        geometry=alanya_geometry(),
    )
    with pytest.raises(ValidationError, match="Район не относится к выбранной провинции"):
        area.full_clean()
```

```python
# backend/apps/geography/tests/test_api.py
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_search_area_api_requires_authentication_and_returns_geojson_bbox():
    call_command("seed_reference_data")
    anonymous = APIClient().get("/api/v1/geography/search-areas/")
    assert anonymous.status_code == 403

    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user("owner", password="password"))
    response = client.get("/api/v1/geography/search-areas/")
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["name"] == "Аланья — пилот"
    assert item["bbox"] == [31.7, 36.3, 32.65, 36.75]
    assert item["geometry"]["type"] == "MultiPolygon"
    assert item["district"]["slug"] == "alanya"
```

```python
# backend/apps/geography/tests/test_seed.py
import pytest
from django.core.management import call_command
from apps.geography.models import Country, Province, District, SearchArea


@pytest.mark.django_db
def test_reference_seed_is_idempotent_and_creates_alanya_pilot_area():
    call_command("seed_reference_data")
    call_command("seed_reference_data")
    assert Country.objects.filter(code="TR").count() == 1
    assert Province.objects.filter(country__code="TR", code="07").count() == 1
    assert District.objects.filter(province__code="07", slug="alanya").count() == 1
    assert SearchArea.objects.filter(name="Аланья — пилот", is_active=True).count() == 1
```

- [x] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/geography/tests -q
```

Expected: FAIL с отсутствующим module/models.

- [x] **Step 3: Создать extension migration до schema migration**

```python
# 0001_extensions.py
from django.contrib.postgres.operations import CreateExtension, TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    operations = [
        CreateExtension("postgis"),
        TrigramExtension(),
        UnaccentExtension(),
    ]
```

В `backend/apps/geography/tests/test_models.py` добавить точную проверку migration:

```python
@pytest.mark.django_db
def test_required_postgres_extensions_are_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension")
        names = {row[0] for row in cursor.fetchall()}
    assert {"postgis", "pg_trgm", "unaccent"}.issubset(names)
```

Импортировать `connection` из `django.db`.

- [x] **Step 4: Реализовать models, hierarchy validation и API**

Geometry fields — `MultiPolygonField(srid=4326, null=True)` у admin levels и required у `SearchArea`; явно добавить GiST index для `SearchArea.geometry`. Serializer отдаёт `id`, `name`, ancestry, `geometry` и `[west, south, east, north]` bbox.

- [x] **Step 5: Реализовать идемпотентный seed**

Command создаёт codes/slugs и operational rectangle:

```python
ALANYA_PILOT_BBOX = (31.70, 36.30, 32.65, 36.75)
```

В README пояснить, что это operational AOI, не юридическая граница. Два запуска command дают по одной записи каждого уровня и один `SearchArea`.

- [x] **Step 6: Проверить GREEN, migrations и spatial query**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py seed_reference_data
docker compose run --rm backend python manage.py seed_reference_data
docker compose run --rm backend pytest apps/geography/tests -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
```

Expected: tests PASS; second seed creates nothing extra; no pending migrations.

- [x] **Step 7: Commit**

```bash
git add backend/apps/geography backend/config README.md
git commit -m "feat: add geographic hierarchy and Alanya search area"
```

---

### Task 8: Добавить Source configuration и read API

**Files:**
- Create: `backend/apps/sources/apps.py`
- Create: `backend/apps/sources/models.py`
- Create: `backend/apps/sources/migrations/0001_initial.py`
- Create: `backend/apps/sources/api/serializers.py`
- Create: `backend/apps/sources/api/views.py`
- Create: `backend/apps/sources/api/urls.py`
- Create: `backend/apps/sources/tests/test_source_model.py`
- Create: `backend/apps/sources/tests/test_source_api.py`
- Create: `backend/apps/sources/management/commands/seed_sources.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/api_urls.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: common UUID model; authenticated API.
- Produces: `Source(code="overture"|"osm")`; `GET /sources/`.

- [x] **Step 1: Написать failing Source tests**

```python
@pytest.mark.django_db
def test_source_code_is_unique_and_operational_limits_are_explicit():
    source = Source.objects.create(
        code="osm",
        name="OpenStreetMap",
        source_type=Source.Type.OPEN_DATA,
        attribution="© OpenStreetMap contributors",
        license_code="ODbL-1.0",
        requests_per_second=Decimal("0.20"),
        concurrency=1,
        timeout_seconds=60,
        max_retries=3,
    )
    assert source.is_paid is False
    assert source.settings == {}
    with pytest.raises(IntegrityError):
        Source.objects.create(
            code="osm",
            name="Duplicate",
            source_type=Source.Type.OPEN_DATA,
            attribution="fixture",
            license_code="fixture-only",
        )
```

```python
@pytest.mark.django_db
def test_source_rejects_secret_like_settings_keys():
    source = Source(
        code="unsafe",
        name="Unsafe",
        source_type=Source.Type.OPEN_DATA,
        attribution="fixture",
        license_code="fixture-only",
        settings={"nested": {"api_token": "must-not-be-stored"}},
    )
    with pytest.raises(ValidationError, match="api_token"):
        source.full_clean()


@pytest.mark.django_db
def test_source_api_requires_auth_and_exposes_only_public_configuration(
    api_client, owner, osm_source
):
    assert api_client.get("/api/v1/sources/").status_code == 403
    api_client.force_authenticate(owner)
    response = api_client.get("/api/v1/sources/")
    assert response.status_code == 200
    item = next(row for row in response.json()["results"] if row["code"] == "osm")
    assert set(item) == {
        "id", "code", "name", "source_type", "is_paid", "is_active",
        "attribution", "license_code", "requests_per_second", "concurrency",
        "timeout_seconds", "max_retries",
    }
    assert "settings" not in item
    assert "endpoint" not in item
```

В этом Task добавить в `backend/conftest.py` fixtures `overture_source` и `osm_source` из §1.1; каждый сначала вызывает `seed_sources`, поэтому API test использует production seed, а не случайные defaults.

- [x] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/sources/tests/test_source_model.py apps/sources/tests/test_source_api.py -q
```

Expected: FAIL с отсутствующим `Source`.

- [x] **Step 3: Реализовать model/serializer/API**

`Source` fields соответствуют spec, включая обязательные `attribution` и `license_code`. `clean()` рекурсивно запрещает JSON keys, чьё lowercase имя содержит `secret`, `token`, `password`, `api_key`, в `settings`. Serializer read-only и отдаёт operational limits, attribution и license metadata, но не environment values.

- [x] **Step 4: Реализовать идемпотентный seed**

```text
overture: Overture Maps, open_data, CDLA-Permissive-2.0/Apache-2.0, active
osm: OpenStreetMap, open_data, ODbL-1.0, active, concurrency=1
```

`seed_sources` обновляет display metadata/limits по `code`, не меняет вручную установленный `is_active` без `--reset-active`.

- [x] **Step 5: Проверить GREEN**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py seed_sources
docker compose run --rm backend pytest apps/sources/tests -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
```

Expected: PASS, два source rows, no pending migrations.

- [x] **Step 6: Commit**

```bash
git add backend/apps/sources backend/config
git commit -m "feat: add configurable discovery sources"
```

---

### Task 9: Добавить taxonomy и provider category mappings

**Files:**
- Create: `backend/apps/taxonomy/apps.py`
- Create: `backend/apps/taxonomy/models.py`
- Create: `backend/apps/taxonomy/migrations/0001_initial.py`
- Create: `backend/apps/taxonomy/api/serializers.py`
- Create: `backend/apps/taxonomy/api/views.py`
- Create: `backend/apps/taxonomy/api/urls.py`
- Create: `backend/apps/taxonomy/services.py`
- Create: `backend/apps/taxonomy/management/commands/seed_taxonomy.py`
- Create: `backend/apps/taxonomy/tests/test_models.py`
- Create: `backend/apps/taxonomy/tests/test_mapping.py`
- Create: `backend/apps/taxonomy/tests/test_api.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/api_urls.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: `Source` from Task 8.
- Produces: `BusinessCategory`, `SourceCategoryMapping`, `resolve_category(source_id, external_category) -> UUID | None`, `resolve_external_categories(source_id, category_ids) -> tuple[str, ...]`, `GET /taxonomy/categories/`.

- [x] **Step 1: Написать failing hierarchy/mapping tests**

```python
from django.core.management import call_command


@pytest.mark.django_db
def test_resolve_category_returns_internal_leaf_for_osm_tag(osm_source):
    root = BusinessCategory.objects.create(name="Медицина", slug="health")
    dentist = BusinessCategory.objects.create(name="Стоматология", slug="dentist", parent=root)
    SourceCategoryMapping.objects.create(
        source=osm_source, external_category="amenity=dentist", category=dentist
    )
    assert resolve_category(osm_source.id, "amenity=dentist") == dentist.id


@pytest.mark.django_db
def test_unknown_category_returns_none_instead_of_rejecting_record(osm_source):
    assert resolve_category(osm_source.id, "shop=unknown") is None


@pytest.mark.django_db
def test_empty_internal_selection_expands_all_active_mappings_for_each_source(
    osm_source
):
    call_command("seed_taxonomy")
    assert resolve_external_categories(osm_source.id, ()) == (
        "amenity=dentist",
        "office=estate_agent",
        "shop=beauty",
        "tourism=hotel",
    )
```

```python
@pytest.mark.django_db
def test_category_rejects_self_parent_and_longer_cycle():
    first = BusinessCategory.objects.create(name="Первая", slug="first")
    second = BusinessCategory.objects.create(name="Вторая", slug="second", parent=first)
    first.parent = first
    with pytest.raises(ValidationError, match="своим родителем"):
        first.full_clean()
    first.parent = second
    with pytest.raises(ValidationError, match="цикл"):
        first.full_clean()


@pytest.mark.django_db(transaction=True)
def test_external_category_is_unique_within_source(osm_source, dentist_category):
    SourceCategoryMapping.objects.create(
        source=osm_source,
        external_category="amenity=dentist",
        category=dentist_category,
    )
    with pytest.raises(IntegrityError):
        SourceCategoryMapping.objects.create(
            source=osm_source,
            external_category="amenity=dentist",
            category=dentist_category,
        )
```

Импорты для этих tests: `ValidationError` из `django.core.exceptions` и `IntegrityError` из `django.db`. В этом Task добавить `dentist_category` fixture из §1.1 в `backend/conftest.py`.

- [x] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/taxonomy/tests -q
```

Expected: FAIL с отсутствующими models/service.

- [x] **Step 3: Реализовать models и cycle-safe validation**

`BusinessCategory.clean()` проходит ancestors по `parent_id` и поднимает русскую `ValidationError` при цикле. DB constraints покрывают self-parent и unique slug. `SourceCategoryMapping` имеет `is_active`; resolver учитывает только active source/mapping/category. `resolve_external_categories` сортирует unique provider values лексикографически; пустой `category_ids` разворачивает все active mappings только данного source, непустой tuple — mappings выбранных внутренних categories.

- [x] **Step 4: Реализовать seed с точными mappings**

```text
overture dentist             → dentist
overture real_estate_agent   → real-estate-agency
overture hotel               → hotel
overture beauty_salon        → beauty-salon
osm amenity=dentist          → dentist
osm office=estate_agent      → real-estate-agency
osm tourism=hotel            → hotel
osm shop=beauty              → beauty-salon
```

Категории: четыре root + четыре leaves из spec. API отдаёт дерево, а не flat parent labels.

- [x] **Step 5: Проверить GREEN**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py seed_taxonomy
docker compose run --rm backend pytest apps/taxonomy/tests -q
docker compose run --rm backend ruff check apps/taxonomy
```

Expected: all PASS; repeated seed is idempotent.

- [x] **Step 6: Commit**

```bash
git add backend/apps/taxonomy backend/config
git commit -m "feat: add business taxonomy and source mappings"
```

---

### Task 10: Смоделировать DiscoveryCampaign, selections и source runs

**Files:**
- Create: `backend/apps/campaigns/apps.py`
- Create: `backend/apps/campaigns/models.py`
- Create: `backend/apps/campaigns/migrations/0001_initial.py`
- Create: `backend/apps/campaigns/domain.py`
- Create: `backend/apps/campaigns/services.py`
- Create: `backend/apps/campaigns/api/serializers.py`
- Create: `backend/apps/campaigns/api/views.py`
- Create: `backend/apps/campaigns/api/urls.py`
- Create: `backend/apps/campaigns/tests/test_models.py`
- Create: `backend/apps/campaigns/tests/test_services.py`
- Create: `backend/apps/campaigns/tests/test_api.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/api_urls.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: authenticated `User`, `SearchArea`, `Source`, `BusinessCategory`.
- Produces: `DiscoveryCampaign`, `CampaignSource`, `CampaignCategory`, `CampaignSourceRun`; `create_campaign(*, actor, command) -> DiscoveryCampaign`; list/create/detail API.

```python
@dataclass(frozen=True)
class CreateCampaignCommand:
    name: str
    search_area_id: UUID
    source_ids: tuple[UUID, ...]
    category_ids: tuple[UUID, ...]


class CampaignValidationError(Exception):
    def __init__(
        self, code: str, detail: str, fields: dict[str, list[str]] | None = None
    ) -> None: ...
```

- [ ] **Step 1: Написать failing state/model tests**

```python
@pytest.mark.django_db
def test_create_campaign_persists_explicit_sources_and_empty_categories_means_all(
    owner, alanya_area, overture_source, osm_source
):
    campaign = create_campaign(
        actor=owner,
        command=CreateCampaignCommand(
            name="Аланья — первичный сбор",
            search_area_id=alanya_area.id,
            source_ids=(overture_source.id, osm_source.id),
            category_ids=(),
        ),
    )
    assert campaign.status == DiscoveryCampaign.Status.DRAFT
    assert set(campaign.sources.values_list("code", flat=True)) == {"overture", "osm"}
    assert campaign.categories.count() == 0
    assert campaign.total_jobs == 0


@pytest.mark.django_db
def test_source_run_retry_budget_starts_at_zero(source_run):
    assert source_run.source_retry_count == 0


@pytest.mark.django_db
def test_campaign_rejects_source_without_active_category_mappings(
    owner, alanya_area, active_source_without_mappings
):
    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand(
                name="Некорректная кампания",
                search_area_id=alanya_area.id,
                source_ids=(active_source_without_mappings.id,),
                category_ids=(),
            ),
        )
    assert error.value.code == "SOURCE_HAS_NO_ACTIVE_MAPPINGS"
```

```python
@pytest.mark.django_db
def test_create_campaign_requires_at_least_one_source(owner, alanya_area):
    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand("Без источников", alanya_area.id, (), ()),
        )
    assert error.value.code == "NO_SOURCES_SELECTED"
    assert error.value.fields == {"source_ids": ["Выберите хотя бы один источник."]}


@pytest.mark.django_db
def test_create_campaign_rejects_inactive_source(owner, alanya_area, osm_source):
    osm_source.is_active = False
    osm_source.save(update_fields=["is_active"])
    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand("Неактивный источник", alanya_area.id, (osm_source.id,), ()),
        )
    assert error.value.code == "SOURCE_INACTIVE"


@pytest.mark.django_db
def test_campaign_detail_hides_other_owners_campaign(api_client, other_owner, alanya_campaign):
    api_client.force_authenticate(other_owner)
    response = api_client.get(f"/api/v1/campaigns/{alanya_campaign.id}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.django_db(transaction=True)
def test_campaign_through_rows_are_unique(alanya_campaign, osm_source, dentist_category):
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignSource.objects.create(campaign=alanya_campaign, source=osm_source)
    CampaignCategory.objects.create(campaign=alanya_campaign, category=dentist_category)
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignCategory.objects.create(campaign=alanya_campaign, category=dentist_category)
```

Импорты: `IntegrityError, transaction` из `django.db`. В Task 10 добавить в `backend/conftest.py` fixtures `other_owner`, `active_source_without_mappings`, `alanya_campaign` и `source_run` по seed rules из §1.1.

- [ ] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/campaigns/tests -q
```

Expected: FAIL с отсутствующим app/models.

- [ ] **Step 3: Реализовать models и constraints**

`DiscoveryCampaign.Status`: `draft`, `queued`, `running`, `completed`, `completed_with_errors`, `failed`. `CampaignSourceRun.Status`: `pending`, `running`, `normalizing`, `completed`, `completed_with_errors`, `failed`. Все record/job counters — `PositiveBigIntegerField(default=0)`; `request_count` также non-negative, а `source_retry_count` — `PositiveSmallIntegerField(default=0)` и хранит число атомарно выданных business retry reservations для transient provider/raw-write ошибок этого source run. `cost` — `DecimalField(max_digits=12, decimal_places=4, default=0)`, version/error/timestamps nullable до соответствующего transition. `CampaignSource` и `CampaignCategory` — explicit through models с `UniqueConstraint`. `CampaignSourceRun.campaign` использует `related_name="source_runs"`; run unique `(campaign, source)` для этого slice.

`CampaignSource` defaults: `is_enabled=True`, `priority=100`, `request_limit=None`, `budget_limit=None`. Free sources reject non-zero budget in validation.

- [ ] **Step 4: Реализовать create/list/detail API**

`POST /api/v1/campaigns/` принимает exact request из spec. Serializer валидирует UUIDs одной bulk query на model, передаёт immutable command service и возвращает 201. Для каждого выбранного source service вызывает `resolve_external_categories`; пустой итог отклоняет весь request с code `SOURCE_HAS_NO_ACTIVE_MAPPINGS` и `fields.source_ids`, поэтому unbounded provider query невозможен. List/detail фильтруются `created_by=request.user`; никаких organization/workspace fields.

- [ ] **Step 5: Проверить GREEN и query count**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend pytest apps/campaigns/tests -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend ruff check apps/campaigns
```

Expected: PASS. List serializer prefetches sources/categories и не создаёт N+1; закрепить query-count test на 10 campaigns.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/campaigns backend/config
git commit -m "feat: add discovery campaign model and API"
```

---

### Task 11: Реализовать deterministic raw payload storage в MinIO

**Files:**
- Create: `backend/common/json_types.py`
- Create: `backend/apps/sources/storage/__init__.py`
- Create: `backend/apps/sources/storage/base.py`
- Create: `backend/apps/sources/storage/s3.py`
- Create: `backend/apps/sources/tests/conftest.py`
- Create: `backend/apps/sources/tests/test_raw_payload_storage.py`
- Create: `backend/apps/sources/tests/integration/test_s3_raw_payload_storage.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/conftest.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: private S3-compatible bucket and `S3_*` settings.
- Produces:

```python
@dataclass(frozen=True)
class StoredPayload:
    key: str
    sha256: str
    size_bytes: int
    content_type: str
    content_encoding: str


class RawPayloadStore(Protocol):
    def put_json(
        self,
        *,
        source_code: str,
        campaign_id: UUID,
        external_id: str,
        payload: dict[str, JSONValue],
        metadata: Mapping[str, str],
    ) -> StoredPayload: ...

    def get_json(self, key: str) -> dict[str, JSONValue]: ...


class RawStorageUnavailable(Exception):
    code = "RAW_STORAGE_UNAVAILABLE"
```

- [ ] **Step 1: Написать failing deterministic serialization test**

```python
def test_equivalent_json_produces_same_content_addressed_key(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    first = store.put_json(
        source_code="osm",
        campaign_id=UUID("00000000-0000-0000-0000-000000000001"),
        external_id="node/42",
        payload={"name": "Diş", "id": 42},
        metadata={"payload-schema-version": "1", "source-dataset-version": "2026-09"},
    )
    second = store.put_json(
        source_code="osm",
        campaign_id=UUID("00000000-0000-0000-0000-000000000001"),
        external_id="node/42",
        payload={"id": 42, "name": "Diş"},
        metadata={"payload-schema-version": "1", "source-dataset-version": "2026-09"},
    )
    assert first == second
    external_id_sha256 = hashlib.sha256(b"node/42").hexdigest()
    assert first.key == (
        "raw/osm/00000000-0000-0000-0000-000000000001/"
        f"{external_id_sha256}/{first.sha256}.json.gz"
    )
```

`backend/apps/sources/tests/conftest.py` определяет `fake_s3_client` через `moto.mock_aws()`, создаёт bucket `raw-test` и закрывает mock после test. Второй test фиксирует round-trip, gzip и весь metadata contract:

```python
def test_unicode_round_trip_has_zero_gzip_mtime_and_exact_metadata(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"id": 42, "name": "Çağlar Diş Kliniği"}
    stored = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/42",
        payload=payload,
        metadata={"payload-schema-version": "1", "source-dataset-version": "2026-09"},
    )
    response = fake_s3_client.get_object(Bucket="raw-test", Key=stored.key)
    compressed = response["Body"].read()
    assert compressed[4:8] == b"\x00\x00\x00\x00"
    assert json.loads(gzip.decompress(compressed)) == payload
    head = fake_s3_client.head_object(Bucket="raw-test", Key=stored.key)
    assert head["ContentLength"] == stored.size_bytes == len(compressed)
    assert head["ContentType"] == "application/json"
    assert head["ContentEncoding"] == "gzip"
    assert head["Metadata"] == {
        "source-code": "osm",
        "campaign-id": str(campaign_id),
        "external-id": "node/42",
        "sha256": stored.sha256,
        "payload-schema-version": "1",
        "source-dataset-version": "2026-09",
    }
    assert store.get_json(stored.key) == payload


def test_equal_payload_for_different_external_ids_has_distinct_metadata(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"name": "Payload without embedded provider ID"}
    first = store.put_json(
        source_code="osm", campaign_id=campaign_id, external_id="node/1",
        payload=payload,
        metadata={"payload-schema-version": "1", "source-dataset-version": "fixture"},
    )
    second = store.put_json(
        source_code="osm", campaign_id=campaign_id, external_id="node/2",
        payload=payload,
        metadata={"payload-schema-version": "1", "source-dataset-version": "fixture"},
    )
    assert first.sha256 == second.sha256
    assert first.key != second.key
    first_meta = fake_s3_client.head_object(Bucket="raw-test", Key=first.key)["Metadata"]
    second_meta = fake_s3_client.head_object(Bucket="raw-test", Key=second.key)["Metadata"]
    assert first_meta["external-id"] == "node/1"
    assert second_meta["external-id"] == "node/2"
```

Integration module задаёт `pytestmark = pytest.mark.integration`. Root fixture `minio_store` в `backend/conftest.py` сначала требует `STORAGE_INTEGRATION_PROJECT == "1"` (иначе immediately fails), затем читает `S3_*` settings активного изолированного Compose project, создаёт bucket `lbi-storage-test-{uuid4().hex}`, yields `S3RawPayloadStore`, а в `finally` удаляет objects и только этот bucket. Она никогда не использует development bucket. Sibling `backend/apps/sources/tests/conftest.py` содержит только unit `fake_s3_client`.

- [ ] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/sources/tests/test_raw_payload_storage.py -q
```

Expected: FAIL с отсутствующим `storage` package.

- [ ] **Step 3: Реализовать canonical JSON и S3 store**

```python
def canonical_json_bytes(payload: dict[str, JSONValue]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
```

`payload_sha256` считается по этим bytes; `external_id_sha256` — по `external_id.encode("utf-8")`; gzip создаётся `gzip.compress(data, mtime=0)`. Key строго `raw/{source_code}/{campaign_id}/{external_id_sha256}/{payload_sha256}.json.gz`. `put_object` задаёт `ContentType="application/json"`, `ContentEncoding="gzip"` и ровно metadata `source-code`, `campaign-id`, `external-id`, `sha256`, `payload-schema-version`, `source-dataset-version`; service обязан передать последние два, store вычисляет/добавляет первые четыре. Повтор того же key разрешён и возвращает тот же result. `S3RawPayloadStore` переводит timeout, connection failure, throttling и retryable S3 `5xx` в provider-neutral `RawStorageUnavailable`; permanent auth/configuration errors не маскирует этим типом.

- [ ] **Step 4: Запустить unit GREEN**

```bash
docker compose run --rm backend pytest apps/sources/tests/test_raw_payload_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: Запустить реальный MinIO integration test**

Integration test создаёт уникальный bucket, делает put/get/head, проверяет metadata и удаляет только свой bucket в fixture teardown. Зафиксировать отдельный Compose project, отдельные volumes/network, отсутствие host ports и unconditional cleanup в `Makefile`:

```make
STORAGE_TEST_COMPOSE = docker compose -p local-business-intelligence-storage-test -f docker-compose.yml -f docker-compose.e2e.yml

storage-integration:
	@set -eu; trap '$(STORAGE_TEST_COMPOSE) down -v' EXIT INT TERM; \
	$(STORAGE_TEST_COMPOSE) up -d postgres redis minio minio-ready minio-init; \
	$(STORAGE_TEST_COMPOSE) run --rm -e STORAGE_INTEGRATION_PROJECT=1 backend \
	  pytest apps/sources/tests/integration/test_s3_raw_payload_storage.py -q
```

Run:

```bash
make storage-integration
```

Expected: PASS; downloaded JSON полностью равен исходному payload; trap удаляет только `local-business-intelligence-storage-test` volumes. Запрещено заменять этот command обычным `docker compose ...`, потому что он мог бы обратиться к development MinIO.

- [ ] **Step 6: Commit**

```bash
git add backend/common backend/apps/sources/storage backend/apps/sources/tests backend/config/settings backend/conftest.py Makefile
git commit -m "feat: store immutable raw payloads in MinIO"
```

---

### Task 12: Добавить SourceRecord и идемпотентный persistence service

**Files:**
- Modify: `backend/apps/sources/models.py`
- Create: `backend/apps/sources/migrations/0002_sourcerecord.py`
- Create: `backend/apps/sources/domain.py`
- Create: `backend/apps/sources/services.py`
- Create: `backend/apps/sources/tests/fakes.py`
- Create: `backend/apps/sources/tests/test_source_record_model.py`
- Create: `backend/apps/sources/tests/test_persist_source_payload.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: `RawPayloadStore`, `CampaignSourceRun` и две временные immutable value objects ниже; Task 13 переносит их в окончательную discovery boundary без изменения signatures.
- Produces: immutable `SourceRecord`, durable `SourceRecordConflict`; `persist_source_payload(...) -> PersistedSourceRecord`.

```python
from collections.abc import Callable


@dataclass(frozen=True)
class SourceProvenance:
    dataset_version: str
    source_url: str | None
    attribution: str
    license_code: str


@dataclass(frozen=True)
class SourcePayload:
    external_id: str
    payload: dict[str, JSONValue]
    fetched_at: datetime
    provenance: SourceProvenance


@dataclass(frozen=True)
class RawBusinessRecord:
    external_id: str
    raw_name: str | None
    raw_category: str | None
    raw_address: str | None
    raw_phones: tuple[str, ...]
    raw_emails: tuple[str, ...]
    raw_websites: tuple[str, ...]
    raw_social_urls: dict[str, tuple[str, ...]]
    longitude: float | None
    latitude: float | None


class SourcePayloadParseError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SourceRecordConflictError(Exception):
    pass


@dataclass(frozen=True)
class PersistedSourceRecord:
    source_record_id: UUID
    created: bool
    raw_payload_key: str
    checksum: str
    normalization_status: Literal["pending", "failed"]


def persist_source_payload(
    *,
    source_run: CampaignSourceRun,
    source_payload: SourcePayload,
    parse_payload: Callable[[SourcePayload], RawBusinessRecord],
    store: RawPayloadStore,
) -> PersistedSourceRecord: ...
```

- [ ] **Step 1: Написать failing idempotency/conflict tests**

```python
@pytest.mark.django_db
def test_same_campaign_source_external_id_and_checksum_is_idempotent(source_run, payload, parsed, store):
    first = persist_source_payload(
        source_run=source_run, source_payload=payload, parse_payload=lambda _: parsed, store=store
    )
    second = persist_source_payload(
        source_run=source_run, source_payload=payload, parse_payload=lambda _: parsed, store=store
    )
    assert first.created is True
    assert second.created is False
    assert SourceRecord.objects.count() == 1
    assert SourceRecord.objects.get().normalization_retry_count == 0
    assert store.object_count == 1


@pytest.mark.django_db
def test_changed_payload_for_same_campaign_external_id_preserves_first_record(source_run, payload, parsed, store):
    persist_source_payload(source_run=source_run, source_payload=payload, parse_payload=lambda _: parsed, store=store)
    changed = replace(payload, payload={**payload.payload, "name": "Changed"})
    with pytest.raises(SourceRecordConflictError):
        persist_source_payload(source_run=source_run, source_payload=changed, parse_payload=lambda _: parsed, store=store)
    assert SourceRecord.objects.get().raw_name == parsed.raw_name
    assert SourceRecordConflict.objects.filter(
        source_run=source_run, external_id=payload.external_id
    ).count() == 1
    source_run.refresh_from_db()
    assert source_run.stored_records == 2
    assert source_run.failed_records == 1


@pytest.mark.django_db(transaction=True)
def test_raw_object_is_stored_before_parser_failure_and_failed_counter_is_once_only(
    source_run, payload, store
):
    def failing_parser(_: SourcePayload) -> RawBusinessRecord:
        assert store.object_count == 1
        raise SourcePayloadParseError("INVALID_SOURCE_PAYLOAD")

    first = persist_source_payload(
        source_run=source_run, source_payload=payload, parse_payload=failing_parser, store=store
    )
    second = persist_source_payload(
        source_run=source_run, source_payload=payload, parse_payload=failing_parser, store=store
    )
    record = SourceRecord.objects.get(id=first.source_record_id)
    source_run.refresh_from_db()
    assert first.created is True
    assert second.created is False
    assert record.raw_payload_key
    assert record.raw_payload_bytes > 0
    assert record.raw_name is None
    assert record.normalization_status == SourceRecord.NormalizationStatus.FAILED
    assert record.parser_error_code == "INVALID_SOURCE_PAYLOAD"
    assert record.normalization_error_code == "INVALID_SOURCE_PAYLOAD"
    assert source_run.failed_records == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_payload_creates_one_record_and_counters_once(
    source_run, payload, parsed, thread_safe_store
):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections

    def persist_once() -> PersistedSourceRecord:
        close_old_connections()
        run = CampaignSourceRun.objects.get(id=source_run.id)
        return persist_source_payload(
            source_run=run,
            source_payload=payload,
            parse_payload=lambda _: parsed,
            store=thread_safe_store,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: persist_once(), range(2)))
    source_run.refresh_from_db()
    assert sorted(result.created for result in results) == [False, True]
    assert SourceRecord.objects.count() == 1
    assert source_run.stored_records == 1
    assert source_run.failed_records == 0
```

Точный fake для обоих fixtures находится в `backend/apps/sources/tests/fakes.py` и повторно использует production serializer, а не собственную JSON-семантику:

```python
class InMemoryRawPayloadStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._objects: dict[str, bytes] = {}

    @property
    def object_count(self) -> int:
        with self._lock:
            return len(self._objects)

    def put_json(self, *, source_code, campaign_id, external_id, payload, metadata):
        raw = canonical_json_bytes(payload)
        checksum = hashlib.sha256(raw).hexdigest()
        body = gzip.compress(raw, mtime=0)
        external_id_checksum = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
        key = f"raw/{source_code}/{campaign_id}/{external_id_checksum}/{checksum}.json.gz"
        with self._lock:
            self._objects.setdefault(key, body)
        return StoredPayload(
            key=key,
            sha256=checksum,
            size_bytes=len(body),
            content_type="application/json",
            content_encoding="gzip",
        )

    def get_json(self, key):
        with self._lock:
            body = self._objects[key]
        return json.loads(gzip.decompress(body))
```

`backend/conftest.py` добавляет `payload`, `parsed`, `store` и `thread_safe_store` ровно по §1.1. Оба store fixtures возвращают новый `InMemoryRawPayloadStore`; отдельные имена подчёркивают, что concurrency test обязан использовать его lock-safe implementation.

- [ ] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/sources/tests/test_source_record_model.py apps/sources/tests/test_persist_source_payload.py -q
```

Expected: FAIL с отсутствующим model/service.

- [ ] **Step 3: Реализовать SourceRecord schema**

`SourceRecord` содержит все поля design spec. `source_run` использует `related_name="records"`. Scalar raw fields (`raw_name`, `raw_category`, `raw_address`, `raw_location`) nullable; `raw_phones`, `raw_emails`, `raw_websites` default to `[]`, а `raw_social_urls` — к `{}`. `normalization_retry_count = PositiveSmallIntegerField(default=0)` хранит число атомарно выданных business retry reservations для transient raw-read/storage ошибок именно этой записи. Если provider payload сохранён, но parser поднял `SourcePayloadParseError`, row всё равно создаётся с пустыми raw contact collections, `normalization_status="failed"` и `normalization_error_code=error.code`. `raw_payload_bytes` всегда равен `StoredPayload.size_bytes` (размер gzip object), не размеру canonical JSON.

Constraints: `UniqueConstraint(fields=["campaign", "source", "external_id"], name="uniq_campaign_source_external")`; indexes `(campaign, normalization_status)`, `(source, external_id)`, `fetched_at`, GiST `raw_location`. В той же migration создать `SourceRecordConflict` с полями `campaign`, `source_run`, `source`, `external_id`, `original_source_record`, `conflicting_payload_sha256`, `raw_payload_key`, `raw_payload_bytes`, `payload_schema_version`, `source_dataset_version`, `error_code="SOURCE_RECORD_CONFLICT"`, nullable `counted_at`, timestamps и `UniqueConstraint(fields=["campaign", "source", "external_id", "conflicting_payload_sha256"], name="uniq_campaign_source_external_conflict_sha")`. Conflict row — durable provenance попытки с другим payload; он никогда не изменяет исходный `SourceRecord` или его raw object.

- [ ] **Step 4: Реализовать transaction boundary**

Алгоритм:

1. до любого parser call вызвать `store.put_json(source_code=..., campaign_id=..., external_id=..., ...)` и передать metadata `payload-schema-version="1"`, `source-dataset-version=source_payload.provenance.dataset_version`; `RawPayloadStore` по arguments/canonical JSON записывает полный exact metadata set: `source-code`, `campaign-id`, `external-id`, `sha256`, `payload-schema-version`, `source-dataset-version`;
2. после успешного object put вызвать pure `parse_payload(source_payload)` в памяти; сохранить либо полный `RawBusinessRecord`, либо typed parser error. `parsed.external_id != source_payload.external_id` преобразовать в `INVALID_SOURCE_PAYLOAD`. При crash здесь retry повторно использует тот же deterministic dual-digest object;
3. внутри `transaction.atomic()` сначала заблокировать `DiscoveryCampaign`, затем `CampaignSourceRun` через `select_for_update()` и получить `SourceRecord` по `(campaign, source, external_id)`; этот порядок locks обязателен во всех counter services;
4. если checksum совпадает — вернуть existing/no-op со stored status и не менять counters; существующая row уже содержит целиком parsed либо failed outcome, потому что она создаётся только на шаге 6;
5. если checksum отличается — `get_or_create` durable `SourceRecordConflict` по `(campaign, source, external_id, conflicting_payload_sha256)` со ссылкой на новый dual-digest object; только создавшая transaction ставит `counted_at`, увеличивает `discovered_records`, `stored_records`, `failed_records` и campaign `raw_records_found` по одному. Выйти из atomic block, дать transaction commit и лишь затем поднять `SourceRecordConflictError`; никогда не поднимать исключение внутри atomic block после `get_or_create`, иначе conflict/counters откатятся. Повтор того же conflict не меняет counters; исходная `SourceRecord` и её object не меняются;
6. если row нет и parser успешен — одной insert создать `SourceRecord` со всеми raw scalar/location/contact fields и `normalization_status="pending"`; если parser завершился typed error — одной insert создать row с nullable/empty raw fields, `normalization_status="failed"`, `parser_error_code` и `normalization_error_code`;
7. для любой новой row atomically увеличить `CampaignSourceRun.discovered_records`/`stored_records` и campaign `raw_records_found`; для parser-error row также увеличить `failed_records`. Вернуть `PersistedSourceRecord` только после commit.

Глобальной транзакции S3+PostgreSQL нет; deterministic key позволяет retry использовать тот же object. Lock на source run сериализует два concurrent inserts для одного run, а оба unique constraints остаются final DB guard. Новый conflict увеличивает и `stored_records`, и `failed_records`, поэтому invariant `normalized + rejected + failed == stored` сохраняется; загруженный conflicting object удерживается как evidence и достижим через `SourceRecordConflict`.

- [ ] **Step 5: Проверить GREEN и database constraints**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend pytest apps/sources/tests/test_source_record_model.py apps/sources/tests/test_persist_source_payload.py -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
```

Expected: PASS; concurrent regression above creates exactly one complete parsed row and increments counters once; повтор parser failure остаётся одной complete failed row и `failed_records == 1`; crash point между object put и DB transaction безопасно повторяется.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/sources
git commit -m "feat: persist idempotent source records"
```

---

### Task 13: Зафиксировать discovery adapter contract, errors и registry

**Files:**
- Create: `backend/apps/discovery/apps.py`
- Create: `backend/apps/discovery/domain.py`
- Create: `backend/apps/discovery/errors.py`
- Create: `backend/apps/discovery/registry.py`
- Create: `backend/apps/discovery/tests/fakes.py`
- Create: `backend/apps/discovery/tests/test_registry.py`
- Create: `backend/apps/discovery/tests/contracts.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/apps/sources/domain.py`
- Modify: `backend/apps/sources/services.py`

**Interfaces:**
- Consumes: `SearchArea`, active source/category mappings.
- Produces the following exact provider-neutral boundary; `get_adapter(source_code) -> DiscoveryAdapter` returns a new adapter instance for one source run.

```python
# backend/apps/discovery/domain.py
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeAlias
from uuid import UUID

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class DiscoveryRequest:
    campaign_id: UUID
    source_run_id: UUID
    search_area_id: UUID
    dataset_version: str
    bbox: BoundingBox
    geometry_geojson: dict[str, JSONValue]
    external_categories: tuple[str, ...]
    result_limit: int | None
    correlation_id: str


@dataclass(frozen=True)
class SourceProvenance:
    dataset_version: str
    source_url: str | None
    attribution: str
    license_code: str


@dataclass(frozen=True)
class SourcePayload:
    external_id: str
    payload: dict[str, JSONValue]
    fetched_at: datetime
    provenance: SourceProvenance


@dataclass(frozen=True)
class RawBusinessRecord:
    external_id: str
    raw_name: str | None
    raw_category: str | None
    raw_address: str | None
    raw_phones: tuple[str, ...]
    raw_emails: tuple[str, ...]
    raw_websites: tuple[str, ...]
    raw_social_urls: dict[str, tuple[str, ...]]
    longitude: float | None
    latitude: float | None


class DiscoveryAdapter(Protocol):
    source_code: str

    def resolve_dataset_version(self) -> str: ...
    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]: ...
    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord: ...
```

```python
# backend/apps/discovery/errors.py
class DiscoveryError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class TransientSourceError(DiscoveryError):
    pass


class RateLimitedSourceError(TransientSourceError):
    def __init__(self, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("SOURCE_RATE_LIMITED")


class PermanentSourceError(DiscoveryError):
    pass


class InvalidSourcePayload(PermanentSourceError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("INVALID_SOURCE_PAYLOAD", detail)


class UnknownDiscoveryAdapter(PermanentSourceError):
    def __init__(self, source_code: str) -> None:
        self.source_code = source_code
        super().__init__("UNKNOWN_DISCOVERY_ADAPTER", source_code)
```

`BoundingBox.__post_init__` must reject non-WGS84 coordinates, `west >= east` and `south >= north`; `DiscoveryRequest.__post_init__` rejects empty `dataset_version`, empty `correlation_id`, empty `external_categories`, and `result_limit <= 0`. Empty internal `category_ids` has already been expanded per source before this boundary, so an adapter can never interpret an empty tuple as an unbounded query. `DiscoveryAdapter.discover()` performs only provider I/O; persistence, normalization and retries remain outside the adapter.

- [ ] **Step 1: Написать failing registry/contract tests**

```python
# backend/apps/discovery/tests/test_registry.py
def test_registry_returns_adapter_configured_for_source(settings):
    settings.DISCOVERY_ADAPTERS = {
        "fixture": "apps.discovery.tests.fakes.FixtureDiscoveryAdapter"
    }
    adapter = get_adapter("fixture")
    assert adapter.source_code == "fixture"


# backend/apps/discovery/tests/contracts.py
def assert_adapter_contract(adapter: DiscoveryAdapter, request: DiscoveryRequest) -> None:
    assert adapter.resolve_dataset_version()
    payloads = list(adapter.discover(request))
    assert payloads
    for source_payload in payloads:
        assert source_payload.external_id
        assert source_payload.provenance.dataset_version
        parsed = adapter.parse_payload(source_payload)
        assert parsed.external_id == source_payload.external_id


# backend/apps/discovery/tests/test_registry.py
def test_contract_probe_executes_shared_contract():
    adapter = make_contract_adapter()
    request = make_discovery_request(external_categories=("dentist",))
    assert_adapter_contract(adapter, request)
```

`make_contract_adapter()` и `make_discovery_request()` живут в `tests/fakes.py`; первый fake возвращает минимум один payload и parsed record. Поэтому helper является collectable test path, а не dead example. Tests также требуют `UnknownDiscoveryAdapter("missing")`, immutable value objects, invalid `BoundingBox`, empty dataset version, and non-positive `result_limit`.

- [ ] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_registry.py -q
```

Expected: FAIL с отсутствующим discovery package.

- [ ] **Step 3: Реализовать exact domain types и errors**

Создать `domain.py` и `errors.py` exactly as declared in the Interfaces block. `InvalidSourcePayload` is the sole parser-error type passed from an adapter to persistence; network timeouts use `TransientSourceError("SOURCE_TIMEOUT")`, 429 uses `RateLimitedSourceError(retry_after_seconds=...)`, and unrecoverable provider configuration/schema errors use `PermanentSourceError(code)`.

- [ ] **Step 4: Реализовать lazy registry**

Registry читает dotted paths из `settings.DISCOVERY_ADAPTERS`, импортирует через `import_string`, кэширует factory, но возвращает новый adapter instance для каждого source run. Никаких global mutable HTTP clients.

- [ ] **Step 5: Перенести временные domain types из Task 12**

`sources.services` imports `SourcePayload` and `RawBusinessRecord` only from `apps.discovery.domain`; replace temporary `SourcePayloadParseError` with `InvalidSourcePayload`. Keep `SourceRecordConflictError` in `apps.sources.domain`, so Task 12 persistence signature and conflict tests do not change. This is a refactor only after Task 12 GREEN.

- [ ] **Step 6: Проверить GREEN**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_registry.py apps/sources/tests/test_persist_source_payload.py -q
docker compose run --rm backend ruff check apps/discovery apps/sources
```

Expected: PASS/exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/discovery backend/apps/sources backend/config/settings
git commit -m "feat: define source-neutral discovery adapter contract"
```

---

### Task 14: Реализовать Overture Places adapter на официальном Python client

**Files:**
- Create: `backend/apps/discovery/adapters/__init__.py`
- Create: `backend/apps/discovery/adapters/overture.py`
- Create: `backend/apps/discovery/tests/test_overture_adapter.py`
- Create: `backend/tests/fixtures/sources/overture/place_taxonomy.json`
- Create: `backend/tests/fixtures/sources/overture/place_legacy_categories.json`
- Modify: `backend/apps/discovery/tests/contracts.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/requirements/base.in`
- Modify: `backend/requirements/base.txt`
- Modify: `backend/requirements/development.txt`
- Modify: `backend/requirements/production.txt`

**Interfaces:**
- Consumes: official `overturemaps.core.get_latest_release`, `record_batch_reader`; Task 13 contract.
- Produces: `OvertureAdapter(source_code="overture")`; `OvertureClient.iter_places(...)` wrapper.

```python
class OvertureClient(Protocol):
    def latest_release(self) -> str: ...
    def iter_places(
        self,
        *,
        bbox: tuple[float, float, float, float],
        release: str,
    ) -> Iterator[dict[str, JSONValue]]: ...
```

- [ ] **Step 1: Добавить реальные representative fixtures**

`place_taxonomy.json` содержит полный минимально нужный shape: `id`, `version`, `names.primary`, `taxonomy.primary/hierarchy`, `basic_category`, `addresses`, `phones`, `websites`, `socials`, `emails`, `confidence`, `geometry`, `bbox`. `place_legacy_categories.json` заменяет taxonomy fields на `categories.primary/alternate`. Fixtures содержат вымышленные business/contact values и поле `_fixture_notice`, поэтому не распространяют реальные контакты.

- [ ] **Step 2: Написать failing parser/contract tests**

```python
def test_overture_parser_prefers_new_taxonomy(overture_adapter, taxonomy_payload):
    source_payload = SourcePayload(
        external_id=taxonomy_payload["id"],
        payload=taxonomy_payload,
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="2026-08-19.0",
            source_url=None,
            attribution="Overture Maps Foundation",
            license_code="CDLA-Permissive-2.0/Apache-2.0",
        ),
    )
    record = overture_adapter.parse_payload(source_payload)
    assert record.external_id == taxonomy_payload["id"]
    assert record.raw_category == "dentist"
    assert record.raw_name == "Alanya Test Diş Kliniği"
    assert (record.longitude, record.latitude) == (32.001, 36.544)


def test_overture_parser_falls_back_to_legacy_categories(overture_adapter, legacy_payload):
    record = overture_adapter.parse_payload(make_payload(legacy_payload))
    assert record.raw_category == "dentist"


def test_overture_adapter_satisfies_shared_contract(
    overture_adapter, overture_discovery_request
):
    assert_adapter_contract(overture_adapter, overture_discovery_request)
```

Discover test injects fake client and asserts request bbox/release, category filtering и `result_limit` without asserting mock existence. Provider category semantics are exact: Overture emits the selected provider value (`taxonomy.primary`, then `basic_category`, then `categories.primary`) as `raw_category` (for example `dentist`), never the internal slug or Russian label. `external_categories` всегда non-empty и содержит только значения из active mappings выбранного source.

Parser preserves provider order in `phones`, `emails`, `websites`; `socials` groups URLs by provider key in `raw_social_urls`. Missing collections become empty tuples/dict, never `None`. Address picks the first structured address exactly as a readable raw string while the complete address array remains in MinIO.

- [ ] **Step 3: Запустить RED**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_overture_adapter.py -q
```

Expected: FAIL с отсутствующим `OvertureAdapter`.

- [ ] **Step 4: Реализовать client wrapper и streaming adapter**

Добавить `overturemaps==1.0.2` в `base.in` и перекомпилировать все три lockfiles exact commands из Task 2. Wrapper:

```python
reader = record_batch_reader(
    "place",
    bbox=bbox,
    release=release,
    connect_timeout=source.timeout_seconds,
    request_timeout=source.timeout_seconds,
    stac=True,
)
for batch in reader:
    for row in batch.to_pylist():
        yield make_json_compatible(row)
```

Не материализовать всю Alanya выборку в list. Category filter применяется к parsed `taxonomy.primary`, `basic_category` или legacy `categories.primary` и пропускает только `DiscoveryRequest.external_categories`; пустой tuple отклонён domain contract до provider I/O. `resolve_dataset_version()` получает release через STAC один раз; orchestration записывает его в `CampaignSourceRun` и передаёт как `DiscoveryRequest.dataset_version`. Adapter использует это значение и не меняет его внутри iterator.

- [ ] **Step 5: Классифицировать client failures**

Timeout/network → `TransientSourceError("SOURCE_TIMEOUT")`; unknown release/schema → `PermanentSourceError("INVALID_SOURCE_PAYLOAD")`; invalid geometry не мешает raw storage, parser возвращает исходные числовые coordinates, а normalization преобразует их в `location=None` + `INVALID_COORDINATES`. Отсутствующие coordinates становятся `None` + `MISSING_COORDINATES`.

- [ ] **Step 6: Проверить GREEN и общий adapter contract**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_overture_adapter.py apps/discovery/tests/test_registry.py -q
docker compose run --rm backend ruff check apps/discovery
```

Expected: PASS/exit 0. Никакого live S3/STAC call в обязательных tests.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/discovery backend/tests/fixtures backend/requirements backend/config/settings
git commit -m "feat: add Overture Places discovery adapter"
```

---

### Task 15: Реализовать OSM/Overpass adapter с configurable endpoint

**Files:**
- Create: `backend/apps/discovery/adapters/osm.py`
- Create: `backend/apps/discovery/config.py`
- Create: `backend/apps/discovery/osm_query.py`
- Create: `backend/apps/discovery/tests/test_osm_query.py`
- Create: `backend/apps/discovery/tests/test_osm_adapter.py`
- Create: `backend/apps/discovery/tests/test_production_settings.py`
- Create: `backend/tests/fixtures/sources/osm/alanya_elements.json`
- Modify: `backend/apps/discovery/tests/contracts.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/settings/production.py`
- Modify: `backend/requirements/base.in`
- Modify: `backend/requirements/base.txt`
- Modify: `backend/requirements/development.txt`
- Modify: `backend/requirements/production.txt`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `OVERPASS_URL`, `SOURCE_USER_AGENT`, Source operational limits, Task 13 contract.
- Produces: `build_overpass_query(bbox, selectors) -> str`; `OverpassClient.fetch(query) -> dict`; `OpenStreetMapAdapter(source_code="osm")`.

- [ ] **Step 1: Написать failing query builder test**

```python
def test_query_builder_uses_selected_mappings_and_bounded_resources():
    query = build_overpass_query(
        bbox=BoundingBox(west=31.70, south=36.30, east=32.65, north=36.75),
        selectors=("amenity=dentist", "tourism=hotel"),
        timeout_seconds=60,
        max_size_bytes=268_435_456,
    )
    assert query == (
        "[out:json][timeout:60][maxsize:268435456];"
        "(nwr[\"amenity\"=\"dentist\"](36.3,31.7,36.75,32.65);"
        "nwr[\"tourism\"=\"hotel\"](36.3,31.7,36.75,32.65););"
        "out center tags;"
    )
```

```python
@pytest.mark.parametrize(
    "selector",
    ['amenity=dentist\";out;', "amenity=dentist\nnode(0,0,1,1)", "amenity"],
)
def test_query_builder_rejects_selector_injection(selector):
    with pytest.raises(InvalidSelector):
        build_overpass_query(
            bbox=BoundingBox(31.70, 36.30, 32.65, 36.75),
            selectors=(selector,),
            timeout_seconds=60,
            max_size_bytes=268_435_456,
        )


def test_query_builder_accepts_only_documented_selector_alphabet():
    query = build_overpass_query(
        bbox=BoundingBox(31.70, 36.30, 32.65, 36.75),
        selectors=("contact:healthcare=dentist-clinic",),
        timeout_seconds=60,
        max_size_bytes=268_435_456,
    )
    assert '["contact:healthcare"="dentist-clinic"]' in query
```

Implementation сначала проверяет каждый полный selector expression regex `^[a-z0-9_:.-]+=[a-z0-9_:.-]+$`, затем безопасно разделяет ровно по первому `=`; quote/newline никогда не достигают query template.

- [ ] **Step 2: Написать failing parser/error tests**

```python
def test_osm_parser_uses_node_coordinates_and_way_center(osm_adapter, osm_fixture):
    records = [osm_adapter.parse_payload(item) for item in make_osm_payloads(osm_fixture)]
    assert records[0].external_id == "node/101"
    assert (records[0].longitude, records[0].latitude) == (32.002, 36.545)
    assert records[1].external_id == "way/202"
    assert (records[1].longitude, records[1].latitude) == (32.010, 36.550)
    assert records[0].raw_category == "amenity=dentist"
```

HTTP tests через `respx`: 200 JSON → payloads; 429 с `Retry-After` → `RateLimitedSourceError`; 504 → `TransientSourceError`; 400 → `PermanentSourceError`; invalid JSON → `InvalidSourcePayload`.

Тот же module обязан вызвать общий helper реальным adapter с injected fake HTTP client:

```python
def test_osm_adapter_satisfies_shared_contract(osm_adapter, osm_discovery_request):
    assert_adapter_contract(osm_adapter, osm_discovery_request)
```

`test_production_settings.py` запускает отдельный Django process, чтобы проверить именно import-time behavior `production.py`, а не только pure helper:

```python
def test_production_settings_reject_placeholder_source_user_agent():
    environment = {
        **os.environ,
        "DJANGO_SECRET_KEY": "production-test-key-with-at-least-32-characters",
        "DJANGO_ALLOWED_HOSTS": "lbi.example.test",
        "DATABASE_URL": "postgis://lbi:test@postgres:5432/lbi",
        "REDIS_URL": "redis://redis:6379/0",
        "S3_ENDPOINT_URL": "https://s3.example.test",
        "S3_ACCESS_KEY_ID": "test-access-key",
        "S3_SECRET_ACCESS_KEY": "test-secret-key",
        "S3_BUCKET_NAME": "lbi-production-test",
        "OVERPASS_URL": "https://overpass.example.test/api/interpreter",
        "OSM_DATASET_VERSION": "2026-08-snapshot",
        "SOURCE_USER_AGENT": "local-business-intelligence/0.1 (+https://example.invalid/contact)",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--settings=config.settings.production"],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SOURCE_USER_AGENT" in result.stdout + result.stderr
```

Pure validator дополнительно параметризован для empty `OVERPASS_URL`, empty `OSM_DATASET_VERSION`, `.invalid`, `.example`, `localhost` и user agent без URI/email; отдельный positive test принимает HTTPS endpoint и реальный contact URI.

- [ ] **Step 3: Запустить RED**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_osm_query.py apps/discovery/tests/test_osm_adapter.py apps/discovery/tests/test_production_settings.py -q
```

Expected: FAIL с отсутствующими builder/adapter.

- [ ] **Step 4: Реализовать query builder/client/parser**

Добавить `httpx==0.28.1` в `base.in`, перекомпилировать все три lockfiles exact commands из Task 2. `OverpassClient` делает один synchronous `httpx.Client.post(url, data={"data": query})` с explicit timeout и headers:

```python
{
    "User-Agent": settings.SOURCE_USER_AGENT,
    "Accept": "application/json",
}
```

`SOURCE_USER_AGENT` содержит product name и реальный contact URI/email. `OVERPASS_URL` пуст по умолчанию; live adapter поднимает `PermanentSourceError("OVERPASS_NOT_CONFIGURED")`, а tests/e2e inject fake client. `apps.discovery.config.validate_live_osm_configuration(...)` реализует один pure validation contract; `production.py` безусловно вызывает его при import, поэтому development placeholder нельзя случайно перенести в live deployment.

OSM contact extraction is exact: phones come from `contact:phone` then `phone`, emails from `contact:email` then `email`, websites from `contact:website` then `website` then `url`; semicolon-separated values are trimmed but otherwise remain raw. `contact:facebook`, `contact:instagram`, `contact:twitter`/`contact:x` populate provider-keyed `raw_social_urls`. `addr:*` fields are joined in order `street`, `housenumber`, `suburb`, `city`, `postcode`; missing values stay empty.

`.env.example` добавляет безопасные placeholders:

```dotenv
OVERPASS_URL=
OSM_DATASET_VERSION=
SOURCE_USER_AGENT=local-business-intelligence/0.1 (+https://example.invalid/contact)
```

Значение `example.invalid` — только development placeholder. `production.py` отказывает в запуске live OSM adapter без непустых `OVERPASS_URL`, `OSM_DATASET_VERSION` и контактного `SOURCE_USER_AGENT`, а также явно отклоняет `.invalid`, `.example`, `localhost` и строку без URI/email; fixture mode эти checks не обходит вне testing settings.

- [ ] **Step 5: Реализовать mapping semantics**

Если campaign выбрала categories, selectors берутся из active `SourceCategoryMapping.external_category` для этих category IDs отдельно для каждого выбранного source. Пустой `category_ids` означает все active mappings выбранного source: для OSM seed это `amenity=dentist`, `office=estate_agent`, `tourism=hotel`, `shop=beauty`, для Overture — `dentist`, `real_estate_agent`, `hotel`, `beauty_salon`. Отсутствие mappings отклоняется ещё в `create_campaign`; defensive повторная проверка в `start_campaign` возвращает `SOURCE_HAS_NO_ACTIVE_MAPPINGS` до создания/enqueue source runs, если configuration изменилась после создания draft. OSM parser применяет tag precedence `amenity`, `office`, `tourism`, `shop` и возвращает exact `key=value` как `raw_category`.

`OpenStreetMapAdapter.resolve_dataset_version()` возвращает `OSM_DATASET_VERSION` для production snapshot; без него только в development/test строит retrieval marker `overpass-live:{sha256(normalized_endpoint)[:12]}:{run_started_at_rfc3339}` с injected clock. Значение вычисляется один раз при старте source run, сохраняется в `CampaignSourceRun.source_dataset_version` и передаётся каждому payload provenance. Retry существующего run использует сохранённое значение и не вызывает resolver повторно.

- [ ] **Step 6: Проверить GREEN и contract**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_osm_query.py apps/discovery/tests/test_osm_adapter.py -q
docker compose run --rm backend pytest apps/discovery/tests -q
docker compose run --rm backend ruff check apps/discovery
```

Expected: all PASS; no request reaches public Overpass.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/discovery backend/tests/fixtures backend/requirements backend/config/settings .env.example
git commit -m "feat: add configurable OpenStreetMap discovery adapter"
```

---

### Task 16: Реализовать versioned Turkish normalization и materialized result

**Files:**
- Create: `backend/apps/normalization/apps.py`
- Create: `backend/apps/normalization/domain.py`
- Create: `backend/apps/normalization/rules/names.py`
- Create: `backend/apps/normalization/rules/phones.py`
- Create: `backend/apps/normalization/rules/urls.py`
- Create: `backend/apps/normalization/rules/emails.py`
- Create: `backend/apps/normalization/rules/addresses.py`
- Create: `backend/apps/normalization/rules/socials.py`
- Create: `backend/apps/normalization/rules/coordinates.py`
- Create: `backend/apps/normalization/services.py`
- Create: `backend/apps/normalization/tests/test_names.py`
- Create: `backend/apps/normalization/tests/test_phones.py`
- Create: `backend/apps/normalization/tests/test_urls.py`
- Create: `backend/apps/normalization/tests/test_emails.py`
- Create: `backend/apps/normalization/tests/test_addresses.py`
- Create: `backend/apps/normalization/tests/test_socials.py`
- Create: `backend/apps/normalization/tests/test_service.py`
- Create: `backend/apps/sources/migrations/0003_normalizedsourcerecord.py`
- Modify: `backend/apps/sources/models.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/requirements/base.in`
- Modify: `backend/requirements/base.txt`
- Modify: `backend/requirements/development.txt`
- Modify: `backend/requirements/production.txt`

**Interfaces:**
- Consumes: `RawBusinessRecord`, `resolve_category`, source record raw fields.
- Produces: exact `GeoPoint`, `NormalizedBusinessData`, `NormalizationResult`, `NormalizedStrings(values: tuple[str, ...], warnings: tuple[str, ...])`; `normalize_business_record(raw, *, category_id) -> NormalizationResult`; `normalize_emails(values) -> NormalizedStrings`; `normalize_address(raw_address) -> str`; `normalize_social_urls(values) -> dict[str, tuple[str, ...]]`; `materialize_normalization(source_record_id) -> NormalizedSourceRecord | None`. `NormalizedSourceRecord` implements every field in spec §9.6: `source_record`, `display_name`, `normalized_name`, `match_name`, nullable `category`, `address_text`, nullable country/province/district/neighborhood, nullable location, `phones`, `emails`, `websites`, `social_urls`, `attributes`, `warnings`, `normalization_version`, timestamps.

```python
@dataclass(frozen=True)
class NormalizedStrings:
    values: tuple[str, ...]
    warnings: tuple[str, ...]


def normalize_emails(values: Iterable[str]) -> NormalizedStrings: ...
def normalize_address(raw_address: str | None) -> str: ...
def normalize_social_urls(
    values: Mapping[str, Iterable[str]],
) -> dict[str, tuple[str, ...]]: ...
def materialize_normalization(source_record_id: UUID) -> NormalizedSourceRecord | None: ...
```

- [ ] **Step 1: Написать failing Turkish name tests**

```python
@pytest.mark.parametrize(
    ("raw", "display", "normalized", "match"),
    [
        (
            "  Alanya Smile Diş Kliniği LTD. ŞTİ. ",
            "Alanya Smile Diş Kliniği",
            "alanya smile diş kliniği",
            "alanya smile dis klinigi",
        ),
        ("GÖZDE GÜZELLİK A.Ş.", "GÖZDE GÜZELLİK", "gözde güzellik", "gozde guzellik"),
    ],
)
def test_normalize_turkish_business_name(raw, display, normalized, match):
    assert normalize_name(raw) == NameParts(display, normalized, match)
```

```python
def test_legal_suffix_is_removed_only_at_end_of_name():
    assert normalize_name("A.Ş. Yapı Market") == NameParts(
        "A.Ş. Yapı Market", "a.ş. yapı market", "a s yapi market"
    )
    assert normalize_name("A.Ş. Yapı Market A.Ş.") == NameParts(
        "A.Ş. Yapı Market", "a.ş. yapı market", "a s yapi market"
    )
```

Implementation удаляет legal suffix одним end-anchored expression после whitespace normalization; глобальная замена `A.Ş.` запрещена этим regression test.

- [ ] **Step 2: Написать failing phone/URL/coordinate tests**

```python
def test_turkish_mobile_phone_is_e164():
    assert normalize_phone("0532 123 45 67", default_region="TR") == "+905321234567"


def test_url_normalizes_host_and_removes_fragment_without_dropping_path_query():
    assert normalize_url("HTTPS://Example.COM/hizmet?x=1#team") == "https://example.com/hizmet?x=1"


@pytest.mark.parametrize("lon,lat", [(181, 36), (32, 91)])
def test_invalid_coordinates_are_rejected(lon, lat):
    with pytest.raises(InvalidCoordinates):
        normalize_coordinates(lon, lat)
```

`test_emails.py` требует `normalize_emails([" Test@Example.COM ", "bad"]) == NormalizedStrings(("test@example.com",), ("INVALID_EMAIL",))`; `test_addresses.py` требует `normalize_address("  Atatürk  Cd.\n 12 ") == "Atatürk Cd. 12"` и `normalize_address(None) == ""`; `test_socials.py` проверяет canonical HTTPS URL, lowercase host, сохранение provider keys и stable first-seen deduplication. В aggregate test координаты `181,36` дают `location is None` и `INVALID_COORDINATES`, без исключения.

- [ ] **Step 3: Запустить RED для pure rules**

```bash
docker compose run --rm backend pytest apps/normalization/tests/test_names.py apps/normalization/tests/test_phones.py apps/normalization/tests/test_urls.py apps/normalization/tests/test_emails.py apps/normalization/tests/test_addresses.py apps/normalization/tests/test_socials.py -q
```

Expected: FAIL с отсутствующими functions.

- [ ] **Step 4: Реализовать minimal pure rules**

Добавить `phonenumbers==9.0.38` в `base.in` и перекомпилировать все три lockfiles exact commands из Task 2. Name pipeline: NFKC → whitespace collapse → terminal legal suffix removal → `casefold` → explicit Turkish transliteration только для `match_name`. Collections deduplicate while retaining first-seen order. `normalize_emails` lowercases valid addresses, drops invalid values и возвращает `INVALID_EMAIL` в result warnings; `normalize_address` applies NFKC/whitespace collapse and returns empty string for null input. `normalize_social_urls` принимает provider→URLs, пропускает только `http/https`, canonicalizes host/fragment и сохраняет provider keys. Invalid optional phone/email/URL gives warning, не rejects record. Out-of-range coordinates return `location=None` and warning `INVALID_COORDINATES`; absent coordinates return `location=None` and `MISSING_COORDINATES`; neither raises from the aggregate normalizer. Geography FKs копируются из campaign `SearchArea` как scope сбора, а не геокодируются из `raw_address`; записать `attributes.geography_basis="search_area"`.

- [ ] **Step 5: Написать failing aggregate/materialization tests**

```python
@pytest.mark.django_db
def test_unknown_category_is_normalized_with_warning(source_record):
    result = materialize_normalization(source_record.id)
    assert result.category_id is None
    assert result.warnings == ["UNKNOWN_CATEGORY"]
    assert result.normalization_version == "tr-v1"
    source_record.refresh_from_db()
    assert source_record.normalization_status == SourceRecord.NormalizationStatus.NORMALIZED


@pytest.mark.django_db
def test_missing_name_rejects_but_preserves_source_record(source_record_without_name):
    result = materialize_normalization(source_record_without_name.id)
    assert result is None
    source_record_without_name.refresh_from_db()
    assert source_record_without_name.normalization_status == "rejected"
    assert source_record_without_name.normalization_error_code == "MISSING_NAME"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("longitude", "latitude", "warning"),
    [(181.0, 36.0, "INVALID_COORDINATES"), (None, None, "MISSING_COORDINATES")],
)
def test_optional_coordinate_problem_keeps_record_normalized(
    source_record_factory, longitude, latitude, warning
):
    record = source_record_factory(longitude=longitude, latitude=latitude)
    normalized = materialize_normalization(record.id)
    record.refresh_from_db()
    assert record.normalization_status == "normalized"
    assert normalized.location is None
    assert warning in normalized.warnings
```

Test повторного `materialize_normalization` доказывает one-to-one upsert и одну normalized row. `materialize_normalization` единолично владеет переходами, вызванными normalization rules (`pending → normalized|rejected|failed`), и соответствующими counters; Task 12 отдельно владеет parser-failed insert, Task 17 — AOI rejection через `reject_source_record_once`. Pure rules и Celery wrappers counters не изменяют. Каждый outcome учитывается ровно один раз с общим lock order; `normalized`/`rejected` также увеличивает одноимённый campaign counter.

- [ ] **Step 6: Запустить aggregate RED**

```bash
docker compose run --rm backend pytest apps/normalization/tests/test_service.py -q
```

Expected: FAIL с отсутствующим model/service.

- [ ] **Step 7: Реализовать model/service и проверить полный GREEN**

`NormalizedSourceRecord` fields строго из spec. `materialize_normalization` использует `transaction.atomic()` + `select_for_update()` на source record, source run и campaign в порядке `campaign → source run → source record`, получает category mapping, вызывает pure function, upserts one-to-one result и обновляет status/counters ровно один раз. Все остальные services используют тот же lock order, чтобы не создавать deadlock.

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend pytest apps/normalization/tests apps/sources/tests -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend ruff check apps/normalization apps/sources
```

Expected: all PASS/exit 0.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/normalization backend/apps/sources backend/requirements backend/config/settings
git commit -m "feat: normalize Turkish source records"
```

---

### Task 17: Связать campaign orchestration, Celery tasks и долговечный progress

**Files:**
- Create: `backend/apps/campaigns/migrations/0002_pipeline_retry_reservation.py`
- Create: `backend/apps/campaigns/progress.py`
- Create: `backend/apps/campaigns/retries.py`
- Create: `backend/apps/campaigns/tests/test_progress.py`
- Create: `backend/apps/campaigns/tests/test_retries.py`
- Create: `backend/apps/discovery/services.py`
- Create: `backend/apps/discovery/tasks.py`
- Create: `backend/apps/discovery/tests/conftest.py`
- Create: `backend/apps/discovery/tests/test_services.py`
- Create: `backend/apps/discovery/tests/test_tasks.py`
- Create: `backend/apps/normalization/tasks.py`
- Create: `backend/apps/normalization/tests/test_tasks.py`
- Create: `backend/apps/sources/storage/factory.py`
- Create: `backend/config/celery_retry.py`
- Modify: `backend/apps/campaigns/models.py`
- Modify: `backend/apps/campaigns/services.py`
- Modify: `backend/apps/campaigns/api/serializers.py`
- Modify: `backend/apps/campaigns/api/views.py`
- Modify: `backend/apps/campaigns/api/urls.py`
- Modify: `backend/apps/campaigns/tests/test_api.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/conftest.py`

**Interfaces:**
- Consumes: Tasks 10–16 models, adapters, storage и normalizer.
- Produces:

```python
def start_campaign(*, campaign_id: UUID, actor: User, enqueue: Enqueue) -> DiscoveryCampaign: ...
def build_discovery_request(source_run: CampaignSourceRun) -> DiscoveryRequest: ...
def run_source_discovery_now(
    *, source_run_id: UUID, adapter: DiscoveryAdapter, store: RawPayloadStore,
    enqueue_normalization: Callable[[UUID], None]
) -> None: ...
def reject_source_record_once(*, source_record_id: UUID, error_code: str) -> bool: ...
def make_delivery_token(*, task_id: str | None, retries: int) -> str: ...
def retry_or_requeue(task: Task, *, exc: Exception, countdown: int) -> NoReturn: ...
def consume_source_retry(*, source_run_id: UUID, delivery_token: str) -> bool: ...
def consume_normalization_retry(*, source_record_id: UUID, delivery_token: str) -> bool: ...
def mark_source_discovery_exhausted(
    *, source_run_id: UUID, error_code: str, error_detail: str = ""
) -> CampaignSourceRun.Status: ...
def fail_source_record_once(*, source_record_id: UUID, error_code: str) -> bool: ...
def finalize_source_run(
    *, source_run_id: UUID, status: Literal["completed", "completed_with_errors", "failed"],
    error_code: str | None = None, error_detail: str = ""
) -> CampaignSourceRun.Status: ...
def try_finalize_campaign(campaign_id: UUID) -> DiscoveryCampaign.Status: ...
def get_campaign_progress(campaign_id: UUID, actor: User) -> CampaignProgress: ...
def run_campaign_synchronously(
    campaign_id: UUID,
    *,
    get_adapter: Callable[[str], DiscoveryAdapter],
    store: RawPayloadStore,
) -> None: ...  # test support only

@shared_task(bind=True, max_retries=None, name="apps.discovery.tasks.run_discovery_campaign")
def run_discovery_campaign(self, campaign_id: str) -> None: ...

@shared_task(bind=True, max_retries=None, name="apps.discovery.tasks.run_source_discovery")
def run_source_discovery(self, source_run_id: str) -> None: ...

@shared_task(bind=True, max_retries=None, name="apps.normalization.tasks.normalize_source_record")
def normalize_source_record(self, source_record_id: str) -> None: ...
```

`make_delivery_token` возвращает `{task_id}:{retries}`; fallback `direct:{retries}` разрешён только для прямого unit-вызова `.run()`, production Celery request обязан иметь task ID. `retry_or_requeue` вызывает `task.retry`, а transport `OperationalError` переводит в `Reject(requeue=True)`; все infrastructure и business retry paths обязаны идти через него. `consume_source_retry` и `consume_normalization_retry` принимают token и возвращают `True`, только если business retry разрешён. Первое решение для token и увеличение соответствующего durable counter сохраняются одной transaction в `PipelineRetryReservation`; повтор token возвращает прежнее решение без нового списания. `False` означает, что лимит уже исчерпан. Celery `request.retries` участвует только в token/backoff и никогда напрямую не определяет provider/storage exhaustion.

- [ ] **Step 1: Написать failing campaign start API test**

```python
@pytest.mark.django_db(transaction=True)
def test_start_draft_campaign_queues_work_after_commit(
    auth_client, campaign, enqueue_spy, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = auth_client.post(f"/api/v1/campaigns/{campaign.id}/start/")
        assert enqueue_spy.ids == []
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    campaign.refresh_from_db()
    assert campaign.status == DiscoveryCampaign.Status.QUEUED
    assert len(callbacks) == 1
    callbacks[0]()
    assert enqueue_spy.ids == [str(campaign.id)]


@pytest.mark.django_db
def test_starting_same_campaign_twice_is_rejected(auth_client, running_campaign):
    response = auth_client.post(f"/api/v1/campaigns/{running_campaign.id}/start/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CAMPAIGN_NOT_DRAFT"
```

Test вручную выполняет captured on-commit callback; assertion внутри capture context доказывает, что task не отправлена до commit boundary.

- [ ] **Step 2: Запустить start RED**

```bash
docker compose run --rm backend pytest apps/campaigns/tests/test_api.py -k start -q
```

Expected: FAIL с 404 для `/start/`.

- [ ] **Step 3: Реализовать atomic start transition**

`start_campaign` делает `select_for_update()`, проверяет owner/status/sources и повторно разрешает non-empty mappings для каждого source (защита от configuration drift после создания draft). Только затем он создаёт `CampaignSourceRun`, устанавливает `total_jobs`, `status=queued` и через `transaction.on_commit` вызывает injected `enqueue(campaign_id)`. При пустом mapping transaction остаётся `draft` и API возвращает 409 `SOURCE_HAS_NO_ACTIVE_MAPPINGS`. Worker атомарно переводит campaign `queued → running` ровно один раз; повторный delivery для `running`/terminal campaign является no-op. Endpoint возвращает 202 и не знает Celery task ID.

- [ ] **Step 4: Написать failing source pipeline test**

```python
@pytest.mark.django_db(transaction=True)
def test_source_run_streams_payloads_to_storage_and_enqueues_record_ids(
    queued_source_run, fixture_adapter, fake_store, normalization_queue
):
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=fixture_adapter,
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )
    queued_source_run.refresh_from_db()
    assert queued_source_run.source_dataset_version == "fixture-2026-09"
    assert queued_source_run.status == CampaignSourceRun.Status.NORMALIZING
    assert queued_source_run.stored_records == 2
    assert SourceRecord.objects.count() == 2
    assert normalization_queue == list(SourceRecord.objects.order_by("created_at").values_list("id", flat=True))
```

`backend/apps/discovery/tests/conftest.py` задаёт `adapter_factory(payloads=(), parsed=None, error=None)`, реализующий весь `DiscoveryAdapter` и fixed version `fixture-2026-09`; `queued_source_run` — единственный OSM run кампании, переведённой `start_campaign(..., enqueue=noop)` в `queued`; `normalization_queue` — новый `list[UUID]`; `fake_store` — `InMemoryRawPayloadStore`. Добавить concrete edge tests:

```python
@pytest.mark.django_db(transaction=True)
def test_empty_adapter_completes_source_run_with_zero_counters(
    queued_source_run, adapter_factory, fake_store
):
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter_factory(payloads=()),
        store=fake_store,
        enqueue_normalization=lambda _: pytest.fail("nothing may be enqueued"),
    )
    queued_source_run.refresh_from_db()
    assert queued_source_run.status == CampaignSourceRun.Status.COMPLETED
    assert (
        queued_source_run.discovered_records,
        queued_source_run.stored_records,
        queued_source_run.normalized_records,
        queued_source_run.rejected_records,
        queued_source_run.failed_records,
    ) == (0, 0, 0, 0, 0)


@pytest.mark.django_db(transaction=True)
def test_start_rechecks_mapping_drift_before_enqueue(
    owner, single_source_draft_campaign
):
    SourceCategoryMapping.objects.filter(
        source__campaignsource__campaign=single_source_draft_campaign
    ).update(is_active=False)
    queued: list[str] = []
    with pytest.raises(CampaignValidationError) as error:
        start_campaign(
            campaign_id=single_source_draft_campaign.id,
            actor=owner,
            enqueue=lambda campaign_id: queued.append(str(campaign_id)),
        )
    single_source_draft_campaign.refresh_from_db()
    assert error.value.code == "SOURCE_HAS_NO_ACTIVE_MAPPINGS"
    assert single_source_draft_campaign.status == DiscoveryCampaign.Status.DRAFT
    assert queued == []


@pytest.mark.django_db(transaction=True)
def test_conflicting_payload_is_counted_once_and_does_not_stop_stream(
    queued_source_run, payload, parsed, adapter_factory, fake_store, normalization_queue
):
    changed = replace(payload, payload={**payload.payload, "name": "Changed"})
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter_factory(payloads=(payload, changed), parsed=parsed),
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )
    queued_source_run.refresh_from_db()
    assert SourceRecord.objects.filter(source_run=queued_source_run).count() == 1
    assert SourceRecordConflict.objects.filter(source_run=queued_source_run).count() == 1
    assert (
        queued_source_run.discovered_records,
        queued_source_run.stored_records,
        queued_source_run.failed_records,
    ) == (2, 2, 1)
    assert len(normalization_queue) == 1
```

Root `backend/conftest.py` дополнительно создаёт `running_source_run`: campaign уже `running`, run уже `running`, source имеет `max_retries=3`, `source_retry_count=0`; это состояние непосредственно предшествует вызову synchronous core и доступно cross-app retry tests. Там же определить `running_source_run_with_pending_record`, `source_run_with_two_records`, `one_pending_record` и `ready_run_with_one_pending_record` с согласованными counters. `backend/apps/discovery/tests/conftest.py` оставляет только adapter-specific factories/queues. В `test_tasks.py` импортировать `Mock`, `patch` из `unittest.mock`, `OperationalError as BrokerOperationalError`, `Reject`, `Retry` из `celery.exceptions`, `OperationalError` из `django.db`, `PipelineRetryReservation`, task object и typed errors. Exact task-wrapper tests:

```python
@pytest.mark.django_db(transaction=True)
def test_transient_source_error_consumes_one_durable_retry_and_retries(
    running_source_run, monkeypatch
):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with patch.object(run_source_discovery, "retry", side_effect=Retry()) as retry:
        with pytest.raises(Retry):
            run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert running_source_run.status == CampaignSourceRun.Status.RUNNING
    retry.assert_called_once()
    assert "max_retries" not in retry.call_args.kwargs


@pytest.mark.django_db(transaction=True)
def test_retry_publish_failure_redelivery_reuses_the_same_reservation(
    running_source_run, monkeypatch
):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    monkeypatch.setattr(
        "apps.discovery.tasks.make_delivery_token",
        Mock(return_value="task-42:0"),
    )
    with patch.object(
        run_source_discovery,
        "retry",
        side_effect=BrokerOperationalError("retry publish failed"),
    ):
        with pytest.raises(Reject) as rejected:
            run_source_discovery.run(str(running_source_run.id))
    assert rejected.value.requeue is True
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert PipelineRetryReservation.objects.filter(
        scope="source_discovery",
        work_id=running_source_run.id,
        delivery_token="task-42:0",
        allowed=True,
    ).count() == 1

    with patch.object(run_source_discovery, "retry", side_effect=Retry()):
        with pytest.raises(Retry):
            run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert running_source_run.status == CampaignSourceRun.Status.RUNNING


@pytest.mark.django_db(transaction=True)
def test_exhausted_source_budget_marks_empty_run_failed_without_retry(
    running_source_run, monkeypatch
):
    running_source_run.source_retry_count = running_source_run.source.max_retries
    running_source_run.save(update_fields=["source_retry_count"])
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(running_source_run.id))
    retry.assert_not_called()
    running_source_run.refresh_from_db()
    running_source_run.campaign.refresh_from_db()
    assert running_source_run.discovery_finished_at is not None
    assert running_source_run.status == CampaignSourceRun.Status.FAILED
    assert running_source_run.failed_records == 0
    assert running_source_run.campaign.failed_jobs == 1


@pytest.mark.django_db(transaction=True)
def test_database_retry_does_not_spend_source_business_budget(
    running_source_run, monkeypatch
):
    core = Mock(
        side_effect=[
            OperationalError("database unavailable"),
            TransientSourceError("SOURCE_TIMEOUT"),
        ]
    )
    monkeypatch.setattr("apps.discovery.tasks.run_source_discovery_now", core)

    with patch.object(run_source_discovery, "retry", side_effect=Retry()):
        with pytest.raises(Retry):
            run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 0

    with patch.object(run_source_discovery, "retry", side_effect=Retry()):
        with pytest.raises(Retry):
            run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1


@pytest.mark.django_db(transaction=True)
def test_permanent_source_error_fails_without_retry(running_source_run, monkeypatch):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=PermanentSourceError("INVALID_SOURCE_PAYLOAD")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(running_source_run.id))
    retry.assert_not_called()
    running_source_run.refresh_from_db()
    assert running_source_run.status == CampaignSourceRun.Status.FAILED
    assert running_source_run.error_code == "INVALID_SOURCE_PAYLOAD"


@pytest.mark.django_db(transaction=True)
def test_exhausted_source_waits_for_its_pending_record_before_terminal_status(
    running_source_run_with_pending_record, monkeypatch
):
    run = running_source_run_with_pending_record
    run.source_retry_count = run.source.max_retries
    run.save(update_fields=["source_retry_count"])
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(run.id))
    retry.assert_not_called()
    run.refresh_from_db()
    run.campaign.refresh_from_db()
    assert run.discovery_finished_at is not None
    assert run.status == CampaignSourceRun.Status.NORMALIZING
    assert run.campaign.completed_jobs == 0
    record = run.records.get(normalization_status="pending")

    assert fail_source_record_once(
        source_record_id=record.id, error_code="NORMALIZATION_ERROR"
    ) is True
    run.refresh_from_db()
    run.campaign.refresh_from_db()
    assert run.status == CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
    assert run.campaign.status == DiscoveryCampaign.Status.COMPLETED_WITH_ERRORS
```

`running_source_run_with_pending_record` создаёт один уже посчитанный `pending` record (`stored_records=1`) и согласованные campaign counters. Повтор conflict/exhaustion cases сравнивает неизменный tuple counters и количество rows.

- [ ] **Step 5: Запустить pipeline RED**

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_services.py apps/discovery/tests/test_tasks.py -q
```

Expected: FAIL с отсутствующими orchestration service/task wrappers и retry services.

- [ ] **Step 6: Реализовать synchronous orchestration core**

`run_source_discovery_now`:

1. прочитать только `campaign_id`, затем в transaction lock `DiscoveryCampaign → CampaignSourceRun` и idempotently перевести run `pending → running`; root orchestration уже выполнил campaign `queued → running`. Любой последующий AOI/counter update добавляет `SourceRecord` lock только третьим;
2. если `source_dataset_version` пуст, вызвать `adapter.resolve_dataset_version()` и сохранить non-empty result под lock; иначе reuse persisted value. Ни retry, ни возобновлённый iterator не выбирают новую Overture release/OSM marker;
3. construct `DiscoveryRequest` from `SearchArea.extent`, exact geometry GeoJSON, non-empty per-source mappings, request limit и correlation ID; provider bbox is only a coarse prefilter;
4. iterate payloads lazily;
5. передать каждый `SourcePayload` в `persist_source_payload`, который сначала сохраняет raw object, затем pure-парсит его и одной DB transaction создаёт/находит durable parsed-or-failed row; invalid payload с доступным adapter external ID создаёт failed `SourceRecord`. Если даже external ID отсутствует, adapter использует stable `invalid:{payload_sha256}` до вызова persistence;
6. для успешно parsed row с валидной точкой выполнить PostGIS `SearchArea.geometry__covers=raw_location`; точка вне AOI атомарно переводит `pending → rejected` с `OUTSIDE_SEARCH_AREA` и увеличивает source-run и campaign `rejected_records` один раз. Отсутствующая/invalid точка не доказывает выход за AOI: row идёт в normalization с `location=None` и warning `MISSING_COORDINATES`/`INVALID_COORDINATES`;
7. enqueue normalization только для `pending` row; idempotent no-op и conflicts не enqueue;
8. atomically set `discovery_finished_at` and `normalizing`, затем вызвать `finalize_source_run` сразу, если `stored_records == rejected_records + failed_records` и normalizable rows нет;
9. call `try_finalize_campaign`.

`run_source_discovery_now` ловит `SourceRecordConflictError` на уровне одного payload, пишет structured event и продолжает iterator: durable conflict уже посчитан как failed outcome. Исключения raw storage завершают/retry весь source task, а не маскируются как parser failure.

The synchronous test runner accepts explicit `get_adapter` and `store`, calls the same service cores as Celery, and drains an in-process normalization queue. It is test-support only and never imported by production tasks.

No `list(adapter.discover(...))` and no payload in broker message.

После minimal core implementation подтвердить GREEN только для уже реализованного слоя; wrapper tests из Step 4 намеренно остаются RED до общей реализации Step 9:

```bash
docker compose run --rm backend pytest apps/discovery/tests/test_services.py -q
```

Expected: service tests PASS; `apps/discovery/tests/test_tasks.py` ещё не объявляется зелёным.

- [ ] **Step 7: Написать failing normalization counter/finalization tests**

```python
@pytest.mark.django_db(transaction=True)
def test_last_normalized_record_completes_source_run_and_campaign(source_run_with_two_records):
    first, second = source_run_with_two_records.records.order_by("created_at")
    normalize_source_record_now(first.id)
    assert get_campaign_progress(
        source_run_with_two_records.campaign_id,
        actor=source_run_with_two_records.campaign.created_by,
    ).totals.normalized == 1
    normalize_source_record_now(second.id)
    source_run_with_two_records.refresh_from_db()
    source_run_with_two_records.campaign.refresh_from_db()
    assert source_run_with_two_records.status == "completed"
    assert source_run_with_two_records.campaign.status == "completed"


@pytest.mark.django_db(transaction=True)
def test_retrying_normalization_does_not_double_count(one_pending_record):
    normalize_source_record_now(one_pending_record.id)
    normalize_source_record_now(one_pending_record.id)
    run = one_pending_record.source_run
    run.refresh_from_db()
    assert run.normalized_records == 1


@pytest.mark.django_db(transaction=True)
def test_exhausted_normalization_marks_pending_record_failed_once(
    ready_run_with_one_pending_record,
):
    record = ready_run_with_one_pending_record.records.get()
    assert fail_source_record_once(
        source_record_id=record.id,
        error_code="RAW_STORAGE_UNAVAILABLE",
    ) is True
    assert fail_source_record_once(
        source_record_id=record.id,
        error_code="RAW_STORAGE_UNAVAILABLE",
    ) is False
    record.refresh_from_db()
    ready_run_with_one_pending_record.refresh_from_db()
    assert record.normalization_status == "failed"
    assert record.normalization_error_code == "RAW_STORAGE_UNAVAILABLE"
    assert ready_run_with_one_pending_record.failed_records == 1
    assert ready_run_with_one_pending_record.status == "completed_with_errors"
```

Первые три retry-reservation tests ниже находятся в `apps/campaigns/tests/test_retries.py`; следующие task-wrapper tests — в `apps/normalization/tests/test_tasks.py`. Они используют тот же durable budget, а не подменяют `self.request.retries`. Fixture задаёт `source.max_retries=3`; imports совпадают с discovery test плюс `RawStorageUnavailable` и normalization task object:

```python
@pytest.mark.django_db(transaction=True)
def test_exhausted_retry_token_is_denied_idempotently_without_counter_change(
    ready_run_with_one_pending_record
):
    record = ready_run_with_one_pending_record.records.get()
    record.normalization_retry_count = record.source.max_retries
    record.save(update_fields=["normalization_retry_count"])
    assert consume_normalization_retry(
        source_record_id=record.id, delivery_token="task-denied:3"
    ) is False
    assert consume_normalization_retry(
        source_record_id=record.id, delivery_token="task-denied:3"
    ) is False
    record.refresh_from_db()
    assert record.normalization_retry_count == record.source.max_retries
    assert PipelineRetryReservation.objects.filter(
        scope="source_normalization",
        work_id=record.id,
        delivery_token="task-denied:3",
        allowed=False,
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_source_retry_reservation_is_single_and_db_unique_guard_holds(
    running_source_run
):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import IntegrityError, close_old_connections, transaction

    def reserve_once(_: int) -> bool:
        close_old_connections()
        try:
            return consume_source_retry(
                source_run_id=running_source_run.id,
                delivery_token="task-concurrent:0",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(reserve_once, range(2))) == [True, True]
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    reservation = PipelineRetryReservation.objects.get(
        scope="source_discovery",
        work_id=running_source_run.id,
        delivery_token="task-concurrent:0",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PipelineRetryReservation.objects.create(
            campaign=running_source_run.campaign,
            scope=reservation.scope,
            work_id=reservation.work_id,
            delivery_token=reservation.delivery_token,
            allowed=True,
        )


@pytest.mark.django_db(transaction=True)
def test_same_normalization_delivery_token_reserves_budget_once(
    ready_run_with_one_pending_record
):
    record = ready_run_with_one_pending_record.records.get()
    assert consume_normalization_retry(
        source_record_id=record.id, delivery_token="task-99:0"
    ) is True
    assert consume_normalization_retry(
        source_record_id=record.id, delivery_token="task-99:0"
    ) is True
    record.refresh_from_db()
    assert record.normalization_retry_count == 1
    assert PipelineRetryReservation.objects.filter(
        scope="source_normalization",
        work_id=record.id,
        delivery_token="task-99:0",
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_exhausted_normalization_budget_fails_record_once_without_retry(
    ready_run_with_one_pending_record, monkeypatch
):
    record = ready_run_with_one_pending_record.records.get()
    record.normalization_retry_count = record.source.max_retries
    record.save(update_fields=["normalization_retry_count"])
    monkeypatch.setattr(
        "apps.normalization.tasks.normalize_source_record_now",
        Mock(side_effect=RawStorageUnavailable()),
    )
    with patch.object(normalize_source_record, "retry") as retry:
        normalize_source_record.run(str(record.id))
    retry.assert_not_called()
    record.refresh_from_db()
    ready_run_with_one_pending_record.refresh_from_db()
    ready_run_with_one_pending_record.campaign.refresh_from_db()
    assert record.normalization_status == SourceRecord.NormalizationStatus.FAILED
    assert record.normalization_error_code == "RAW_STORAGE_UNAVAILABLE"
    assert ready_run_with_one_pending_record.failed_records == 1
    assert ready_run_with_one_pending_record.status == "completed_with_errors"
    assert ready_run_with_one_pending_record.campaign.status == "completed_with_errors"


@pytest.mark.django_db(transaction=True)
def test_database_retry_does_not_spend_normalization_storage_budget(
    ready_run_with_one_pending_record, monkeypatch
):
    record = ready_run_with_one_pending_record.records.get()
    core = Mock(
        side_effect=[OperationalError("database unavailable"), RawStorageUnavailable()]
    )
    monkeypatch.setattr("apps.normalization.tasks.normalize_source_record_now", core)

    with patch.object(normalize_source_record, "retry", side_effect=Retry()):
        with pytest.raises(Retry):
            normalize_source_record.run(str(record.id))
    record.refresh_from_db()
    assert record.normalization_retry_count == 0

    with patch.object(normalize_source_record, "retry", side_effect=Retry()) as retry:
        with pytest.raises(Retry):
            normalize_source_record.run(str(record.id))
    record.refresh_from_db()
    assert record.normalization_retry_count == 1
    assert record.normalization_status == SourceRecord.NormalizationStatus.PENDING
    retry.assert_called_once()
    assert "max_retries" not in retry.call_args.kwargs
```

`campaign_with_ready_runs(statuses, counters)` — local factory fixture: создаёт два runs, задаёт `discovery_finished_at`, согласованные counters и вызывает только public `finalize_source_run`, не пишет terminal status напрямую. Matrix фиксируется так:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("completed", "completed"), "completed"),
        (("failed", "completed"), "completed_with_errors"),
        (("failed", "failed"), "failed"),
    ],
)
def test_campaign_terminal_status_matrix(campaign_with_ready_runs, statuses, expected):
    campaign = campaign_with_ready_runs(statuses=statuses)
    assert try_finalize_campaign(campaign.id) == expected
    campaign.refresh_from_db()
    assert campaign.status == expected


@pytest.mark.django_db(transaction=True)
def test_rejected_record_is_processed_but_not_failed(campaign_with_ready_runs):
    campaign = campaign_with_ready_runs(
        statuses=("completed", "completed"),
        counters=((1, 0, 1, 0), (0, 0, 0, 0)),
        # each tuple: stored, normalized, rejected, failed
    )
    run = campaign.source_runs.order_by("source__code").first()
    assert run.normalized_records + run.rejected_records + run.failed_records == run.stored_records
    assert run.failed_records == 0
    assert try_finalize_campaign(campaign.id) == "completed"
```

- [ ] **Step 8: Запустить finalization RED**

```bash
docker compose run --rm backend pytest \
  apps/discovery/tests/test_tasks.py \
  apps/normalization/tests/test_tasks.py \
  apps/campaigns/tests/test_retries.py \
  apps/campaigns/tests/test_progress.py -q
```

Expected: FAIL с отсутствующими task/progress functions.

- [ ] **Step 9: Реализовать task wrappers и durable finalization**

В `campaigns.models` и migration `0002_pipeline_retry_reservation.py` добавить `PipelineRetryReservation`: UUID `id`, FK `campaign`, `scope` choices `source_discovery|source_normalization`, UUID `work_id`, `delivery_token=CharField(max_length=128)`, `allowed=BooleanField`, timestamps; `UniqueConstraint(fields=["scope", "work_id", "delivery_token"], name="uniq_pipeline_retry_delivery")`, index `(campaign, scope, created_at)` и `CheckConstraint` на два разрешённых scope. `delivery_token` не содержит secrets и строится как `{self.request.id or 'direct'}:{self.request.retries}`. Durable counters уже созданы в Task 10 (`CampaignSourceRun.source_retry_count`) и Task 12 (`SourceRecord.normalization_retry_count`); migration `0002` добавляет только reservation ledger и не дублирует эти columns.

Обе `consume_*_retry` функции выполняют один `transaction.atomic()`. Сначала получают IDs без locks, затем блокируют `DiscoveryCampaign → CampaignSourceRun` и, для normalization, `→ SourceRecord`. Если reservation для `(scope, work_id, delivery_token)` уже существует, сразу возвращают её `allowed`. Иначе сравнивают durable counter с текущим `Source.max_retries`, создают `allowed=false` без изменения counter при exhaustion либо в той же transaction увеличивают counter и создают `allowed=true`. Поэтому повторная доставка одного broker message не может второй раз списать budget, включая сбой между commit reservation и публикацией retry.

Celery wrappers вызывают synchronous core и объявлены с task-level `max_retries=None`. Это даёт неограниченный механический envelope для восстановления инфраструктуры; business limits не читают `self.request.retries`. Внешний `try/except django.db.OperationalError` охватывает и core, и durable retry-decision transaction, чтобы database error, возникший при любом из этих шагов, всегда шёл только по infrastructure path.

Для `TransientSourceError`, `RateLimitedSourceError` и `RawStorageUnavailable` внутри discovery wrapper вызывает `consume_source_retry(source_run_id=..., delivery_token=make_delivery_token(...))`. При `True` wrapper вызывает `retry_or_requeue(self, exc=error, countdown=provider_backoff(...))` без аргумента `max_retries`; countdown имеет exponential backoff + jitter и cap 300 секунд. `False` ведёт в `mark_source_discovery_exhausted(...)` и normal return без `retry`. Permanent errors идут в terminal-marking path сразу и business counter не меняют.

`mark_source_discovery_exhausted` под lock order campaign → source run заполняет `discovery_finished_at` и sanitized `error_code/error_detail`: zero-record ready run передаётся в `finalize_source_run(..., status="failed")`; run с сохранёнными outcomes передаётся как `completed_with_errors`, если уже ready, либо остаётся `normalizing` до обработки pending rows. Последняя normalization видит operational error и выбирает `completed_with_errors`, а не `completed`.

`normalize_source_record` применяет тот же алгоритм к `RawStorageUnavailable`, но через `consume_normalization_retry(source_record_id=..., delivery_token=make_delivery_token(...))`. При `True` вызывается `retry_or_requeue(...)` без `max_retries`; при `False` `fail_source_record_once` атомарно переводит только `pending → failed`, записывает `RAW_STORAGE_UNAVAILABLE`, увеличивает source-run/campaign `failed_records` ровно один раз и после commit вызывает `finalize_source_run(..., status="completed_with_errors")`. Повторная доставка для уже terminal record — no-op.

Потеря соединения с PostgreSQL — отдельный случай: пока database нельзя записать, честный terminal transition невозможен. Wrapper пишет structured alert `database.unavailable` и вызывает только `retry_or_requeue(self, exc=error, countdown=database_backoff(...))`; task-level `max_retries=None` делает этот путь unbounded, cap countdown — 300 секунд. Ни `source_retry_count`, ни `normalization_retry_count` не меняются. После восстановления тот же idempotent task либо завершается, либо получает полный остаток provider/storage budget. Mixed-sequence tests выше фиксируют именно это поведение и запрещают использовать механический Celery retry counter как business limit.

`celery.exceptions.OperationalError` (broker transport error, alias Kombu) при публикации `self.retry` не ловится как database error. Wrapper пишет `broker.retry_publish_failed` и поднимает `celery.exceptions.Reject(error, requeue=True)`, поэтому worker явно возвращает исходную delivery broker. Redelivery получает тот же `{task_id}:{retries}`, находит прежнюю reservation и не списывает budget повторно. Test `test_retry_publish_failure_redelivery_reuses_the_same_reservation` запрещает regression в этом окне.

Counter update выполняется только при переходе record/source-run terminal status внутри row lock. `finalize_source_run` блокирует campaign, затем source run в одном `transaction.atomic()`: вычисляет `ready`, и если оно false, terminal transition запрещён. Для irrecoverable provider failure функция сначала ставит `discovery_finished_at` (если пуст), но status `failed` допустим только когда `processed == stored`; при уже сохранённых pending rows run остаётся `normalizing`, а после их обработки завершается `completed_with_errors`. Если run уже terminal, функция возвращает no-op; иначе устанавливает terminal status/`finished_at`, увеличивает `campaign.completed_jobs` для `completed`/`completed_with_errors` либо `campaign.failed_jobs` для `failed` ровно один раз и после commit вызывает `try_finalize_campaign`. Только эта функция записывает terminal source-run status. `try_finalize_campaign` counters не меняет: она блокирует campaign, читает runs и проверяет formula:

```python
processed = run.normalized_records + run.rejected_records + run.failed_records
ready = run.discovery_finished_at is not None and processed == run.stored_records
```

Campaign finalization requires `all(run.ready and run.status in terminal_statuses)`. A ready run with `failed_records > 0` or an operational error after some stored records becomes `completed_with_errors`; rejected-only records do not make it an error. Zero stored records is `completed` if every run completed normally, `completed_with_errors` if at least one run is `completed_with_errors` or `failed` but another completed, and `failed` only when every enabled run is `failed`. `run_discovery_campaign` performs the single `queued → running` transition, then enqueues each still-`pending` source run; repeat delivery never creates a second run or increments jobs.

- [ ] **Step 10: Реализовать progress endpoint**

`GET /api/v1/campaigns/{id}/progress/` возвращает exact response из spec, агрегируя rows одним query/prefetch. Status labels не переводятся API. `get_campaign_progress` проверяет owner.

- [ ] **Step 11: Проверить GREEN, routing и restart durability**

```bash
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend pytest apps/campaigns/tests apps/discovery/tests apps/normalization/tests -q
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose up -d backend celery-discovery celery-normalization
docker compose exec celery-discovery celery -A config inspect active_queues
docker compose restart backend celery-normalization
docker compose run --rm backend pytest apps/campaigns/tests/test_progress.py -q
```

Expected: tests PASS; workers слушают только свои queues; progress DB assertions неизменны после restart.

- [ ] **Step 12: Commit**

```bash
git add backend/apps/campaigns backend/apps/discovery backend/apps/normalization backend/apps/sources backend/config backend/conftest.py
git commit -m "feat: orchestrate discovery campaigns with durable progress"
```

---

### Task 18: Добавить read API для предварительных records и dashboard summary

**Files:**
- Create: `backend/apps/businesses/apps.py`
- Create: `backend/apps/businesses/api/serializers.py`
- Create: `backend/apps/businesses/api/pagination.py`
- Create: `backend/apps/businesses/api/views.py`
- Create: `backend/apps/businesses/api/urls.py`
- Create: `backend/apps/businesses/tests/conftest.py`
- Create: `backend/apps/businesses/tests/test_source_record_api.py`
- Create: `backend/apps/businesses/tests/test_dashboard_api.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/api_urls.py`

**Interfaces:**
- Consumes: `SourceRecord`, `NormalizedSourceRecord`, campaigns/source/category/geography.
- Produces: paginated `GET /source-records/`, detail `GET /source-records/{id}/`, `GET /dashboard/summary/`.

```python
from __future__ import annotations


class SourceRecordListItem(TypedDict):
    id: str
    display_name: str
    source: dict[str, str]
    category: dict[str, str] | None
    district: dict[str, str] | None
    phones: list[str]
    websites: list[str]
    normalization_status: Literal["normalized"]
    fetched_at: str
    is_canonical: Literal[False]


class SourceRecordDetail(TypedDict):
    id: str
    is_canonical: Literal[False]
    campaign_id: str
    source_run_id: str
    source: dict[str, str]  # exact keys: code, name
    external_id: str
    source_dataset_version: str
    source_url: str | None
    attribution: str
    license_code: str
    raw: RawSourceRecordDetail
    payload: RawPayloadDetail
    normalization_status: Literal["pending", "normalized", "rejected", "failed"]
    normalization_error_code: str | None
    parser_error_code: str | None
    fetched_at: str
    normalized: NormalizedSourceRecordDetail | None


class RawSourceRecordDetail(TypedDict):
    name: str | None
    category: str | None
    address: str | None
    phones: list[str]
    emails: list[str]
    websites: list[str]
    social_urls: dict[str, list[str]]
    location: dict[str, JSONValue] | None  # GeoJSON Point


class RawPayloadDetail(TypedDict):
    key: str
    sha256: str
    bytes: int
    schema_version: str


class NormalizedSourceRecordDetail(TypedDict):
    display_name: str
    normalized_name: str
    match_name: str
    category: dict[str, str] | None  # exact keys: id, name, slug
    address_text: str
    country: dict[str, str] | None
    province: dict[str, str] | None
    district: dict[str, str] | None
    neighborhood: dict[str, str] | None
    location: dict[str, JSONValue] | None  # GeoJSON Point
    phones: list[str]
    emails: list[str]
    websites: list[str]
    social_urls: dict[str, list[str]]
    attributes: dict[str, JSONValue]
    warnings: list[str]
    normalization_version: str
    normalized_at: str
```

Raw payload body, object/presigned URL и S3 credentials отсутствуют в detail response.

- [ ] **Step 1: Написать failing pagination/filter tests**

```python
@pytest.mark.django_db
def test_source_record_list_is_paginated_and_explicitly_noncanonical(auth_client, normalized_records):
    response = auth_client.get("/api/v1/source-records/?page=1&page_size=2&ordering=display_name")
    assert response.status_code == 200
    assert response.json()["count"] == len(normalized_records)
    assert len(response.json()["results"]) == 2
    assert all(item["is_canonical"] is False for item in response.json()["results"])


@pytest.mark.django_db
def test_source_record_list_filters_campaign_source_category_and_search(auth_client, records):
    response = auth_client.get(
        f"/api/v1/source-records/?campaign={records.target.campaign_id}"
        f"&source=osm&category=dentist&search=smile"
    )
    assert [item["id"] for item in response.json()["results"]] == [str(records.target.id)]
```

`backend/apps/businesses/tests/conftest.py` определяет `RecordsFixture(target, rejected, failed, foreign)` и создаёт через production persistence/materialization services: три records owner-а (`normalized`, `rejected`, `failed`) и один normalized record `other_owner`; `normalized_records` добавляет ещё два owned normalized rows для pagination. Никаких прямых updates materialized fields в fixtures. Затем добавить точные boundary tests:

```python
DETAIL_KEYS = {
    "id", "is_canonical", "campaign_id", "source_run_id", "source",
    "external_id", "source_dataset_version", "source_url", "attribution",
    "license_code", "raw", "payload", "normalization_status",
    "normalization_error_code", "parser_error_code", "fetched_at", "normalized",
}
RAW_KEYS = {"name", "category", "address", "phones", "emails", "websites", "social_urls", "location"}
PAYLOAD_KEYS = {"key", "sha256", "bytes", "schema_version"}
NORMALIZED_KEYS = {
    "display_name", "normalized_name", "match_name", "category", "address_text",
    "country", "province", "district", "neighborhood", "location", "phones",
    "emails", "websites", "social_urls", "attributes", "warnings",
    "normalization_version", "normalized_at",
}


@pytest.mark.django_db
def test_list_rejects_unsafe_query_and_never_leaks_non_normalized_rows(
    auth_client, records
):
    too_large = auth_client.get("/api/v1/source-records/?page_size=101")
    unknown_filter = auth_client.get("/api/v1/source-records/?normalization_status=rejected")
    visible = auth_client.get("/api/v1/source-records/").json()["results"]
    assert too_large.status_code == 400
    assert unknown_filter.status_code == 400
    assert {item["id"] for item in visible}.isdisjoint(
        {str(records.rejected.id), str(records.failed.id), str(records.foreign.id)}
    )


@pytest.mark.django_db
def test_detail_shape_is_exact_and_contains_metadata_not_payload_body(auth_client, records):
    response = auth_client.get(f"/api/v1/source-records/{records.target.id}/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert body["is_canonical"] is False
    assert set(body["source"]) == {"code", "name"}
    assert set(body["raw"]) == RAW_KEYS
    assert set(body["payload"]) == PAYLOAD_KEYS
    assert set(body["normalized"]) == NORMALIZED_KEYS
    rendered = json.dumps(body)
    for forbidden in ("payload_body", "presigned_url", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        assert forbidden not in rendered


@pytest.mark.django_db
@pytest.mark.parametrize("record_name", ["rejected", "failed"])
def test_owned_non_normalized_detail_is_visible_with_null_normalized(
    auth_client, records, record_name
):
    record = getattr(records, record_name)
    response = auth_client.get(f"/api/v1/source-records/{record.id}/")
    assert response.status_code == 200
    assert response.json()["normalized"] is None
    assert response.json()["normalization_status"] == record_name


@pytest.mark.django_db
def test_foreign_and_missing_detail_are_indistinguishable(auth_client, records):
    foreign = auth_client.get(f"/api/v1/source-records/{records.foreign.id}/")
    missing = auth_client.get(
        "/api/v1/source-records/00000000-0000-0000-0000-000000000000/"
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


@pytest.mark.django_db
def test_anonymous_list_is_forbidden(api_client):
    assert api_client.get("/api/v1/source-records/").status_code == 403
```

- [ ] **Step 2: Написать failing dashboard summary test**

```python
@pytest.mark.django_db
def test_dashboard_summary_uses_persisted_campaign_and_record_counts(auth_client, campaign):
    response = auth_client.get("/api/v1/dashboard/summary/")
    assert response.status_code == 200
    assert response.json() == {
        "records": {"raw": 3, "normalized": 2, "rejected": 1, "failed": 0},
        "campaigns": {"total": 1, "running": 0, "with_errors": 0},
        "recent_campaigns": [
            {
                "id": str(campaign.id),
                "name": campaign.name,
                "status": "completed",
                "normalized": 2,
                "updated_at": campaign.updated_at.isoformat().replace("+00:00", "Z"),
            }
        ],
    }
```

- [ ] **Step 3: Запустить RED**

```bash
docker compose run --rm backend pytest apps/businesses/tests -q
```

Expected: FAIL с 404/absent app.

- [ ] **Step 4: Реализовать querysets/serializers**

List queryset начинает с `NormalizedSourceRecord`, ограничивает `source_record__campaign__created_by=request.user`, делает `select_related` source record/source/category/district и возвращает только materialized normalized rows (rejected/pending raw records не возвращаются). Поэтому query parameter `normalization_status` удалён из API и UI; статус списка всегда `normalized`. `campaign` принимает UUID, `source` — source code, `category` — category slug. Search использует `normalized_name__icontains` в slice; trigram ranking откладывается до canonical search plan. Allowed ordering: `display_name`, `-fetched_at`, `fetched_at`; неизвестный filter/ordering и `page_size > 100` → 400 через strict query serializer и `SourceRecordPagination(default=50, max=100)`.

Detail использует ту же owner scope и отдаёт exact `SourceRecordDetail`, включая raw contact collections, checksum, payload key/bytes, dataset version, attribution, license, warnings и normalized fields. Raw body скачивается только внутренним service/management command.

- [ ] **Step 5: Проверить query counts и GREEN**

```bash
docker compose run --rm backend pytest apps/businesses/tests -q
docker compose run --rm backend pytest apps/system/tests apps/businesses/tests -q
docker compose run --rm backend ruff check apps/businesses
```

Expected: PASS; list of 50 rows делает bounded query count (зафиксировать ≤ 5).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/businesses backend/config
git commit -m "feat: expose normalized discovery records and dashboard summary"
```

---

### Task 19: Реализовать создание кампании и polling progress в React

**Files:**
- Create: `frontend/src/features/geography/types.ts`
- Create: `frontend/src/features/geography/api.ts`
- Create: `frontend/src/features/taxonomy/types.ts`
- Create: `frontend/src/features/taxonomy/api.ts`
- Create: `frontend/src/features/sources/types.ts`
- Create: `frontend/src/features/sources/api.ts`
- Create: `frontend/src/features/campaigns/types.ts`
- Create: `frontend/src/features/campaigns/api.ts`
- Create: `frontend/src/features/campaigns/queries.ts`
- Create: `frontend/src/features/campaigns/CampaignListPage.tsx`
- Create: `frontend/src/features/campaigns/CampaignCreatePage.tsx`
- Create: `frontend/src/features/campaigns/CampaignDetailPage.tsx`
- Create: `frontend/src/features/campaigns/CampaignCreatePage.test.tsx`
- Create: `frontend/src/features/campaigns/CampaignDetailPage.test.tsx`
- Create: `frontend/src/components/ProgressBar.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/shared/labels.ts`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/test/handlers.ts`

**Interfaces:**
- Consumes: geography/taxonomy/source/campaign endpoints Tasks 7–10, start/progress Task 17.
- Produces exact frontend types:

```ts
export type CampaignStatus =
  | 'draft'
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_errors'
  | 'failed';

export type CreateCampaignInput = {
  name: string;
  search_area_id: string;
  source_ids: string[];
  category_ids: string[];
};

export type CampaignProgress = {
  id: string;
  status: CampaignStatus;
  totals: {
    jobs: number;
    completed_jobs: number;
    failed_jobs: number;
    discovered: number;
    stored: number;
    normalized: number;
    rejected: number;
    failed_records: number;
  };
  sources: SourceProgress[];
};

export type SourceProgress = {
  code: string;
  name: string;
  status:
    | 'pending'
    | 'running'
    | 'normalizing'
    | 'completed'
    | 'completed_with_errors'
    | 'failed';
  dataset_version: string | null;
  discovered: number;
  stored: number;
  normalized: number;
  rejected: number;
  failed_records: number;
};
```

- [ ] **Step 1: Написать failing campaign form test**

```tsx
it('создаёт черновик из выбранной области и двух источников', async () => {
  const { user } = renderAuthenticatedApp('/campaigns/new');
  await screen.findByRole('heading', { name: 'Новая кампания' });
  await user.type(screen.getByLabelText('Название кампании'), 'Аланья — первичный сбор');
  await user.selectOptions(screen.getByLabelText('Область поиска'), ALANYA_ID);
  await user.click(screen.getByRole('checkbox', { name: 'Overture Maps' }));
  await user.click(screen.getByRole('checkbox', { name: 'OpenStreetMap' }));
  await user.click(screen.getByRole('button', { name: 'Создать кампанию' }));
  expect(await screen.findByRole('heading', { name: 'Аланья — первичный сбор' })).toBeInTheDocument();
  expect(capturedCreateBody).toEqual({
    name: 'Аланья — первичный сбор',
    search_area_id: ALANYA_ID,
    source_ids: [OVERTURE_ID, OSM_ID],
    category_ids: [],
  });
});
```

```tsx
it('не отправляет POST и показывает три русские field errors для пустой формы', async () => {
  const { user } = renderAuthenticatedApp('/campaigns/new');
  await user.click(await screen.findByRole('button', { name: 'Создать кампанию' }));
  expect(screen.getByText('Введите название кампании.')).toBeInTheDocument();
  expect(screen.getByText('Выберите область поиска.')).toBeInTheDocument();
  expect(screen.getByText('Выберите хотя бы один источник.')).toBeInTheDocument();
  expect(campaignCreateRequests).toHaveLength(0);
});

it('показывает detail API, но не технический trace', async () => {
  server.use(campaignCreateErrorHandler);
  const { user } = renderAuthenticatedApp('/campaigns/new');
  await user.type(await screen.findByLabelText('Название кампании'), 'Аланья');
  await user.selectOptions(screen.getByLabelText('Область поиска'), ALANYA_ID);
  await user.click(screen.getByRole('checkbox', { name: 'OpenStreetMap' }));
  await user.click(screen.getByRole('button', { name: 'Создать кампанию' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Для источника нет активных сопоставлений категорий.',
  );
  expect(screen.queryByText(/Traceback|stack|CampaignValidationError/)).not.toBeInTheDocument();
});

it('отклоняет неизвестный progress status на API boundary', () => {
  expect(campaignProgressSchema.safeParse({ ...runningProgress, status: 'paused' }).success).toBe(false);
});
```

`campaignCreateRequests` — очищаемый в `beforeEach` массив, в который default MSW POST handler кладёт `await request.json()`; первый happy-path test сравнивает его единственный item с UUID arrays в выбранном порядке и пустым `category_ids`. `campaignProgressSchema` описывает весь `CampaignProgress`/`SourceProgress`, а `api.ts` применяет `.parse()` до передачи данных UI.

- [ ] **Step 2: Запустить form RED**

```bash
cd frontend
npm run test:run -- src/features/campaigns/CampaignCreatePage.test.tsx
```

Expected: FAIL с missing module/route.

- [ ] **Step 3: Реализовать API hooks и form**

Queries имеют stable keys: `['search-areas']`, `['categories']`, `['sources']`, `['campaigns']`, `['campaign', id]`, `['campaign-progress', id]`. Empty `category_ids` отображается radio/label «Все поддерживаемые категории». После create navigate `/campaigns/{id}`; start остаётся отдельной кнопкой, чтобы пользователь видел preview.

- [ ] **Step 4: Написать failing progress polling test с fake timers**

```tsx
it('после запуска опрашивает progress каждые 3 секунды и прекращает на terminal status', async () => {
  vi.useFakeTimers();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  progressResponses.enqueue(runningProgress, completedProgress);
  renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);
  await user.click(await screen.findByRole('button', { name: 'Запустить кампанию' }));
  expect(await screen.findByText('Выполняется')).toBeInTheDocument();
  await vi.advanceTimersByTimeAsync(3000);
  expect(await screen.findByText('Завершена')).toBeInTheDocument();
  await vi.advanceTimersByTimeAsync(6000);
  expect(progressResponses.requestCount).toBe(2);
  vi.useRealTimers();
});
```

- [ ] **Step 5: Запустить progress RED**

```bash
cd frontend
npm run test:run -- src/features/campaigns/CampaignDetailPage.test.tsx
```

Expected: FAIL с отсутствующим detail/progress behavior.

- [ ] **Step 6: Реализовать detail/progress UI**

`refetchInterval` возвращает `3000` только для `queued`/`running` (и прекращается после terminal response), иначе `false`. UI показывает status, start time, totals и отдельную строку каждого `SourceProgress`: code, name, status, dataset version, stored, normalized, rejected, failed. ProgressBar использует `processed / max(stored, 1)` и доступные `aria-valuenow/min/max`; при discovery без известного total показывается indeterminate label «Сбор данных…», не фиктивный процент. Tests подтверждают отсутствие polling после `completed`, `completed_with_errors` и `failed`.

`labels.ts` содержит exhaustive `satisfies Record<CampaignStatus, string>`:

```ts
export const campaignStatusLabel = {
  draft: 'Черновик',
  queued: 'В очереди',
  running: 'Выполняется',
  completed: 'Завершена',
  completed_with_errors: 'Завершена с ошибками',
  failed: 'Ошибка',
} satisfies Record<CampaignStatus, string>;
```

- [ ] **Step 7: Проверить GREEN**

```bash
cd frontend
npm run test:run -- src/features/campaigns
npm run lint
npm run typecheck
```

Expected: all PASS/exit 0; состояния загрузки, пустого результата и ошибки покрыты отдельными tests.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features frontend/src/components frontend/src/shared frontend/src/app frontend/src/test
git commit -m "feat: add campaign creation and progress dashboard"
```

---

### Task 20: Реализовать Overview и предварительную таблицу «Бизнесы»

**Files:**
- Create: `frontend/src/features/dashboard/types.ts`
- Create: `frontend/src/features/dashboard/api.ts`
- Create: `frontend/src/features/dashboard/DashboardPage.tsx`
- Create: `frontend/src/features/dashboard/DashboardPage.test.tsx`
- Create: `frontend/src/features/businesses/types.ts`
- Create: `frontend/src/features/businesses/api.ts`
- Create: `frontend/src/features/businesses/queries.ts`
- Create: `frontend/src/features/businesses/BusinessesPage.tsx`
- Create: `frontend/src/features/businesses/BusinessesPage.test.tsx`
- Create: `frontend/src/components/DataTable.tsx`
- Create: `frontend/src/components/Pagination.tsx`
- Create: `frontend/src/components/SourceBadge.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/test/handlers.ts`

**Interfaces:**
- Consumes: Task 18 dashboard/source-record endpoints.
- Produces `DashboardSummary`, `SourceRecordListItem`, `Paginated<T>`, query-param state for pagination/search/source/category.

```ts
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type SourceRecordListItem = {
  id: string;
  is_canonical: false;
  display_name: string;
  source: { code: string; name: string };
  category: { id: string; name: string; slug: string } | null;
  district: { id: string; name: string; slug: string } | null;
  phones: string[];
  websites: string[];
  normalization_status: 'normalized';
  fetched_at: string;
};

export type DashboardSummary = {
  records: { raw: number; normalized: number; rejected: number; failed: number };
  campaigns: { total: number; running: number; with_errors: number };
  recent_campaigns: Array<{
    id: string;
    name: string;
    status: CampaignStatus;
    normalized: number;
    updated_at: string;
  }>;
};

export type SourceRecordQuery = {
  page: number;
  search?: string;
  campaign?: string;
  source?: string;
  category?: string;
  ordering?: 'display_name' | 'fetched_at' | '-fetched_at';
};
```

- [ ] **Step 1: Написать failing dashboard behavior test**

```tsx
it('показывает честные сводные показатели первого среза', async () => {
  renderAuthenticatedApp('/');
  expect(await screen.findByRole('heading', { name: 'Обзор' })).toBeInTheDocument();
  expect(screen.getByText('Сырых записей')).toBeInTheDocument();
  expect(screen.getByText('Нормализовано')).toBeInTheDocument();
  expect(screen.queryByText('Уникальных бизнесов')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Аланья — первичный сбор' })).toHaveAttribute(
    'href',
    `/campaigns/${CAMPAIGN_ID}`,
  );
});
```

- [ ] **Step 2: Написать failing business table tests**

```tsx
it('показывает предупреждение до дедупликации и серверную пагинацию', async () => {
  const { user } = renderAuthenticatedApp('/businesses');
  expect(await screen.findByRole('heading', { name: 'Бизнесы' })).toBeInTheDocument();
  expect(screen.getByRole('note')).toHaveTextContent(
    'Предварительные записи. Дедупликация ещё не выполнена',
  );
  expect(screen.getByText('Найдено записей: 120')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Следующая страница' }));
  await waitFor(() => expect(lastRequestUrl.searchParams.get('page')).toBe('2'));
});

it('не показывает canonical scores или возможности', async () => {
  renderAuthenticatedApp('/businesses');
  await screen.findByRole('table');
  expect(screen.queryByText('Приоритет')).not.toBeInTheDocument();
  expect(screen.queryByText('Цифровой потенциал')).not.toBeInTheDocument();
});
```

```tsx
it('debounce отправляет один search request через 300 ms и сбрасывает page', async () => {
  vi.useFakeTimers();
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  renderAuthenticatedApp('/businesses?page=3');
  await screen.findByRole('table');
  const baseline = businessListRequests.length;
  await user.type(screen.getByRole('searchbox', { name: 'Поиск' }), 'smile');
  await vi.advanceTimersByTimeAsync(299);
  expect(businessListRequests).toHaveLength(baseline);
  await vi.advanceTimersByTimeAsync(1);
  await waitFor(() => expect(businessListRequests).toHaveLength(baseline + 1));
  const url = businessListRequests.at(-1)!;
  expect(url.searchParams.get('search')).toBe('smile');
  expect(url.searchParams.get('page')).toBe('1');
  vi.useRealTimers();
});

it('source/category filters и heading используют только server-side query params', async () => {
  const { user } = renderAuthenticatedApp('/businesses?page=3');
  await user.selectOptions(await screen.findByLabelText('Источник'), 'osm');
  await waitFor(() => expect(businessListRequests.at(-1)!.searchParams.get('source')).toBe('osm'));
  expect(businessListRequests.at(-1)!.searchParams.get('page')).toBe('1');
  await user.selectOptions(screen.getByLabelText('Категория'), 'dentist');
  await user.click(screen.getByRole('columnheader', { name: 'Название' }));
  const url = businessListRequests.at(-1)!;
  expect(url.searchParams.get('category')).toBe('dentist');
  expect(url.searchParams.get('ordering')).toBe('display_name');
});

it('показывает отдельные empty и safe server-error states', async () => {
  server.use(businessesEmptyHandler);
  const empty = renderAuthenticatedApp('/businesses');
  expect(await screen.findByText('Записей не найдено')).toBeInTheDocument();
  empty.unmount();
  server.use(businessesServerErrorHandler);
  renderAuthenticatedApp('/businesses');
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить записи.');
  expect(screen.queryByText(/Traceback|stack|SQL/)).not.toBeInTheDocument();
});

it('отклоняет каноническую строку на границе API первого среза', () => {
  const response = { ...businessesResponse, results: [{ ...businessesResponse.results[0], is_canonical: true }] };
  expect(sourceRecordPageSchema.safeParse(response).success).toBe(false);
});
```

`businessListRequests` хранит `new URL(request.url)` и очищается в `beforeEach`; `sourceRecordPageSchema` требует literal `is_canonical: z.literal(false)`. Эти tests идут в `BusinessesPage.test.tsx`, а именованные empty/error handlers — в `frontend/src/test/handlers.ts`.

- [ ] **Step 3: Запустить RED**

```bash
cd frontend
npm run test:run -- src/features/dashboard src/features/businesses
```

Expected: FAIL с отсутствующими pages/components.

- [ ] **Step 4: Реализовать DashboardPage**

Cards: «Сырых записей», «Нормализовано», «Отклонено», «С ошибками», «Кампаний выполняется». Recent campaign rows используют `campaignStatusLabel`. Zero state: «Кампаний пока нет» + link «Создать первую кампанию».

- [ ] **Step 5: Реализовать DataTable и query-param filters**

Columns строго: «Название», «Источник», «Категория», «Район», «Телефон», «Сайт», «Статус», «Получено». Search debounce 300 ms; filters/source/category и `page` живут в URL. Изменение search/filter сбрасывает page на 1. Phone/site cells показывают первый item и `+N`, пустое значение — `—`. Site link имеет safe `rel="noopener noreferrer"` и открывается в новой вкладке.

Table не делает client-side sorting полного dataset: header меняет API `ordering`; `page_size` фиксирован 50. API и UI не передают `normalization_status`, поскольку endpoint возвращает только normalized rows.

- [ ] **Step 6: Проверить loading/error/empty states и GREEN**

```bash
cd frontend
npm run test:run -- src/features/dashboard src/features/businesses
npm run lint
npm run typecheck
npm run build
```

Expected: all PASS/exit 0. MSW tests отдельно проверяют русское сообщение при 500 и пустой результат после фильтрации.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/dashboard frontend/src/features/businesses frontend/src/components frontend/src/app frontend/src/test
git commit -m "feat: show discovery overview and preliminary business records"
```

---

### Task 21: Добавить observability и security regression coverage

**Files:**
- Create: `backend/common/observability.py`
- Create: `backend/common/celery_signals.py`
- Create: `backend/common/tests/test_observability.py`
- Create: `backend/apps/system/middleware.py`
- Create: `backend/apps/system/tests/test_security_logging.py`
- Create: `backend/config/sentry.py`
- Create: `frontend/src/app/observability.ts`
- Create: `frontend/src/app/observability.test.ts`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/settings/testing.py`
- Modify: `backend/requirements/base.in`
- Modify: `backend/requirements/base.txt`
- Modify: `backend/requirements/development.txt`
- Modify: `backend/requirements/production.txt`
- Modify: `backend/apps/discovery/services.py`
- Modify: `backend/apps/sources/storage/s3.py`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/Dockerfile`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Produces `CorrelationIdMiddleware`, `structured_event(event: str, **context) -> None`, `sanitize_log_context(context) -> dict`, `init_backend_sentry(dsn: str) -> bool`, `initFrontendObservability(dsn?: string) -> boolean`.
- Structured JSON fields are exactly `timestamp`, `level`, `service`, `event`, `message`, `request_id`, `task_id`, `correlation_id`, `campaign_id`, `source_run_id`, `source`, `source_record_id`, `error_code`, `duration_ms`. Context outside this allowlist is dropped, not merely masked.
- Optional Sentry is enabled only when `SENTRY_DSN`/`VITE_SENTRY_DSN` is non-empty, with `send_default_pii=False`; tests keep it disabled and make no outbound telemetry.

- [ ] **Step 1: Написать failing observability/security tests**

```python
@pytest.mark.django_db
def test_request_gets_safe_correlation_id(api_client):
    response = api_client.get(
        "/api/v1/health/live/", HTTP_X_CORRELATION_ID="campaign-ui-42"
    )
    assert response["X-Correlation-ID"] == "campaign-ui-42"


@pytest.mark.parametrize("unsafe", ["x\nforged", "x" * 129])
def test_unsafe_correlation_id_is_replaced(api_client, unsafe):
    response = api_client.get("/api/v1/health/live/", HTTP_X_CORRELATION_ID=unsafe)
    UUID(response["X-Correlation-ID"])


def test_structured_context_drops_secrets_payload_and_contacts(caplog):
    structured_event(
        "source_record.stored",
        campaign_id="campaign-id",
        source="osm",
        password="secret",
        authorization="Bearer token",
        raw_payload={"phone": "+905321234567"},
        email="person@example.test",
    )
    rendered = caplog.records[-1].getMessage()
    assert "campaign-id" in rendered
    for forbidden in ("secret", "Bearer", "+905321234567", "person@example.test"):
        assert forbidden not in rendered


def test_backend_sentry_is_disabled_for_empty_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    assert init_backend_sentry("") is False
    assert calls == []
```

`test_security_logging.py` дополнительно отправляет неверный CSRF/session request и проверяет generic API envelope без cookie, token, stack trace или username. `celery_signals` test создаёт fake task request: header `correlation_id` имеет приоритет, иначе используется Celery `task_id`; lifecycle event всегда содержит оба идентификатора.

- [ ] **Step 2: Запустить RED**

```bash
docker compose run --rm backend pytest common/tests/test_observability.py apps/system/tests/test_security_logging.py -q
```

Expected: FAIL с отсутствующими middleware/functions.

- [ ] **Step 3: Реализовать structured logging, correlation и backend Sentry**

Добавить `python-json-logger==4.2.0` и `sentry-sdk[django]==2.68.1` в `base.in`, затем перекомпилировать все три lockfiles exact commands из Task 2. `CorrelationIdMiddleware` принимает только printable ASCII `[A-Za-z0-9._:-]{1,128}`, иначе генерирует UUID, сохраняет его в `request.correlation_id` и возвращает `X-Correlation-ID`. `structured_event` строит новый dict только из allowlist; values должны быть scalar, UUID/datetime приводятся к string. Campaign start, source-run transition, object put, normalization и terminal completion вызывают этот helper без payload/contact arguments. Django `LOGGING` выводит JSON в stdout.

`init_backend_sentry` вызывает `sentry_sdk.init(dsn=..., integrations=[DjangoIntegration(), CeleryIntegration()], send_default_pii=False, before_send=sanitize_sentry_event)` только при непустом DSN; sanitizer удаляет request headers/cookies/body и user IP/email. `testing.py` задаёт `SENTRY_DSN=""`.

- [ ] **Step 4: Написать RED и реализовать React boundary**

```ts
it('не инициализирует Sentry без DSN', () => {
  expect(initFrontendObservability(undefined)).toBe(false);
  expect(sentryInitSpy).not.toHaveBeenCalled();
});

it('удаляет user и request headers из события', () => {
  const safe = sanitizeFrontendEvent({
    user: { email: 'person@example.test' },
    request: { headers: { authorization: 'Bearer token' } },
    message: 'UI failed',
  });
  expect(safe.user).toBeUndefined();
  expect(safe.request?.headers).toBeUndefined();
});
```

Run RED:

```bash
cd frontend
npm run test:run -- src/app/observability.test.ts
```

Выполнить `npm install --save-exact @sentry/react@10.73.0` и commit обновлённого lockfile. `main.tsx` вызывает `initFrontendObservability(import.meta.env.VITE_SENTRY_DSN)` до render; initializer sets `sendDefaultPii: false` and `beforeSend: sanitizeFrontendEvent`, returns `false` без DSN. `.env.example` добавляет пустой `VITE_SENTRY_DSN=`; build stage уже принимает одноимённый `ARG`/`ENV`, а Task 21 добавляет в `nginx.build.args` exact mapping `VITE_SENTRY_DSN: "${VITE_SENTRY_DSN:-}"`. DSN считается build-time config, не runtime secret.

- [ ] **Step 5: Проверить GREEN**

```bash
docker compose run --rm backend pytest common/tests apps/system/tests -q
docker compose run --rm backend ruff check common apps/system
cd frontend
npm run test:run -- src/app/observability.test.ts
npm run lint
npm run typecheck
```

Expected: PASS with deterministic log assertions and no network calls.

- [ ] **Step 6: Commit**

```bash
git add backend/common backend/apps/system backend/apps/discovery backend/apps/sources backend/config backend/requirements frontend/src/app frontend/Dockerfile frontend/package.json frontend/package-lock.json docker-compose.yml .env.example
git commit -m "feat: add structured observability and security logging"
```

---

### Task 22: Добавить полный acceptance flow, CI и operational runbook

**Files:**
- Create: `backend/apps/discovery/tests/fake_adapter.py`
- Modify: `backend/apps/discovery/tests/conftest.py`
- Create: `backend/apps/discovery/tests/integration/test_pipeline.py`
- Create: `backend/apps/discovery/tests/integration/test_celery_redis.py`
- Create: `backend/apps/system/management/commands/bootstrap_environment.py`
- Create: `backend/apps/system/tests/test_bootstrap_environment.py`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/discovery-flow.spec.ts`
- Create: `.github/workflows/ci.yml`
- Create: `infrastructure/scripts/bootstrap-dev.sh`
- Create: `infrastructure/scripts/verify.sh`
- Modify: `docker-compose.e2e.yml`
- Modify: `backend/config/settings/testing.py`
- Modify: `backend/apps/discovery/registry.py`
- Modify: `Makefile`
- Modify: `README.md`

**Interfaces:**
- Consumes: весь vertical slice Tasks 1–21.
- Produces: reproducible fake-source E2E, real Redis/MinIO/PostGIS integration suite, CI gates и documented local/live launch.

- [ ] **Step 1: Написать failing backend pipeline acceptance test**

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
def test_fixture_campaign_reaches_completed_with_raw_and_normalized_records(
    owner, alanya_campaign, minio_store, fixture_adapter_registry
):
    run_campaign_synchronously(
        alanya_campaign.id,
        get_adapter=fixture_adapter_registry.get,
        store=minio_store,
    )
    alanya_campaign.refresh_from_db()
    assert alanya_campaign.status == "completed"
    assert alanya_campaign.raw_records_found == 4
    assert alanya_campaign.normalized_records == 4
    assert SourceRecord.objects.filter(campaign=alanya_campaign).count() == 4
    assert NormalizedSourceRecord.objects.filter(
        source_record__campaign=alanya_campaign
    ).count() == 4
    for record in SourceRecord.objects.filter(campaign=alanya_campaign):
        assert minio_store.get_json(record.raw_payload_key)
```

Fixture adapter выдаёт по две вымышленные records для Overture/OSM, включая одну намеренную одинаковую компанию. Assertion требует четыре normalized rows: это доказывает отсутствие скрытой deduplication.

- [ ] **Step 2: Запустить pipeline RED**

```bash
docker compose -p local-business-intelligence-e2e \
  -f docker-compose.yml -f docker-compose.e2e.yml run --rm \
  -e STORAGE_INTEGRATION_PROJECT=1 backend \
  pytest apps/discovery/tests/integration/test_pipeline.py -q
```

Expected: FAIL, пока e2e settings/fake registry/bootstrap не связаны.

- [ ] **Step 3: Реализовать test-only adapter wiring**

`testing.py` разрешает fixture registry только при `DISCOVERY_USE_FIXTURES=1`; production/development settings этот flag игнорируют. Test adapter boundary:

```python
class FixtureDiscoveryAdapter:
    def __init__(self, source_code: Literal["overture", "osm"]) -> None:
        self.source_code = source_code

    def resolve_dataset_version(self) -> str:
        return "fixture-2026-09"

    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]:
        for payload in FIXTURE_PAYLOADS[self.source_code]:
            yield SourcePayload(
                external_id=payload["id"],
                payload=payload,
                fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
                provenance=SourceProvenance(
                    dataset_version=request.dataset_version,
                    source_url=None,
                    attribution=FIXTURE_ATTRIBUTION[self.source_code],
                    license_code="fixture-only",
                ),
            )

    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord:
        return parse_fixture_payload(source_payload)


class FixtureOvertureAdapter(FixtureDiscoveryAdapter):
    def __init__(self) -> None:
        super().__init__("overture")


class FixtureOsmAdapter(FixtureDiscoveryAdapter):
    def __init__(self) -> None:
        super().__init__("osm")
```

`DISCOVERY_ADAPTERS` maps `overture`/`osm` to the two subclasses. Each returns exactly two invented payloads: IDs `fixture-overture-1`, `fixture-shared`, `fixture-osm-1`, `fixture-shared`; the two `fixture-shared` rows have equal name/location but remain different source records. All coordinates are covered by the pilot AOI and all versions are `fixture-2026-09`.

`docker-compose.e2e.yml` is an exact override; `!reset`/`!override` require Docker Compose v2.24+:

```yaml
services:
  postgres:
    environment:
      POSTGRES_DB: lbi_e2e
      POSTGRES_USER: lbi_e2e
      POSTGRES_PASSWORD: lbi-e2e-only
    ports: !reset []
  redis:
    ports: !reset []
  minio:
    environment:
      MINIO_ROOT_USER: minio-e2e
      MINIO_ROOT_PASSWORD: minio-e2e-only
    ports: !reset []
  minio-init:
    environment:
      S3_ACCESS_KEY_ID: minio-e2e
      S3_SECRET_ACCESS_KEY: minio-e2e-only
      S3_BUCKET_NAME: lbi-e2e
  backend:
    environment: &e2e-environment
      DJANGO_SETTINGS_MODULE: config.settings.testing
      DATABASE_URL: postgis://lbi_e2e:lbi-e2e-only@postgres:5432/lbi_e2e
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_TASK_IGNORE_RESULT: "true"
      S3_ENDPOINT_URL: http://minio:9000
      S3_ACCESS_KEY_ID: minio-e2e
      S3_SECRET_ACCESS_KEY: minio-e2e-only
      S3_BUCKET_NAME: lbi-e2e
      S3_REGION_NAME: us-east-1
      DISCOVERY_USE_FIXTURES: "1"
      E2E_FIXTURE_CREDENTIALS: "1"
      # Public fixture credential, never a development/production secret.
      DJANGO_SUPERUSER_USERNAME: owner
      DJANGO_SUPERUSER_PASSWORD: e2e-password
    ports: !reset []
  celery-discovery:
    environment: *e2e-environment
  celery-normalization:
    environment: *e2e-environment
  frontend:
    ports: !reset []
  nginx:
    ports: !override
      - "127.0.0.1:8081:80"
```

Project isolation comes from every command's `-p local-business-intelligence-e2e`; separate project-scoped volumes plus `lbi_e2e` DB/bucket prevent any development data access.

- [ ] **Step 4: Написать failing real Celery/Redis test**

`backend/apps/discovery/tests/integration/test_celery_redis.py` запускает настоящие Celery consumers по очереди через `celery.contrib.testing.worker`: broker остаётся настоящим Redis, result backend отключён, а test точно контролирует отсутствие normalization consumer без управления Docker из test process.

```python
import time

import pytest
from celery.contrib.testing.worker import start_worker
from django.db import close_old_connections

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.services import start_campaign
from apps.discovery.tasks import run_discovery_campaign
from apps.sources.models import NormalizedSourceRecord, SourceRecord
from config.celery import app as celery_app


def wait_until(predicate, *, description: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        close_old_connections()
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timeout while waiting for {description}")


@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
def test_real_redis_keeps_normalization_work_until_worker_returns(
    owner, alanya_campaign
):
    assert celery_app.conf.task_always_eager is False
    assert celery_app.conf.task_routes["apps.discovery.tasks.*"]["queue"] == "discovery"
    assert celery_app.conf.task_routes["apps.normalization.tasks.*"]["queue"] == "normalization"
    celery_app.control.purge()  # безопасно: Compose project и Redis DB принадлежат этому E2E run

    captured_root_ids: list[str] = []
    start_campaign(
        campaign_id=alanya_campaign.id,
        actor=owner,
        enqueue=lambda campaign_id: captured_root_ids.append(str(campaign_id)),
    )
    assert captured_root_ids == [str(alanya_campaign.id)]

    def discovery_has_finished() -> bool:
        runs = list(
            CampaignSourceRun.objects.filter(campaign=alanya_campaign)
            .order_by("source__code")
            .values("discovery_finished_at", "stored_records")
        )
        return len(runs) == 2 and all(
            row["discovery_finished_at"] is not None and row["stored_records"] == 2
            for row in runs
        )

    with start_worker(
        celery_app,
        queues=["discovery"],
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
    ):
        run_discovery_campaign.delay(str(alanya_campaign.id))
        wait_until(discovery_has_finished, description="both discovery source runs")

    # normalization messages существуют в Redis, но consumer ещё не запускался.
    alanya_campaign.refresh_from_db()
    assert alanya_campaign.status == DiscoveryCampaign.Status.RUNNING
    assert alanya_campaign.raw_records_found == 4
    assert alanya_campaign.normalized_records == 0
    assert SourceRecord.objects.filter(campaign=alanya_campaign).count() == 4

    with start_worker(
        celery_app,
        queues=["normalization"],
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
    ):
        wait_until(
            lambda: DiscoveryCampaign.objects.filter(
                id=alanya_campaign.id,
                status=DiscoveryCampaign.Status.COMPLETED,
                normalized_records=4,
            ).exists(),
            description="normalization and campaign finalization",
        )

    alanya_campaign.refresh_from_db()
    before_retry = (
        alanya_campaign.raw_records_found,
        alanya_campaign.normalized_records,
        alanya_campaign.completed_jobs,
        alanya_campaign.failed_jobs,
    )
    assert before_retry == (4, 4, 2, 0)
    assert NormalizedSourceRecord.objects.filter(
        source_record__campaign=alanya_campaign
    ).count() == 4

    # Повторная доставка root task — no-op и не удваивает durable counters.
    with start_worker(
        celery_app,
        queues=["discovery"],
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
    ):
        replay = run_discovery_campaign.delay(str(alanya_campaign.id))
        replay.get(timeout=10)
    alanya_campaign.refresh_from_db()
    assert (
        alanya_campaign.raw_records_found,
        alanya_campaign.normalized_records,
        alanya_campaign.completed_jobs,
        alanya_campaign.failed_jobs,
    ) == before_retry
```

Для этого integration module `testing.py` задаёт `CELERY_TASK_ALWAYS_EAGER=False`, а fixture registry включается только через E2E environment. Test моделирует restart boundary точнее, чем `docker compose restart`: первый worker context полностью закрывается, messages остаются в Redis, второй consumer появляется позже.

Run:

```bash
docker compose -p local-business-intelligence-e2e \
  -f docker-compose.yml -f docker-compose.e2e.yml \
  up -d --build postgres redis minio minio-ready minio-init
docker compose -p local-business-intelligence-e2e -f docker-compose.yml -f docker-compose.e2e.yml run --rm backend \
  pytest apps/discovery/tests/integration/test_celery_redis.py -q
```

Expected first run before final wiring: FAIL по timeout/non-terminal state.

- [ ] **Step 5: Завершить integration wiring и получить backend GREEN**

`bootstrap_environment` сначала валидирует credential mode, затем выполняет `migrate`, `seed_reference_data`, `seed_sources`, `seed_taxonomy` и идемпотентно создаёт/обновляет owner только если заданы `DJANGO_SUPERUSER_USERNAME` и `DJANGO_SUPERUSER_PASSWORD`; `--require-owner` завершает command с ошибкой, если переменных нет. Password никогда не печатается. Значение `e2e-password` является публичной fixture-константой, не секретом: command принимает его только когда одновременно true `DISCOVERY_USE_FIXTURES` и `E2E_FIXTURE_CREDENTIALS` из `testing.py`; development/production эти flags игнорируют, и validation выполняется до migrations/seeds. Tests дважды вызывают command, проверяют одну user row/seed и работоспособность password, а также фиксируют guard:

```python
@override_settings(DISCOVERY_USE_FIXTURES=False, E2E_FIXTURE_CREDENTIALS=False)
def test_bootstrap_rejects_fixture_password_outside_fixture_mode(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "owner")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "e2e-password")
    with pytest.raises(CommandError, match="fixture-only"):
        call_command("bootstrap_environment", "--require-owner")
```

Host script `bootstrap-dev.sh` только вызывает management command через Compose и не содержит credentials.

```sh
#!/bin/sh
set -eu
docker compose run --rm \
  -e DJANGO_SUPERUSER_USERNAME \
  -e DJANGO_SUPERUSER_PASSWORD \
  backend python manage.py bootstrap_environment "$@"
```

Development owner передаётся только на время command:

```bash
export DJANGO_SUPERUSER_USERNAME=owner
read -r -s "DJANGO_SUPERUSER_PASSWORD?Пароль локального владельца: "
export DJANGO_SUPERUSER_PASSWORD
./infrastructure/scripts/bootstrap-dev.sh --require-owner
unset DJANGO_SUPERUSER_PASSWORD DJANGO_SUPERUSER_USERNAME
```

Команда предназначена для `zsh` из project prerequisites; пароль не попадает в shell history или repository.

```bash
docker compose -p local-business-intelligence-e2e -f docker-compose.yml -f docker-compose.e2e.yml run --rm backend \
  python manage.py bootstrap_environment --require-owner
docker compose -p local-business-intelligence-e2e -f docker-compose.yml -f docker-compose.e2e.yml run --rm \
  -e STORAGE_INTEGRATION_PROJECT=1 backend \
  pytest apps/discovery/tests/integration/test_pipeline.py \
         apps/discovery/tests/integration/test_celery_redis.py \
         apps/sources/tests/integration/test_s3_raw_payload_storage.py -q
```

Expected: PASS.

- [ ] **Step 6: Написать failing Playwright flow**

```ts
import { expect, test } from '@playwright/test';

test('login → campaign → progress → preliminary records', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Имя пользователя').fill('owner');
  await page.getByLabel('Пароль').fill('e2e-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.getByRole('link', { name: 'Новая кампания' }).click();
  await page.getByLabel('Название кампании').fill('E2E — Аланья');
  await page.getByLabel('Область поиска').selectOption({ label: 'Аланья — пилот' });
  await page.getByRole('checkbox', { name: 'Overture Maps' }).check();
  await page.getByRole('checkbox', { name: 'OpenStreetMap' }).check();
  await page.getByRole('button', { name: 'Создать кампанию' }).click();
  await page.getByRole('button', { name: 'Запустить кампанию' }).click();
  await expect(page.getByText('Завершена')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Бизнесы' }).click();
  await expect(page.getByText('Найдено записей: 4')).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Дедупликация ещё не выполнена');
});
```

`owner`/`e2e-password` в этом test — только публичная E2E fixture pair, защищённая settings/command guard выше; README прямо запрещает использовать её как development/production credential.

- [ ] **Step 7: Запустить Playwright RED, затем GREEN**

RED до test data/bootstrap/browser config:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

`frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:8081',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
```

Makefile contract:

```make
E2E_COMPOSE = docker compose -p local-business-intelligence-e2e -f docker-compose.yml -f docker-compose.e2e.yml
PLAYWRIGHT_INSTALL ?= npx playwright install chromium

e2e:
	@set -eu; trap '$(E2E_COMPOSE) down -v' EXIT INT TERM; \
	$(E2E_COMPOSE) build backend celery-discovery celery-normalization frontend nginx; \
	$(E2E_COMPOSE) up -d postgres redis minio minio-ready minio-init; \
	$(E2E_COMPOSE) run --rm backend python manage.py bootstrap_environment --require-owner; \
	$(E2E_COMPOSE) run --rm -e STORAGE_INTEGRATION_PROJECT=1 backend pytest -m integration \
	  apps/discovery/tests/integration/test_pipeline.py \
	  apps/discovery/tests/integration/test_celery_redis.py \
	  apps/sources/tests/integration/test_s3_raw_payload_storage.py -q; \
	$(E2E_COMPOSE) up -d --wait --wait-timeout 120 \
	  backend celery-discovery celery-normalization nginx; \
	cd frontend && npm ci && $(PLAYWRIGHT_INSTALL) && npm run test:e2e
```

`--wait` использует healthchecks backend, production nginx image и обоих Celery workers из Task 3. Worker считается healthy только после targeted `active_queues()` с его именем и ожидаемой queue; 30 healthcheck attempts и общий `--wait-timeout 120` ограничивают ожидание и устраняют race между стартом container process и регистрацией consumer. Playwright не запускается, пока API, обе очереди и `http://127.0.0.1:8081/` не готовы. Отдельный Vite `frontend` service в E2E runtime не нужен: nginx уже содержит production build. На macOS default устанавливает только Chromium; системные Linux packages не запрашиваются. CI ниже overrides command на `npx playwright install --with-deps chromium`. Expected final: backend integration modules PASS, Playwright 1 PASS и cleanup even after failure.

- [ ] **Step 8: Создать verification script и CI gates**

`infrastructure/scripts/verify.sh` выполняется с `set -eu`:

```bash
docker compose config --quiet
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run
docker compose run --rm backend pytest -m "not integration" -q
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run test:run
docker compose run --rm frontend npm run build
```

Final Makefile wiring:

```make
bootstrap:
	./infrastructure/scripts/bootstrap-dev.sh

verify:
	./infrastructure/scripts/verify.sh
```

После создания scripts выполнить `chmod +x infrastructure/scripts/verify.sh infrastructure/scripts/bootstrap-dev.sh` и проверить `git ls-files --stage`, где executable files имеют mode `100755`.

CI запускает `verify.sh`, а отдельный e2e job использует только fixture adapters и объявленный `bootstrap_environment`. Создать exact workflow:

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cp .env.example .env
      - run: chmod +x infrastructure/scripts/verify.sh
      - run: ./infrastructure/scripts/verify.sh

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: cp .env.example .env
      - run: make PLAYWRIGHT_INSTALL='npx playwright install --with-deps chromium' e2e
```

`make e2e` уже содержит `trap` cleanup, поэтому CI не дублирует orchestration contract. `verify.sh` и `bootstrap-dev.sh` получают executable bit в Git (`chmod +x` перед commit). Live Overture/OSM credentials не нужны ни одному job; fixture registry обязателен в e2e override.

- [ ] **Step 9: Дописать русский runbook**

README exact sections:

- prerequisites: Git, Docker Engine, Docker Compose `>=2.24.0`, Node.js `24.x`/bundled npm; команды проверки `git --version`, `docker version`, `docker compose version --short`, `node --version`, `npm --version`;
- `cp .env.example .env`;
- bootstrap/start/stop;
- URL dashboard/API/MinIO console;
- создание owner;
- команды test/lint/e2e;
- live Overture opt-in;
- обязательный `OVERPASS_URL`/`SOURCE_USER_AGENT` и запрет bulk dependency на public Overpass;
- raw object key/backup priorities;
- troubleshooting Redis/MinIO/PostGIS;
- предупреждение, что записи ещё не являются каноническими бизнесами.

- [ ] **Step 10: Полная свежая verification**

```bash
make down
docker compose -p local-business-intelligence-e2e \
  -f docker-compose.yml -f docker-compose.e2e.yml down -v
make up
make verify
make e2e
```

Expected: clean e2e database/bootstrap succeeds; all backend/frontend/e2e checks pass; no warnings/errors in test output. `down -v` использует отдельный Compose project `local-business-intelligence-e2e`; development volumes не удаляются.

- [ ] **Step 11: Commit**

```bash
git add backend/apps/discovery backend/apps/system backend/config frontend/e2e frontend/playwright.config.ts infrastructure/scripts .github Makefile README.md docker-compose.e2e.yml
git commit -m "test: verify end-to-end discovery vertical slice"
```

---

## 2. Итоговый API contract

```text
GET  /api/v1/health/live/
GET  /api/v1/health/ready/
GET  /api/v1/auth/csrf/
POST /api/v1/auth/login/
POST /api/v1/auth/logout/
GET  /api/v1/auth/session/
GET  /api/v1/geography/search-areas/
GET  /api/v1/taxonomy/categories/
GET  /api/v1/sources/
GET  /api/v1/campaigns/
POST /api/v1/campaigns/
GET  /api/v1/campaigns/{id}/
POST /api/v1/campaigns/{id}/start/
GET  /api/v1/campaigns/{id}/progress/
GET  /api/v1/source-records/
GET  /api/v1/source-records/{id}/
GET  /api/v1/dashboard/summary/
```

Любой endpoint вне этого списка требует отдельного scope decision. В частности, `/businesses/`, pause/resume/cancel, raw download и admin mutation APIs в этом плане отсутствуют.

## 3. Итоговые queue и persistence invariants

```text
apps.discovery.tasks.*       → discovery
apps.normalization.tasks.*   → normalization
```

- `(campaign_id, source_id, external_id)` не дублируется.
- Для одного `(source, campaign, external_id)` одинаковый raw JSON всегда даёт одинаковый payload SHA-256, gzip bytes и object key; другой `external_id` даёт отдельный key/metadata.
- `SourceRecord` создаётся только после успешного object put.
- Повтор persistence/normalization task не увеличивает counters второй раз.
- Один delivery token создаёт не более одной `PipelineRetryReservation`; broker redelivery не списывает business retry budget повторно.
- Database retries не меняют provider/storage retry counters; исчерпанный business budget всегда приводит к durable terminal outcome.
- Каждый worker healthy только при точном множестве queues: `{discovery}` либо `{normalization}`.
- `normalized + rejected + failed == stored` для terminal source run.
- Campaign terminal status выводится только из PostgreSQL source runs.
- Две одинаковые компании из Overture и OSM остаются двумя normalized rows до следующего deduplication plan.

## 4. Финальный checklist перед merge

- [ ] Fresh `docker compose config --quiet` завершился с exit 0.
- [ ] Fresh backend `ruff check`, `ruff format --check`, Django check и migration check прошли.
- [ ] Fresh full backend pytest suite прошёл с 0 failures.
- [ ] Fresh frontend lint, typecheck, Vitest и production build прошли.
- [ ] Fresh Playwright discovery flow прошёл на clean e2e volumes.
- [ ] Нет real secrets, `.env`, raw contact fixtures или public MinIO bucket в diff.
- [ ] Нет apps/queues/routes для отложенных подсистем.
- [ ] Все UI strings первого среза русские; API keys/status codes английские.
- [ ] Overture/OSM attribution и dataset version видимы в record detail/progress.
- [ ] UI нигде не утверждает, что records уникальны или дедуплицированы.
- [ ] `git status --short` содержит только ожидаемые implementation changes до финального commit и пуст после него.

## 5. Рекомендуемый следующий план

После фактической проверки этого среза на Alanya fixtures и небольшом разрешённом live sample создать отдельный spec/plan для:

```text
NormalizedSourceRecord
→ candidate generation
→ deterministic match scoring
→ AUTO_MERGE / POSSIBLE_DUPLICATE / DISTINCT
→ canonical Business
→ reversible merge + review UI
```

Не добавлять enrichment/crawling/audits/scoring в deduplication plan: каждый из них должен оставаться отдельным проверяемым vertical slice.
