import { request } from '../../api/client';
import { dashboardSummarySchema } from './types';

export async function getDashboardSummary() {
  const body = await request<unknown>('/api/v1/dashboard/summary/');
  return dashboardSummarySchema.parse(body);
}
