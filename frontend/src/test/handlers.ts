import { http, HttpResponse } from 'msw';

import type { ApiErrorBody } from '../features/auth/types';

export const ALANYA_ID = '11111111-1111-4111-8111-111111111111';
export const OVERTURE_ID = '22222222-2222-4222-8222-222222222222';
export const OSM_ID = '33333333-3333-4333-8333-333333333333';
export const CAMPAIGN_ID = '55555555-5555-4555-8555-555555555555';
export const BUSINESS_ID = '66666666-6666-4666-8666-666666666666';
export const DENTIST_ID = '77777777-7777-4777-8777-777777777777';

export const campaignCreateRequests: unknown[] = [];

const alanyaArea = {
  id: ALANYA_ID,
  name: 'Аланья — пилот',
  country: { id: 'country-tr', code: 'TR', name: 'Türkiye', name_ru: 'Турция' },
  province: { id: 'province-07', code: '07', name: 'Antalya', name_ru: 'Анталья' },
  district: { id: 'district-alanya', slug: 'alanya', name: 'Alanya', name_ru: 'Аланья' },
  neighborhood: null,
  geometry: { type: 'MultiPolygon', coordinates: [] },
  bbox: [31.7, 36.3, 32.65, 36.75],
};

const sources = [
  {
    id: OVERTURE_ID,
    code: 'overture',
    name: 'Overture Maps',
    source_type: 'file',
    is_paid: false,
    is_active: true,
    attribution: 'Overture Maps Foundation',
    license_code: 'CDLA-Permissive-2.0',
    requests_per_second: 1,
    concurrency: 1,
    timeout_seconds: 60,
    max_retries: 3,
  },
  {
    id: OSM_ID,
    code: 'osm',
    name: 'OpenStreetMap',
    source_type: 'api',
    is_paid: false,
    is_active: true,
    attribution: '© OpenStreetMap contributors',
    license_code: 'ODbL-1.0',
    requests_per_second: 1,
    concurrency: 1,
    timeout_seconds: 60,
    max_retries: 3,
  },
];

const categories = [
  {
    id: '88888888-8888-4888-8888-888888888888',
    name: 'Медицина',
    slug: 'health',
    children: [{ id: DENTIST_ID, name: 'Стоматология', slug: 'dentist', children: [] }],
  },
];

export const business = {
  id: BUSINESS_ID,
  is_canonical: true as const,
  display_name: 'Smile Dental Alanya',
  category: { id: DENTIST_ID, name: 'Стоматология', slug: 'dentist' },
  district: {
    id: '99999999-9999-4999-8999-999999999999',
    name: 'Аланья',
    slug: 'alanya',
  },
  phones: ['+902425551212', '+902425551313'],
  emails: ['hello@smile.example'],
  websites: ['https://smile.example', 'https://booking.smile.example'],
  social_urls: { instagram: ['https://instagram.com/smile'] },
  address_text: 'Atatürk Caddesi 7, Аланья',
  location: { type: 'Point' as const, coordinates: [31.99, 36.54] },
  source_count: 2,
  source_record_count: 3,
  pending_duplicate_count: 1,
  first_seen_at: '2026-09-01T12:30:00Z',
  last_seen_at: '2026-09-04T12:30:00Z',
};

export const businessesResponse = {
  count: 120,
  next: '/api/v1/businesses/?page=2&page_size=50',
  previous: null,
  results: [business],
};

export const businessListRequests: URL[] = [];

export const businessesEmptyHandler = http.get('/api/v1/businesses/', ({ request }) => {
  businessListRequests.push(new URL(request.url));
  return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
});

export const businessesServerErrorHandler = http.get('/api/v1/businesses/', ({ request }) => {
  businessListRequests.push(new URL(request.url));
  return HttpResponse.json(
    {
      error: {
        code: 'DATABASE_ERROR',
        detail: 'SQL stack Traceback: connection unavailable',
        fields: {},
      },
    },
    { status: 500 },
  );
});

