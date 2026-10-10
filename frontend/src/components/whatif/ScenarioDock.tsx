/** Always-visible status of the numbers on screen: confirmed, recalculating, or failed (with the last confirmed kept). */
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, Undo2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ScenarioLab } from '../../hooks/useScenarioLab';
import { ScenarioIdBadge } from '../common/ScenarioIdBadge';
import './lab.css';

export function ScenarioDock({ lab }: { lab: ScenarioLab }) {
  const { state, status } = lab;
  const pendingChange = state.inflight?.change ?? state.failure?.change ?? null;
  const text =
    status === 'recalculating' ? 'Working out the new numbers…'
      : status === 'failed' ? 'Couldn’t update. You’re seeing the previous numbers.'
        : status === 'ready' ? (lab.pending ? 'Change noted…' : 'Numbers are up to date')
          : status === 'loading' ? 'Loading…' : 'Could not load this home';
  return (
    <div className={`dock dock-${status}`} role="region" aria-label="Scenario status">
      <div className="page dock-inner">
        <span className="dock-state" aria-live="polite" aria-atomic="true">
          {status === 'recalculating' || status === 'loading' ? <Loader2 size={16} className="spin" aria-hidden="true" />
            : status === 'failed' || status === 'error' ? <AlertTriangle size={16} aria-hidden="true" />
              : <CheckCircle2 size={16} aria-hidden="true" />}
          <span>{text}</span>
        </span>
        <span className="dock-changes">
          {(pendingChange ?? (status === 'ready' ? state.confirmedChange : [])).slice(0, 3).map((c) => (
            <span key={c} className={`chip ${pendingChange ? 'chip-ink' : ''}`}>{c}</span>
          ))}
        </span>
        <span className="spacer" />
        <ScenarioIdBadge id={state.confirmed?.scenario_id} label="Result" />
        {state.failure && <button className="btn btn-sm btn-ghost" onClick={lab.retry}><RotateCcw size={14} aria-hidden="true" /> Retry</button>}
        {(lab.pending || state.failure) && <button className="btn btn-sm btn-ghost" onClick={lab.revert}><Undo2 size={14} aria-hidden="true" /> Revert</button>}
        <Link className="btn btn-sm btn-ghost dock-link" to="?tab=try">Try changes</Link>
      </div>
    </div>
  );
}
