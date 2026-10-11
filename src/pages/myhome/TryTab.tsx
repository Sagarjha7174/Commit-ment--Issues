import { Check, Plus, Users } from 'lucide-react';
import { MEASURE_ORDER, type ScenarioResult } from '../../api/schema';
import { useEvidence, useTransport } from '../../api/queries';
import type { ScenarioLab } from '../../hooks/useScenarioLab';
import { useSituation } from '../../hooks/useSituation';
import { fmtKg, fmtKwh, isNum, savingDirection, shortId } from '../../utils/format';
import { measureLabel } from '../../utils/labels';
import { permissionFor } from '../../utils/permissions';
import { scopRange } from '../../utils/scop';
import { DirectionTag } from '../../components/common/Knowledge';
import { ErrorState } from '../../components/common/States';
import { Term } from '../../components/common/Term';
import { Diff, ReadingForm } from '../../components/whatif/ScenarioLab';
import { NextButton, type TabId } from './StepBar';

const OCCUPANCY = [
  { v: 0.85, label: 'Fewer people' },
  { v: 1, label: 'As recorded' },
  { v: 1.15, label: 'More people' },
] as const;

function Change({ label, v }: { label: string; v: number | null | undefined }) {
  const d = savingDirection(v);
  return (
    <div className="mini">
      <span className="mini-label">{label}</span>
      <b>{!isNum(v) ? 'Not estimated' : d === 'none' ? 'No change' : `${fmtKwh(Math.abs(v))} ${d === 'reduction' ? 'less' : 'more'}`}</b>
      {d !== 'unknown' && d !== 'none' && <DirectionTag direction={d} />}
    </div>
  );
}