export function campaignResponse(
  name = 'Аланья — первичный сбор',
  status: 'draft' | 'queued' | 'running' | 'completed' | 'completed_with_errors' | 'failed' =
    'draft',
) {
  return {
    id: CAMPAIGN_ID,
    name,
    status,
    search_area: { id: ALANYA_ID, name: alanyaArea.name },
    sources: sources.map(({ id, code, name: sourceName }) => ({ id, code, name: sourceName })),
    categories: [],
    total_jobs: 0,
    completed_jobs: 0,
    failed_jobs: 0,
    raw_records_found: 0,
    normalized_records: 0,
    rejected_records: 0,
    started_at: null,
    finished_at: null,
    created_at: '2026-09-04T10:00:00Z',
    updated_at: '2026-09-04T10:00:00Z',
  };
}

export const runningProgress = {
  id: CAMPAIGN_ID,
  status: 'running' as const,
  totals: {
    jobs: 2,
    completed_jobs: 0,
    failed_jobs: 0,
    discovered: 8,
    stored: 8,
    normalized: 3,
    rejected: 1,
    failed_records: 0,
  },
  sources: [
    {
      code: 'osm',
      name: 'OpenStreetMap',
      status: 'normalizing' as const,
      dataset_version: '2026-09-04',
      discovered: 8,
      stored: 8,
      normalized: 3,
      rejected: 1,
      failed_records: 0,
    },
  ],
};

export const completedProgress = {
  ...runningProgress,
  status: 'completed' as const,
  totals: {
    ...runningProgress.totals,
    completed_jobs: 2,
    normalized: 7,
  },
  sources: runningProgress.sources.map((source) => ({
    ...source,
    status: 'completed' as const,
    normalized: 7,
  })),
};

export const progressResponses = {
  requestCount: 0,
  responses: [] as unknown[],
  enqueue(...responses: unknown[]) {
    this.responses.push(...responses);
  },
  reset() {
    this.requestCount = 0;
    this.responses.length = 0;
  },
  take() {
    this.requestCount += 1;
    return this.responses.shift() ?? completedProgress;
  },
};

export const campaignCreateErrorHandler = http.post('/api/v1/campaigns/', () =>
  HttpResponse.json(
    {
      error: {
        code: 'MISSING_CATEGORY_MAPPING',
        detail: 'Для источника нет активных сопоставлений категорий.',
        fields: {},
      },
    },
    { status: 400 },
  ),
);

export const testAuthUser = {
  id: 1,
  username: 'owner',
  display_name: 'Владелец',
};

export const testCsrfToken = 'test-csrf-token';

const anonymousResponse: ApiErrorBody = {
  error: {
    code: 'NOT_AUTHENTICATED',
    detail: 'Требуется вход.',
    fields: {},
  },
};

function hasValidUnsafeRequestOptions(request: Request) {
  return (
    request.credentials === 'include' &&
    request.headers.get('X-CSRFToken') === testCsrfToken
  );
}

function invalidCredentialsResponse() {
  return HttpResponse.json(
    {
      error: {
        code: 'INVALID_CREDENTIALS',
        detail: 'Неверное имя пользователя или пароль.',
        fields: {},
      },
    } satisfies ApiErrorBody,
    { status: 400 },
  );
}

export const authenticatedSessionHandler = http.get('/api/v1/auth/session/', ({ request }) => {
  if (request.credentials !== 'include') {
    return HttpResponse.json({ detail: 'credentials отсутствуют' }, { status: 400 });
  }

  return HttpResponse.json(testAuthUser);
});

export const invalidCredentialsHandler = http.post('/api/v1/auth/login/', ({ request }) => {
  if (!hasValidUnsafeRequestOptions(request)) {
    return HttpResponse.json({ detail: 'CSRF заголовок отсутствует' }, { status: 403 });
  }

  return invalidCredentialsResponse();
});

