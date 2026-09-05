type ProgressBarProps = {
  processed: number;
  stored: number;
  discoveryRunning?: boolean;
};

export function ProgressBar({ processed, stored, discoveryRunning = false }: ProgressBarProps) {
  if (discoveryRunning && stored === 0) {
    return <p className="progress-indeterminate">Сбор данных…</p>;
  }

  const maximum = Math.max(stored, 1);
  const current = Math.min(processed, maximum);
  const percentage = Math.round((current / maximum) * 100);

  return (
    <div className="progress-wrap">
      <div
        className="progress-bar"
        role="progressbar"
        aria-label="Обработка записей"
        aria-valuemin={0}
        aria-valuemax={maximum}
        aria-valuenow={current}
      >
        <span style={{ width: `${percentage}%` }} />
      </div>
      <span>{percentage}%</span>
    </div>
  );
}
