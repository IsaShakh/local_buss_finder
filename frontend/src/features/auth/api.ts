import { request } from '../../api/client';
import type { AuthUser } from './types';

export function getSession() {
  return request<AuthUser>('/api/v1/auth/session/');
}

export function login(input: { username: string; password: string }) {
  return request<AuthUser>('/api/v1/auth/login/', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function logout() {
  return request<void>('/api/v1/auth/logout/', { method: 'POST' });
}
