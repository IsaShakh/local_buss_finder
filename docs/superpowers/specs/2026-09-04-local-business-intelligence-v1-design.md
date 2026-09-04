# Local Business Intelligence v1 — Design Spec

**Статус:** согласовано для планирования<br>
**Версия документа:** 1.0<br>
**Дата:** 2026-09-04<br>
**Основной рынок:** Турция<br>
**Первый operational area:** Antalya → Alanya<br>
**Целевой объём v1:** 100 000–300 000 найденных `SourceRecord` до дедупликации<br>
**Тип продукта:** внутренний single-user инструмент<br>
**Язык продукта и документации:** русский
**Язык кода, API, схемы данных и технических статусов:** английский

## 1. Назначение

Система находит записи о локальных бизнесах из нескольких публичных источников, сохраняет исходные данные с provenance и приводит записи к единому формату. После отдельного entity-resolution среза она формирует канонические `Business`, проверяет их цифровое присутствие и определяет коммерческие возможности.

Конечный v1 должен помогать находить кандидатов на следующие услуги:

- создание или модернизация сайта;
- онлайн-запись и бронирование;
- WhatsApp-автоматизация;
- автоматизация обработки заявок;
- мультиязычный сайт;
- базовые SEO-улучшения;
- другие возможности, выводимые прозрачными детерминированными правилами.

v1 не автоматизирует продажи. Его результат — качественная, объяснимая и фильтруемая база потенциальных клиентов.

## 2. Зафиксированные принципы

1. Архитектура географически универсальна. Alanya — параметр первого запуска, а не условие в коде.
2. Backend — modular monolith. Асинхронные процессы запускаются Celery workers из одной кодовой базы.
3. Источники подключаются через единый adapter contract. Pipeline после discovery не знает деталей провайдера.
4. Полный raw payload сохраняется до преобразований. Нормализацию можно повторить без нового запроса к источнику.
5. `SourceRecord` и provenance не уничтожаются при последующей дедупликации.
6. PostgreSQL — источник истины для состояния и прогресса. Redis можно потерять и восстановить.
7. Пользовательские тексты — русские; enum values, field names, error codes и identifiers — английские.
8. Scoring и opportunity detection в полном v1 детерминированы и версионированы. AI/ML не используется.
9. Отсутствие сайта или контактов не является причиной удалить `SourceRecord` или его raw lineage; после entity resolution то же правило применяется к canonical `Business`.
10. Крупные национальные и международные сети позднее исключаются из qualified leads, но их записи сохраняются.
11. Платные источники применяются только точечно после измерения прироста качества.
12. Любое новое поведение разрабатывается через RED → GREEN → REFACTOR.
13. Все статусы, сохраняемые в PostgreSQL и передаваемые API, используют lowercase English values (например, `queued`, `normalizing`, `completed_with_errors`); error codes используют uppercase snake case.

## 3. Границы продукта

### 3.1. Полный scope v1

В целевой v1 входят:

- управление сбором из React dashboard;
- выбор географии, категорий и источников;
- multi-source discovery;
- raw payload storage и provenance;
- normalization и source category mapping;
- deterministic deduplication и review queue;
- различение дубля и отдельного филиала;
- `BusinessGroup` и классификация сетей;
- поиск и проверка официального сайта;
- сбор публичных телефонов, email, WhatsApp и социальных профилей;
- ограниченный crawling ключевых страниц;
- сохранение HTML snapshots;
- технический и conversion-oriented website audit;
- deterministic scoring и объяснимые score components;
- commercial opportunities;
- таблица, карточка и карта бизнесов;
- quality-control screens;
- CSV/XLSX export;
- статистика запросов и стоимости платных источников.

### 3.2. Non-scope v1

Не входят:

- CRM и история коммуникаций;
- email, WhatsApp или phone outreach;
- multi-tenancy, organizations, workspaces и роли команды;
- SaaS billing и subscriptions;
- AI-анализ, ML scoring и AI-оценка дизайна;
- автоматический recurring discovery/re-crawl;
- социальная аналитика;
- скриншоты сайтов;
- полноценный конкурентный анализ;
- Kubernetes, Kafka, Elasticsearch, MongoDB и microservices.

### 3.3. Delivery slices

Полный v1 поставляется последовательными вертикальными срезами.

Первый срез ограничен цепочкой:

```text
Войти в русский dashboard
→ создать кампанию для SearchArea
→ выбрать Overture и/или OSM
→ запустить Celery discovery
→ сохранить gzip JSON в S3-compatible object storage
→ сохранить SourceRecord в PostgreSQL
→ нормализовать SourceRecord
→ показать предварительные найденные записи
→ показать долговечный прогресс кампании
```

В первом срезе не реализуются `deduplication`, canonical `Business`, `enrichment`, `crawling`, `audits`, `scoring`, `opportunities` и exports. Каждая из этих подсистем получает отдельные spec, plan и acceptance criteria до реализации; наличие её в полном scope v1 не разрешает добавлять её в этот срез.

## 4. Разрешение термина «таблица бизнесов» в первом срезе

В полной архитектуре `Business` — каноническая физическая точка после entity resolution. Создать такую сущность корректно до дедупликации нельзя.

Поэтому экран «Бизнесы» первого среза показывает `NormalizedSourceRecord` и явно сообщает:

> Предварительные записи. Дедупликация ещё не выполнена; одна компания может встречаться несколько раз.

