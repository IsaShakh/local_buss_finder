import { Link } from 'react-router-dom';

import { StatusBadge } from '../../components/StatusBadge';
import { campaignStatusLabel } from '../../shared/labels';
import { useCampaigns } from './queries';

export function CampaignListPage() {
  const campaigns = useCampaigns();

  return (
    <section className="page-stack">
      <div className="page-heading">
        <h1>Кампании</h1>
        <Link className="primary-link" to="/campaigns/new">
          Новая кампания
        </Link>
      </div>
      {campaigns.isPending && <p>Загрузка кампаний…</p>}
      {campaigns.isError && <p role="alert">Не удалось загрузить кампании.</p>}
      {campaigns.data?.results.length === 0 && <p>Кампаний пока нет.</p>}
      {campaigns.data && campaigns.data.results.length > 0 && (
        <ul className="card-list">
          {campaigns.data.results.map((campaign) => (
            <li key={campaign.id}>
              <Link to={`/campaigns/${campaign.id}`}>{campaign.name}</Link>
              <span>{campaign.search_area.name}</span>
              <StatusBadge status={campaign.status}>
                {campaignStatusLabel[campaign.status]}
              </StatusBadge>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
