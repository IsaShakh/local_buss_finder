import { request } from '../../api/client';
import { businessPageSchema, duplicateCandidatePageSchema, duplicateDecisionSchema } from './types';
import type { BusinessListQuery, DuplicateCandidate, DuplicateDecision } from './types';

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

export async function getDuplicateCandidates(): Promise<DuplicateCandidate[]> {
  const candidates: DuplicateCandidate[] = [];
  let page = 1;
  while (true) {
    const body = await request<unknown>(`/api/v1/duplicate-candidates/?page=${page}&page_size=${PAGE_SIZE}`);
    const result = duplicateCandidatePageSchema.parse(body);
    candidates.push(...result.results);
    if (result.next === null) return candidates;
    page += 1;
  }
}

export async function confirmDuplicate(id: string): Promise<DuplicateDecision> {
  return duplicateDecisionSchema.parse(await request<unknown>(`/api/v1/duplicate-candidates/${id}/confirm/`, {
    method: 'POST', body: JSON.stringify({}),
  }));
}

export async function rejectDuplicate(id: string): Promise<DuplicateDecision> {
  return duplicateDecisionSchema.parse(await request<unknown>(`/api/v1/duplicate-candidates/${id}/reject/`, {
    method: 'POST', body: JSON.stringify({}),
  }));
}
