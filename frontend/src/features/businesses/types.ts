import { z } from 'zod';

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type Reference = {
  id: string;
  name: string;
  slug: string;
};

export type GeoJsonPoint = {
  type: 'Point';
  coordinates: [number, number];
};

export type BusinessListItem = {
  id: string;
  is_canonical: true;
  display_name: string;
  category: Reference | null;
  district: Reference | null;
  address_text: string;
  location: GeoJsonPoint | null;
  phones: string[];
  emails: string[];
  websites: string[];
  social_urls: Record<string, string[]>;
  source_count: number;
  source_record_count: number;
  pending_duplicate_count: number;
  first_seen_at: string;
  last_seen_at: string;
};

export type BusinessListQuery = {
  page: number;
  search?: string;
  campaign?: string;
  source?: string;
  category?: string;
  ordering?:
    | 'display_name'
    | 'first_seen_at'
    | '-first_seen_at'
    | 'last_seen_at'
    | '-last_seen_at'
    | 'updated_at'
    | '-updated_at';
};

const referenceSchema = z.object({ id: z.string().uuid(), name: z.string(), slug: z.string() });
const geoJsonPointSchema: z.ZodType<GeoJsonPoint> = z.object({
  type: z.literal('Point'),
  coordinates: z.tuple([z.number(), z.number()]),
});
const businessListItemSchema: z.ZodType<BusinessListItem> = z.object({
  id: z.string().uuid(),
  is_canonical: z.literal(true),
  display_name: z.string(),
  category: referenceSchema.nullable(),
  district: referenceSchema.nullable(),
  address_text: z.string(),
  location: geoJsonPointSchema.nullable(),
  phones: z.array(z.string()),
  emails: z.array(z.string()),
  websites: z.array(z.string()),
  social_urls: z.record(z.string(), z.array(z.string())),
  source_count: z.number().int().nonnegative(),
  source_record_count: z.number().int().nonnegative(),
  pending_duplicate_count: z.number().int().nonnegative(),
  first_seen_at: z.string(),
  last_seen_at: z.string(),
});

export const businessPageSchema: z.ZodType<Paginated<BusinessListItem>> = z.object({
  count: z.number().int().nonnegative(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(businessListItemSchema),
});

export const duplicateCandidateSchema = z.object({
  id: z.string().uuid(),
  left_business: businessListItemSchema,
  right_business: businessListItemSchema,
  score: z.number().int().min(0).max(100),
  signals: z.array(z.object({
    code: z.string(),
    label: z.string(),
    weight: z.number().int(),
    value: z.union([z.string(), z.number()]).nullable(),
  })),
  created_at: z.string(),
  updated_at: z.string(),
});

export type DuplicateCandidate = z.infer<typeof duplicateCandidateSchema>;

export const duplicateCandidatePageSchema = z.object({
  count: z.number().int().nonnegative(),
  next: z.string().nullable(),
  previous: z.string().nullable(),
  results: z.array(duplicateCandidateSchema),
});

// Decision endpoints return an acknowledgement, not a pending comparison.
export const duplicateDecisionSchema = z.object({
  id: z.string().uuid(),
  status: z.enum(['confirmed', 'rejected']),
  survivor_business_id: z.string().uuid().nullable(),
  merged_business_id: z.string().uuid().nullable(),
});

export type DuplicateDecision = z.infer<typeof duplicateDecisionSchema>;
