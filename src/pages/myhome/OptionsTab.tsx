import { useState } from 'react';
import { Activity, Check, PoundSterling, ShieldAlert, ShieldCheck, Star } from 'lucide-react';
import type { FeaturedPick, MeasureId, PackageResult, ScenarioResult } from '../../api/schema';
import { useBudgetSearch } from '../../api/queries';
import { toApiError } from '../../api/errors';
import type { ScenarioLab } from '../../hooks/useScenarioLab';
import { HORIZON_TEXT, PRIORITY_OBJECTIVE, ROLE_SHORT, useSituation, type Situation } from '../../hooks/useSituation';
import { fmtGbp, fmtKg, fmtKwh, fmtPct, isNum, savingDirection } from '../../utils/format';
import { MEASURE_SHORT, OBJECTIVE_SHORT, packageIdFor, packageName } from '../../utils/labels';
import { permissionFor, PERMISSION_NOTE } from '../../utils/permissions';
import { DirectionTag } from '../../components/common/Knowledge';
import { Skeleton } from '../../components/common/States';
import { Term } from '../../components/common/Term';
import type { TabId } from './StepBar';

const PLAIN_TITLE = {
  lowest_cost_meeting_threshold: 'Cheapest real improvement',
  largest_carbon_saving: 'Biggest carbon cut',
  best_carbon_per_pound: 'Best value for money',
} as const;

/** Budgets the engine's package search is run with (offline snapshot: these exact values). */
const BUDGET_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'No limit', value: null },
  { label: '£1,000', value: 1000 },
  { label: '£5,000', value: 5000 },
  { label: '£15,000', value: 15000 },
];

function intro(s: Situation, r: ScenarioResult): string[] {
  const out: string[] = [];
  if (s.role === 'tenant') out.push('As a tenant, every one of these needs your landlord’s permission. Step 4 writes the request for you.');
  if (s.role === 'landlord') out.push('As a landlord: lower bills mostly go to your tenants; the work and cost are yours.');
  if (s.role === 'leaseholder' || s.role === 'manager' || r.home.property_type === 'Flat') out.push('In a shared building, roof, wall and window work needs building approval.');
  if (s.horizon === 'lt2') out.push('You may move within 2 years: permanent upgrades stay with the home.');
  if (s.horizon !== 'unknown' && s.horizon !== 'lt2') out.push(`You plan to stay ${HORIZON_TEXT[s.horizon].toLowerCase()}, so longer-lasting upgrades have time to pay off in comfort and carbon.`);
  return out;
}

function BudgetBar({ s, update }: { s: Situation; update: (p: Partial<Situation>) => void }) {
  return (
    <div className="budgetbar" role="group" aria-labelledby="budget-l">
      <span id="budget-l" className="budgetbar-label"><PoundSterling size={14} aria-hidden="true" /> Spend now, up to</span>
      <div className="seg">
        {BUDGET_OPTIONS.map((b) => (
          <button key={b.label} aria-pressed={s.budgetAnswered && s.budgetGbp === b.value} onClick={() => update({ budgetGbp: b.value, budgetAnswered: true })}>{b.label}</button>
        ))}
      </div>
    </div>
  );
}

