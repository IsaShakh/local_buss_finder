import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listSearchAreas } from '../geography/api';
import { listSources } from '../sources/api';
import { listCategories } from '../taxonomy/api';
import {
  createCampaign,
  getCampaign,
  getCampaignProgress,
  listCampaigns,
  startCampaign,
} from './api';

export const campaignKeys = {
  searchAreas: ['search-areas'] as const,
  categories: ['categories'] as const,
  sources: ['sources'] as const,
  campaigns: ['campaigns'] as const,
  campaign: (id: string) => ['campaign', id] as const,
  progress: (id: string) => ['campaign-progress', id] as const,
};

export function useCampaignReferences() {
  const searchAreas = useQuery({ queryKey: campaignKeys.searchAreas, queryFn: listSearchAreas });
  const categories = useQuery({ queryKey: campaignKeys.categories, queryFn: listCategories });
  const sources = useQuery({ queryKey: campaignKeys.sources, queryFn: listSources });
  return { searchAreas, categories, sources };
}

export function useCampaigns() {
  return useQuery({ queryKey: campaignKeys.campaigns, queryFn: listCampaigns });
}

export function useCampaign(id: string) {
  return useQuery({ queryKey: campaignKeys.campaign(id), queryFn: () => getCampaign(id) });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCampaign,
    onSuccess: (campaign) => {
      queryClient.setQueryData(campaignKeys.campaign(campaign.id), campaign);
      void queryClient.invalidateQueries({ queryKey: campaignKeys.campaigns });
    },
  });
}

export function useStartCampaign(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => startCampaign(id),
    onSuccess: (campaign) => {
      queryClient.setQueryData(campaignKeys.campaign(id), campaign);
      void queryClient.invalidateQueries({ queryKey: campaignKeys.progress(id) });
      void queryClient.invalidateQueries({ queryKey: campaignKeys.campaigns });
    },
  });
}

export function useCampaignProgress(id: string, enabled: boolean) {
  return useQuery({
    queryKey: campaignKeys.progress(id),
    queryFn: () => getCampaignProgress(id),
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'queued' || status === 'running' ? 3000 : false;
    },
  });
}
