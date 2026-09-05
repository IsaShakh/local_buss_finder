import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { CAMPAIGN_ID } from '../../test/handlers';
import { renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';

describe('обзор', () => {
  it('показывает отдельные показатели канонических бизнесов и исходных записей', async () => {
    renderAuthenticatedApp('/');

    expect(await screen.findByRole('heading', { name: 'Обзор' })).toBeInTheDocument();
    expect(screen.getByText('Сырых записей')).toBeInTheDocument();
    expect(screen.getByText('Нормализовано')).toBeInTheDocument();
    expect(screen.getByText('Уникальные бизнесы')).toBeInTheDocument();
    expect(screen.getByText('Ожидают проверки')).toBeInTheDocument();
    expect(screen.getByText('Уникальные бизнесы').parentElement).toHaveTextContent('12');
    expect(screen.getByText('Ожидают проверки').parentElement).toHaveTextContent('1');
    expect(screen.getByRole('link', { name: 'Аланья — первичный сбор' })).toHaveAttribute(
      'href',
      `/campaigns/${CAMPAIGN_ID}`,
    );
  });

  it('показывает zero state и ссылку на первую кампанию', async () => {
    server.use(
      http.get('/api/v1/dashboard/summary/', () =>
        HttpResponse.json({
          records: { raw: 0, normalized: 0, rejected: 0, failed: 0 },
          campaigns: { total: 0, running: 0, with_errors: 0 },
          businesses: { active: 0, pending_duplicates: 0 },
          recent_campaigns: [],
        }),
      ),
    );
    renderAuthenticatedApp('/');

    expect(await screen.findByText('Кампаний пока нет')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Создать первую кампанию' })).toHaveAttribute(
      'href',
      '/campaigns/new',
    );
  });

  it('показывает безопасную ошибку summary API', async () => {
    server.use(
      http.get('/api/v1/dashboard/summary/', () =>
        HttpResponse.json(
          { error: { code: 'API_ERROR', detail: 'SQL stack Traceback', fields: {} } },
          { status: 500 },
        ),
      ),
    );
    renderAuthenticatedApp('/');

    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить обзор.');
    expect(screen.queryByText(/Traceback|stack|SQL/)).not.toBeInTheDocument();
  });
});
