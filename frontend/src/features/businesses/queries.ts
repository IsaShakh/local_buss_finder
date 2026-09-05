import { useQuery } from '@tanstack/react-query';

import { listSources } from '../sources/api';
import { listCategories } from '../taxonomy/api';
import { listBusinesses } from './api';
import type { BusinessListQuery } from './types';

export function useBusinesses(query: BusinessListQuery) {
  return useQuery({
    queryKey: ['businesses', query],
    queryFn: () => listBusinesses(query),
    placeholderData: (previous) => previous,
  });
}

export function useBusinessFilters() {
  const sources = useQuery({ queryKey: ['sources'], queryFn: listSources });
  const categories = useQuery({ queryKey: ['categories'], queryFn: listCategories });
  return { sources, categories };
}
