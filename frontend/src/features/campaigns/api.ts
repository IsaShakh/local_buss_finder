import { request } from '../../api/client';
import { campaignProgressSchema } from './types';
import type { Campaign, CampaignPage, CreateCampaignInput } from './types';

export function listCampaigns() {
  return request<CampaignPage>('/api/v1/campaigns/');
}

export function getCampaign(id: string) {
  return request<Campaign>(`/api/v1/campaigns/${id}/`);
}

export function createCampaign(input: CreateCampaignInput) {
  return request<Campaign>('/api/v1/campaigns/', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function startCampaign(id: string) {
  return request<Campaign>(`/api/v1/campaigns/${id}/start/`, { method: 'POST' });
}

export async function getCampaignProgress(id: string) {
  const body = await request<unknown>(`/api/v1/campaigns/${id}/progress/`);
  return campaignProgressSchema.parse(body);
}
