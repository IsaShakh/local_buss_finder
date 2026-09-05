type PaginationProps = {
  page: number;
  hasNext: boolean;
  hasPrevious: boolean;
  onNext: () => void;
  onPrevious: () => void;
};

export function Pagination({ page, hasNext, hasPrevious, onNext, onPrevious }: PaginationProps) {
  return (
    <nav className="pagination" aria-label="Пагинация записей">
      <button
        type="button"
        aria-label="Предыдущая страница"
        onClick={onPrevious}
        disabled={!hasPrevious}
      >
        Назад
      </button>
      <span>Страница {page}</span>
      <button
        type="button"
        aria-label="Следующая страница"
        onClick={onNext}
        disabled={!hasNext}
      >
        Вперёд
      </button>
    </nav>
  );
}
