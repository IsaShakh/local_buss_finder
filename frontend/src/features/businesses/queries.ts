import { useQuery } from '@tanstack/react-query';

import { listSources } from '../sources/api';
import { listCategories } from '../taxonomy/api';
import { listSourceRecords } from './api';
import type { SourceRecordQuery } from './types';

export function useSourceRecords(query: SourceRecordQuery) {
  return useQuery({
    queryKey: ['source-records', query],
    queryFn: () => listSourceRecords(query),
    placeholderData: (previous) => previous,
  });
}

export function useBusinessFilters() {
  const sources = useQuery({ queryKey: ['sources'], queryFn: listSources });
  const categories = useQuery({ queryKey: ['categories'], queryFn: listCategories });
  return { sources, categories };
}
