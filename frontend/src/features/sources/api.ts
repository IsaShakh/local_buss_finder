import { request } from '../../api/client';
import type { Source } from './types';

type SourcePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: Source[];
};

export function listSources() {
  return request<SourcePage>('/api/v1/sources/');
}
