import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '../components/AppShell';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { LoginPage } from '../features/auth/LoginPage';

function SectionPage({ title }: { title: string }) {
  return <h1>{title}</h1>;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<SectionPage title="Обзор" />} />
          <Route path="campaigns" element={<SectionPage title="Кампании" />} />
          <Route path="businesses" element={<SectionPage title="Бизнесы" />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
