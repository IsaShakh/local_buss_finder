import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate } from 'react-router-dom';
import { z } from 'zod';

import { ApiClientError } from '../../api/errors';
import { useAuth } from './auth-context';

const loginSchema = z.object({
  username: z.string().trim().min(1, 'Введите имя пользователя.'),
  password: z.string().min(1, 'Введите пароль.'),
});

type LoginInput = z.infer<typeof loginSchema>;

export function LoginPage() {
  const auth = useAuth();
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });

  if (auth.status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  const submit = handleSubmit(async (input) => {
    setApiError(null);
    try {
      await auth.signIn(input);
    } catch (error) {
      setApiError(
        error instanceof ApiClientError ? error.message : 'Не удалось выполнить вход.',
      );
    }
  });

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <p className="product-name">Локальные бизнесы</p>
        <h1 id="login-title">Вход</h1>
        <p className="login-intro">Войдите, чтобы продолжить работу с кампаниями.</p>

        <form onSubmit={submit} noValidate>
          {apiError !== null && <p role="alert">{apiError}</p>}

          <div className="form-field">
            <label htmlFor="username">Имя пользователя</label>
            <input
              id="username"
              autoComplete="username"
              aria-invalid={errors.username ? 'true' : 'false'}
              {...register('username')}
            />
            {errors.username && <p role="alert">{errors.username.message}</p>}
          </div>

          <div className="form-field">
            <label htmlFor="password">Пароль</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={errors.password ? 'true' : 'false'}
              {...register('password')}
            />
            {errors.password && <p role="alert">{errors.password.message}</p>}
          </div>

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Входим…' : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  );
}
