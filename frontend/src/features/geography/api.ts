import { request } from '../../api/client';
import type { SearchArea } from './types';

type SearchAreaPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: SearchArea[];
};

export function listSearchAreas() {
  return request<SearchAreaPage>('/api/v1/geography/search-areas/');
}
