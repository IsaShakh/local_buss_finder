import * as Sentry from '@sentry/react';
import type { Event } from '@sentry/react';

export function sanitizeFrontendEvent<T extends Event>(event: T): T {
  const safe = { ...event } as T;
  delete safe.user;
  if (safe.request !== undefined) {
    safe.request = { ...safe.request };
    delete safe.request.headers;
    delete safe.request.cookies;
    delete safe.request.data;
  }
  return safe;
}

export function initFrontendObservability(dsn?: string): boolean {
  if (!dsn?.trim()) {
    return false;
  }
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    beforeSend: sanitizeFrontendEvent,
  });
  return true;
}