API первого среза использует `/api/v1/source-records/`, а `/api/v1/businesses/` резервируется для канонических `Business` следующего среза. Счётчик называется «Найдено записей», не «Уникальных бизнесов».

Это решение не создаёт provisional `Business`, не скрывает межисточниковые дубли и не требует менять контракт `/businesses/` позднее.

## 5. Архитектура

```text
                         nginx
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       React + TypeScript          Django REST API
                                            │
                  ┌─────────────────────────┼───────────────────────┐
                  ▼                         ▼                       ▼
         PostgreSQL + PostGIS           Redis          S3-compatible storage
                  ▲                         │
                  │               ┌─────────┴──────────┐
                  │               ▼                    ▼
                  └──── Celery discovery      Celery normalization
```

- Django API отвечает за session auth, metadata, команды пользователя и чтение состояния.
- Celery workers выполняют внешние I/O и преобразования.
- PostgreSQL/PostGIS хранит domain data, geometry, statuses, counters и audit metadata.
- S3-compatible object storage хранит большие immutable blobs; local/E2E backend — Garage.
- Redis используется как Celery broker и, при необходимости, для краткоживущих locks/rate limits. Результаты Celery tasks не сохраняются: продуктовый progress живёт только в PostgreSQL.
- Frontend получает прогресс периодическим запросом; WebSocket/Channels в первом срезе не нужны.

## 6. Технологический baseline

Консервативная линия для реализации:

| Область | Baseline |
|---|---|
| Python | 3.13.x |
| Django | 5.2 LTS |
| Django REST Framework | 3.16.x |
| PostgreSQL | 17.x |
| PostGIS | 3.6.x |
| Redis | 7.4.x LTS |
| Celery | 5.5.x |
| Node.js | 24.x LTS |
| React / React DOM | 19.2.x |
| TypeScript | 5.x, exact version in lockfile |
| Vite | 8.x, exact version in lockfile |
| Vitest | 5.x, exact version in lockfile |
| Docker Compose | 2.24+ |

Runtime images pin major/minor plus immutable digest before production deployment. Python and npm dependency graphs are committed as lockfiles. Upgrade dependencies отдельными commits с полным test suite.

## 7. Целевая структура monorepo

```text
.
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   ├── testing.py
│   │   │   └── production.py
│   │   ├── api_urls.py
│   │   ├── celery.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── geography/
│   │   ├── taxonomy/
│   │   ├── sources/
│   │   ├── campaigns/
│   │   ├── discovery/
│   │   ├── normalization/
│   │   ├── businesses/
│   │   └── system/
│   ├── common/
│   ├── requirements/
│   ├── tests/
│   ├── manage.py
│   └── Dockerfile
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   ├── app/
│   │   ├── components/
│   │   └── features/
│   ├── e2e/
│   ├── package.json
│   └── Dockerfile
├── infrastructure/
│   ├── nginx/
│   ├── postgres/
│   └── scripts/
├── tests/
│   └── infra/
├── docs/
├── .env.example
├── docker-compose.yml
├── docker-compose.e2e.yml
├── Makefile
└── README.md
```

Модули будущих срезов (`deduplication`, `enrichment`, `crawling`, `audits`, `scoring`, `opportunities`, `exports`) не создаются пустыми заранее. Они добавляются, когда появляется исполняемое поведение.

## 8. Backend modules первого среза

| Module | Ответственность | Не делает |
|---|---|---|
| `system` | health checks, auth endpoints, API error envelope, logging context | discovery и domain transforms |
| `geography` | иерархия территории и `SearchArea.geometry` | geocoding внешних адресов |
| `taxonomy` | внутренняя taxonomy | provider-specific fetching |
| `sources` | `Source`, `SourceRecord`, raw metadata и storage port | normalization rules |
| `campaigns` | campaign state machine, selections, source runs, progress | сетевые запросы к источникам |
| `discovery` | adapter contract, Overture/OSM clients, orchestration | deduplication и scoring |
| `normalization` | pure transforms, versioned result и task | merge записей |
| `businesses` | в первом срезе только read model/API поверх normalized records | canonical `Business` до deduplication |

## 9. Модель данных первого среза

Все domain entities используют UUID primary key и UTC timestamps. Геометрия хранится в SRID 4326.

### 9.1. Geography

```text
Country
  id, code, name, name_ru, geometry, created_at, updated_at

Province
  id, country_id, code, name, name_ru, geometry, created_at, updated_at

District
  id, province_id, slug, name, name_ru, geometry, created_at, updated_at

Neighborhood
  id, district_id, slug, name, name_ru, geometry, created_at, updated_at

SearchArea
  id, name, country_id, province_id, district_id, neighborhood_id,
  geometry, is_active, created_at, updated_at
```

Constraints:

- `Country.code` unique, ISO 3166-1 alpha-2 (`TR` для Türkiye).
- `Province(country_id, code)` unique.
- `District(province_id, slug)` и `Neighborhood(district_id, slug)` unique.
- `SearchArea.geometry` — valid non-empty `MultiPolygon`.
- Если в `SearchArea` указан дочерний уровень, его ancestry должна совпадать с остальными FK.
- GiST indexes создаются для всех geometry fields, используемых в spatial filters.

Первый seed создаёт `Türkiye → Antalya → Alanya` и operational `SearchArea` «Аланья — пилот». Его точный pilot bbox — `(west=31.70, south=36.30, east=32.65, north=36.75)`; `SearchArea.geometry` строится из него как SRID 4326 `MultiPolygon(Polygon.from_bbox(...))`. Геометрия AOI документируется как рабочая область сбора; она не выдаётся за юридически точную административную границу без проверенного источника.

