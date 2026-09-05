import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { invalidCredentialsHandler } from '../../test/handlers';
import { renderApp, renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';

describe('аутентификация', () => {
  it('входит и перенаправляет на обзор', async () => {
    const csrfRequested = vi.fn();
    server.use(
      http.get('/api/v1/auth/csrf/', ({ request }) => {
        csrfRequested();
        expect(request.credentials).toBe('include');
        return HttpResponse.json({ detail: 'CSRF cookie установлена.' });
      }),
    );
    const { user } = renderApp('/login');

    await user.type(screen.getByLabelText('Имя пользователя'), 'owner');
    await user.type(screen.getByLabelText('Пароль'), 'correct-password');
    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('heading', { name: 'Обзор' })).toBeInTheDocument();
    expect(csrfRequested).toHaveBeenCalledOnce();
  });

  it('показывает русскую ошибку API', async () => {
    server.use(invalidCredentialsHandler);
    const { user } = renderApp('/login');

    await user.type(screen.getByLabelText('Имя пользователя'), 'owner');
    await user.type(screen.getByLabelText('Пароль'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Неверное имя пользователя или пароль.',
    );
  });

  it('защищает корневой route и показывает shell только после входа', async () => {
    const anonymous = renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument();

    anonymous.unmount();
    renderAuthenticatedApp('/');

    expect(await screen.findByRole('navigation')).toHaveTextContent('Обзор');
    expect(screen.getByRole('navigation')).toHaveTextContent('Кампании');
    expect(screen.getByRole('navigation')).toHaveTextContent('Бизнесы');
    expect(screen.queryByText('Дедупликация')).not.toBeInTheDocument();
  });

  it('выходит из сессии и возвращает форму входа', async () => {
    const { user } = renderAuthenticatedApp('/');

    await user.click(await screen.findByRole('button', { name: 'Выйти' }));

    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument();
  });

  it('показывает русские ошибки обязательных полей', async () => {
    const { user } = renderApp('/login');

    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByText('Введите имя пользователя.')).toBeInTheDocument();
    expect(screen.getByText('Введите пароль.')).toBeInTheDocument();
  });
});
