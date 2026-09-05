# Canonical Business and Deterministic Deduplication — Design Spec

**Date:** 2026-09-05  
**Status:** approved for implementation  
**Depends on:** `2026-09-04-local-business-intelligence-v1-design.md`  
**Scale target:** 100,000–300,000 normalized source records per deployment

## 1. Goal

Turn normalized provider records into owner-scoped canonical businesses without
discarding provenance. Exact and high-confidence matches are attached
automatically. Ambiguous pairs remain separate and enter an explainable manual
review queue.

The default “Бизнесы” screen becomes a list of unique `Business` objects rather
than a list of preliminary `NormalizedSourceRecord` rows.

## 2. Scope

This slice includes:

- canonical `Business` records;
- durable membership from every normalized source record to one business;
- deterministic candidate generation and scoring;
- conservative automatic attachment;
- an owner-scoped duplicate review queue;
- confirm/reject review actions with durable decision history;
- canonical business list/detail APIs and UI;
- dashboard counts for source records and unique businesses;
- an idempotent backfill command with preview mode;
- automatic resolution as part of future source-record normalization;
- unit, integration, API, frontend, and E2E coverage.

This slice does not include:

- website crawling or contact enrichment;
- website audits, scoring, or commercial opportunities;
- exports;
- AI or embeddings;
- paid APIs;
- recurring discovery or scheduled campaign starts;
- a user-facing undo action for confirmed merges.

Confirmed merges preserve enough history for a later undo feature, but undo is
not exposed in this slice.

## 3. Invariants

1. `SourceRecord`, its raw object, and `NormalizedSourceRecord` remain intact.
2. A normalized record belongs to exactly one canonical business after
   resolution.
3. Businesses and comparisons are scoped to one owner. Cross-owner matching is
   forbidden.
4. Ambiguity creates a review candidate, never an automatic destructive merge.
5. A rejected pair does not reappear unless a future explicit reopen feature is
   added.
6. All canonical fields are reproducible from active memberships.
7. Resolution is deterministic for the same ordered input and algorithm
   version.
8. New normalization and its first canonical membership commit atomically.
9. Reprocessing and task redelivery are idempotent.
10. No entity-resolution path performs provider or website network I/O.

## 4. Ownership and lifecycle

`Business.owner` is the user who owns the campaigns containing its source
records. Deduplication runs across all campaigns belonging to that user, not
only within one campaign. It never shares canonical businesses between users.

An active business has `merged_into = NULL`. Confirming a review candidate
moves memberships to a deterministic survivor and marks the other business as
merged. The merged row is retained for audit history and is excluded from
normal list/search results.

The survivor is selected by:

1. greater active membership count;
2. earlier `created_at`;
3. lexicographically smaller UUID.

## 5. Data model

### 5.1. Business

`Business` lives in `apps.businesses` and uses the project UUID/timestamp base.

Fields:

```text
owner                    FK auth user, PROTECT
primary_normalized_record FK NormalizedSourceRecord, SET_NULL, nullable
display_name             text
normalized_name          text
match_name               text
category                 FK BusinessCategory, PROTECT, nullable
address_text             text, blank
country                  FK Country, PROTECT, nullable
province                 FK Province, PROTECT, nullable
district                 FK District, PROTECT, nullable
neighborhood             FK Neighborhood, PROTECT, nullable
location                 PointField(4326), nullable
phones                   JSON list
emails                   JSON list
websites                 JSON list
domains                  JSON list
social_urls              JSON object of provider -> list
first_seen_at             datetime
last_seen_at              datetime
resolution_version       string, initially deterministic-v1
merged_into              self FK, PROTECT, nullable
```

Indexes:

- B-tree on `(owner, merged_into)` and `(owner, category)`;
- GIST on `location`;
- trigram GIN on `match_name`;
- JSON GIN indexes on `phones` and `domains`.

Application validation prevents self-merges and cross-owner `merged_into`
references.

### 5.2. BusinessSourceMembership

```text
business                 FK Business, CASCADE
normalized_record        OneToOne NormalizedSourceRecord, PROTECT
match_kind               seed | source_identity | automatic | manual
match_score              integer 0..100
match_signals            JSON list of stable signal objects
resolution_version       string
attached_at              datetime
```

The one-to-one constraint makes resolution idempotent and guarantees that a
normalized record cannot silently belong to two businesses.

### 5.3. DuplicateCandidate

```text
owner                    FK auth user, PROTECT
left_business            FK Business, PROTECT
right_business           FK Business, PROTECT
score                    integer 0..100
signals                  JSON list of stable signal objects
resolution_version       string
status                   pending | confirmed | rejected | superseded
decided_by               FK auth user, PROTECT, nullable
decided_at               datetime, nullable
survivor_business        FK Business, PROTECT, nullable
merged_business          FK Business, PROTECT, nullable
moved_membership_ids     JSON list of UUID strings
```

The service always orders the pair by UUID. `(owner, left_business,
right_business)` is unique, so a rejected pair remains durably suppressed.
Validation requires both businesses and the decision actor to have the same
owner.

## 6. Canonical field materialization

