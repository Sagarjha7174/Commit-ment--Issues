import { Check, CircleSlash, HelpCircle, Plus } from 'lucide-react';
import { MEASURE_ORDER, type Evidence, type MeasureId, type ScenarioResult } from '../../api/schema';
import { fmtGbp, fmtKg, fmtSigned, humanise, missingText, savingDirection } from '../../utils/format';
import { measureLabel, MEASURE_SHORT, reasonText } from '../../utils/labels';
import { measureEvidence } from '../../utils/evidence';
import { DirectionTag } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';
import { SectionHeader } from '../common/States';
import './retrofits.css';

type CatalogueMeasure = Evidence['catalogue']['measures'][number];

const STATE_UI = {
  feasible: { label: 'Feasible', cls: 'chip-saving', Icon: Check },
  needs_verification: { label: 'Needs verification', cls: 'chip-verify', Icon: HelpCircle },
  infeasible: { label: 'Not suitable', cls: 'chip-blocked', Icon: CircleSlash },
} as const;

interface Props {
  result: ScenarioResult;
  selected: ReadonlySet<string>;
  onToggle(m: MeasureId): void;
  catalogue?: CatalogueMeasure[];
  busy: boolean;
}

export function MeasureExplorer({ result: r, selected, onToggle, catalogue, busy }: Props) {
  const fmap = new Map(r.feasibility.map((f) => [f.measure, f]));
  const rows = new Map(r.simulation.measures.map((m) => [m.measure, m]));
  const solo = new Map((r.packages?.packages ?? []).map((p) => [p.package_id, p]));
  const cat = new Map((catalogue ?? []).map((m) => [m.id, m]));
  const applied = new Set<string>(r.measures_applied);
  const order = r.measures_applied;

  return (
    <section className="section" aria-labelledby="measures-title">
      <div className="page">
        <SectionHeader
          index="04" kicker="Retrofit controls" id="measures-title" title="Seven measures, checked for this home"
          lead="Missing information never counts as proof that a measure is unsuitable: it becomes ‘needs verification’. Measures are applied in a fixed physical order (fabric first, heat pump after insulation, solar last), so each one works on what the earlier ones leave."
        />
        <ol className="measures">
          {MEASURE_ORDER.map((m, i) => {
            const f = fmap.get(m);
            const state = f?.state ?? 'needs_verification';
            const ui = STATE_UI[state];
            const row = rows.get(m);
            const alone = solo.get(m);
            const c = cat.get(m);
            const isSel = selected.has(m);
            const pendingAdd = isSel && !applied.has(m);
            const pendingRemove = !isSel && applied.has(m);
            const step = order.indexOf(m);
            const deps = (c?.dependencies ?? []).filter((d) => fmap.get(d as MeasureId)?.state !== 'infeasible');
            return (
              <li key={m} className={`measure measure-${state} ${isSel ? 'is-selected' : ''}`}>
                <div className="measure-top">
                  <span className="measure-no serif">{i + 1}</span>
                  <div className="measure-title">
                    <h3>{measureLabel(m)}</h3>
                    <div className="row">
                      <span className={`chip ${ui.cls}`}><ui.Icon size={12} aria-hidden="true" />{ui.label}</span>
                      {f?.suitability && <span className="chip">Suitability {f.suitability}</span>}
                      {pendingAdd && <span className="chip chip-ink">Adding…</span>}
                      {pendingRemove && <span className="chip chip-ink">Removing…</span>}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={`toggle ${isSel ? 'on' : ''}`}
                    aria-pressed={isSel}
                    disabled={state === 'infeasible'}
                    onClick={() => onToggle(m)}
                    aria-label={`${isSel ? 'Remove' : 'Add'} ${measureLabel(m)} ${isSel ? 'from' : 'to'} the scenario`}
                    aria-busy={busy && (pendingAdd || pendingRemove)}
                  >
                    {isSel ? <Check size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
                    {state === 'infeasible' ? 'Unavailable' : isSel ? 'In plan' : 'Add'}
                  </button>
                </div>

                <p className="measure-reason">{f?.reason_text ?? 'Feasibility not reported.'}</p>
                {f && f.missing_inputs.length > 0 && <p className="xsmall measure-missing">Missing: {f.missing_inputs.map(humanise).join(', ')}</p>}

                {state !== 'infeasible' && (
                  <dl className="measure-nums">
                    <div>
                      <dt>In this plan{step >= 0 ? ` · step ${step + 1}` : ''}</dt>
                      <dd>
                        {row && applied.has(m) ? (
                          row.status === 'ok' ? (
                            <>
                              <span className="num">Gas {fmtSigned(row.gas_saving_kwh, 'kWh')}</span>
                              <span className="num">Elec {fmtSigned(row.elec_saving_kwh, 'kWh')}</span>
                              {savingDirection(row.elec_saving_kwh) === 'increase' && <DirectionTag direction="increase" label="electricity up" />}
                            </>
                          ) : <span className="v-unknown">{missingText(row.status)}: {reasonText(row.reason_code)}</span>
                        ) : <span className="muted">Not in the confirmed plan</span>}
                      </dd>
                    </div>
                    <div>
                      <dt>On its own</dt>
                      <dd>
                        {alone && alone.status === 'ok'
                          ? <span className="num">{fmtKg(alone.carbon_saving_kg)} saved</span>
                          : <span className="v-unknown">{alone ? `${missingText(alone.status)}${alone.reason_code ? `: ${reasonText(alone.reason_code)}` : ''}` : 'Not estimated'}</span>}
                      </dd>
                    </div>
                    <div>
                      <dt>Indicative cost</dt>
                      <dd>
                        {alone && alone.cost_gbp != null
                          ? <span className="num v-estimated" title={alone.cost_provenance}>{fmtGbp(alone.cost_gbp)}</span>
                          : <span className="v-unknown">Not available</span>}
                      </dd>
                    </div>
                  </dl>
                )}

                <div className="measure-foot">
                  {c && (
                    <span className="xsmall muted">
                      Impact basis: {humanise(c.impact_basis ?? row?.impact_basis ?? '')} ·{' '}
                      {c.validated ? 'NEED measured saving' : 'not validated against NEED'}
                    </span>
                  )}
                  {deps.length > 0 && <span className="xsmall muted">Works best after: {deps.map((d) => MEASURE_SHORT[d as MeasureId] ?? d).join(', ')}</span>}
                  <span className="spacer" />
                  <WhyButton build={() => measureEvidence(r, m)} />
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
