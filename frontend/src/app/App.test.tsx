import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from './App';

describe('App', () => {
  it('показывает русское название продукта', () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: 'Локальные бизнесы' })).toBeInTheDocument();
  });
});
