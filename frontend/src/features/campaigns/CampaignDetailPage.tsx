import { useParams } from 'react-router-dom';

import { ApiClientError } from '../../api/errors';
import { ProgressBar } from '../../components/ProgressBar';
import { StatusBadge } from '../../components/StatusBadge';
import { campaignStatusLabel, sourceProgressStatusLabel } from '../../shared/labels';
import { useCampaign, useCampaignProgress, useStartCampaign } from './queries';

function formatStartedAt(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function CampaignDetailPage() {
  const { campaignId = '' } = useParams();
  const campaign = useCampaign(campaignId);
  const start = useStartCampaign(campaignId);
  const progress = useCampaignProgress(
    campaignId,
    campaign.data !== undefined && campaign.data.status !== 'draft',
  );

  if (campaign.isPending) {
    return <p>Загрузка кампании…</p>;
  }
  if (campaign.isError) {
    return <p role="alert">Не удалось загрузить кампанию.</p>;
  }

  const item = campaign.data;
  const startError = start.error instanceof ApiClientError ? start.error.message : null;
  const status = progress.data?.status ?? item.status;
  const totals = progress.data?.totals ?? {
    jobs: item.total_jobs,
    completed_jobs: item.completed_jobs,
    failed_jobs: item.failed_jobs,
    discovered: item.raw_records_found,
    stored: item.raw_records_found,
    normalized: item.normalized_records,
    rejected: item.rejected_records,
    failed_records: 0,
  };
  const processed = totals.normalized + totals.rejected + totals.failed_records;
  const isActive = status === 'queued' || status === 'running';

  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">Кампания</p>
        <h1>{item.name}</h1>
      </div>
      <div className="campaign-meta">
        <StatusBadge status={status}>{campaignStatusLabel[status]}</StatusBadge>
        <span>Область: {item.search_area.name}</span>
        {item.started_at !== null && <span>Начата: {formatStartedAt(item.started_at)}</span>}
      </div>
      {item.status === 'draft' && (
        <button type="button" onClick={() => start.mutate()} disabled={start.isPending}>
          {start.isPending ? 'Запускаем…' : 'Запустить кампанию'}
        </button>
      )}
      {startError !== null && <p role="alert">{startError}</p>}
      {progress.isPending && item.status !== 'draft' && <p>Загрузка прогресса…</p>}
      {progress.isError && <p role="alert">Не удалось загрузить прогресс кампании.</p>}
      {(progress.data !== undefined || item.status !== 'draft') && (
        <section className="progress-panel" aria-labelledby="campaign-progress-title">
          <h2 id="campaign-progress-title">Прогресс</h2>
          <ProgressBar processed={processed} stored={totals.stored} discoveryRunning={isActive} />
          <dl className="metric-grid">
            <div>
              <dt>Заданий</dt>
              <dd>{totals.jobs}</dd>
            </div>
            <div>
              <dt>Завершено заданий</dt>
              <dd>{totals.completed_jobs}</dd>
            </div>
            <div>
              <dt>Ошибок заданий</dt>
              <dd>{totals.failed_jobs}</dd>
            </div>
            <div>
              <dt>Найдено</dt>
              <dd>{totals.discovered}</dd>
            </div>
            <div>
              <dt>Сохранено</dt>
              <dd>{totals.stored}</dd>
            </div>
            <div>
              <dt>Нормализовано</dt>
              <dd>{totals.normalized}</dd>
            </div>
            <div>
              <dt>Отклонено</dt>
              <dd>{totals.rejected}</dd>
            </div>
            <div>
              <dt>Ошибок записей</dt>
              <dd>{totals.failed_records}</dd>
            </div>
          </dl>
        </section>
      )}
      {progress.data !== undefined && (
        <section className="source-progress" aria-labelledby="source-progress-title">
          <h2 id="source-progress-title">Источники</h2>
          {progress.data.sources.length === 0 ? (
            <p>Источники ожидают запуска.</p>
          ) : (
            <ul className="source-progress-list">
              {progress.data.sources.map((source) => (
                <li key={source.code}>
                  <div className="source-heading">
                    <div>
                      <strong>{source.name}</strong>
                      <span>{source.code}</span>
                    </div>
                    <StatusBadge status={source.status}>
                      {sourceProgressStatusLabel[source.status]}
                    </StatusBadge>
                  </div>
                  <p>Версия данных: {source.dataset_version ?? '—'}</p>
                  <ul className="source-counters">
                    <li>Сохранено: {source.stored}</li>
                    <li>Нормализовано: {source.normalized}</li>
                    <li>Отклонено: {source.rejected}</li>
                    <li>Ошибок записей: {source.failed_records}</li>
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </section>
  );
}
