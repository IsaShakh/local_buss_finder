import { zodResolver } from '@hookform/resolvers/zod';
import { useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { ApiClientError } from '../../api/errors';
import type { BusinessCategory } from '../taxonomy/types';
import { useCampaignReferences, useCreateCampaign } from './queries';
import type { CreateCampaignInput } from './types';

const createCampaignSchema = z.object({
  name: z.string().trim().min(1, 'Введите название кампании.'),
  search_area_id: z.string().min(1, 'Выберите область поиска.'),
  source_ids: z.array(z.string()).min(1, 'Выберите хотя бы один источник.'),
  category_ids: z.array(z.string()),
});

function flattenCategories(categories: BusinessCategory[]): BusinessCategory[] {
  return categories.flatMap((category) => [category, ...flattenCategories(category.children)]);
}

export function CampaignCreatePage() {
  const navigate = useNavigate();
  const references = useCampaignReferences();
  const create = useCreateCampaign();
  const {
    register,
    handleSubmit,
    setValue,
    control,
    formState: { errors },
  } = useForm<CreateCampaignInput>({
    resolver: zodResolver(createCampaignSchema),
    defaultValues: { name: '', search_area_id: '', source_ids: [], category_ids: [] },
  });
  const categoryIds = useWatch({ control, name: 'category_ids' });

  const isLoading =
    references.searchAreas.isPending || references.sources.isPending || references.categories.isPending;
  const referenceError =
    references.searchAreas.error ?? references.sources.error ?? references.categories.error;
  const apiError = create.error instanceof ApiClientError ? create.error.message : null;

  async function submit(input: CreateCampaignInput) {
    try {
      const campaign = await create.mutateAsync(input);
      navigate(`/campaigns/${campaign.id}`);
    } catch {
      // The mutation state renders the sanitized API error next to the form.
    }
  }

  if (isLoading) {
    return <p>Загрузка справочников…</p>;
  }
  if (referenceError !== null) {
    return <p role="alert">Не удалось загрузить справочники кампании.</p>;
  }

  const searchAreas = references.searchAreas.data?.results ?? [];
  const sources = references.sources.data?.results ?? [];
  const categories = flattenCategories(references.categories.data?.results ?? []);

  return (
    <section className="page-stack">
      <div>
        <p className="eyebrow">Новый сбор данных</p>
        <h1>Новая кампания</h1>
      </div>
      <form className="campaign-form" onSubmit={handleSubmit(submit)} noValidate>
        <div className="form-field">
          <label htmlFor="campaign-name">Название кампании</label>
          <input id="campaign-name" {...register('name')} aria-invalid={Boolean(errors.name)} />
          {errors.name && <span role="alert">{errors.name.message}</span>}
        </div>

        <div className="form-field">
          <label htmlFor="search-area">Область поиска</label>
          <select
            id="search-area"
            {...register('search_area_id')}
            aria-invalid={Boolean(errors.search_area_id)}
          >
            <option value="">Выберите область</option>
            {searchAreas.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
          {errors.search_area_id && <span role="alert">{errors.search_area_id.message}</span>}
        </div>

        <fieldset className="choice-group">
          <legend>Источники</legend>
          {sources.map((source) => (
            <label key={source.id}>
              <input type="checkbox" value={source.id} {...register('source_ids')} />
              {source.name}
            </label>
          ))}
          {errors.source_ids && <span role="alert">{errors.source_ids.message}</span>}
        </fieldset>

        <fieldset className="choice-group">
          <legend>Категории</legend>
          <label>
            <input
              type="radio"
              name="category-mode"
              checked={categoryIds.length === 0}
              onChange={() => setValue('category_ids', [])}
            />
            Все поддерживаемые категории
          </label>
          {categories.map((category) => (
            <label key={category.id}>
              <input type="checkbox" value={category.id} {...register('category_ids')} />
              {category.name}
            </label>
          ))}
        </fieldset>

        {apiError !== null && <p role="alert">{apiError}</p>}
        {create.error !== null && apiError === null && (
          <p role="alert">Не удалось создать кампанию.</p>
        )}
        <button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Создаём…' : 'Создать кампанию'}
        </button>
      </form>
    </section>
  );
}
