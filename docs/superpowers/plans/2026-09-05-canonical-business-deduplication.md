# Canonical Business and Deterministic Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the preliminary normalized-record list with owner-scoped canonical businesses, conservative deterministic deduplication, and a durable manual duplicate-review workflow while preserving every source record and its provenance.

**Architecture:** Keep provider ingestion and normalization unchanged up to `NormalizedSourceRecord`, then resolve each normalized row into exactly one `BusinessSourceMembership` inside the same database transaction. A new pure `apps.deduplication` domain layer extracts identity, scores bounded owner-scoped candidates, chooses only conservative automatic matches, rebuilds canonical fields from memberships, and records ambiguous pairs for manual review. Existing source-record endpoints remain available; new canonical APIs drive the default business UI and dashboard.

**Tech Stack:** Python 3.13, Django 5.2, Django REST Framework, PostgreSQL/PostGIS (`pg_trgm`, GIST, GIN, advisory locks), Celery, pytest; React 19, TypeScript 5.9, TanStack Query, Zod, Vitest/Testing Library, Playwright; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-05-canonical-business-deduplication-design.md`

## Global Constraints

- Preserve `SourceRecord`, raw payload metadata, `NormalizedSourceRecord`, and the existing `/api/v1/source-records/` endpoints.
- Scope every business query, candidate comparison, resolution, and decision to the campaign owner; foreign-owner objects must remain indistinguishable from missing objects.
- Perform no provider, website, AI, or paid-API network calls in entity resolution.
- Use `resolution_version="deterministic-v1"` everywhere in this slice.
- Automatic attachment must use only the approved evidence gates; ambiguity creates a pending candidate and never merges two existing businesses transitively.
- Follow red-green-refactor for every behavior change and commit after each task passes its focused checks.
- Do not broaden this slice into crawling, audits, lead scoring, opportunities, export, scheduling, or merge undo UI.

---

### Task 1: Add canonical persistence models and database constraints

**Files:**

- Create: `backend/apps/businesses/models.py`
- Create: `backend/apps/businesses/migrations/0001_initial.py`
- Create: `backend/apps/businesses/tests/test_models.py`
- Modify: `backend/apps/businesses/apps.py`

**Interfaces:**

- Produce `Business`, `BusinessSourceMembership`, and `DuplicateCandidate` model classes exactly as specified in sections 5.1–5.3.
- `Business.active` is a queryset/manager helper that means `merged_into__isnull=True`; ordinary ownership filters remain explicit.
- `DuplicateCandidate.ordered_pair(left_id, right_id) -> tuple[UUID, UUID]` returns UUIDs in lexical order and is used by all write paths.

- [ ] Write failing model tests covering: all default states; one membership per normalized record; score bounds; unique ordered pair; no self-pair; no self-merge; and model validation rejecting cross-owner business merges, pairs, and decision actors.

- [ ] Run the focused tests and confirm they fail because the models do not exist:

  ```bash
  docker compose run --rm backend pytest apps/businesses/tests/test_models.py -q
  ```

- [ ] Implement `Business` using `TimestampedUUIDModel`, `settings.AUTH_USER_MODEL`, canonical text/geography/contact fields, first/last seen timestamps, `resolution_version`, and nullable `merged_into`. Add B-tree indexes on `(owner, merged_into)` and `(owner, category)`, GIST on `location`, trigram GIN on `match_name`, and JSON GIN indexes on `phones` and `domains`.

- [ ] Implement `BusinessSourceMembership` with a `OneToOneField` to `NormalizedSourceRecord`, FK to `Business`, `match_kind` choices (`seed`, `source_identity`, `automatic`, `manual`), validated integer score, JSON signals, version, and `attached_at`.

- [ ] Implement `DuplicateCandidate` with ordered business FKs, unique `(owner, left_business, right_business)`, statuses (`pending`, `confirmed`, `rejected`, `superseded`), decision/audit fields, validated score, and a database check that the two IDs differ. Put cross-row ownership rules in `clean()` and ensure every service calls `full_clean()` before save.

- [ ] Generate the migration, inspect it for all indexes and constraints, and ensure it has only these three models:

  ```bash
  docker compose run --rm backend python manage.py makemigrations businesses
  docker compose run --rm backend python manage.py migrate
  ```

- [ ] Re-run the focused tests plus migration drift check:

  ```bash
  docker compose run --rm backend pytest apps/businesses/tests/test_models.py -q
  docker compose run --rm backend python manage.py makemigrations --check --dry-run
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/businesses
  git commit -m "feat: add canonical business persistence"
  ```

---

### Task 2: Implement pure identity extraction and deterministic scoring

**Files:**

- Create: `backend/apps/deduplication/__init__.py`
- Create: `backend/apps/deduplication/apps.py`
- Create: `backend/apps/deduplication/domain.py`
- Create: `backend/apps/deduplication/identity.py`
- Create: `backend/apps/deduplication/scoring.py`
- Create: `backend/apps/deduplication/tests/__init__.py`
- Create: `backend/apps/deduplication/tests/test_identity.py`
- Create: `backend/apps/deduplication/tests/test_scoring.py`
- Modify: `backend/config/settings/base.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class MatchFacts:
    source_identity: bool
    phone_match: bool
    domain_match: bool
    exact_name: bool
    name_similarity: float
    exact_address: bool
    address_similarity: float
    distance_m: float | None
    category_relation: Literal["same", "neutral", "incompatible"]

