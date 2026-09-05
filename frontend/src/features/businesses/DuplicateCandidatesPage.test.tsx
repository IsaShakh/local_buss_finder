import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { BrowserRouter } from 'react-router-dom';
import { beforeAll, describe, expect, it } from 'vitest';

import { App } from '../../app/App';
import { authenticatedSessionHandler, businessesResponse, duplicateCandidate, duplicateCandidatesResponse, testCsrfToken } from '../../test/handlers';
import { renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';
import { AuthProvider } from '../auth/AuthProvider';

beforeAll(() => {
  // JSDOM has no native modal implementation; Playwright covers the browser dialog.
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});

describe('проверка дубликатов', () => {
  it('открывает сравнение из навигации с двумя полными сводками и причинами', async () => {
    const { user } = renderAuthenticatedApp('/businesses');
    await user.click(await screen.findByRole('link', { name: 'Дубликаты' }));
    const left = await screen.findByRole('region', { name: 'Компания 1' });
    const right = screen.getByRole('region', { name: 'Компания 2' });
    expect(within(left).getByRole('heading', { name: 'Smile Dental Alanya' })).toBeInTheDocument();
    expect(within(right).getByRole('heading', { name: 'Smile Dental East' })).toBeInTheDocument();
    expect(within(left).getByText('Atatürk Caddesi 7, Аланья')).toBeInTheDocument();
    expect(within(right).getByText('East Street 20')).toBeInTheDocument();
    expect(within(left).getByText('+902425551212, +902425551313')).toBeInTheDocument();
    expect(within(left).getByText('hello@smile.example')).toBeInTheDocument();
    expect(within(left).getByText('Стоматология')).toBeInTheDocument();
    expect(within(left).getByText('Аланья')).toBeInTheDocument();
    expect(within(left).getByText('31.99, 36.54')).toBeInTheDocument();
    expect(within(left).getByText('Источников: 2 · Исходных записей: 3')).toBeInTheDocument();
    expect(screen.getByText('Совпадение: 75 / 100')).toBeInTheDocument();
    expect(screen.getByText('Совпадает телефон')).toBeInTheDocument();
    expect(screen.getByText('Совпадает название')).toBeInTheDocument();
    expect(screen.queryByText('exact_phone')).not.toBeInTheDocument();
  });

  it('загружает кандидатов после первой страницы и проверяет формат ответа', async () => {
    server.use(http.get('/api/v1/duplicate-candidates/', ({ request }) => {
      const page = new URL(request.url).searchParams.get('page');
      return HttpResponse.json(page === '2'
        ? { count: 2, next: null, previous: '?page=1', results: [{ ...duplicateCandidate, id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }] }
        : { ...duplicateCandidatesResponse, count: 2, next: 'http://localhost/api/v1/duplicate-candidates/?page=2' });
    }));
    renderAuthenticatedApp('/businesses/duplicates');
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Объединить' })).toHaveLength(2));
  });

  it('показывает пустую очередь', async () => {
    server.use(http.get('/api/v1/duplicate-candidates/', () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })));
    renderAuthenticatedApp('/businesses/duplicates');
    expect(await screen.findByText('Нет дубликатов для проверки')).toBeInTheDocument();
  });

  it.each([500, 'malformed'])('безопасно показывает ошибку загрузки %s', async (failure) => {
    server.use(http.get('/api/v1/duplicate-candidates/', () => HttpResponse.json(
      failure === 500 ? { detail: 'SQL Traceback private contact' } : { ...duplicateCandidatesResponse, results: [{ ...duplicateCandidate, score: '75' }] },
      { status: failure === 500 ? 500 : 200 },
    )));
    renderAuthenticatedApp('/businesses/duplicates');
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить дубликаты.');
    expect(screen.queryByText(/SQL|Traceback|private contact/)).not.toBeInTheDocument();
  });

  it('отмена подтверждения не отправляет решение и возвращает фокус', async () => {
    let requests = 0;
    server.use(http.post('/api/v1/duplicate-candidates/:id/confirm/', () => { requests++; return HttpResponse.json({}); }));
    const { user } = renderAuthenticatedApp('/businesses/duplicates');
    const trigger = await screen.findByRole('button', { name: 'Объединить' });
    await user.click(trigger);
    expect(screen.getByRole('dialog', { name: 'Объединить компании?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(requests).toBe(0);
    expect(trigger).toHaveFocus();
  });

  it.each([
    ['confirm', 'Объединить', 'Объединить компании?', 'confirmed'],
    ['reject', 'Это разные компании', 'Отметить как разные компании?', 'rejected'],
  ])('%s отправляет пустой POST, блокирует повтор и обновляет все связанные кеши', async (action, label, title, status) => {
    let resolveResponse!: () => void;
    const pendingResponse = new Promise<void>((resolve) => { resolveResponse = resolve; });
    let submitted = false;
    let body: unknown;
    let requestedId: unknown;
    let csrf: string | null = null;
    server.use(
      authenticatedSessionHandler,
      http.get('/api/v1/duplicate-candidates/', () => HttpResponse.json(submitted ? { count: 0, next: null, previous: null, results: [] } : duplicateCandidatesResponse)),
      http.post(`/api/v1/duplicate-candidates/:id/${action}/`, async ({ request, params }) => {
        body = await request.json(); requestedId = params.id; csrf = request.headers.get('X-CSRFToken');
        await pendingResponse;
        submitted = true;
        return HttpResponse.json({ id: duplicateCandidate.id, status, survivor_business_id: action === 'confirm' ? duplicateCandidate.left_business.id : null, merged_business_id: action === 'confirm' ? duplicateCandidate.right_business.id : null });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    client.setQueryData(['businesses', { page: 1 }], businessesResponse);
    client.setQueryData(['dashboard-summary'], { records: { raw: 6, normalized: 6, rejected: 0, failed: 0 }, campaigns: { total: 1, running: 0, with_errors: 0 }, businesses: { active: 5, pending_duplicates: 1 }, recent_campaigns: [] });
    window.history.pushState({}, '', '/businesses/duplicates');
    document.cookie = `csrftoken=${testCsrfToken}; Path=/`;
    render(<QueryClientProvider client={client}><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></QueryClientProvider>);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: label }));
    const dialog = screen.getByRole('dialog', { name: title });
    await user.click(within(dialog).getByRole('button', { name: label }));
    await waitFor(() => expect(body).toEqual({}));
    expect(requestedId).toBe(duplicateCandidate.id);
    expect(csrf).toBe(testCsrfToken);
    for (const button of within(dialog).getAllByRole('button')) expect(button).toBeDisabled();
    expect(screen.getByRole('button', { name: action === 'confirm' ? 'Это разные компании' : 'Объединить' })).toBeDisabled();
    resolveResponse();
    expect(await screen.findByText('Нет дубликатов для проверки')).toBeInTheDocument();
    expect(client.getQueryState(['businesses', { page: 1 }])?.isInvalidated).toBe(true);
    expect(client.getQueryState(['dashboard-summary'])?.isInvalidated).toBe(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it.each([409, 500])('показывает безопасную ошибку решения %s и позволяет закрыть диалог', async (status) => {
    server.use(http.post('/api/v1/duplicate-candidates/:id/confirm/', () => HttpResponse.json({ error: { code: 'INTERNAL', detail: 'SQL Traceback private contact', fields: {} } }, { status })));
    const { user } = renderAuthenticatedApp('/businesses/duplicates');
    await user.click(await screen.findByRole('button', { name: 'Объединить' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Объединить' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(status === 409 ? 'Решение по этой паре уже принято. Обновите список.' : 'Не удалось сохранить решение. Попробуйте ещё раз.');
    expect(screen.queryByText(/SQL|Traceback|private contact/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