### 9.2. Taxonomy

```text
BusinessCategory
  id, name, slug, parent_id, is_active, created_at, updated_at

SourceCategoryMapping
  id, source_id, external_category, category_id, is_active,
  created_at, updated_at
```

Constraints:

- `BusinessCategory.slug` unique.
- Иерархия не допускает self-parent и циклы.
- `SourceCategoryMapping(source_id, external_category)` unique.
- Неизвестная категория даёт `category_id = null` и warning `UNKNOWN_CATEGORY`, но не отбрасывает запись.

Первый seed содержит минимум:

```text
Медицина → Стоматология
Недвижимость → Агентство недвижимости
Гостеприимство → Отель
Красота → Салон красоты
```

Первые provider mappings используют точные строки `external_category`:

```text
overture: dentist → Стоматология
overture: real_estate_agent → Агентство недвижимости
overture: hotel → Отель
overture: beauty_salon → Салон красоты
osm: amenity=dentist → Стоматология
osm: office=estate_agent → Агентство недвижимости
osm: tourism=hotel → Отель
osm: shop=beauty → Салон красоты
```

### 9.3. Source

```text
Source
  id
  code                  overture | osm
  name                  Overture Maps | OpenStreetMap
  source_type           open_data | api | directory | website | manual
  attribution
  license_code
  is_paid
  is_active
  requests_per_second
  concurrency
  timeout_seconds
  max_retries
  settings              JSONB, без secrets
  request_count
  total_cost
  created_at
  updated_at
```

`code` unique. Secrets и private endpoints поступают только через environment/settings, не через `settings` и не через Git.

### 9.4. DiscoveryCampaign

```text
DiscoveryCampaign
  id
  name
  created_by_id
  search_area_id
  status
  started_at
  finished_at
  total_jobs
  completed_jobs
  failed_jobs
  raw_records_found
  normalized_records
  rejected_records
  created_at
  updated_at

CampaignSource
  id, campaign_id, source_id, is_enabled, priority,
  request_limit, budget_limit, created_at, updated_at

CampaignCategory
  id, campaign_id, category_id, created_at

CampaignSourceRun
  id
  campaign_id
  source_id
  status
  source_dataset_version
  discovered_records
  stored_records
  normalized_records
  rejected_records
  failed_records
  request_count
  source_retry_count
  cost
  started_at
  discovery_finished_at
  finished_at
  error_code
  error_detail
  created_at
  updated_at

PipelineRetryReservation
  id
  campaign_id
  scope                     source_discovery | source_normalization
  work_id                   CampaignSourceRun.id | SourceRecord.id
  delivery_token            Celery task-id:delivery-retry-number
  allowed
  created_at
```

Campaign statuses (значения ниже совпадают с PostgreSQL/API):

```text
draft → queued → running → completed
                         ↘ completed_with_errors
             ↘ failed
```

Первый срез не предоставляет pause/resume. Эти transitions добавляются вместе с безопасной отменой и checkpointing, а не имитируются остановкой worker.

Source-run statuses:

```text
pending → running → normalizing → completed
                          ↘ completed_with_errors
          ↘ failed
```

Прогресс рассчитывается только из сохранённых counters и состояний PostgreSQL. Обновление counters атомарно через `F()` expressions или row lock. Если transaction требует несколько locks, порядок всегда `DiscoveryCampaign → CampaignSourceRun → SourceRecord`. `completed_jobs + failed_jobs <= total_jobs` — обязательный invariant. Единственный locked transition source run в terminal state увеличивает ровно один из `completed_jobs` или `failed_jobs` один раз; повтор transition counters не меняет. `source_retry_count` — отдельный durable budget атомарно выданных business retry reservations для transient provider/raw-write ошибок; временная недоступность PostgreSQL этот counter не меняет.

`PipelineRetryReservation` unique по `(scope, work_id, delivery_token)`. Повторная доставка того же Celery message получает прежнее `allowed` и не списывает budget второй раз. Разрешённая reservation и увеличение соответствующего counter фиксируются одной PostgreSQL transaction; запрещённая reservation сохраняет `allowed=false`, не увеличивает counter и детерминированно ведёт к terminal outcome. Это закрывает окно, где публикация `self.retry` не удалась после DB commit: при redelivery тот же delivery token переиспользует reservation.

В первом срезе `discovered_records` и `stored_records` увеличиваются вместе только для нового durable payload outcome (`SourceRecord` либо `SourceRecordConflict`) после успешного object put; retries того же `(external_id, checksum)` их не меняют. Поэтому transient storage attempt не отображается как найденная запись, а terminal invariant остаётся `normalized_records + rejected_records + failed_records == stored_records`. Campaign `raw_records_found` — сумма новых durable payload outcomes, включая conflicts, а не количество canonical businesses.

### 9.5. SourceRecord

```text
SourceRecord
  id
  campaign_id
  source_run_id
  source_id
  external_id
  source_dataset_version
  source_url
  attribution
  license_code
  raw_name                  nullable
  raw_category              nullable
  raw_address               nullable
  raw_phones                JSONB list[str]
  raw_emails                JSONB list[str]
  raw_websites              JSONB list[str]
  raw_social_urls           JSONB object[str, list[str]]
  raw_location              PointField, nullable
  raw_payload_key
  raw_payload_sha256
  raw_payload_bytes
  payload_schema_version
  checksum
  normalization_status
  normalization_retry_count
  normalization_error_code
  parser_error_code         nullable
  fetched_at
  created_at
  updated_at
```

