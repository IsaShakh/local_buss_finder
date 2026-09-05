import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { DataTable } from '../../components/DataTable';
import type { DataTableColumn } from '../../components/DataTable';
import { Pagination } from '../../components/Pagination';
import { SourceBadge } from '../../components/SourceBadge';
import type { BusinessCategory } from '../taxonomy/types';
import { useBusinessFilters, useSourceRecords } from './queries';
import type { SourceRecordListItem, SourceRecordQuery } from './types';

function flattenCategories(categories: BusinessCategory[]): BusinessCategory[] {
  return categories.flatMap((category) => [category, ...flattenCategories(category.children)]);
}

function positivePage(value: string | null) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function firstWithRemainder(values: string[]) {
  if (values.length === 0) return <span>—</span>;
  return (
    <span className="compact-values">
      <span>{values[0]}</span>
      {values.length > 1 && <small>+{values.length - 1}</small>}
    </span>
  );
}

function websiteCell(websites: string[]) {
  if (websites.length === 0) return <span>—</span>;
  return (
    <span className="compact-values">
      <a href={websites[0]} target="_blank" rel="noopener noreferrer">
        {websites[0]}
      </a>
      {websites.length > 1 && <small>+{websites.length - 1}</small>}
    </span>
  );
}

export function BusinessesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = searchParams.get('search') ?? '';
  const [searchInput, setSearchInput] = useState(urlSearch);
  const query = useMemo<SourceRecordQuery>(
    () => ({
      page: positivePage(searchParams.get('page')),
      search: urlSearch || undefined,
      campaign: searchParams.get('campaign') || undefined,
      source: searchParams.get('source') || undefined,
      category: searchParams.get('category') || undefined,
      ordering: (searchParams.get('ordering') as SourceRecordQuery['ordering']) || undefined,
    }),
    [searchParams, urlSearch],
  );
  const records = useSourceRecords(query);
  const filters = useBusinessFilters();

  useEffect(() => {
    if (searchInput === urlSearch) return;
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(searchParams);
      const value = searchInput.trim();
      if (value) next.set('search', value);
      else next.delete('search');
      next.set('page', '1');
      setSearchParams(next, { replace: true });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput, searchParams, setSearchParams, urlSearch]);

  function setFilter(name: 'source' | 'category', value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    next.set('page', '1');
    setSearchParams(next, { replace: true });
  }

  function setPage(page: number) {
    const next = new URLSearchParams(searchParams);
    next.set('page', String(page));
    setSearchParams(next);
  }

  function setOrdering(ordering: NonNullable<SourceRecordQuery['ordering']>) {
    const next = new URLSearchParams(searchParams);
    next.set('ordering', ordering);
    next.set('page', '1');
    setSearchParams(next, { replace: true });
  }

  const columns: DataTableColumn<SourceRecordListItem>[] = [
    {
      key: 'display_name',
      header: 'Название',
      render: (row) => row.display_name,
      onHeaderClick: () => setOrdering('display_name'),
    },
    {
      key: 'source',
      header: 'Источник',
      render: (row) => <SourceBadge code={row.source.code} name={row.source.name} />,
    },
    { key: 'category', header: 'Категория', render: (row) => row.category?.name ?? '—' },
    { key: 'district', header: 'Район', render: (row) => row.district?.name ?? '—' },
    { key: 'phone', header: 'Телефон', render: (row) => firstWithRemainder(row.phones) },
    { key: 'site', header: 'Сайт', render: (row) => websiteCell(row.websites) },
    { key: 'status', header: 'Статус', render: () => 'Нормализовано' },
    {
      key: 'fetched_at',
      header: 'Получено',
      render: (row) => new Intl.DateTimeFormat('ru-RU').format(new Date(row.fetched_at)),
      onHeaderClick: () => setOrdering(query.ordering === '-fetched_at' ? 'fetched_at' : '-fetched_at'),
    },
  ];

  const categories = flattenCategories(filters.categories.data?.results ?? []);

  return (
    <section className="page-stack businesses-page">
      <div>
        <p className="eyebrow">Source records</p>
        <h1>Бизнесы</h1>
      </div>
      <p className="notice" role="note">
        Предварительные записи. Дедупликация ещё не выполнена — один бизнес может встречаться в
        нескольких источниках.
      </p>
      <div className="business-filters">
        <label>
          Поиск
          <input
            type="search"
            aria-label="Поиск"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </label>
        <label>
          Источник
          <select
            aria-label="Источник"
            value={query.source ?? ''}
            onChange={(event) => setFilter('source', event.target.value)}
          >
            <option value="">Все источники</option>
            {(filters.sources.data?.results ?? []).map((source) => (
              <option key={source.id} value={source.code}>
                {source.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Категория
          <select
            aria-label="Категория"
            value={query.category ?? ''}
            onChange={(event) => setFilter('category', event.target.value)}
          >
            <option value="">Все категории</option>
            {categories.map((category) => (
              <option key={category.id} value={category.slug}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {records.isPending && <p>Загрузка записей…</p>}
      {records.isError && <p role="alert">Не удалось загрузить записи.</p>}
      {records.data?.results.length === 0 && <p className="empty-state">Записей не найдено</p>}
      {records.data && records.data.results.length > 0 && (
        <>
          <p>Найдено записей: {records.data.count}</p>
          <DataTable columns={columns} rows={records.data.results} rowKey={(row) => row.id} />
          <Pagination
            page={query.page}
            hasNext={records.data.next !== null}
            hasPrevious={records.data.previous !== null}
            onNext={() => setPage(query.page + 1)}
            onPrevious={() => setPage(Math.max(1, query.page - 1))}
          />
        </>
      )}
    </section>
  );
}
