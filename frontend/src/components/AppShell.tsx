import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';

import { ApiClientError } from '../api/errors';
import { useAuth } from '../features/auth/auth-context';

const navigation = [
  { to: '/', label: 'Обзор', end: true },
  { to: '/campaigns', label: 'Кампании', end: false },
  { to: '/businesses', label: 'Бизнесы', end: false },
];

export function AppShell() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  if (auth.status !== 'authenticated') {
    return null;
  }

  async function handleLogout() {
    setLogoutError(null);
    setIsLoggingOut(true);
    try {
      await auth.signOut();
      navigate('/login', { replace: true });
    } catch (error) {
      setLogoutError(
        error instanceof ApiClientError ? error.message : 'Не удалось выйти из системы.',
      );
      setIsLoggingOut(false);
    }
  }

  return (
    <div className="app-layout">
      <header className="app-header">
        <Link className="brand" to="/">
          Локальные бизнесы
        </Link>
        <div className="account-actions">
          <span>{auth.user.display_name}</span>
          <button type="button" className="secondary-button" onClick={handleLogout} disabled={isLoggingOut}>
            {isLoggingOut ? 'Выходим…' : 'Выйти'}
          </button>
        </div>
        {logoutError !== null && <p role="alert">{logoutError}</p>}
      </header>
      <div className="app-body">
        <nav aria-label="Основная навигация">
          {navigation.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