```text
SourceRecordConflict
  id
  campaign_id
  source_run_id
  source_id
  external_id
  original_source_record_id
  conflicting_payload_sha256
  raw_payload_key
  raw_payload_bytes
  payload_schema_version
  source_dataset_version
  error_code                SOURCE_RECORD_CONFLICT
  counted_at
  created_at
  updated_at
```

Constraints:

- `(campaign_id, source_id, external_id)` unique: retry внутри кампании не создаёт дубль.
- Повтор с тем же checksum идемпотентен.
- `checksum` равен SHA-256 canonical JSON payload и поэтому равен `raw_payload_sha256`.
- Повтор с другим checksum не перезаписывает первый payload. Он создаёт durable `SourceRecordConflict`, unique по `(campaign_id, source_id, external_id, conflicting_payload_sha256)`, с `error_code=SOURCE_RECORD_CONFLICT`; повтор того же конфликта идемпотентен.
- Первый `SourceRecord` остаётся неизменным. Новый immutable raw object сохраняется, а новый conflict outcome атомарно увеличивает `discovered_records`, `stored_records`, `failed_records` и campaign `raw_records_found` ровно один раз, поэтому участвует в finalization invariant даже без второй строки `SourceRecord`.
- Для parser error создаётся `SourceRecord` с nullable raw fields, `normalization_status=failed` и `parser_error_code`; raw payload и provenance всё равно сохраняются.
- `normalization_retry_count` — отдельный durable budget атомарно выданных business retry reservations для transient raw-read/storage ошибок этой записи; он не связан с механическим Celery retry counter.
- `raw_payload_key` указывает на приватный S3-compatible object.
- Удаление campaign не выполняется обычным UI/API; raw lineage сохраняется.

### 9.6. NormalizedSourceRecord

```text
NormalizedSourceRecord
  id
  source_record_id          one-to-one
  display_name
  normalized_name
  match_name
  category_id               nullable
  address_text
  country_id                nullable
  province_id               nullable
  district_id               nullable
  neighborhood_id           nullable
  location                  PointField, nullable
  phones                    JSONB list[str]
  emails                    JSONB list[str]
  websites                  JSONB list[str]
  social_urls               JSONB object[str, list[str]]
  attributes                JSONB
  warnings                  JSONB list[str]
  normalization_version
  normalized_at
  created_at
  updated_at
```

`source_record_id` unique. Повтор той же `normalization_version` обновляет результат детерминированно, не создавая вторую строку. Новая версия сначала перепроверяется на fixtures; история версий нормализации добавляется отдельным решением, когда появится необходимость сохранять несколько materialized outputs одновременно.

## 10. Raw payload storage

PostgreSQL хранит searchable metadata, S3-compatible object storage — полный canonical JSON, сжатый gzip. В local/E2E используется Garage; production provider выбирается отдельно за тем же S3 contract.

Object key:

```text
raw/{source_code}/{campaign_id}/{external_id_sha256}/{payload_sha256}.json.gz
```

`external_id_sha256` — полный lowercase SHA-256 по UTF-8 provider ID; `payload_sha256` — полный lowercase SHA-256 по несжатому canonical JSON. Поэтому разные provider IDs с одинаковым JSON получают разные objects и собственную metadata, а произвольный provider ID не попадает в path. Содержимое сериализуется через UTF-8 JSON с `sort_keys=true`, компактными separators и deterministic gzip `mtime=0`. `raw_payload_bytes` — размер сжатого gzip object в bytes, а не размер canonical JSON.

Object metadata:

```text
source-code
campaign-id
external-id
sha256
payload-schema-version
source-dataset-version
```

Bucket private; API не отдаёт permanent public URL. Все шесть metadata fields выше обязательны для каждого object. Детерминированный key по provider ID и content hash делает повторную загрузку идемпотентной и минимизирует последствия отсутствия общей транзакции PostgreSQL ↔ object storage. Regression contract требует: одинаковый payload с разными `external_id` имеет одинаковый `payload_sha256`, разные keys и корректный `external-id` в metadata каждого object.

## 11. Discovery adapter contract

