import { http, HttpResponse } from 'msw';

import type { ApiErrorBody } from '../features/auth/types';

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
];
