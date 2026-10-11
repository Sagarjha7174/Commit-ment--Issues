import type { ReactNode } from 'react';
import { Bot, FileText, Loader2 } from 'lucide-react';
import type { ExplanationClaim, ScenarioResult } from '../../api/schema';
import type { ExplanationState } from '../../hooks/useExplanation';
import { spanTone } from '../../utils/spanTone';
import { ScenarioIdBadge } from '../common/ScenarioIdBadge';
import { SectionHeader } from '../common/States';
import './explanation.css';

const SOURCE_LABEL: Record<string, string> = {
  llm: 'Written by the LLM, every sentence checked',
  llm_patched: 'Written by the LLM; sentences that failed the checks replaced by the template',
  template: 'Deterministic template',
};

/** Highlight the filled-in numbers (spans) inside a sentence; tone follows what is beneficial/adverse for the homeowner. */
function ClaimText({ c }: { c: ExplanationClaim }) {
  if (!c.spans.length) return <>{c.text}</>;
  const parts: ReactNode[] = [];
  let rest = c.text;
  c.spans.forEach((s, i) => {
    const at = rest.indexOf(s.display);
    if (at < 0) return;
    parts.push(rest.slice(0, at));
    const tone = spanTone(s);
    parts.push(<mark key={i} className={`span span-${tone}`} title={`${s.key}${s.provenance ? ` · ${s.provenance}` : ''}${s.direction ? ` · ${s.direction}` : ''}${s.sentiment ? ` · ${s.sentiment}` : ''}`}>{s.display}</mark>);
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
          index="07" kicker="Scenario assessment" id="explain-title" title="What this plan means for your home"
          lead="Energy, carbon, cost and bills for the plan on screen, bound to one scenario ID. The language model never writes a number: every figure is filled in by code from the engine result, and the app works fully without it."
        />
        <div className="explain panel">
          <div className="row explain-bar">
            {e?.source === 'template' ? <FileText size={16} aria-hidden="true" /> : <Bot size={16} aria-hidden="true" />}
            <span className="small"><b>{SOURCE_LABEL[e?.source ?? 'template'] ?? e?.source}</b>{e?.provider ? ` · ${e.provider}${e.model ? ` ${e.model}` : ''}` : ''}</span>
            {state.loading && <span className="small muted row"><Loader2 size={14} className="spin" aria-hidden="true" /> Updating assessment…</span>}
            <span className="spacer" />
            <label className="row small switch">
              <input type="checkbox" checked={templateMode} onChange={(ev) => onTemplateMode(ev.target.checked)} />
              Template mode
            </label>
            {e && <ScenarioIdBadge id={e.scenario_id} label="Scenario" />}
          </div>
          {state.reason && <p className="xsmall muted">{state.reason}</p>}
          {pending && <p className="xsmall explain-pending" role="status">Recalculating; displaying confirmed scenario figures.</p>}
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