The primary normalized record is chosen by this stable sort:

1. descending completeness count across name, category, address, location,
   phones, emails, websites, and social URLs;
2. descending provider `fetched_at`;
3. source code;
4. normalized-record UUID.

The primary record supplies name, category, address, geography, and location.
Phones, emails, websites, domains, and social URLs are the deterministic union
of all active memberships, normalized, de-duplicated, and sorted. `first_seen_at`
and `last_seen_at` are the minimum and maximum provider `fetched_at` values.

Domains are normalized URL hostnames with lowercase and a removed leading
`www.`. Paths are not part of domain identity. Social-network hosts and known
directory/booking hosts are not treated as official business domains for
matching, though their URLs remain visible in canonical contact data.

Every membership attachment or confirmed merge calls one canonical rebuild
service. Canonical fields are never edited by ad-hoc update code.

## 7. Candidate generation

Candidate generation is bounded and index-backed; it never compares every
business to every other business.

For a new normalized record, consider active businesses owned by the same user
that meet at least one condition:

1. an existing membership has the same source and external ID;
2. at least one normalized phone is equal;
3. at least one official domain is equal;
4. the business is within 500 metres and trigram similarity of `match_name` is
   at least `0.55`.

Spatial candidates are limited to 50, ordered by name similarity, distance,
and UUID. Exact source identity, phone, and domain candidates are not dropped
by that spatial cap.

Category compatibility in `deterministic-v1` is:

- equal category: compatible;
- either category missing: neutral;
- different category: incompatible.

Hierarchy-aware sibling compatibility is deferred until the taxonomy contains
enough production categories to validate it.

## 8. Scoring

The scorer returns an integer score and an ordered list of positive and negative
signals. Exact same-provider identity is a special score of 100.

Other weights:

```text
exact normalized phone                         +35
exact official domain                          +35
exact match_name                               +30
name similarity >= 0.90                        +25
name similarity >= 0.78                        +18
name similarity >= 0.65                        +10
exact non-empty normalized address             +20
address similarity >= 0.80                     +12
distance <= 25 m                               +25
distance <= 75 m                               +20
distance <= 250 m                              +12
distance <= 500 m                               +5
same category                                  +10
incompatible non-empty categories              -25
```

Only one name weight, one address weight, and one distance weight apply. The
final score is clamped to 0..100.

### 8.1. Automatic attachment

Automatic attachment is allowed only for:

- exact source identity; or
- score at least 80 with an exact phone/domain, distance at most 250 metres,
  and name similarity at least 0.65; or
- score at least 80 with exact `match_name`, exact non-empty address, and
  distance at most 75 metres.

Different non-empty categories prevent automatic attachment except for exact
source identity.

### 8.2. Review candidates

A non-automatic score of at least 55 creates or updates a pending
`DuplicateCandidate`. In particular, a shared phone/domain across distant
locations stays separate and is reviewable.

When several active businesses meet automatic rules, the record attaches only
to the highest-scoring deterministic winner. Pairs between that winner and the
other strong contenders become review candidates. One bridging record never
automatically merges two existing businesses.

If no automatic match exists, a new business is seeded from the record before
pending candidates are created.

## 9. Resolution service and concurrency

`resolve_normalized_record(normalized_record_id)`:

1. enters a database transaction;
2. acquires an owner-scoped PostgreSQL transaction advisory lock;
3. returns the existing membership if already resolved;
4. generates and scores bounded candidates;
5. attaches to the automatic winner or creates a new business;
6. creates/updates review candidates;
7. rebuilds canonical fields;
8. emits structured resolution events after commit.

All resolution and manual decision code uses the same owner-scoped advisory
lock. The lock key is derived deterministically from the owner UUID with a
project-specific namespace. This serializes entity changes for one owner while
allowing different owners to resolve concurrently.

Future normalizations call the resolver inside the existing normalization
transaction after materializing `NormalizedSourceRecord`. A failure rolls back
normalization counters, normalized data, business data, and membership
together. Existing Celery database retry behavior therefore applies without a
new worker or queue.

## 10. Manual decisions

Confirming a pending candidate:

1. locks the owner and both active businesses;
2. verifies the candidate is still pending and neither side is already merged;
3. selects the deterministic survivor;
4. records the membership IDs currently owned by the losing business;
5. moves those memberships to the survivor;
6. marks the loser `merged_into=survivor`;
7. rebuilds the survivor;
8. stores actor, timestamp, survivor, loser, and moved IDs on the candidate;
9. marks incompatible pending pairs involving the loser as `superseded`.

Rejecting a pending candidate stores actor, timestamp, and `rejected`. No
business or membership changes.

A repeated or stale decision returns `409 Conflict`. A foreign-owner object is
indistinguishable from a missing object and returns 404.

No source or canonical row is physically deleted by either action.

## 11. Backfill

The management command is:

```text
python manage.py deduplicate_businesses [--owner UUID] [--batch-size N] [--dry-run]
```

It processes unresolved normalized records in stable order by owner,
`normalized_at`, and UUID. Real mode commits resumable batches and is
idempotent. It reports:

