import { Navigate, Outlet } from 'react-router-dom';

import { useAuth } from '../features/auth/auth-context';

export function ProtectedRoute() {
  const auth = useAuth();

  if (auth.status === 'loading') {
    return (
      <main>
        <p role="status">Проверяем сессию…</p>
      </main>
    );
  }
  if (auth.status === 'anonymous') {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
