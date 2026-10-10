import type { ReactNode } from 'react';
import { Bot, FileText, Loader2 } from 'lucide-react';
import type { ExplanationClaim, ScenarioResult } from '../../api/schema';
import type { ExplanationState } from '../../hooks/useExplanation';
import { ScenarioIdBadge } from '../common/ScenarioIdBadge';
import { SectionHeader } from '../common/States';
import './explanation.css';

const SOURCE_LABEL: Record<string, string> = {
  llm: 'Written by the LLM, every sentence checked',
  llm_patched: 'LLM text, with failing sentences replaced by the template',
  template: 'Deterministic template',
};

/** Highlight the filled-in numbers (spans) inside a sentence; direction is spelled out, not only coloured. */
function ClaimText({ c }: { c: ExplanationClaim }) {
  if (!c.spans.length) return <>{c.text}</>;
  const parts: ReactNode[] = [];
  let rest = c.text;
  c.spans.forEach((s, i) => {
    const at = rest.indexOf(s.display);
    if (at < 0) return;
    parts.push(rest.slice(0, at));
    const dir = s.direction === 'reduction' || s.direction === 'down' ? 'reduction' : s.direction === 'increase' || s.direction === 'up' ? 'increase' : 'none';
    parts.push(<mark key={i} className={`span span-${dir}`} title={`${s.key}${s.provenance ? ` · ${s.provenance}` : ''}${s.direction ? ` · ${s.direction}` : ''}`}>{s.display}</mark>);
    rest = rest.slice(at + s.display.length);
  });
  parts.push(rest);
  return <>{parts}</>;
}

export function ExplanationPanel({ result, state, templateMode, onTemplateMode, pending }: {
  result: ScenarioResult; state: ExplanationState; templateMode: boolean; onTemplateMode(v: boolean): void; pending: boolean;
}) {
  const e = state.explanation;
  const matches = e?.scenario_id === result.scenario_id;
  return (
    <section className="section" aria-labelledby="explain-title">
      <div className="page">
        <SectionHeader
          index="07" kicker="Plain-English explanation" id="explain-title" title="What this scenario means"
          lead="The explanation is bound to one scenario ID. The language model never writes a number: figures are filled in by code from the engine result, and the app works fully without it."
        />
        <div className="explain panel">
          <div className="row explain-bar">
            {e?.source === 'template' ? <FileText size={16} aria-hidden="true" /> : <Bot size={16} aria-hidden="true" />}
            <span className="small"><b>{SOURCE_LABEL[e?.source ?? 'template'] ?? e?.source}</b>{e?.provider ? ` · ${e.provider}${e.model ? ` ${e.model}` : ''}` : ''}</span>
            {state.loading && <span className="small muted row"><Loader2 size={14} className="spin" aria-hidden="true" /> LLM version on its way</span>}
            <span className="spacer" />
            <label className="row small switch">
              <input type="checkbox" checked={templateMode} onChange={(ev) => onTemplateMode(ev.target.checked)} />
              Template mode
            </label>
            {e && <ScenarioIdBadge id={e.scenario_id} label="Explains" />}
          </div>
          {state.reason && <p className="xsmall muted">{state.reason}</p>}
          {pending && <p className="xsmall explain-pending" role="status">A change is being recalculated; this text still describes the confirmed scenario.</p>}
          {e && matches ? (
            <div className={`explain-body ${pending ? 'is-stale' : ''}`}>
              {e.sections.map((s) => (
                <div key={s.id} className="explain-section">
                  <h3>{s.title}</h3>
                  <p>{s.claims.map((c, i) => <span key={i} className={`claim claim-${c.type}`}><ClaimText c={c} />{' '}</span>)}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="small muted">No explanation for this scenario.</p>
          )}
        </div>
      </div>
    </section>
  );
}