```python
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

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

`discover()` делает только provider I/O. `parse_payload()` извлекает provider-specific raw fields. Generic persistence и normalization находятся за пределами adapter. Pipeline сначала сохраняет полученный `SourcePayload.payload` в raw storage, а затем вызывает `parse_payload()`; parser failure не может удалить или предотвратить сохранение raw evidence.

Если provider row не содержит usable ID, adapter вычисляет synthetic `external_id="invalid:{sha256-canonical-payload}"`; parser затем возвращает `INVALID_SOURCE_PAYLOAD`. Это даёт failed `SourceRecord` и достижимый raw object вместо бесхозного blob.

`DiscoveryRequest.external_categories` всегда non-empty: пустой пользовательский `category_ids` до adapter boundary разворачивается в active mappings отдельно для каждого source. Это запрещает случайный unbounded запрос «все POI».

Ошибки adapter классифицируются:

```text
TransientSourceError     retry с exponential backoff + jitter
RateLimitedSourceError   retry с учётом Retry-After
PermanentSourceError     без retry
InvalidSourcePayload     запись/запуск помечается ошибкой, payload сохраняется если получен
```

## 12. Overture adapter

`OvertureAdapter` использует официальный Python client и `record_batch_reader("place", bbox=..., release=..., stac=True)`.

Правила:

- release разрешается через Overture STAC один раз при старте `CampaignSourceRun`;
- строка release сохраняется в `source_dataset_version` и используется до конца run;
- внешний ID — Overture GERS `id`;
- географический prefilter выполняется bbox, точная проверка принадлежности `SearchArea.geometry` — локально/PostGIS;
- category parser читает актуальные `taxonomy.primary` / `basic_category` и поддерживает fallback `categories.primary` для переходных releases;
- полный feature превращается в JSON-compatible payload без потери provider fields;
- unit/contract tests используют небольшие fixtures, а не live S3/STAC;
- live smoke test opt-in и не входит в обязательный CI.

## 13. OSM adapter

`OpenStreetMapAdapter` использует Overpass QL через configurable `OVERPASS_URL`.

Для первых mappings:

```text
amenity=dentist       → Стоматология
office=estate_agent   → Агентство недвижимости
tourism=hotel         → Отель
shop=beauty            → Салон красоты
```

Query объединяет `node`, `way`, `relation` через `nwr[...]({bbox})` и возвращает `out center tags;`. External ID имеет форму `{type}/{id}`. Для node используются `lat/lon`, для way/relation — `center.lat/center.lon`.

Public Overpass servers не считаются production dependency для коммерческого bulk discovery. Production требует явно настроенный self-hosted/paid endpoint, соблюдение его limits и контактный `User-Agent`. Endpoint, timeout, concurrency и rate limit меняются без deploy через environment/`Source` settings.

OSM provenance включает `ODbL-1.0` и строку `© OpenStreetMap contributors`. `resolve_dataset_version()` возвращает непустое значение из `OSM_DATASET_VERSION` (для production — обязательный version self-hosted/paid snapshot, например replication sequence); если оно не задано в development, используется явно непроизводственный retrieval marker `overpass-live:<sha256-normalized-endpoint-12>:<UTC-run-start RFC3339>`. Это значение фиксируется на старте `CampaignSourceRun` и передаётся в provenance каждого payload. 429/502/503/504 — transient; malformed query и schema mismatch — permanent/parser error.

## 14. Normalization contract

```python
@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float

@dataclass(frozen=True)
class NormalizedBusinessData:
    display_name: str
    normalized_name: str
    match_name: str
    category_id: UUID | None
    address_text: str
    location: GeoPoint | None
    phones: tuple[str, ...]
    emails: tuple[str, ...]
    websites: tuple[str, ...]
    social_urls: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]
    attributes: dict[str, JSONValue]

@dataclass(frozen=True)
class NormalizationResult:
    status: Literal["normalized", "rejected"]
    data: NormalizedBusinessData | None
    error_code: str | None

def normalize_business_record(
    raw: RawBusinessRecord,
    *,
    category_id: UUID | None,
) -> NormalizationResult: ...
```

Rules `tr-v1`:

- name обязателен; пустое имя → `MISSING_NAME` и rejected;
- Unicode приводится к NFKC, whitespace схлопывается;
- `display_name` сохраняет турецкие символы и читабельный регистр;
- `normalized_name` — lowercase/casefold с нормализованным whitespace;
- `match_name` дополнительно транслитерирует `ç→c`, `ğ→g`, `ı→i`, `ö→o`, `ş→s`, `ü→u` и удаляет юридические suffixes (`Ltd.`, `Ltd. Şti.`, `A.Ş.`, `Anonim Şirketi`) только с конца;
- телефон нормализуется в E.164 с default region `TR`;
- email lowercase; invalid email не публикуется и даёт warning;
- URL получает lowercased hostname, http/https scheme и удалённый fragment; path/query не теряются;
- longitude проверяется в `[-180, 180]`, latitude — в `[-90, 90]`; invalid coordinates не отклоняют запись: `location=null` и warning `INVALID_COORDINATES`;
- unknown category → `category_id=null` + `UNKNOWN_CATEGORY`;
- отсутствие телефона, email, сайта или координат допустимо;
- `country`/`province`/`district`/`neighborhood` копируются из campaign `SearchArea` как scope сбора, а не выводятся из свободного адреса; `attributes.geography_basis="search_area"` делает это происхождение явным;
- выход детерминирован: одинаковые raw input, mapping и version дают одинаковый результат.

## 15. Pipeline и идемпотентность первого среза

```text
POST /campaigns/{id}/start/
  → status queued (transaction.on_commit)
  → run_discovery_campaign(campaign_id)
  → один CampaignSourceRun на enabled source
  → run_source_discovery(source_run_id)
  → adapter.discover()
  → RawPayloadStore.put_json()
  → persist SourceRecord
  → normalize_source_record.delay(source_record_id)
  → persist NormalizedSourceRecord or rejected status
  → atomically update counters
  → try_finalize_campaign(campaign_id)
