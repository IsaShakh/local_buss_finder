import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  ALANYA_ID,
  campaignCreateErrorHandler,
  campaignCreateRequests,
  OSM_ID,
  OVERTURE_ID,
  runningProgress,
} from '../../test/handlers';
import { renderAuthenticatedApp } from '../../test/render';
import { server } from '../../test/server';
import { campaignProgressSchema } from './types';

describe('создание кампании', () => {
  beforeEach(() => {
    campaignCreateRequests.length = 0;
  });

  it('создаёт черновик из выбранной области и двух источников', async () => {
    const { user } = renderAuthenticatedApp('/campaigns/new');

    await screen.findByRole('heading', { name: 'Новая кампания' });
    await user.type(screen.getByLabelText('Название кампании'), 'Аланья — первичный сбор');
    await user.selectOptions(screen.getByLabelText('Область поиска'), ALANYA_ID);
    await user.click(screen.getByRole('checkbox', { name: 'Overture Maps' }));
    await user.click(screen.getByRole('checkbox', { name: 'OpenStreetMap' }));
    await user.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(
      await screen.findByRole('heading', { name: 'Аланья — первичный сбор' }),
    ).toBeInTheDocument();
    expect(campaignCreateRequests).toEqual([
      {
        name: 'Аланья — первичный сбор',
        search_area_id: ALANYA_ID,
        source_ids: [OVERTURE_ID, OSM_ID],
        category_ids: [],
      },
    ]);
  });

  it('не отправляет POST и показывает три русские field errors для пустой формы', async () => {
    const { user } = renderAuthenticatedApp('/campaigns/new');
    await user.click(await screen.findByRole('button', { name: 'Создать кампанию' }));

    expect(screen.getByText('Введите название кампании.')).toBeInTheDocument();
    expect(screen.getByText('Выберите область поиска.')).toBeInTheDocument();
    expect(screen.getByText('Выберите хотя бы один источник.')).toBeInTheDocument();
    expect(campaignCreateRequests).toHaveLength(0);
  });

  it('показывает detail API, но не технический trace', async () => {
    server.use(campaignCreateErrorHandler);
    const { user } = renderAuthenticatedApp('/campaigns/new');
    await user.type(await screen.findByLabelText('Название кампании'), 'Аланья');
    await user.selectOptions(screen.getByLabelText('Область поиска'), ALANYA_ID);
    await user.click(screen.getByRole('checkbox', { name: 'OpenStreetMap' }));
    await user.click(screen.getByRole('button', { name: 'Создать кампанию' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Для источника нет активных сопоставлений категорий.',
    );
    expect(screen.queryByText(/Traceback|stack|CampaignValidationError/)).not.toBeInTheDocument();
  });

  it('отклоняет неизвестный progress status на API boundary', () => {
    expect(
      campaignProgressSchema.safeParse({ ...runningProgress, status: 'paused' }).success,
    ).toBe(false);
  });
});
