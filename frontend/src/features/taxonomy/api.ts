import { request } from '../../api/client';
import type { BusinessCategory } from './types';

type CategoryPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: BusinessCategory[];
};

export function listCategories() {
  return request<CategoryPage>('/api/v1/taxonomy/categories/');
}