@dataclass(frozen=True)
class MatchSignal:
    code: str
    weight: int
    value: str | float | None = None

@dataclass(frozen=True)
class MatchAssessment:
    score: int
    signals: tuple[MatchSignal, ...]
    automatic: bool

def extract_official_domains(websites: Iterable[str]) -> tuple[str, ...]: ...
def category_relation(left_category_id: UUID | None, right_category_id: UUID | None) -> str: ...
def assess_match(facts: MatchFacts) -> MatchAssessment: ...
```

- [ ] Write table-driven failing identity tests for lowercasing, `www.` removal, ports/paths, duplicate hosts, invalid URLs, social hosts, and known directory/booking hosts. The excluded-host set must be a named constant and contacts must remain untouched outside this extractor.

- [ ] Write table-driven failing scoring tests for exact source identity, every name/address/distance boundary, score clamping, stable signal order, category states, both automatic gates, and these safety cases: distant shared phone/domain is reviewable but not automatic; incompatible categories block automatic attachment unless source identity is exact.

- [ ] Run both focused test files and confirm import failures:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_identity.py apps/deduplication/tests/test_scoring.py -q
  ```

- [ ] Register `apps.deduplication.apps.DeduplicationConfig`, implement immutable dataclasses, official-domain extraction via `urllib.parse`, and category relation without database access.

- [ ] Implement scoring with exactly one name, address, and distance tier; ordered signal codes; clamp to `0..100`; candidate eligibility at `>=55`; and the two approved automatic gates. Keep threshold constants named in `scoring.py` so API labels and tests do not duplicate policy.

- [ ] Run tests and static checks:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_identity.py apps/deduplication/tests/test_scoring.py -q
  docker compose run --rm backend ruff check apps/deduplication
  docker compose run --rm backend ruff format --check apps/deduplication
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/deduplication backend/config/settings/base.py
  git commit -m "feat: add deterministic duplicate scoring"
  ```

---

### Task 3: Rebuild canonical fields deterministically from memberships

**Files:**

- Create: `backend/apps/deduplication/materialization.py`
- Create: `backend/apps/deduplication/tests/conftest.py`
- Create: `backend/apps/deduplication/tests/test_materialization.py`

**Interfaces:**

```python
def completeness_score(record: NormalizedSourceRecord) -> int: ...
def select_primary_record(records: Iterable[NormalizedSourceRecord]) -> NormalizedSourceRecord: ...
def seed_business(*, normalized_record: NormalizedSourceRecord, owner_id: UUID) -> Business: ...
def rebuild_business(*, business_id: UUID) -> Business: ...
```

- [ ] Add factories in `test_materialization.py`/`conftest.py` that create normalized records for two sources and campaigns without using live adapters.

- [ ] Write failing tests proving primary selection uses completeness, then fetched time, source code, and normalized UUID; contact unions are normalized, unique, and sorted; social URL lists are merged by provider; domains exclude social/directory hosts; first/last seen are min/max fetched times; geography comes from the primary; and repeated rebuilds are byte-for-byte stable.

- [ ] Run the focused tests and confirm failure:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_materialization.py -q
  ```

