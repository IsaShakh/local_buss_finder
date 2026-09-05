import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listSources } from '../sources/api';
import { listCategories } from '../taxonomy/api';
import { confirmDuplicate, getDuplicateCandidates, listBusinesses, rejectDuplicate } from './api';
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

export function useDuplicateCandidates(page: number) {
  return useQuery({ queryKey: ['duplicate-candidates', page], queryFn: () => getDuplicateCandidates(page) });
}

export function useDuplicateDecision() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'confirm' | 'reject'; returnToPage?: number }) =>
      action === 'confirm' ? confirmDuplicate(id) : rejectDuplicate(id),
    onSuccess: async (_, { returnToPage }) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['businesses'] }),
        client.invalidateQueries({ queryKey: ['duplicate-candidates'], type: 'active', refetchType: returnToPage ? 'none' : 'active' }),
        client.invalidateQueries({ queryKey: ['dashboard-summary'] }),
        // The destination becomes visible after success. Refresh it on mount,
        // without requesting the last page that the decision just removed.
        ...(returnToPage ? [client.invalidateQueries({ queryKey: ['duplicate-candidates', returnToPage], exact: true, refetchType: 'none' })] : []),
      ]);
    },
  });
}