- examined records;
- created businesses;
- automatic attachments;
- pending candidates;
- already-resolved records;
- failures.

`--dry-run` executes the same services inside a rollback-only transaction and
is intended to preview the current local dataset before the first real
backfill. It performs no provider I/O and changes no durable state.

The initial local rollout runs dry-run, applies the real backfill, then compares
source-record and membership counts before enabling the canonical UI for use.

## 12. API

Existing owner-scoped source-record endpoints remain available for provenance.

New endpoints:

```text
GET  /api/v1/businesses/
GET  /api/v1/businesses/{id}/
GET  /api/v1/duplicate-candidates/
POST /api/v1/duplicate-candidates/{id}/confirm/
POST /api/v1/duplicate-candidates/{id}/reject/
```

### 12.1. Business list

List fields:

```text
id, display_name, category, district, address_text, location,
phones, emails, websites, social_urls,
source_count, source_record_count, pending_duplicate_count,
first_seen_at, last_seen_at, is_canonical=true
```

Filters remain server-side:

- `campaign` through memberships;
- `source` through memberships;
- `category` from the canonical category;
- `search` across normalized name, phone, email, and domain;
- page/page size;
- ordering by name, first seen, last seen, or updated time.

Results are distinct active businesses owned by the authenticated user.
Pagination defaults to 50 and caps at 100.

### 12.2. Business detail

Detail includes all list fields plus canonical geography and a pageless bounded
membership summary containing source, external ID, campaign, fetched time,
dataset version, match kind, score, and link to the existing source-record
detail endpoint. Raw payload bodies remain private.

### 12.3. Duplicate candidates

The pending list returns both business summaries, score, translated signal
labels, and creation/update times. Decision endpoints accept no client-selected
survivor; survivor selection remains deterministic.

## 13. Frontend

The “Бизнесы” route switches from `/source-records/` to `/businesses/` and
removes the preliminary-record warning. It displays canonical contacts and:

- number of source records;
- number of distinct sources;
- pending duplicate indicator;
- canonical first/last seen timestamps.

A “Возможные дубликаты” view displays two business cards side by side, the
score and reasons, and buttons “Объединить” and “Это разные компании”. Actions
require confirmation, disable while pending, invalidate business/candidate
queries on success, and show safe API errors.

The dashboard shows source-record totals separately from unique active
businesses and pending duplicate count. Campaign, source, category, search,
ordering, and pagination remain URL-backed.

## 14. Error handling and observability

- Database failures roll back the entire resolution transaction and use the
  existing normalization task retry path.
- Constraint races are resolved by the owner lock and one-to-one membership
  constraint; no duplicate business is returned as success.
- Backfill failure leaves earlier committed batches intact and can be resumed.
- Decision conflicts use stable code `DUPLICATE_CANDIDATE_NOT_PENDING` with HTTP
  409.
- Invalid pair ownership/category/state is rejected before mutation.
- Structured events include owner ID, normalized record ID, business ID,
  candidate ID, resolution version, score, decision, and signal codes. They do
  not log raw contact values.

## 15. Testing

### 15.1. Unit

- signal extraction and stable ordering;
- every score boundary and clamp;
- exact provider identity;
- official-domain normalization and excluded directory/social hosts;
- category compatibility;
- primary-record selection and canonical unions;
- shared phone at a distant branch cannot auto-attach;
- exact name/address within 75 metres can auto-attach.

### 15.2. Integration

- two campaigns for one owner resolve the same source identity once;
- different owners never compare or share businesses;
- parallel resolution produces one membership and one intended business;
- bridging records do not auto-merge existing businesses;
- confirmation preserves all memberships and contacts;
- rejection remains suppressed;
- canonical rebuild is deterministic;
- normalization and first resolution roll back together;
- dry-run leaves no durable rows;
- real backfill is resumable and idempotent.

### 15.3. API

- authentication and owner isolation;
- pagination, strict filters, ordering, and search;
- distinct business results across multi-membership joins;
- bounded provenance detail;
- confirm/reject success and 409 stale decisions;
- dashboard raw/unique/pending counts.

### 15.4. Frontend and E2E

- canonical list replaces the preliminary-record UI;
- source/contact counts and safe links render correctly;
- filters remain URL-backed and server-side;
- empty/error states are separate;
- candidate comparison explains its score;
- confirm/reject refresh affected screens;
- an E2E fixture with exact duplicates yields one business;
- an ambiguous pair remains separate until the user decides.

## 16. Acceptance criteria

The slice is complete when:

1. every successfully normalized new record atomically receives one membership;
2. backfill resolves all existing normalized records exactly once;
3. automatic decisions obey the conservative evidence gates above;
4. ambiguous records stay separate and appear in the review queue;
5. user decisions are durable, owner-scoped, and non-destructive;
6. canonical list/detail and dashboard replace preliminary semantics without
   removing provenance endpoints;
7. required backend, frontend, and E2E suites pass without live provider calls;
8. lint, type checks, migration checks, and production builds pass;
9. README documents backfill preview/application and the absence of scheduled
   discovery;
10. no AI, paid API, crawling, audit, scoring, opportunity, or export behavior
    appears in the implementation.