- [ ] Implement the stable completeness sort. Count the eight approved groups: name, category, address, location, phones, emails, websites, and social URLs. Materialize scalar fields from the first record after sorting and contact unions from all active memberships.

- [ ] Make `seed_business` create a minimal owner-scoped active business plus a `seed` membership, then delegate all canonical writes to `rebuild_business`. Make `rebuild_business` reject a merged business and select related data in a bounded number of queries.

- [ ] Run focused tests and query-count regression coverage:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_materialization.py -q
  docker compose run --rm backend ruff check apps/deduplication/materialization.py
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/deduplication
  git commit -m "feat: materialize canonical business fields"
  ```

---

### Task 4: Generate bounded candidates and resolve normalized records

**Files:**

- Create: `backend/apps/deduplication/candidates.py`
- Create: `backend/apps/deduplication/locks.py`
- Create: `backend/apps/deduplication/services.py`
- Create: `backend/apps/deduplication/tests/test_candidates.py`
- Create: `backend/apps/deduplication/tests/test_services.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class CandidateMatch:
    business_id: UUID
    facts: MatchFacts
    assessment: MatchAssessment

@dataclass(frozen=True)
class ResolutionOutcome:
    business_id: UUID
    membership_id: UUID
    action: Literal["seeded", "source_identity", "automatic", "already_resolved"]
    candidate_ids: tuple[UUID, ...]

@contextmanager
def owner_resolution_lock(owner_id: UUID) -> Iterator[None]: ...
def find_candidate_businesses(*, normalized_record: NormalizedSourceRecord) -> list[CandidateMatch]: ...
def resolve_normalized_record(normalized_record_id: UUID) -> ResolutionOutcome: ...
```

- [ ] Write failing candidate-query tests for same source/external identity across campaigns, exact phone, exact official domain, spatial/name qualification, 50-row spatial cap, inclusion of exact candidates outside the cap, active-only filtering, and absolute exclusion of other owners.

- [ ] Write failing resolver tests for: idempotent replay; seed when no automatic match exists; exact source identity; both automatic gates; deterministic winner ordering by score then UUID; review candidates for non-winning strong contenders; no transitive merge through a bridging record; and no candidate below score 55.

- [ ] Run the focused tests and confirm failure:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_candidates.py apps/deduplication/tests/test_services.py -q
  ```

- [ ] Implement the owner advisory lock as `SELECT pg_advisory_xact_lock(namespace, owner_key)`, with a fixed signed 32-bit project namespace and a deterministic signed 32-bit key derived from the owner UUID. Assert an active transaction before acquiring it.

- [ ] Implement an index-backed union of exact identity, JSON contact, and PostGIS/trigram querysets. De-duplicate business IDs in Python, retain every exact candidate, cap only the spatial branch at 50, calculate final facts consistently, and return matches ordered by descending score then UUID.

- [ ] Implement resolution inside `transaction.atomic()`: determine owner from `source_record.campaign.created_by_id`, acquire the owner lock, return an existing membership on replay, select one automatic winner, otherwise seed a business, create/update ordered pending candidates for eligible non-automatic pairs, rebuild the chosen business, and emit contact-free structured events with `transaction.on_commit()`.

- [ ] Ensure `DuplicateCandidate.update_or_create` never reopens `rejected`, `confirmed`, or `superseded` rows. An existing pending row may refresh score/signals/version.

