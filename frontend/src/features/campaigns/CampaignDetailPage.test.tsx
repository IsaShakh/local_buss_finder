import { act, fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CAMPAIGN_ID,
  campaignResponse,
  completedProgress,
  progressResponses,
  runningProgress,
} from '../../test/handlers';
import { renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';

describe('progress кампании', () => {
  beforeEach(() => {
    progressResponses.reset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('после запуска опрашивает progress каждые 3 секунды и прекращает на terminal status', async () => {
    progressResponses.enqueue(runningProgress, completedProgress);
    renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);
    const startButton = await screen.findByRole('button', { name: 'Запустить кампанию' });
    vi.useFakeTimers();

    await act(async () => {
      fireEvent.click(startButton);
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.waitFor(() => expect(screen.getByText('Выполняется')).toBeInTheDocument());
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await act(async () => {
      await vi.waitFor(() => expect(screen.getByText('Завершена')).toBeInTheDocument());
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(progressResponses.requestCount).toBe(2);
  });

  it.each(['completed', 'completed_with_errors', 'failed'] as const)(
    'не продолжает polling после terminal status %s',
    async (status) => {
      progressResponses.enqueue({ ...completedProgress, status });
      renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);
      const startButton = await screen.findByRole('button', { name: 'Запустить кампанию' });
      vi.useFakeTimers();

      await act(async () => {
        fireEvent.click(startButton);
        await vi.advanceTimersByTimeAsync(0);
      });
      const label =
        status === 'completed'
          ? 'Завершена'
          : status === 'completed_with_errors'
            ? 'Завершена с ошибками'
            : 'Ошибка';
      await act(async () => {
        await vi.waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(progressResponses.requestCount).toBe(1);
    },
  );

  it('показывает источник, счётчики и доступный progress bar', async () => {
    progressResponses.enqueue(runningProgress);
    renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Запустить кампанию' }));

    expect(await screen.findByText('OpenStreetMap')).toBeInTheDocument();
    expect(screen.getByText('osm')).toBeInTheDocument();
    expect(screen.getByText(/Версия данных: 2026-09-04/)).toBeInTheDocument();
    expect(screen.getByText(/Сохранено: 8/)).toBeInTheDocument();
    expect(screen.getByText(/Нормализовано: 3/)).toBeInTheDocument();
    expect(screen.getByText(/Отклонено: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Ошибок записей: 0/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '8');
  });

  it('показывает indeterminate-состояние, пока discovery не нашёл записи', async () => {
    progressResponses.enqueue({
      ...runningProgress,
      totals: { ...runningProgress.totals, discovered: 0, stored: 0, normalized: 0, rejected: 0 },
      sources: [],
    });
    renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Запустить кампанию' }));

    expect(await screen.findByText('Сбор данных…')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('показывает ошибку загрузки detail', async () => {
    server.use(
      http.get('/api/v1/campaigns/:id/', () =>
        HttpResponse.json(
          { error: { code: 'NOT_FOUND', detail: 'Кампания не найдена.', fields: {} } },
          { status: 404 },
        ),
      ),
    );
    renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);

    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить кампанию.');
  });

  it('показывает сохранённое время запуска', async () => {
    server.use(
      http.get('/api/v1/campaigns/:id/', () =>
        HttpResponse.json({
          ...campaignResponse('Завершённая кампания', 'completed'),
          started_at: '2026-09-04T10:15:00Z',
        }),
      ),
    );
    progressResponses.enqueue(completedProgress);
    renderAuthenticatedApp(`/campaigns/${CAMPAIGN_ID}`);

    expect(await screen.findByText(/Начата:/)).toBeInTheDocument();
  });
});

describe('список кампаний', () => {
  it('показывает состояние загрузки', async () => {
    server.use(
      http.get('/api/v1/campaigns/', async () => {
        await delay('infinite');
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    renderAuthenticatedApp('/campaigns');

    expect(await screen.findByText('Загрузка кампаний…')).toBeInTheDocument();
  });

  it('показывает пустой результат', async () => {
    renderAuthenticatedApp('/campaigns');

    expect(await screen.findByText('Кампаний пока нет.')).toBeInTheDocument();
  });

  it('показывает ошибку списка', async () => {
    server.use(
      http.get('/api/v1/campaigns/', () =>
        HttpResponse.json(
          { error: { code: 'API_ERROR', detail: 'Ошибка списка.', fields: {} } },
          { status: 500 },
        ),
      ),
    );
    renderAuthenticatedApp('/campaigns');

    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить кампании.');
  });
});
