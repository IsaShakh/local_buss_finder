import { useQueryClient } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AppProviders } from './providers';

function RetryPolicyProbe() {
  const retry = useQueryClient().getDefaultOptions().queries?.retry;

  return <output>{String(retry)}</output>;
}

describe('AppProviders', () => {
  it('отключает повторы запросов в тестах', () => {
    render(
      <AppProviders>
        <RetryPolicyProbe />
      </AppProviders>,
    );

    expect(screen.getByRole('status')).toHaveTextContent('false');
  });
});
