export type Source = {
  id: string;
  code: string;
  name: string;
  source_type: string;
  is_paid: boolean;
  is_active: boolean;
  attribution: string;
  license_code: string;
  requests_per_second: number;
  concurrency: number;
  timeout_seconds: number;
  max_retries: number;
};
