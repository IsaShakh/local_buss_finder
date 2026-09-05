import { z } from 'zod';

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type SourceRecordListItem = {
  id: string;
  is_canonical: false;
  display_name: string;
  source: { code: string; name: string };
  category: { id: string; name: string; slug: string } | null;
  district: { id: string; name: string; slug: string } | null;
  phones: string[];
  websites: string[];
  normalization_status: 'normalized';
  fetched_at: string;
};

export type SourceRecordQuery = {
  page: number;
  search?: string;
  campaign?: string;
  source?: string;
  category?: string;
  ordering?: 'display_name' | 'fetched_at' | '-fetched_at';
};

const referenceSchema = z.object({ id: z.string().uuid(), name: z.string(), slug: z.string() });
const sourceRecordSchema: z.ZodType<SourceRecordListItem> = z.object({
  id: z.string().uuid(),
  is_canonical: z.literal(false),
  display_name: z.string(),
  source: z.object({ code: z.string(), name: z.string() }),
  category: referenceSchema.nullable(),
  district: referenceSchema.nullable(),
  phones: z.array(z.string()),
  websites: z.array(z.string()),
  normalization_status: z.literal('normalized'),
  fetched_at: z.string(),
});

export const sourceRecordPageSchema: z.ZodType<Paginated<SourceRecordListItem>> = z.object({
  count: z.number().int().nonnegative(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(sourceRecordSchema),
});