export const handlers = [
  http.get('/api/v1/auth/session/', ({ request }) => {
    if (request.credentials !== 'include') {
      return HttpResponse.json({ detail: 'credentials отсутствуют' }, { status: 400 });
    }

    return HttpResponse.json(anonymousResponse, { status: 403 });
  }),
  http.get('/api/v1/auth/csrf/', ({ request }) => {
    if (request.credentials !== 'include') {
      return HttpResponse.json({ detail: 'credentials отсутствуют' }, { status: 400 });
    }

    return HttpResponse.json({ detail: 'CSRF cookie установлена.' });
  }),
  http.post('/api/v1/auth/login/', async ({ request }) => {
    if (!hasValidUnsafeRequestOptions(request)) {
      return HttpResponse.json({ detail: 'CSRF заголовок отсутствует' }, { status: 403 });
    }

    const body = (await request.json()) as { username?: string; password?: string };
    if (body.username !== 'owner' || body.password !== 'correct-password') {
      return invalidCredentialsResponse();
    }

    return HttpResponse.json(testAuthUser);
  }),
  http.post('/api/v1/auth/logout/', ({ request }) => {
    if (!hasValidUnsafeRequestOptions(request)) {
      return HttpResponse.json({ detail: 'CSRF заголовок отсутствует' }, { status: 403 });
    }

    return new HttpResponse(null, { status: 204 });
  }),
  http.get('/api/v1/geography/search-areas/', () =>
    HttpResponse.json({ count: 1, next: null, previous: null, results: [alanyaArea] }),
  ),
  http.get('/api/v1/taxonomy/categories/', () =>
    HttpResponse.json({ count: 1, next: null, previous: null, results: categories }),
  ),
  http.get('/api/v1/sources/', () =>
    HttpResponse.json({ count: sources.length, next: null, previous: null, results: sources }),
  ),
  http.get('/api/v1/campaigns/', () =>
    HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
  ),
  http.post('/api/v1/campaigns/', async ({ request }) => {
    if (!hasValidUnsafeRequestOptions(request)) {
      return HttpResponse.json({ detail: 'CSRF заголовок отсутствует' }, { status: 403 });
    }
    const body = await request.json();
    campaignCreateRequests.push(body);
    const name =
      typeof body === 'object' && body !== null && 'name' in body && typeof body.name === 'string'
        ? body.name
        : undefined;
    return HttpResponse.json(campaignResponse(name), { status: 201 });
  }),
  http.get('/api/v1/campaigns/:id/', () => HttpResponse.json(campaignResponse())),
  http.post('/api/v1/campaigns/:id/start/', ({ request }) => {
    if (!hasValidUnsafeRequestOptions(request)) {
      return HttpResponse.json({ detail: 'CSRF заголовок отсутствует' }, { status: 403 });
    }
    return HttpResponse.json(campaignResponse('Аланья — первичный сбор', 'queued'), {
      status: 202,
    });
  }),
  http.get('/api/v1/campaigns/:id/progress/', () => HttpResponse.json(progressResponses.take())),
  http.get('/api/v1/dashboard/summary/', () =>
    HttpResponse.json({
      records: { raw: 120, normalized: 96, rejected: 20, failed: 4 },
      campaigns: { total: 3, running: 1, with_errors: 1 },
      businesses: { active: 12, pending_duplicates: 1 },
      recent_campaigns: [
        {
          id: CAMPAIGN_ID,
          name: 'Аланья — первичный сбор',
          status: 'completed_with_errors',
          normalized: 96,
          updated_at: '2026-09-04T13:00:00Z',
        },
      ],
    }),
  ),
  http.get('/api/v1/businesses/', ({ request }) => {
    const url = new URL(request.url);
    businessListRequests.push(url);
    const page = Number(url.searchParams.get('page') ?? '1');
    return HttpResponse.json({
      ...businessesResponse,
      next: page * 50 < businessesResponse.count ? `/api/v1/businesses/?page=${page + 1}` : null,
      previous: page > 1 ? `/api/v1/businesses/?page=${page - 1}` : null,
    });
  }),
];
