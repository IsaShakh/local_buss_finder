import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../test/render';

describe('App', () => {
  it('показывает русское название продукта на странице входа', async () => {
    renderApp('/login');

    expect(await screen.findByText('Локальные бизнесы')).toBeInTheDocument();
  });
});
