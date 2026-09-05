import type { CampaignStatus, SourceProgress } from '../features/campaigns/types';

export const campaignStatusLabel = {
  draft: 'Черновик',
  queued: 'В очереди',
  running: 'Выполняется',
  completed: 'Завершена',
  completed_with_errors: 'Завершена с ошибками',
  failed: 'Ошибка',
} satisfies Record<CampaignStatus, string>;

export const sourceProgressStatusLabel = {
  pending: 'Ожидает',
  running: 'Сбор данных',
  normalizing: 'Нормализация',
  completed: 'Завершён',
  completed_with_errors: 'Завершён с ошибками',
  failed: 'Ошибка',
} satisfies Record<SourceProgress['status'], string>;
