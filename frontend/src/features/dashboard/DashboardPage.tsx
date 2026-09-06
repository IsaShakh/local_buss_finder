import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { StatusBadge } from '../../components/StatusBadge';
import { campaignStatusLabel } from '../../shared/labels';
import { getDashboardSummary } from './api';

export function DashboardPage() {
  const summary = useQuery({ queryKey: ['dashboard-summary'], queryFn: getDashboardSummary });

  if (summary.isPending) {
    return <p>Загрузка обзора…</p>;
  }
  if (summary.isError) {
    return <p role="alert">Не удалось загрузить обзор.</p>;
  }

  const { records, campaigns, businesses, recent_campaigns: recentCampaigns } = summary.data;
  const cards = [
    ['Сырых записей', records.raw],
    ['Нормализовано', records.normalized],
    ['Отклонено', records.rejected],
    ['С ошибками', records.failed],
    ['Уникальные бизнесы', businesses.active],
    ['Ожидают проверки', businesses.pending_duplicates],
    ['Кампаний выполняется', campaigns.running],
  ] as const;

  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">Discovery pipeline</p>
        <h1>Обзор</h1>
      </div>
      <dl className="summary-grid">
        {cards.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <section aria-labelledby="recent-campaigns-title">
        <div className="section-heading">
          <h2 id="recent-campaigns-title">Последние кампании</h2>
          {campaigns.total > 0 && <span>Всего: {campaigns.total}</span>}
        </div>
        {recentCampaigns.length === 0 ? (
          <div className="empty-state">
            <p>Кампаний пока нет</p>
            <Link className="primary-link" to="/campaigns/new">
              Создать первую кампанию
            </Link>
          </div>
        ) : (
          <ul className="card-list">
            {recentCampaigns.map((campaign) => (
              <li key={campaign.id}>
                <Link to={`/campaigns/${campaign.id}`}>{campaign.name}</Link>
                <span>Нормализовано: {campaign.normalized}</span>
                <StatusBadge status={campaign.status}>
                  {campaignStatusLabel[campaign.status]}
                </StatusBadge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