export function OptionsTab({ r, lab, onTab }: { r: ScenarioResult; lab: ScenarioLab; onTab(t: TabId): void }) {
  const [s, update] = useSituation();
  const [ignoreBudget, setIgnoreBudget] = useState(false);
  const ps = r.packages;
  const byId = new Map((ps?.packages ?? []).map((p) => [p.package_id, p]));
  const fmap = new Map(r.feasibility.map((f) => [f.measure, f]));
  const want = PRIORITY_OBJECTIVE[s.priority];
  const currentId = packageIdFor(lab.selectedMeasures);
  const notes = intro(s, r);

  const budget = s.budgetAnswered ? s.budgetGbp : null;
  const wantsBudget = budget !== null && budget > 0 && !ignoreBudget;
  const q = useBudgetSearch(wantsBudget
    ? { home_id: r.home.home_id, assumptions: r.request.assumptions, user_reading: r.request.user_reading, budget_gbp: budget }
    : null);
  const budgetMode = wantsBudget && !!q.data;
  const picks: FeaturedPick[] = budgetMode ? q.data!.featured : (ps?.featured ?? []);
  const fallbacks = budgetMode ? q.data!.fallbacks : (ps?.fallbacks ?? []);
  const unbudgeted = new Map((ps?.featured ?? []).map((f) => [f.objective, f.package_id]));

  const choose = (ms: readonly MeasureId[]) => {
    lab.setMeasures(ms);
    onTab('plan');
  };

  return (
    <div className="tab-stack">
      <header className="tab-head">
        <p className="kicker">Your options</p>
        <h2 className="tab-title">{budgetMode ? `Three ways to improve this home for ${fmtGbp(budget)} or less` : 'Three ways to improve this home'}</h2>
        <p className="small">
          The engine tried <b>{ps?.packages.length ?? 0}</b> combinations{budgetMode && <> and kept only those costing <b>{fmtGbp(budget)}</b> or less</>}, then picked three, each best at one thing. There is no single “right” answer: choose what matters to you.
        </p>
        {notes.length > 0 && <ul className="notes">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </header>

      <BudgetBar s={s} update={(p) => { setIgnoreBudget(false); update(p); }} />
      {budget === 0 && <p className="callout callout-verify">Every improvement the engine knows about has a cost, so a £0 budget leaves nothing to choose. Showing all plans instead.</p>}
      {wantsBudget && q.isPending && <div role="status" className="small muted">Asking the engine for plans within {fmtGbp(budget)}…<Skeleton h={6} /></div>}
      {wantsBudget && q.error && (
        <p className="callout callout-verify" role="note">{toApiError(q.error).message} Showing all plans, marked against your budget.</p>
      )}
      {budgetMode && (
        <p className="small">
          Filtered by the engine to {fmtGbp(budget)}. <button className="btn-link" onClick={() => setIgnoreBudget(true)}>Compare with no budget limit</button>
        </p>
      )}
      {ignoreBudget && budget !== null && budget > 0 && (
        <p className="small">Showing plans with no budget limit. <button className="btn-link" onClick={() => setIgnoreBudget(false)}>Back to plans within {fmtGbp(budget)}</button></p>
      )}

      {fallbacks.length ? <p className="callout callout-verify">{fallbacks.join(' · ')}{r.baseline.source === 'unavailable' ? '. Try adding a meter reading in step 3.' : '.'}</p> : null}

      <div className="options">
        {picks.map((f) => {
          const p: PackageResult | undefined = f.package_id ? byId.get(f.package_id) : undefined;
          const match = want === f.objective;
          const sameAsUnbudgeted = unbudgeted.get(f.objective) === f.package_id;
          const surv = sameAsUnbudgeted ? r.sensitivity?.survival[f.objective] : undefined;
          const without = budgetMode && !sameAsUnbudgeted ? byId.get(unbudgeted.get(f.objective) ?? '') : undefined;
          const over = !budgetMode && budget !== null && budget > 0 && p?.cost_gbp != null && p.cost_gbp > budget;
          const perms = p ? p.measures.map((m) => permissionFor(m, fmap.get(m), s.role, r.home)) : [];
          const needAsk = perms.filter((x) => x.state === 'needs_consent' || x.state === 'needs_building_approval');
          const elecDir = savingDirection(p?.elec_saving_kwh);
          const isCurrent = p && p.package_id === currentId;
          return (
            <article key={f.objective} className={`option ${match ? 'is-match' : ''} ${over ? 'is-over' : ''}`} aria-labelledby={`opt-${f.objective}`}>
              {match && <p className="option-badge"><Star size={12} aria-hidden="true" /> Matches what matters to you</p>}
              <p className="kicker">{OBJECTIVE_SHORT[f.objective].kicker}</p>
              <h3 id={`opt-${f.objective}`} className="option-title">{PLAIN_TITLE[f.objective]}</h3>
              <p className="xsmall muted">{f.label}</p>
              {!p ? (
                <p className="v-unknown small">{f.message ?? 'No plan qualifies.'}</p>
              ) : (
                <>
                  <p className="option-measures">{p.measures.map((m) => MEASURE_SHORT[m]).join(' + ')}</p>
                  <dl className="option-nums">
                    <div><dt>Cost</dt><dd>
                      <b>{p.cost_gbp != null ? `About ${fmtGbp(p.cost_gbp)}` : 'Not known'}</b>
                      {budgetMode && <span className="fit fit-ok">Within your budget</span>}
                      {over && <span className="fit fit-over">Over your {fmtGbp(budget)} budget</span>}
                    </dd></div>
                    <div><dt>Carbon</dt><dd><b>{fmtKg(p.carbon_saving_kg)} less</b>{isNum(p.carbon_saving_pct) && <span className="muted"> ({fmtPct(p.carbon_saving_pct)} of today)</span>}</dd></div>
                    <div><dt>Gas</dt><dd>{fmtKwh(p.gas_saving_kwh)} less</dd></div>
                    <div><dt>Electricity</dt><dd>{isNum(p.elec_saving_kwh) && p.elec_saving_kwh < -0.5 ? <><b>{fmtKwh(Math.abs(p.elec_saving_kwh))} more</b> <DirectionTag direction={elecDir} label="goes up" /></> : isNum(p.elec_saving_kwh) && p.elec_saving_kwh > 0.5 ? `${fmtKwh(p.elec_saving_kwh)} less` : 'No change'}</dd></div>
                  </dl>
                  <ul className="option-flags">
                    {surv && <li>{surv.changed_under.length ? <Activity size={13} aria-hidden="true" /> : <ShieldCheck size={13} aria-hidden="true" />} Still the pick in {surv.survives.replace('/', ' of ')} “what if” <Term k="sensitivity">tests</Term></li>}
                    {!surv && budgetMode && <li className="muted">“What if” tests are run for the no-limit plans only.</li>}
                    {without && <li className="muted">Without a budget limit: {packageName(without.package_id)} ({fmtGbp(without.cost_gbp)}, {fmtKg(without.carbon_saving_kg)} less)</li>}
                    {needAsk.length > 0 && <li><ShieldAlert size={13} aria-hidden="true" /> {s.role === 'tenant' ? 'Needs landlord permission' : 'Needs building approval'} ({needAsk.length})</li>}
                    {!p.confirmed && <li><ShieldAlert size={13} aria-hidden="true" /> Needs a survey to confirm: {p.must_verify.join('; ')}</li>}
                  </ul>
                  {isCurrent
                    ? <p className="chip chip-saving"><Check size={12} aria-hidden="true" /> This is your current plan</p>
                    : <button className="btn" onClick={() => choose(p.measures)}>Choose this plan</button>}
                </>
              )}
            </article>
          );
        })}
      </div>
      <p className="xsmall muted">Costs are typical EPC figures for York, not quotes. Savings are estimates. {s.role !== 'unknown' && `Permission notes are for a ${ROLE_SHORT[s.role].toLowerCase()}. `}{PERMISSION_NOTE}</p>
      <div className="row">
        <button className="btn btn-ghost" onClick={() => onTab('try')}>Or build your own mix →</button>
        <button className="btn btn-link small" onClick={() => onTab('expert')}>See all {ps?.packages.length ?? 0} combinations</button>
      </div>
    </div>
  );
}
