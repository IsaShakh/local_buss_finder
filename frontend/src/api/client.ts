import { ApiClientError, isApiErrorBody } from './errors';

const csrfEndpoint = '/api/v1/auth/csrf/';
const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

let csrfInitialized = false;
let csrfInitialization: Promise<void> | null = null;

function readCookie(name: string) {
  const prefix = `${name}=`;
  const cookie = document.cookie
    .split(';')
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));

  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  const text = await response.text();
  return text.length > 0 ? text : undefined;
}

function toApiError(response: Response, body: unknown) {
  if (isApiErrorBody(body)) {
    return new ApiClientError(body, response.status);
  }

  return new ApiClientError(
    {
      error: {
        code: 'API_ERROR',
        detail: 'Не удалось выполнить запрос.',
        fields: {},
      },
    },
    response.status,
  );
}

async function initializeCsrf() {
  const response = await fetch(csrfEndpoint, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw toApiError(response, body);
  }
  if (readCookie('csrftoken') === null) {
    throw new ApiClientError(
      {
        error: {
          code: 'CSRF_COOKIE_MISSING',
          detail: 'Не удалось подготовить защищённый запрос.',
          fields: {},
        },
      },
      403,
    );
  }

  csrfInitialized = true;
}

async function ensureCsrf() {
  if (csrfInitialized && readCookie('csrftoken') !== null) {
    return;
  }

  csrfInitialization ??= initializeCsrf().finally(() => {
    csrfInitialization = null;
  });
  await csrfInitialization;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');

  if (unsafeMethods.has(method)) {
    await ensureCsrf();
    const csrfToken = readCookie('csrftoken');
    if (csrfToken !== null) {
      headers.set('X-CSRFToken', csrfToken);
    }
  }

  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, {
    ...init,
    method,
    headers,
    credentials: 'include',
  });
  const body = await readResponseBody(response);

  if (!response.ok) {
    throw toApiError(response, body);
  }

  return body as T;
}
