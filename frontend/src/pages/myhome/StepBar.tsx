import { Settings2, UserRound } from 'lucide-react';
import { situationSummary, useSituation } from '../../hooks/useSituation';
import { TABS, type TabId } from './tabs';

export type { TabId };

export function StepBar({ tab, onTab, onEditSituation }: { tab: TabId; onTab(t: TabId): void; onEditSituation(): void }) {
  const [s] = useSituation();
  return (
    <div className="stepbar">
      <div className="page stepbar-inner">
        <div className="steps" role="tablist" aria-label="Steps">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              className={`step ${t.id === 'expert' ? 'step-expert' : ''}`}
              onClick={() => onTab(t.id)}
            >
              <span className="step-n" aria-hidden="true">{t.id === 'expert' ? <Settings2 size={13} /> : t.n}</span>
              <span className="step-text"><b>{t.label}</b><small>{t.hint}</small></span>
            </button>
          ))}
        </div>
        <button className="sit-chip" onClick={onEditSituation} title="Change your answers">
          <UserRound size={14} aria-hidden="true" />
          <span className="sit-chip-text">{situationSummary(s)}</span>
          <span className="sr-only">Edit your situation</span>
        </button>
      </div>
    </div>
  );
}

export function NextButton({ to, label, onTab }: { to: TabId; label: string; onTab(t: TabId): void }) {
  return (
    <div className="next-row">
      <button className="btn btn-next" onClick={() => onTab(to)}>{label} →</button>
    </div>
  );
}