- [ ] Run focused tests, query plans for representative exact/spatial lookups, and lint:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_candidates.py apps/deduplication/tests/test_services.py -q
  docker compose run --rm backend ruff check apps/deduplication
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/deduplication
  git commit -m "feat: resolve normalized records into businesses"
  ```

---

### Task 5: Make normalization and first membership atomic

**Files:**

- Modify: `backend/apps/normalization/services.py`
- Modify: `backend/apps/normalization/tests/test_service.py`
- Create: `backend/apps/deduplication/tests/test_concurrency.py`
- Modify: `backend/apps/discovery/tests/integration/test_pipeline.py`

**Interfaces:**

- `materialize_normalization(source_record_id: UUID) -> NormalizedSourceRecord | None` keeps its public signature.
- On a normalized outcome, `_materialize_result(...)` must be followed by `resolve_normalized_record(normalized.id)` before the existing outer transaction commits.

- [ ] Extend normalization tests to assert one active business and one membership after success, no duplicate membership on replay, and total rollback of normalized row, counters, business, membership, and candidates when the resolver raises.

- [ ] Add a PostgreSQL transaction test that resolves the same unresolved normalized record in two workers and asserts one membership and one intended business. Add a second two-owner test proving independent owners never share or compare businesses.

- [ ] Extend the fixture pipeline integration assertion to include canonical counts produced by the current four-record fixture: four memberships and three active businesses because the shared Overture/OSM record auto-attaches by exact name/address/location.

- [ ] Run the new tests and confirm failure before wiring the resolver:

  ```bash
  docker compose run --rm backend pytest apps/normalization/tests/test_service.py apps/deduplication/tests/test_concurrency.py -q
  ```

- [ ] Call the resolver immediately after `_materialize_result` and before returning. Do not catch resolution exceptions in the service; allow the existing Celery database retry path to observe the rolled-back normalization attempt.

- [ ] Run focused unit and isolated pipeline integration tests:

  ```bash
  docker compose run --rm backend pytest apps/normalization/tests/test_service.py apps/deduplication/tests/test_concurrency.py -q
  docker compose -p local-business-intelligence-e2e -f docker-compose.yml -f docker-compose.e2e.yml run --rm -e STORAGE_INTEGRATION_PROJECT=1 backend pytest -m integration apps/discovery/tests/integration/test_pipeline.py -q
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/normalization backend/apps/deduplication/tests/test_concurrency.py backend/apps/discovery/tests/integration/test_pipeline.py
  git commit -m "feat: resolve businesses during normalization"
  ```

---

### Task 6: Implement durable confirm and reject decisions

**Files:**

- Create: `backend/apps/deduplication/decisions.py`
- Create: `backend/apps/deduplication/exceptions.py`
- Create: `backend/apps/deduplication/tests/test_decisions.py`

**Interfaces:**

```python
class DuplicateCandidateNotPending(Exception):
    code = "DUPLICATE_CANDIDATE_NOT_PENDING"

def confirm_duplicate(*, candidate_id: UUID, actor: User) -> DuplicateCandidate: ...
def reject_duplicate(*, candidate_id: UUID, actor: User) -> DuplicateCandidate: ...
```

- [ ] Write failing tests for deterministic survivor selection by membership count, created time, then UUID; moving every losing membership; retaining the losing row with `merged_into`; rebuilding all contact unions; recording moved membership IDs and actor/time; superseding pending pairs involving the loser; rejection without business changes; stale/repeated decisions; and 404-style absence for foreign-owner IDs.

- [ ] Run the focused tests and confirm failure:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_decisions.py -q
  ```

- [ ] Implement both actions under `transaction.atomic()` plus the same owner advisory lock. Fetch the candidate through an actor-owned queryset, lock candidate and businesses with `select_for_update()`, call `full_clean()` before state saves, and raise `DuplicateCandidateNotPending` for any non-pending or stale merged state.

- [ ] In confirmation, sort moved membership UUID strings before audit storage, update memberships in one query, set the loser link without deletion, rebuild the survivor, and mark remaining pending pairs touching the loser `superseded`. Emit only IDs, score, resolution version, and decision in the post-commit event.

