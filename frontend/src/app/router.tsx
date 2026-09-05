import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '../components/AppShell';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { LoginPage } from '../features/auth/LoginPage';
import { CampaignCreatePage } from '../features/campaigns/CampaignCreatePage';
import { CampaignDetailPage } from '../features/campaigns/CampaignDetailPage';
import { CampaignListPage } from '../features/campaigns/CampaignListPage';
import { BusinessesPage } from '../features/businesses/BusinessesPage';
import { DuplicateCandidatesPage } from '../features/businesses/DuplicateCandidatesPage';
import { DashboardPage } from '../features/dashboard/DashboardPage';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="campaigns" element={<CampaignListPage />} />
          <Route path="campaigns/new" element={<CampaignCreatePage />} />
          <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
          <Route path="businesses" element={<BusinessesPage />} />
          <Route path="businesses/duplicates" element={<DuplicateCandidatesPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