```

`run_discovery_campaign` атомарно переводит campaign `queued → running` перед запуском source runs. Для каждого полученного provider payload pipeline сначала записывает immutable canonical gzip object, затем парсит его и создаёт normalizable `SourceRecord` либо failed `SourceRecord` с `parser_error_code`. Celery messages передают UUID, а не payload. Retry policy применяется только к transient I/O. Validation и parser errors не ретраятся бесконечно.

Business retry budgets хранятся независимо: `CampaignSourceRun.source_retry_count` для discovery/provider/raw-write и `SourceRecord.normalization_retry_count` для normalization/raw-read. При transient business error worker атомарно создаёт идемпотентную `PipelineRetryReservation` для delivery token и увеличивает соответствующий counter, только если лимит `Source.max_retries` ещё не исчерпан; иначе записывает terminal outcome без нового retry. Встроенный Celery `request.retries` участвует в delivery token и capped exponential backoff, но не определяет business exhaustion. Database connection failure использует механический unbounded retry task с alert, не изменяет business counters и после восстановления оставляет полный неистраченный provider/storage budget. После исчерпания короткой publish-retry policy broker publish failure преобразуется в явный `Reject(requeue=True)`; redelivery переиспользует ту же reservation. Эти гарантии проверяются mixed-sequence test `database failure → recovery → provider/storage failure` и test `retry publish failure → same-token redelivery`.

После parser возвращает координаты, pipeline выполняет точную проверку `SearchArea.geometry.covers(point)` в PostGIS для всех adapters: bbox — только prefilter. Payload с валидной точкой вне AOI создаёт долговечный `SourceRecord` с `normalization_status=rejected` и `normalization_error_code=OUTSIDE_SEARCH_AREA`; он учитывается один раз в `discovered_records`, `stored_records`, `rejected_records` и campaign counters, но не попадает в normalized-only list API. Так raw object не становится бесхозным, а AOI остаётся точным фильтром продуктового результата. Payload без координат допустим: он создаёт/нормализует `SourceRecord` с `location=null`, warning `MISSING_COORDINATES`, не считается доказанно находящимся внутри AOI и не получает искусственной географии.

Campaign завершается, когда:

1. все source runs закончили discovery;
2. для каждого run `normalized_records + rejected_records + failed_records == stored_records`;
3. нет source run в `pending`, `running` или `normalizing`.

Успешно завершившийся source run с нулём результатов является `completed`. Irrecoverable provider failure до появления records даёт ready run `failed`; если records уже сохранены, run сначала обрабатывает их и становится `completed_with_errors`. Campaign finalization требует, чтобы все runs одновременно были ready и terminal. Если хотя бы один run `completed_with_errors`/`failed` или есть failed records, но существует успешно завершившийся run, campaign получает `completed_with_errors`; если все enabled source runs `failed`, campaign получает `failed`; иначе `completed`.

## 16. API первого среза

Все endpoints находятся под `/api/v1/`, требуют session authentication, кроме health и login/CSRF.

```text
GET  /health/live/
GET  /health/ready/

GET  /auth/csrf/
POST /auth/login/
POST /auth/logout/
GET  /auth/session/

GET  /geography/search-areas/
GET  /taxonomy/categories/
GET  /sources/

GET  /campaigns/
POST /campaigns/
GET  /campaigns/{id}/
POST /campaigns/{id}/start/
GET  /campaigns/{id}/progress/

GET  /source-records/
GET  /source-records/{id}/

