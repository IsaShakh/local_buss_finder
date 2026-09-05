import { createContext, useContext } from 'react';

import type { AuthUser } from './types';

export type AuthState =
  | { status: 'loading'; user: null }
  | { status: 'anonymous'; user: null }
  | { status: 'authenticated'; user: AuthUser };

export type AuthContextValue = AuthState & {
  signIn: (input: { username: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth должен использоваться внутри AuthProvider.');
  }
  return context;
}
