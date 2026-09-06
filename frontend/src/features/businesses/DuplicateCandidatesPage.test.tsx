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

  it('загружает только видимую страницу и хранит переходы вперёд и назад в URL', async () => {
    // Catches eager traversal, missing count/link controls, and client-only page state.
    const requests: string[] = [];
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      ...duplicateCandidate, id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index).padStart(12, '0')}`,
    }));
    server.use(http.get('/api/v1/duplicate-candidates/', ({ request }) => {
      requests.push(new URL(request.url).search);
      const page = new URL(request.url).searchParams.get('page');
      return HttpResponse.json(page === '2'
        ? { count: 51, next: null, previous: '?page=1', results: [{ ...duplicateCandidate, score: 55 }] }
        : { count: 51, next: '?page=2', previous: null, results: firstPage });
    }));
    const { user } = renderAuthenticatedApp('/businesses/duplicates');
    await screen.findAllByRole('article', { name: 'Сравнение компаний' });
    expect(requests).toEqual(['?page=1&page_size=50']);
    expect(screen.getAllByRole('article', { name: 'Сравнение компаний' })).toHaveLength(50);
    expect(screen.getByText('Найдено пар: 51')).toBeInTheDocument();
    expect(screen.getByText('Страница 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Предыдущая страница' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Следующая страница' }));
    expect(await screen.findByText('Совпадение: 55 / 100')).toBeInTheDocument();
    expect(window.location.search).toBe('?page=2');
    expect(requests).toEqual(['?page=1&page_size=50', '?page=2&page_size=50']);
    expect(screen.getAllByRole('article', { name: 'Сравнение компаний' })).toHaveLength(1);
    expect(screen.getByText('Страница 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Следующая страница' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Предыдущая страница' }));
    await waitFor(() => expect(screen.getAllByRole('article', { name: 'Сравнение компаний' })).toHaveLength(50));
    expect(window.location.search).toBe('?page=1');
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
  ])('%s обновляет только видимую страницу очереди и связанные кеши', async (action, label, title, status) => {
    let resolveResponse!: () => void;
    const pendingResponse = new Promise<void>((resolve) => { resolveResponse = resolve; });
    let submitted = false;
    let body: unknown;
    let requestedId: unknown;
    let csrf: string | null = null;
    const requestedPages: string[] = [];
    const remainingCandidate = { ...duplicateCandidate, id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', score: 55 };
    server.use(
      authenticatedSessionHandler,
      http.get('/api/v1/duplicate-candidates/', ({ request }) => {
        requestedPages.push(new URL(request.url).search);
        return HttpResponse.json({
          count: submitted ? 51 : 52, next: null, previous: '?page=1',
          results: submitted ? [remainingCandidate] : [duplicateCandidate, remainingCandidate],
        });
      }),
      http.post(`/api/v1/duplicate-candidates/:id/${action}/`, async ({ request, params }) => {
        body = await request.json(); requestedId = params.id; csrf = request.headers.get('X-CSRFToken');
        await pendingResponse;
        submitted = true;
        return HttpResponse.json({ id: duplicateCandidate.id, status, survivor_business_id: action === 'confirm' ? duplicateCandidate.left_business.id : null, merged_business_id: action === 'confirm' ? duplicateCandidate.right_business.id : null });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    client.setQueryData(['businesses', { page: 1 }], businessesResponse);
    client.setQueryData(['duplicate-candidates', 1], duplicateCandidatesResponse);
    client.setQueryData(['dashboard-summary'], { records: { raw: 6, normalized: 6, rejected: 0, failed: 0 }, campaigns: { total: 1, running: 0, with_errors: 0 }, businesses: { active: 5, pending_duplicates: 1 }, recent_campaigns: [] });
    window.history.pushState({}, '', '/businesses/duplicates?page=2');
    document.cookie = `csrftoken=${testCsrfToken}; Path=/`;
    render(<QueryClientProvider client={client}><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></QueryClientProvider>);
    const user = userEvent.setup();
    const firstCard = (await screen.findAllByRole('article', { name: 'Сравнение компаний' }))[0];
    const trigger = within(firstCard).getByRole('button', { name: label });
    expect(requestedPages).toEqual(['?page=2&page_size=50']);
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: title });
    await user.click(within(dialog).getByRole('button', { name: label }));
    await waitFor(() => expect(body).toEqual({}));
    expect(requestedId).toBe(duplicateCandidate.id);
    expect(csrf).toBe(testCsrfToken);
    for (const button of within(dialog).getAllByRole('button')) expect(button).toBeDisabled();
    expect(within(firstCard).getByRole('button', { name: action === 'confirm' ? 'Это разные компании' : 'Объединить' })).toBeDisabled();
    resolveResponse();
    await waitFor(() => expect(screen.getAllByRole('article', { name: 'Сравнение компаний' })).toHaveLength(1));
    expect(client.getQueryState(['businesses', { page: 1 }])?.isInvalidated).toBe(true);
    expect(client.getQueryState(['dashboard-summary'])?.isInvalidated).toBe(true);
    expect(client.getQueryState(['duplicate-candidates', 1])?.isInvalidated).toBe(false);
    expect(requestedPages).toEqual(['?page=2&page_size=50', '?page=2&page_size=50']);
    expect(window.location.search).toBe('?page=2');
    expect(screen.getByText('Найдено пар: 51')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Предыдущая страница' })).toBeEnabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('после удаления последней пары на странице запрашивает только предыдущую страницу', async () => {
    // DRF returns 404 once page 2 disappears; do not refetch a known-empty page.
    let submitted = false;
    const requestedPages: string[] = [];
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      ...duplicateCandidate, id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index).padStart(12, '0')}`,
    }));
    server.use(
      http.get('/api/v1/duplicate-candidates/', ({ request }) => {
        const page = new URL(request.url).searchParams.get('page');
        requestedPages.push(page ?? 'missing');
        if (submitted && page === '2') return HttpResponse.json({ error: { code: 'NOT_FOUND', detail: 'Invalid page.', fields: {} } }, { status: 404 });
        return HttpResponse.json(page === '2'
          ? { count: 51, next: null, previous: '?page=1', results: [duplicateCandidate] }
          : { count: 50, next: null, previous: null, results: firstPage });
      }),
      http.post('/api/v1/duplicate-candidates/:id/reject/', () => {
        submitted = true;
        return HttpResponse.json({ id: duplicateCandidate.id, status: 'rejected', survivor_business_id: null, merged_business_id: null });
      }),
    );
    const { user } = renderAuthenticatedApp('/businesses/duplicates?page=2');
    await user.click(await screen.findByRole('button', { name: 'Это разные компании' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Это разные компании' }));
    await waitFor(() => expect(window.location.search).toBe('?page=1'));
    expect(await screen.findByText('Найдено пар: 50')).toBeInTheDocument();
    expect(requestedPages).toEqual(['2', '1']);
    expect(screen.getAllByRole('article', { name: 'Сравнение компаний' })).toHaveLength(50);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
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