GET  /dashboard/summary/
```

`POST /campaigns/`:

```json
{
  "name": "Аланья — первичный сбор",
  "search_area_id": "uuid",
  "source_ids": ["uuid", "uuid"],
  "category_ids": []
}
```

Пустой `category_ids` означает «все активные mappings выбранного source» и разворачивается независимо для каждого source, а не в запрос всех возможных OSM tags. Для непустого списка берутся только active mappings выбранного source для выбранных categories. Если для выбранного source итоговый набор mappings пуст, campaign не создаётся и API возвращает `SOURCE_HAS_NO_ACTIVE_MAPPINGS` с field error для этого source.

`GET /campaigns/{id}/progress/`:

```json
{
  "id": "uuid",
  "status": "running",
  "totals": {
    "jobs": 2,
    "completed_jobs": 0,
    "failed_jobs": 0,
    "discovered": 120,
    "stored": 120,
    "normalized": 93,
    "rejected": 2,
    "failed_records": 0
  },
  "sources": [
    {
      "code": "overture",
      "name": "Overture Maps",
      "status": "normalizing",
      "dataset_version": "2026-08-19.0",
      "discovered": 80,
      "stored": 80,
      "normalized": 60,
      "rejected": 1,
      "failed_records": 0
    }
  ]
}
```

API error envelope:

```json
{
  "error": {
    "code": "CAMPAIGN_NOT_DRAFT",
    "detail": "Запустить можно только черновик кампании.",
    "fields": {}
  }
}
```

Pagination — server-side, default 50, maximum 100. `/source-records/` возвращает только `NormalizedSourceRecord` и поддерживает `search`, `campaign`, `source`, `category`, `ordering`; `normalization_status` не является filter параметром этого normalized-only endpoint.

List endpoint normalized-only, но detail endpoint принимает ID любого принадлежащего пользователю `SourceRecord`, включая `pending`, `rejected` и `failed`: это нужно для provenance/диагностики. Чужой или несуществующий ID возвращает одинаковый 404.

`GET /source-records/{id}/` возвращает exact detail response; raw payload body, presigned/public object URL и S3 credentials в него не входят:

```json
{
  "id": "uuid",
  "is_canonical": false,
  "campaign_id": "uuid",
  "source_run_id": "uuid",
  "source": {"code": "osm", "name": "OpenStreetMap"},
  "external_id": "node/101",
  "source_dataset_version": "overpass-live:93a4c12572a1:2026-09-04T12:00:00Z",
  "source_url": null,
  "attribution": "© OpenStreetMap contributors",
  "license_code": "ODbL-1.0",
  "raw": {
    "name": "Alanya Test Diş Kliniği",
    "category": "amenity=dentist",
    "address": null,
    "phones": [],
    "emails": [],
    "websites": [],
    "social_urls": {},
    "location": {"type": "Point", "coordinates": [32.002, 36.545]}
  },
  "payload": {
    "key": "raw/osm/campaign-id/external-id-sha256/payload-sha256.json.gz",
    "sha256": "sha256",
    "bytes": 123,
    "schema_version": "1"
  },
  "normalization_status": "normalized",
  "normalization_error_code": null,
  "parser_error_code": null,
  "fetched_at": "2026-09-04T12:00:00Z",
  "normalized": {
    "display_name": "Alanya Test Diş Kliniği",
    "normalized_name": "alanya test diş kliniği",
    "match_name": "alanya test dis klinigi",
    "category": {"id": "uuid", "name": "Стоматология", "slug": "dentist"},
    "address_text": "",
    "country": {"id": "uuid", "name": "Турция", "code": "TR"},
    "province": {"id": "uuid", "name": "Анталья", "code": "07"},
    "district": {"id": "uuid", "name": "Аланья", "slug": "alanya"},
    "neighborhood": null,
    "location": {"type": "Point", "coordinates": [32.002, 36.545]},
    "phones": [],
    "emails": [],
    "websites": [],
    "social_urls": {},
    "attributes": {},
    "warnings": [],
    "normalization_version": "tr-v1",
    "normalized_at": "2026-09-04T12:00:01Z"
  }
}
```

Для rejected/failed record `normalized` равно `null`; nullable raw fields и payload metadata всё равно возвращаются. List items также всегда содержат `is_canonical: false`.

## 17. Frontend первого среза

Routes:

```text
/login
/
/campaigns
/campaigns/new
/campaigns/:campaignId
/businesses
```

Обязательные экраны:

- русская форма входа и выход;
- защищённая оболочка приложения с навигацией;
- «Обзор» со счётчиками и последними кампаниями;
- список кампаний;
- форма новой кампании: название, `SearchArea`, все/выбранные категории, Overture/OSM;
- экран кампании с опросом раз в 3 секунды для `queued`/`running`;
- «Бизнесы» как таблица `NormalizedSourceRecord` с постраничной навигацией и явным предупреждением: «Предварительные записи. Дедупликация ещё не выполнена».

Route `/businesses` сохраняется как удобное навигационное имя, но в этом срезе он всегда показывает `NormalizedSourceRecord`, никогда не canonical `Business`.

Таблица первого среза:

```text
Название | Источник | Категория | Район | Телефон | Сайт | Статус | Получено
```

Frontend никогда не запрашивает весь dataset. Data fetching сосредоточен в `src/api/` и feature hooks на TanStack Query. Forms используют React Hook Form + Zod. Table — TanStack Table. Russian labels маппятся из технических enum в одном `labels.ts`, а не размазываются по components.

## 18. Полный v1 после первого среза

Следующие планы добавляют, не меняя raw/discovery contracts:

1. `deduplication`: candidate generation, deterministic match score, `AUTO_MERGE | POSSIBLE_DUPLICATE | DISTINCT`, reversible merge и canonical `Business`.
2. `BusinessGroup`: branches и `independent | local_chain | regional_chain | large_chain`.
3. `enrichment`: website/contact/social candidates и confidence.
4. `crawling`: httpx/lxml first, Playwright fallback, 10–20 ключевых страниц, gzip HTML snapshots.
5. `audits`: availability, HTTPS, metadata, mobile viewport, forms, booking, WhatsApp, languages, CMS; Lighthouse только для отобранных кандидатов.
6. `scoring`: `BusinessScore`, `ScoreComponent`, versioned deterministic formulas.
7. `opportunities`: `Opportunity`, `reason_code`, `reason_data`, category-aware rules.
8. quality-control, map, business card, saved filters и background exports.

Каждый следующий vertical slice начинается только после отдельного acceptance spec с его contracts, invariants, test strategy и acceptance criteria; этот документ не является acceptance approval для перечисленных возможностей.

## 19. Infrastructure и operations

Development Compose services:

```text
postgres
redis
garage
backend
celery-discovery
celery-normalization
frontend
nginx
```

Один `backend/Dockerfile` используется API и обоими workers; отличаются только commands и queue subscriptions. Browser image отсутствует до crawling/audit slice.

Каждый Celery worker имеет targeted readiness check: он становится healthy только когда зарегистрирован под ожидаемым node name и `active_queues()` подтверждает ровно назначенную ему queue (`discovery` либо `normalization`). E2E ожидает эти healthchecks с bounded timeout до запуска браузерного сценария.

Production request path:

```text
Internet → nginx ├─ /api/ → Gunicorn/Django
                 └─ /     → static React build