- [ ] Run focused tests and lint:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_decisions.py -q
  docker compose run --rm backend ruff check apps/deduplication/decisions.py apps/deduplication/exceptions.py
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/deduplication
  git commit -m "feat: add duplicate review decisions"
  ```

---

### Task 7: Backfill existing normalized records safely

**Files:**

- Create: `backend/apps/deduplication/management/__init__.py`
- Create: `backend/apps/deduplication/management/commands/__init__.py`
- Create: `backend/apps/deduplication/management/commands/deduplicate_businesses.py`
- Create: `backend/apps/deduplication/tests/test_backfill_command.py`

**Interfaces:**

```text
python manage.py deduplicate_businesses [--owner UUID] [--batch-size N] [--dry-run]
```

The final summary keys are `examined`, `created_businesses`, `automatic_attachments`, `pending_candidates`, `already_resolved`, and `failures`.

- [ ] Write failing command tests for stable owner/normalized-time/UUID ordering, owner filtering, positive batch-size validation, real batch commits, dry-run rollback, exact summary counts, resumability after a forced batch failure, idempotent second execution, and absence of any adapter/network call.

- [ ] Run the focused tests and confirm command discovery fails:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_backfill_command.py -q
  ```

- [ ] Implement unresolved-row iteration with `iterator(chunk_size=batch_size)` and stable ordering. Run each real batch in its own atomic block; count outcomes returned by `resolve_normalized_record`; continue to the next record after reporting an isolated failure only when doing so cannot partially commit the failed record.

- [ ] Implement dry-run as the same iteration and resolver calls inside a rollback-only outer transaction. Ensure `transaction.on_commit()` resolution events do not fire from dry-run.

- [ ] Run command tests and a local preview against the current database:

  ```bash
  docker compose run --rm backend pytest apps/deduplication/tests/test_backfill_command.py -q
  docker compose run --rm backend python manage.py deduplicate_businesses --dry-run
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/deduplication/management backend/apps/deduplication/tests/test_backfill_command.py
  git commit -m "feat: backfill canonical businesses"
  ```

---

### Task 8: Expose canonical businesses, review queue, and dashboard counts

**Files:**

- Modify: `backend/apps/businesses/api/pagination.py`
- Modify: `backend/apps/businesses/api/serializers.py`
- Modify: `backend/apps/businesses/api/views.py`
- Modify: `backend/apps/businesses/api/urls.py`
- Modify: `backend/apps/businesses/tests/conftest.py`
- Create: `backend/apps/businesses/tests/test_business_api.py`
- Create: `backend/apps/businesses/tests/test_duplicate_candidate_api.py`
- Modify: `backend/apps/businesses/tests/test_dashboard_api.py`

**Interfaces:**

```text
GET  /api/v1/businesses/
GET  /api/v1/businesses/{id}/
GET  /api/v1/duplicate-candidates/
POST /api/v1/duplicate-candidates/{id}/confirm/
POST /api/v1/duplicate-candidates/{id}/reject/
```

- `BusinessQuerySerializer` accepts only `page`, `page_size`, `campaign`, `source`, `category`, `search`, and `ordering`; ordering choices are `display_name`, `first_seen_at`, `-first_seen_at`, `last_seen_at`, `-last_seen_at`, `updated_at`, `-updated_at`.
- Business detail returns at most `100` memberships ordered by `-fetched_at, id`, plus `memberships_truncated`.
- Dashboard adds `businesses: {active, pending_duplicates}` while retaining existing `records` and `campaigns` objects.

- [ ] Write failing business API tests for authentication, owner isolation, active-only results, strict filters, contact search, ordering, pagination cap, `distinct()` across multi-membership filters, source/source-record counts, canonical detail, 100-row provenance bound, and existing source-record endpoint compatibility.

- [ ] Write failing candidate API tests for pending-only owner-scoped listing, both business summaries, ordered translated signals, confirm/reject success, no client survivor input, foreign-owner 404, and stale decision response `{code: "DUPLICATE_CANDIDATE_NOT_PENDING"}` with HTTP 409.

- [ ] Extend dashboard tests to distinguish raw/normalized source counts, active canonical businesses, merged exclusions, and pending candidates.

- [ ] Run all business API tests and confirm the new routes fail:

  ```bash
  docker compose run --rm backend pytest apps/businesses/tests -q
  ```

