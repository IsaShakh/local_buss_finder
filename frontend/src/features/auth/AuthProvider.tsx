import { useEffect, useMemo, useRef, useState } from 'react';
import type { PropsWithChildren } from 'react';

import { getSession, login, logout } from './api';
import { AuthContext } from './auth-context';
import type { AuthContextValue, AuthState } from './auth-context';

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null });
  const revision = useRef(0);

  useEffect(() => {
    const requestRevision = revision.current;
    let active = true;

    getSession()
      .then((user) => {
        if (active && revision.current === requestRevision) {
          setState({ status: 'authenticated', user });
        }
      })
      .catch(() => {
        if (active && revision.current === requestRevision) {
          setState({ status: 'anonymous', user: null });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      async signIn(input) {
        revision.current += 1;
        try {
          const user = await login(input);
          setState({ status: 'authenticated', user });
        } catch (error) {
          setState((current) =>
            current.status === 'loading' ? { status: 'anonymous', user: null } : current,
          );
          throw error;
        }
      },
      async signOut() {
        revision.current += 1;
        await logout();
        setState({ status: 'anonymous', user: null });
      },
    }),
    [state],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