```

PostgreSQL, Redis и Garage не публикуются в Internet. Dev ports, если нужны, bind только к `127.0.0.1`.

Required environment groups:

```text
DJANGO_SECRET_KEY, DJANGO_SETTINGS_MODULE, DJANGO_ALLOWED_HOSTS
DATABASE_URL
CELERY_BROKER_URL
S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET_NAME
OVERPASS_URL, OSM_DATASET_VERSION, SOURCE_USER_AGENT
SENTRY_DSN, VITE_SENTRY_DSN (optional)
```

`.env.example` содержит только безопасные examples; реальные secrets не коммитятся.

## 20. Security, privacy и лицензии

- Django session cookie: `HttpOnly`, `Secure` в production, `SameSite=Lax`.
- Все unsafe API methods защищены CSRF.
- CORS разрешён только для configured development origin; same-origin в production.
- Object-storage bucket private, credentials доступны только backend/workers.
- Structured logs не содержат raw payload, phone/email values или secrets.
- Доступ к dashboard только authenticated user.
- Source provenance и license сохраняются на каждой записи.
- Overture release/licensing и OSM/Overpass terms проверяются перед live production campaign.
- Для OSM отображается требуемая attribution; deployment не полагается на public Overpass для bulk commercial workload.
- Политика retention и обработки публичных contact data должна быть утверждена до начала outreach; outreach не входит в v1.

## 21. Observability и ошибки

Structured log fields:

```text
timestamp, level, service, event, message, request_id, task_id, correlation_id,
campaign_id, source_run_id, source, source_record_id, error_code, duration_ms
```

User-facing ошибки русские, technical codes английские. Минимальные codes первого среза:

```text
SOURCE_TIMEOUT
SOURCE_RATE_LIMITED
SOURCE_UNAVAILABLE
INVALID_SOURCE_PAYLOAD
SOURCE_RECORD_CONFLICT
SOURCE_HAS_NO_ACTIVE_MAPPINGS
RAW_STORAGE_UNAVAILABLE
OUTSIDE_SEARCH_AREA
MISSING_NAME
INVALID_COORDINATES
UNKNOWN_CATEGORY
NORMALIZATION_ERROR
CAMPAIGN_NOT_DRAFT
CAMPAIGN_ALREADY_STARTED
```

Sentry подключается для Django, Celery и React при наличии `SENTRY_DSN`. Flower может запускаться dev profile, но не заменяет продуктовый progress endpoint.

## 22. Testing strategy

### Backend

- unit tests для pure normalization, state transitions, query builders и parsers;
- model/database integration tests с реальным PostgreSQL/PostGIS;
- S3-compatible integration tests на Garage для gzip round-trip и metadata;
- adapter contract tests на сохранённых fixtures;
- HTTP client tests через local mock transport/server, без live public APIs;
- Celery integration tests с настоящим Redis для routing/retry/idempotency;
- API tests для auth, permissions, validation, pagination и progress;
- pipeline test: fixture adapter → S3 storage → SourceRecord → normalization → progress.

### Frontend

- Vitest + Testing Library для observable UI behavior;
- MSW для API boundaries;
- tests для перенаправления при аутентификации, русских подписей, форм, состояний загрузки/пустого результата/ошибки, периодического опроса и постраничной навигации;
- Playwright acceptance для login → create campaign → start → progress → preliminary business table.

### TDD discipline

Для каждого поведения:

1. тест на публичный результат;
2. запуск и подтверждённый expected RED;
3. минимальная реализация;
4. targeted GREEN;
5. relevant suite GREEN;
6. refactor при зелёных tests;
7. небольшой commit.

Mocks используются только на внешней границе. Assertions проверяют state/output системы, а не факт существования mock.

## 23. Acceptance criteria первого среза

1. `docker compose up --build` поднимает PostgreSQL/PostGIS, Redis, Garage, Django, два Celery worker, React и nginx с readiness/health checks.
2. Миграции включают `postgis`, `pg_trgm`, `unaccent`.
3. Seed создаёт Türkiye → Antalya → Alanya, четыре taxonomy leaves и два active sources.
4. Неавторизованный пользователь не видит dashboard/API; авторизованный видит русский интерфейс.
5. Пользователь создаёт и запускает кампанию с Overture и/или OSM.
6. Внешний payload сохраняется как deterministic `.json.gz` в private S3-compatible bucket.
7. `SourceRecord` сохраняет raw fields, checksum, object metadata и provenance.
8. Повтор task с тем же input не создаёт второй record/object/result.
9. Normalization `tr-v1` корректно обрабатывает турецкие имена, адреса, TR phones, email, URL/social links, coordinates и unknown categories.
10. Progress переживает restart API/worker, потому что хранится в PostgreSQL.
11. Кампания получает `completed`, `completed_with_errors` или `failed` по формальным правилам.
12. Экран «Бизнесы» показывает paginated normalized records и предупреждение о том, что дедупликация не выполнена.
13. Обязательные backend, frontend и e2e tests проходят без live-запросов к Overture/OSM.
14. CI выполняет lint, typecheck, migrations check, unit/integration tests и production frontend build.
15. Worker readiness подтверждает точное множество очередей `{discovery}` и `{normalization}` до начала E2E.
16. Database/broker recovery не расходует business retry budget повторно; одинаковый delivery token имеет одну durable reservation, а exhaustion переводит работу в terminal state.

## 24. Источники технических решений

- [Django 5.2 release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/)
- [Node.js release schedule](https://nodejs.org/en/about/previous-releases)
- [Vite releases](https://vite.dev/releases)
- [Celery tasks, retry and reject semantics](https://docs.celeryq.dev/en/v5.5.3/userguide/tasks.html)
- [Overture data quickstart](https://docs.overturemaps.org/getting-data/)
- [Overture Python client](https://docs.overturemaps.org/getting-data/overturemaps-py/)
- [Overture Places guide](https://docs.overturemaps.org/guides/places/)
- [Overpass API documentation](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OpenStreetMap attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)

## 25. Решения, вынесенные в следующие specs

- точные пороги deduplication и calibration dataset;
- canonical field precedence после merge;
- reversible merge representation;
- branch/network classification thresholds;
- website candidate confidence rules;
- crawl limits и robots policy;
- audit score formulas;
- scoring/opportunity weights;
- production backup/restore RPO/RTO;
- recurring discovery и immutable revision history;
- contact-data retention и outreach compliance.