- [ ] Add a generic 50/default, 100/max pagination class while retaining `SourceRecordPagination` as a compatibility alias. Implement serializers that expose only safe provenance metadata and annotate list querysets with distinct source, source-record, and pending-candidate counts.

- [ ] Implement strict owner-scoped list/detail/candidate querysets, API decision calls, and exception mapping. Search canonical normalized name plus JSON phone/email/domain values without interpolated SQL; use ORM expressions and `distinct()`.

- [ ] Update dashboard aggregation and run focused tests plus schema/migration checks:

  ```bash
  docker compose run --rm backend pytest apps/businesses/tests -q
  docker compose run --rm backend python manage.py check
  docker compose run --rm backend python manage.py makemigrations --check --dry-run
  ```

- [ ] Commit:

  ```bash
  git add backend/apps/businesses
  git commit -m "feat: expose canonical business APIs"
  ```

---

### Task 9: Switch the business list and dashboard to canonical data

**Files:**

- Modify: `frontend/src/features/businesses/types.ts`
- Modify: `frontend/src/features/businesses/api.ts`
- Modify: `frontend/src/features/businesses/queries.ts`
- Modify: `frontend/src/features/businesses/BusinessesPage.tsx`
- Modify: `frontend/src/features/businesses/BusinessesPage.test.tsx`
- Modify: `frontend/src/features/dashboard/types.ts`
- Modify: `frontend/src/features/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/features/dashboard/DashboardPage.test.tsx`
- Modify: `frontend/src/test/handlers.ts`

**Interfaces:**

```typescript
export type BusinessListItem = {
  id: string;
  is_canonical: true;
  display_name: string;
  category: Reference | null;
  district: Reference | null;
  address_text: string;
  location: GeoJsonPoint | null;
  phones: string[];
  emails: string[];
  websites: string[];
  social_urls: Record<string, string[]>;
  source_count: number;
  source_record_count: number;
  pending_duplicate_count: number;
  first_seen_at: string;
  last_seen_at: string;
};
```

- [ ] Replace MSW fixtures with canonical `/api/v1/businesses/` responses and write failing UI/schema tests for canonical marker, source/source-record counts, pending indicator, canonical first/last seen, safe external links, URL-backed filters/order/page, and distinct loading/empty/error states. Assert the preliminary warning is absent.

- [ ] Extend dashboard schema/UI tests for `businesses.active` and `businesses.pending_duplicates`, keeping source-record metrics separately labelled.

- [ ] Run focused frontend tests and confirm failures:

  ```bash
  docker compose run --rm frontend npm run test:run -- src/features/businesses/BusinessesPage.test.tsx src/features/dashboard/DashboardPage.test.tsx
  ```

- [ ] Replace source-record types/query keys/API URL with canonical equivalents. Keep campaign/source/category/search/ordering/page in URL state and retain the existing 300 ms search debounce.

- [ ] Render canonical columns: name, category, district, primary phone/site, distinct sources, source records, pending duplicate state, and last seen. Remove the source-record warning and make labels explicitly distinguish “Исходные записи” from “Уникальные бизнесы”.

- [ ] Run focused tests, typecheck, and lint:

  ```bash
  docker compose run --rm frontend npm run test:run -- src/features/businesses/BusinessesPage.test.tsx src/features/dashboard/DashboardPage.test.tsx
  docker compose run --rm frontend npm run typecheck
  docker compose run --rm frontend npm run lint
  ```

- [ ] Commit:

  ```bash
  git add frontend/src/features/businesses frontend/src/features/dashboard frontend/src/test/handlers.ts
  git commit -m "feat: show canonical businesses in the app"
  ```

---

### Task 10: Add duplicate review UI and prove the complete flow

**Files:**

