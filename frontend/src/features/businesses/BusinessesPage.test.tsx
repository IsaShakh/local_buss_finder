import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  businessListRequests,
  businessesEmptyHandler,
  businessesResponse,
  businessesServerErrorHandler,
} from '../../test/handlers';
import { renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';
import { sourceRecordPageSchema } from './types';

describe('предварительные записи бизнесов', () => {
  beforeEach(() => {
    businessListRequests.length = 0;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('показывает предупреждение до дедупликации и серверную пагинацию', async () => {
    const { user } = renderAuthenticatedApp('/businesses');

    expect(await screen.findByRole('heading', { name: 'Бизнесы' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(
      'Предварительные записи. Дедупликация ещё не выполнена',
    );
    expect(await screen.findByText('Найдено записей: 120')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Следующая страница' }));
    await waitFor(() =>
      expect(businessListRequests.at(-1)?.searchParams.get('page')).toBe('2'),
    );
  });

  it('не показывает canonical scores или возможности', async () => {
    renderAuthenticatedApp('/businesses');
    await screen.findByRole('table');

    expect(screen.queryByText('Приоритет')).not.toBeInTheDocument();
    expect(screen.queryByText('Цифровой потенциал')).not.toBeInTheDocument();
  });

  it('debounce отправляет один search request через 300 ms и сбрасывает page', async () => {
    renderAuthenticatedApp('/businesses?page=3');
    await screen.findByRole('table');
    const baseline = businessListRequests.length;
    vi.useFakeTimers();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск' }), {
      target: { value: 'smile' },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(299);
    });
    expect(businessListRequests).toHaveLength(baseline);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    await act(async () => {
      await vi.waitFor(() => expect(businessListRequests).toHaveLength(baseline + 1));
    });
    const url = businessListRequests.at(-1);
    expect(url?.searchParams.get('search')).toBe('smile');
    expect(url?.searchParams.get('page')).toBe('1');
  });

  it('source/category filters и heading используют только server-side query params', async () => {
    const { user } = renderAuthenticatedApp('/businesses?page=3');

    await screen.findByRole('option', { name: 'OpenStreetMap' });
    await user.selectOptions(screen.getByLabelText('Источник'), 'osm');
    await waitFor(() =>
      expect(businessListRequests.at(-1)?.searchParams.get('source')).toBe('osm'),
    );
    expect(businessListRequests.at(-1)?.searchParams.get('page')).toBe('1');
    await user.selectOptions(screen.getByLabelText('Категория'), 'dentist');
    await user.click(screen.getByRole('columnheader', { name: 'Название' }));
    await waitFor(() => {
      const url = businessListRequests.at(-1);
      expect(url?.searchParams.get('category')).toBe('dentist');
      expect(url?.searchParams.get('ordering')).toBe('display_name');
    });
  });

  it('показывает отдельные empty и safe server-error states', async () => {
    server.use(businessesEmptyHandler);
    const empty = renderAuthenticatedApp('/businesses');
    expect(await screen.findByText('Записей не найдено')).toBeInTheDocument();
    empty.unmount();

    server.use(businessesServerErrorHandler);
    renderAuthenticatedApp('/businesses');
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить записи.');
    expect(screen.queryByText(/Traceback|stack|SQL/)).not.toBeInTheDocument();
  });

  it('отклоняет каноническую строку на границе API первого среза', () => {
    const response = {
      ...businessesResponse,
      results: [{ ...businessesResponse.results[0], is_canonical: true }],
    };
    expect(sourceRecordPageSchema.safeParse(response).success).toBe(false);
  });

  it('показывает первый контакт, количество остальных и безопасную ссылку', async () => {
    renderAuthenticatedApp('/businesses');
    await screen.findByRole('table');

    expect(screen.getByText('+902425551212')).toBeInTheDocument();
    expect(screen.getAllByText('+1')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'https://smile.example' })).toHaveAttribute(
      'target',
      '_blank',
    );
    expect(screen.getByRole('link', { name: 'https://smile.example' })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
  });

  it('фиксирует page_size=50 и не отправляет normalization_status', async () => {
    renderAuthenticatedApp('/businesses');
    await screen.findByRole('table');

    const url = businessListRequests.at(-1);
    expect(url?.searchParams.get('page_size')).toBe('50');
    expect(url?.searchParams.has('normalization_status')).toBe(false);
  });
});
