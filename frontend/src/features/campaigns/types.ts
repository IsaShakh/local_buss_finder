import { z } from 'zod';

export const campaignStatusSchema = z.enum([
  'draft',
  'queued',
  'running',
  'completed',
  'completed_with_errors',
  'failed',
]);

export type CampaignStatus = z.infer<typeof campaignStatusSchema>;

export const sourceProgressStatusSchema = z.enum([
  'pending',
  'running',
  'normalizing',
  'completed',
  'completed_with_errors',
  'failed',
]);

export type SourceProgress = {
  code: string;
  name: string;
  status: z.infer<typeof sourceProgressStatusSchema>;
  dataset_version: string | null;
  discovered: number;
  stored: number;
  normalized: number;
  rejected: number;
  failed_records: number;
};

export type CampaignProgress = {
  id: string;
  status: CampaignStatus;
  totals: {
    jobs: number;
    completed_jobs: number;
    failed_jobs: number;
    discovered: number;
    stored: number;
    normalized: number;
    rejected: number;
    failed_records: number;
  };
  sources: SourceProgress[];
};

const progressCountSchema = z.number().int().nonnegative();

const sourceProgressSchema = z.object({
  code: z.string(),
  name: z.string(),
  status: sourceProgressStatusSchema,
  dataset_version: z.string().nullable(),
  discovered: progressCountSchema,
  stored: progressCountSchema,
  normalized: progressCountSchema,
  rejected: progressCountSchema,
  failed_records: progressCountSchema,
});

export const campaignProgressSchema: z.ZodType<CampaignProgress> = z.object({
  id: z.string().uuid(),
  status: campaignStatusSchema,
  totals: z.object({
    jobs: progressCountSchema,
    completed_jobs: progressCountSchema,
    failed_jobs: progressCountSchema,
    discovered: progressCountSchema,
    stored: progressCountSchema,
    normalized: progressCountSchema,
    rejected: progressCountSchema,
    failed_records: progressCountSchema,
  }),
  sources: z.array(sourceProgressSchema),
});

export type CreateCampaignInput = {
  name: string;
  search_area_id: string;
  source_ids: string[];
  category_ids: string[];
};

export type Campaign = {
  id: string;
  name: string;
  status: CampaignStatus;
  search_area: { id: string; name: string };
  sources: Array<{ id: string; code: string; name: string }>;
  categories: Array<{ id: string; slug: string; name: string }>;
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  raw_records_found: number;
  normalized_records: number;
  rejected_records: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CampaignPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Campaign[];
};