- Create: `frontend/src/features/businesses/DuplicateCandidatesPage.tsx`
- Create: `frontend/src/features/businesses/DuplicateCandidatesPage.test.tsx`
- Modify: `frontend/src/features/businesses/types.ts`
- Modify: `frontend/src/features/businesses/api.ts`
- Modify: `frontend/src/features/businesses/queries.ts`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles/global.css`
- Modify: `frontend/src/test/handlers.ts`
- Modify: `backend/apps/discovery/tests/fake_adapter.py`
- Modify: `backend/apps/discovery/tests/integration/test_pipeline.py`
- Modify: `frontend/e2e/discovery-flow.spec.ts`
- Modify: `README.md`

**Interfaces:**

- Route: `/businesses/duplicates`, navigation label “Дубликаты”.
- `getDuplicateCandidates(): Promise<DuplicateCandidate[]>`
- `confirmDuplicate(id: string): Promise<DuplicateCandidate>`
- `rejectDuplicate(id: string): Promise<DuplicateCandidate>`
- Mutation success invalidates `['businesses']`, `['duplicate-candidates']`, and `['dashboard-summary']`.

- [ ] Write failing component tests for two side-by-side summaries, score and translated reasons, empty/error states, confirmation prompts, disabled buttons during mutation, confirm/reject calls, cache invalidation, and safe display of HTTP 409/other API errors.

- [ ] Run the new component tests and confirm route/component failures:

  ```bash
  docker compose run --rm frontend npm run test:run -- src/features/businesses/DuplicateCandidatesPage.test.tsx
  ```

- [ ] Implement Zod-validated candidate types/API/query hooks and the comparison page. The client sends an empty POST body and never chooses the survivor. Add accessible confirmation dialogs and labels “Объединить” / “Это разные компании”.

- [ ] Add an E2E-only ambiguous pair to the two fixture adapters: include a `phone` value in both fixture payloads, teach `parse_fixture_payload` to pass that value through `raw_phones`, use equal phone and exact name, and place the records more than 500 m apart. The pair therefore scores 75 (phone + exact name + category) but cannot auto-attach. Update integration expectations to six normalized records, six memberships, five active businesses, and one pending candidate; retain the existing exact Overture/OSM duplicate.

- [ ] Update Playwright flow to assert five canonical businesses from six source records, open the pending comparison, reject the ambiguous pair, verify it disappears and remains five businesses, and verify the exact duplicate never appears twice.

- [ ] Document local rollout and operation in `README.md`:

  ```bash
  docker compose run --rm backend python manage.py migrate
  docker compose run --rm backend python manage.py deduplicate_businesses --dry-run
  docker compose run --rm backend python manage.py deduplicate_businesses
  ```

  State clearly that discovery starts only from the campaign button and that this slice adds no scheduler, AI, paid API, crawler, audit, scoring, or export.

- [ ] Run focused frontend/backend tests, then the full verification suites:

  ```bash
  docker compose run --rm frontend npm run test:run -- src/features/businesses
  docker compose run --rm backend pytest -m "not integration" -q
  make backend-check
  make frontend-check
  make verify
  make e2e
  ```

- [ ] Run migration/backfill acceptance checks on the local dataset: dry-run first, compare normalized count to membership count after real execution, verify every owner has zero unresolved normalized records, and inspect active/pending counts in the UI.

- [ ] Review `git diff origin/main...HEAD` for secrets, raw contacts in logs, unrelated scope, placeholders, and accidental changes to the source-record provenance API.

- [ ] Commit final UI/docs/E2E work:

  ```bash
  git add frontend backend/apps/discovery README.md
  git commit -m "feat: add duplicate review workflow"
  ```

---

## Completion Checklist

- [ ] Every normalized record has exactly one membership; no rejected/failed source record does.
- [ ] Automatic matches satisfy one approved gate and never bridge-merge existing businesses.
- [ ] Owner isolation, replay idempotency, concurrency, dry-run rollback, and manual decision history are covered by tests.
- [ ] `/source-records/` remains available while `/businesses/` powers the default UI.
- [ ] Full backend, frontend, integration, E2E, lint, type, build, Django, and migration checks pass from fresh containers.
- [ ] `rg -n "TODO|FIXME|placeholder|NotImplemented" backend/apps/deduplication backend/apps/businesses frontend/src/features/businesses README.md` finds no unfinished implementation markers introduced by this slice.
- [ ] The final diff contains no AI, paid API, crawler, audit, scoring, opportunity, export, or scheduled-discovery implementation.
