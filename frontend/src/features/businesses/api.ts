import { request } from '../../api/client';
import { sourceRecordPageSchema } from './types';
import type { SourceRecordQuery } from './types';

const PAGE_SIZE = 50;

export async function listSourceRecords(query: SourceRecordQuery) {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(PAGE_SIZE) });
  if (query.search) params.set('search', query.search);
  if (query.campaign) params.set('campaign', query.campaign);
  if (query.source) params.set('source', query.source);
  if (query.category) params.set('category', query.category);
  if (query.ordering) params.set('ordering', query.ordering);

  const body = await request<unknown>(`/api/v1/source-records/?${params.toString()}`);
  return sourceRecordPageSchema.parse(body);
}
