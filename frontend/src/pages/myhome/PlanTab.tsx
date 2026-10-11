import type { ScenarioResult } from '../../api/schema';
import type { ScenarioLab } from '../../hooks/useScenarioLab';
import type { ExplanationState } from '../../hooks/useExplanation';
import { useSituation } from '../../hooks/useSituation';
import { MEASURE_SHORT } from '../../utils/labels';
import { PlanCheck } from '../../components/plan/PlanCheck';
import { RequestLetter } from '../../components/plan/RequestLetter';
import { SavePlan } from '../../components/plan/SavePlan';
import { ExplanationPanel } from '../../components/explanation/ExplanationPanel';
import { PERMISSION_NOTE } from '../../utils/permissions';
import type { TabId } from './StepBar';

export function PlanTab({ r, lab, onTab, explanation, templateMode, onTemplateMode }: {
  r: ScenarioResult; lab: ScenarioLab; onTab(t: TabId): void;
  explanation: ExplanationState; templateMode: boolean; onTemplateMode(v: boolean): void;
}) {
  const [s] = useSituation();
  const sel = r.measures_applied;
  return (
    <div className="tab-stack">
      <header className="tab-head">
        <p className="kicker">Your plan</p>
        <h2 className="tab-title">{sel.length ? `${sel.length} improvement${sel.length > 1 ? 's' : ''}` : 'No improvements chosen yet'}</h2>
        {sel.length > 0 && <p className="plan-list">{sel.map((m) => <span key={m} className="chip">{MEASURE_SHORT[m]}</span>)}</p>}
        {!sel.length && <button className="btn" onClick={() => onTab('options')}>Pick a plan</button>}
        {lab.pending && <p className="small explain-pending" role="status">Your latest change is still being calculated; this page shows the previous result until it’s ready.</p>}
      </header>

      <div className="plan-grid">
        <section aria-labelledby="six-q">
          <h3 id="six-q" className="plan-h">Before you start</h3>
          <PlanCheck result={r} situation={s} />
          <p className="xsmall muted">{PERMISSION_NOTE}</p>
        </section>
        <div className="tab-stack">
          <SavePlan result={r} lab={lab} situation={s} onOpened={() => onTab('try')} />
          <RequestLetter result={r} situation={s} />
        </div>
      </div>

      <details className="howto">
        <summary>Read the whole plan as a short report</summary>
        <ExplanationPanel result={r} state={explanation} templateMode={templateMode} onTemplateMode={onTemplateMode} pending={lab.pending} />
      </details>
    </div>
  );
}