export function TryTab({ r, lab, onTab }: { r: ScenarioResult; lab: ScenarioLab; onTab(t: TabId): void }) {
  const t = useTransport();
  const [s] = useSituation();
  const fmap = new Map(r.feasibility.map((f) => [f.measure, f]));
  const selected = new Set(lab.selectedMeasures);
  const a = lab.state.draft.assumptions;
  const evData = useEvidence().data;
  const scop = scopRange(evData) ?? { low: 2.5, mid: 2.9, high: 3.5 };
  const showHp = selected.has('heat_pump');
  const f = lab.state.failure;
  const carbonDir = savingDirection(r.carbon.total_kg);

  return (
    <div className="tab-stack">
      <header className="tab-head">
        <p className="kicker">Try changes</p>
        <h2 className="tab-title">Change one thing, see what moves</h2>
        <p className="small">Every change is recalculated by the engine. The bar at the bottom tells you when the new numbers are ready.</p>
      </header>

      {f && (
        <ErrorState error={f.error} onRetry={lab.retry}>
          <p className="small">This change couldn’t be calculated: <b>{f.change.join('; ')}</b>. You’re still seeing the previous result.</p>
          <div className="row">
            <button className="btn btn-sm btn-ghost" onClick={lab.revert}>Undo this change</button>
            {f.error.kind === 'fixture_miss' && <button className="btn btn-sm btn-ghost" onClick={() => lab.setMeasures(null)}>Use the engine’s suggested set</button>}
          </div>
        </ErrorState>
      )}

      <div className="now panel">
        <p className="kicker">Right now (scenario <span className="mono">{shortId(r.scenario_id)}</span>)</p>
        <div className="minis">
          <div className="mini">
            <span className="mini-label">Score after</span>
            <b>{r.score_after?.total != null ? `${r.score_after.total}/100` : 'Not estimated'}</b>
            <span className="xsmall muted">today {r.score_before.total ?? '?'}</span>
          </div>
          <div className="mini">
            <span className="mini-label">Carbon</span>
            <b>{isNum(r.carbon.total_kg) ? `${fmtKg(Math.abs(r.carbon.total_kg))} ${carbonDir === 'increase' ? 'more' : 'less'}` : 'Not estimated'}</b>
            {carbonDir !== 'unknown' && carbonDir !== 'none' && <DirectionTag direction={carbonDir} />}
          </div>
          <Change label="Gas" v={r.simulation.gas_saving_kwh} />
          <Change label="Electricity" v={r.simulation.elec_saving_kwh} />
        </div>
      </div>

      <div className="try-grid">
        <section className="plan-card" aria-labelledby="try-measures">
          <h3 id="try-measures">Improvements</h3>
          <ul className="tlist">
            {MEASURE_ORDER.map((m) => {
              const fe = fmap.get(m);
              const blocked = fe?.state === 'infeasible';
              const on = selected.has(m);
              const perm = permissionFor(m, fe, s.role, r.home);
              return (
                <li key={m} className={blocked ? 'is-blocked' : ''}>
                  <div>
                    <b>{measureLabel(m)}</b>
                    <span className="xsmall muted">{blocked ? fe?.reason_text : perm.state === 'no_known_issue' ? 'Possible' : perm.label}</span>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${on ? 'on' : ''}`}
                    aria-pressed={on}
                    disabled={blocked}
                    onClick={() => lab.toggleMeasure(m)}
                    aria-label={`${on ? 'Remove' : 'Add'} ${measureLabel(m)}`}
                  >
                    {blocked ? 'Not possible' : on ? <><Check size={14} aria-hidden="true" /> In plan</> : <><Plus size={14} aria-hidden="true" /> Add</>}
                  </button>
                </li>
              );
            })}
          </ul>
          <button className="btn btn-sm btn-link" onClick={() => lab.setMeasures(null)}>Reset to the engine’s suggested set</button>
        </section>

        <div className="tab-stack">
          <section className="plan-card" aria-labelledby="try-people">
            <h3 id="try-people"><Users size={16} aria-hidden="true" /> People at home</h3>
            <p className="small muted">More people usually means more heating, hot water and electricity. The engine re-runs with energy use ±15%.</p>
            <div className="seg seg-wide" role="group" aria-labelledby="try-people">
              {OCCUPANCY.map((o) => (
                <button key={o.v} aria-pressed={a.baseline_scale === o.v} onClick={() => lab.setAssumptions({ baseline_scale: o.v })}>{o.label}</button>
              ))}
            </div>
            {(s.change === 'more_people' || s.change === 'fewer_people') && a.baseline_scale === 1 && (
              <p className="small">You said you expect <b>{s.change === 'more_people' ? 'more' : 'fewer'} people</b>. <button className="btn-link" onClick={() => lab.setAssumptions({ baseline_scale: s.change === 'more_people' ? 1.15 : 0.85 })}>Try it</button></p>
            )}
            {t.kind === 'fixtures' && <p className="xsmall muted">Offline snapshot: works with the engine’s suggested set and its three plans.</p>}
          </section>

          {showHp && (
            <section className="plan-card" aria-labelledby="try-hp">
              <h3 id="try-hp">How efficient is the <Term k="heat pump">heat pump</Term>?</h3>
              <div className="seg seg-wide" role="group" aria-labelledby="try-hp">
                {[scop.low, null, scop.high].map((v) => (
                  <button key={String(v)} aria-pressed={a.heat_pump_scop === v} onClick={() => lab.setAssumptions({ heat_pump_scop: v })}>
                    {v === null ? 'Typical' : v === scop.low ? 'Less efficient' : 'More efficient'}
                  </button>
                ))}
              </div>
              <p className="xsmall muted"><Term k="SCOP">SCOP</Term> {scop.low} / typical {scop.mid} / {scop.high} (UK field trials).</p>
            </section>
          )}

          <ReadingForm key={`${r.home.home_id}-${JSON.stringify(r.request.user_reading)}`} lab={lab} homeId={r.home.home_id} />
        </div>
      </div>

      {lab.state.previous && <Diff prev={lab.state.previous} curr={r} />}
      <NextButton to="plan" label="Check this plan" onTab={onTab} />
    </div>
  );
}
