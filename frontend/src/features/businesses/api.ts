import { request } from '../../api/client';
import { businessPageSchema } from './types';
import type { BusinessListQuery } from './types';

const PAGE_SIZE = 50;

export async function listBusinesses(query: BusinessListQuery) {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(PAGE_SIZE) });
  if (query.search) params.set('search', query.search);
  if (query.campaign) params.set('campaign', query.campaign);
  if (query.source) params.set('source', query.source);
  if (query.category) params.set('category', query.category);
  if (query.ordering) params.set('ordering', query.ordering);

  const body = await request<unknown>(`/api/v1/businesses/?${params.toString()}`);
  return businessPageSchema.parse(body);
}
