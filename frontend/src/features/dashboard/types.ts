import { z } from 'zod';

import { campaignStatusSchema } from '../campaigns/types';
import type { CampaignStatus } from '../campaigns/types';

export type DashboardSummary = {
  records: { raw: number; normalized: number; rejected: number; failed: number };
  campaigns: { total: number; running: number; with_errors: number };
  businesses: { active: number; pending_duplicates: number };
  recent_campaigns: Array<{
    id: string;
    name: string;
    status: CampaignStatus;
    normalized: number;
    updated_at: string;
  }>;
};

const countSchema = z.number().int().nonnegative();

export const dashboardSummarySchema: z.ZodType<DashboardSummary> = z.object({
  records: z.object({
    raw: countSchema,
    normalized: countSchema,
    rejected: countSchema,
    failed: countSchema,
  }),
  campaigns: z.object({
    total: countSchema,
    running: countSchema,
    with_errors: countSchema,
  }),
  businesses: z.object({
    active: countSchema,
    pending_duplicates: countSchema,
  }),
  recent_campaigns: z.array(
    z.object({
      id: z.string().uuid(),
      name: z.string(),
      status: campaignStatusSchema,
      normalized: countSchema,
      updated_at: z.string(),
    }),
  ),
});
