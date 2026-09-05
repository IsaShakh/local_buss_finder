import * as Sentry from '@sentry/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { initFrontendObservability, sanitizeFrontendEvent } from './observability';

vi.mock('@sentry/react', () => ({ init: vi.fn() }));

const sentryInitSpy = vi.mocked(Sentry.init);

describe('frontend observability', () => {
  beforeEach(() => {
    sentryInitSpy.mockClear();
  });

  it('не инициализирует Sentry без DSN', () => {
    expect(initFrontendObservability(undefined)).toBe(false);
    expect(initFrontendObservability('')).toBe(false);
    expect(sentryInitSpy).not.toHaveBeenCalled();
  });

  it('удаляет user и request headers из события', () => {
    const safe = sanitizeFrontendEvent({
      user: { email: 'person@example.test' },
      request: { headers: { authorization: 'Bearer token' }, url: '/businesses' },
      message: 'UI failed',
    });

    expect(safe.user).toBeUndefined();
    expect(safe.request?.headers).toBeUndefined();
    expect(safe.request?.url).toBe('/businesses');
    expect(safe.message).toBe('UI failed');
  });

  it('инициализирует Sentry без PII и с sanitizer', () => {
    expect(initFrontendObservability('https://public@example.test/1')).toBe(true);

    expect(sentryInitSpy).toHaveBeenCalledOnce();
    const options = sentryInitSpy.mock.calls[0]?.[0];
    expect(options).toMatchObject({
      dsn: 'https://public@example.test/1',
      sendDefaultPii: false,
      beforeSend: sanitizeFrontendEvent,
    });
  });
});
