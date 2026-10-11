import { useState, type FormEvent } from 'react';
import { Download, FolderOpen, Printer, Save, Trash2 } from 'lucide-react';
import type { ScenarioResult } from '../../api/schema';
import { draftOf, type ScenarioLab } from '../../hooks/useScenarioLab';
import { useSavedPlans } from '../../hooks/useSavedPlans';
import type { Situation } from '../../hooks/useSituation';
import { buildDecisionRecord, downloadJson } from '../../utils/decisionRecord';
import { fmtDate, shortId } from '../../utils/format';
import { MEASURE_SHORT } from '../../utils/labels';
import type { MeasureId } from '../../api/schema';

export function SavePlan({ result: r, lab, situation, onOpened }: { result: ScenarioResult; lab: ScenarioLab; situation: Situation; onOpened(): void }) {
  const saved = useSavedPlans(r.home.home_id);
  const [name, setName] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = name.trim() || `Plan ${saved.plans.length + 1}`;
    saved.save({ name: n, homeId: r.home.home_id, draft: draftOf(r), scenarioId: r.scenario_id, measures: r.measures_applied });
    setName('');
    setMsg(`Saved “${n}”.`);
  };
  return (
    <div className="plan-card">
      <h3>Keep this plan</h3>
      <form className="row" onSubmit={submit}>
        <label htmlFor="plan-name" className="sr-only">Plan name</label>
        <input id="plan-name" className="input" style={{ flex: 1, minWidth: 160 }} placeholder="Name, e.g. “Before talking to installer”" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        <button className="btn btn-sm" type="submit" disabled={lab.pending}><Save size={14} aria-hidden="true" /> Save</button>
      </form>
      <p className="xsmall muted" role="status">{msg ?? 'Saved in this browser only.'}</p>
      <div className="row">
        <button className="btn btn-sm btn-ghost" onClick={() => downloadJson(`green-home-record-${r.home.home_id}-${shortId(r.scenario_id)}.json`, buildDecisionRecord(r, situation))}>
          <Download size={14} aria-hidden="true" /> Download decision record
        </button>
        <button className="btn btn-sm btn-ghost" onClick={() => window.print()}><Printer size={14} aria-hidden="true" /> Print</button>
      </div>
      {saved.plans.length > 0 && (
        <ul className="saved">
          {saved.plans.map((p) => (
            <li key={p.id}>
              <div>
                <b>{p.name}</b>
                <span className="xsmall muted">{p.measures.length ? p.measures.map((m) => MEASURE_SHORT[m as MeasureId] ?? m).join(' + ') : 'No measures'} · {fmtDate(p.savedAt)}</span>
                {p.scenarioId === r.scenario_id && <span className="chip chip-saving">Showing now</span>}
              </div>
              <div className="row">
                <button className="btn btn-sm btn-ghost" onClick={() => { lab.restore(p.draft); onOpened(); }} aria-label={`Open saved plan ${p.name}`}><FolderOpen size={14} aria-hidden="true" /> Open</button>
                <button className="btn btn-sm btn-ghost" onClick={() => saved.remove(p.id)} aria-label={`Delete saved plan ${p.name}`}><Trash2 size={14} aria-hidden="true" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
