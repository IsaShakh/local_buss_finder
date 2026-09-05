import { useEffect, useRef, useState } from 'react';

import { ApiClientError } from '../../api/errors';
import { useDuplicateCandidates, useDuplicateDecision } from './queries';
import type { BusinessListItem, DuplicateCandidate } from './types';

function BusinessSummary({ business, label }: { business: BusinessListItem; label: string }) {
  return (
    <section className="duplicate-summary" aria-label={label}>
      <p className="eyebrow">{label}</p>
      <h3>{business.display_name}</h3>
      <dl>
        <dt>Категория</dt><dd>{business.category?.name ?? '—'}</dd>
        <dt>Район</dt><dd>{business.district?.name ?? '—'}</dd>
        <dt>Адрес</dt><dd>{business.address_text || '—'}</dd>
        <dt>Координаты (долгота, широта)</dt><dd>{business.location?.coordinates.join(', ') ?? '—'}</dd>
        <dt>Телефоны</dt><dd>{business.phones.join(', ') || '—'}</dd>
        <dt>Email</dt><dd>{business.emails.join(', ') || '—'}</dd>
        <dt>Сайты</dt><dd>{business.websites.join(', ') || '—'}</dd>
        <dt>Социальные сети</dt><dd>{Object.values(business.social_urls).flat().join(', ') || '—'}</dd>
      </dl>
      <p>Источников: {business.source_count} · Исходных записей: {business.source_record_count}</p>
    </section>
  );
}

type Selection = { candidate: DuplicateCandidate; action: 'confirm' | 'reject'; trigger: HTMLButtonElement };

export function DuplicateCandidatesPage() {
  const candidates = useDuplicateCandidates();
  const decision = useDuplicateDecision();
  const [selection, setSelection] = useState<Selection | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (selection !== null) dialog.current?.showModal();
  }, [selection]);

  function closeDialog() {
    if (decision.isPending) return;
    dialog.current?.close();
    selection?.trigger.focus();
    setSelection(null);
    decision.reset();
  }

  function submitDecision() {
    if (selection === null || decision.isPending) return;
    decision.mutate({ id: selection.candidate.id, action: selection.action }, {
      onSuccess: () => {
        dialog.current?.close();
        setSelection(null);
        heading.current?.focus();
      },
    });
  }

  const confirming = selection?.action === 'confirm';
  const errorMessage = decision.error instanceof ApiClientError && decision.error.status === 409
    ? 'Решение по этой паре уже принято. Обновите список.'
    : 'Не удалось сохранить решение. Попробуйте ещё раз.';

  return (
    <section className="page-stack">
      <h1 ref={heading} tabIndex={-1}>Дубликаты</h1>
      <p>Сравните компании и подтвердите совпадение или отметьте их как разные.</p>
      <button type="button" onClick={() => void candidates.refetch()} disabled={candidates.isFetching || decision.isPending}>Обновить список</button>
      {candidates.isPending && <p>Загрузка дубликатов…</p>}
      {candidates.isError && <p role="alert">Не удалось загрузить дубликаты.</p>}
      {candidates.data?.length === 0 && <p className="empty-state">Нет дубликатов для проверки</p>}
      {candidates.data?.map((candidate) => (
        <article className="duplicate-card" key={candidate.id} aria-label="Сравнение компаний">
          <h2>Совпадение: {candidate.score} / 100</h2>
          <ul>{candidate.signals.map((signal) => <li key={signal.code}>{signal.label}</li>)}</ul>
          <div className="duplicate-comparison">
            <BusinessSummary business={candidate.left_business} label="Компания 1" />
            <BusinessSummary business={candidate.right_business} label="Компания 2" />
          </div>
          <div className="duplicate-actions">
            <button className="primary-link" type="button" disabled={decision.isPending} onClick={(event) => {
              decision.reset(); setSelection({ candidate, action: 'confirm', trigger: event.currentTarget });
            }}>Объединить</button>
            <button className="secondary-button" type="button" disabled={decision.isPending} onClick={(event) => {
              decision.reset(); setSelection({ candidate, action: 'reject', trigger: event.currentTarget });
            }}>Это разные компании</button>
          </div>
        </article>
      ))}
      {selection !== null && (
        <dialog ref={dialog} className="duplicate-dialog" aria-labelledby="duplicate-decision-title" aria-describedby="duplicate-decision-description" onCancel={(event) => { event.preventDefault(); closeDialog(); }}>
          <h2 id="duplicate-decision-title">{confirming ? 'Объединить компании?' : 'Отметить как разные компании?'}</h2>
          <p id="duplicate-decision-description">
            «{selection.candidate.left_business.display_name}» и «{selection.candidate.right_business.display_name}».
            {' '}{confirming ? 'Их исходные записи будут объединены в одну компанию.' : 'Пара будет исключена из очереди проверки без объединения.'}
          </p>
          {decision.isError && <p role="alert">{errorMessage}</p>}
          <div className="duplicate-actions">
            <button className="secondary-button" type="button" autoFocus disabled={decision.isPending} onClick={closeDialog}>Отмена</button>
            <button className="primary-link" type="button" disabled={decision.isPending} onClick={submitDecision}>
              {decision.isPending ? 'Сохраняем…' : confirming ? 'Объединить' : 'Это разные компании'}
            </button>
          </div>
        </dialog>
      )}
    </section>
  );
}
