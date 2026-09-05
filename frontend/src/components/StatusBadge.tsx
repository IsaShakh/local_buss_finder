import type { ReactNode } from 'react';

export function StatusBadge({ children, status }: { children: ReactNode; status: string }) {
  return (
    <span className={`status-badge status-${status}`} data-status={status}>
      {children}
    </span>
  );
}
