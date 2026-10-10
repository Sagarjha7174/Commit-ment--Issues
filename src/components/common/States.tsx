import type { ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { ERROR_TITLES, toApiError } from '../../api/errors';

export function Skeleton({ h = 16, w = '100%', className = '' }: { h?: number | string; w?: number | string; className?: string }) {
  return <span className={`skeleton ${className}`} style={{ display: 'block', height: h, width: w }} aria-hidden="true" />;
}

export function LoadingBlock({ label, lines = 3 }: { label: string; lines?: number }) {
  return (
    <div role="status" aria-live="polite" className="stack">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} h={i === 0 ? 28 : 14} w={i === 0 ? '40%' : `${90 - i * 12}%`} />)}
    </div>
  );
}

export function ErrorState({ error, onRetry, children }: { error: unknown; onRetry?: () => void; children?: ReactNode }) {
  const e = toApiError(error);
  return (
    <div className="state state-error" role="alert">
      <h3><AlertTriangle size={16} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-3px', marginRight: 6 }} />{ERROR_TITLES[e.kind]}</h3>
      <p className="small">{e.message}</p>
      {children}
      {onRetry && <div><button className="btn btn-sm btn-ghost" onClick={onRetry}><RefreshCw size={14} aria-hidden="true" /> Try again</button></div>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <h3>{title}</h3>
      {children && <div className="small muted">{children}</div>}
    </div>
  );
}

export function SectionHeader({ index, kicker, title, lead, id, aside }: { index: string; kicker: string; title: string; lead?: ReactNode; id: string; aside?: ReactNode }) {
  return (
    <header className="section-head">
      <p className="kicker"><b>{index}</b>{kicker}</p>
      <h2 className="section-title" id={id}>{title}</h2>
      {lead && <p className="lead">{lead}</p>}
      {aside}
    </header>
  );
}
