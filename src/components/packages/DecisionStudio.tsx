import type { ReactNode } from 'react';
import { AlertTriangle, ArrowDownToLine, Check, ShieldCheck, ShieldAlert } from 'lucide-react';
import type { MeasureId, Objective, PackageResult, ScenarioResult } from '../../api/schema';
import { barPct, fmtGbp, fmtKg, fmtKwh, fmtNumber, fmtPct, fmtSigned, savingDirection } from '../../utils/format';
import { MEASURE_SHORT, OBJECTIVE_SHORT, packageIdFor, prettyText } from '../../utils/labels';
import { costEvidence } from '../../utils/evidence';
import { DirectionTag } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';
import { EmptyState, SectionHeader } from '../common/States';
import { PackageMatrix } from './PackageMatrix';
import './studio.css';

interface Props {
  result: ScenarioResult;
  selectedObjective: Objective;
  onSelectObjective(o: Objective): void;
  onApply(measures: readonly MeasureId[]): void;
  currentSelection: readonly string[];
}

function Ring({ k, n }: { k: number; n: number }) {
  const pct = n ? k / n : 0;
  const c = 2 * Math.PI * 16;
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" className="ring" aria-hidden="true">
      <circle cx="22" cy="22" r="16" className="ring-bg" />
      <circle cx="22" cy="22" r="16" className="ring-fg" strokeDasharray={`${c * pct} ${c}`} transform="rotate(-90 22 22)" />
      <text x="22" y="26" textAnchor="middle">{k}/{n}</text>
    </svg>
  );
}

function parseSurvives(s: string | undefined): [number, number] | null {
  const m = s?.match(/^(\d+)\/(\d+)$/);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

function Metric({ label, value, pct, tone, extra }: { label: string; value: string; pct: number; tone: string; extra?: ReactNode }) {
  return (
    <div className="metric">
      <div className="metric-head"><span>{label}</span><b className="num">{value}</b></div>
      <div className={`bar ${tone}`}><span style={{ width: `${pct}%` }} /></div>
      {extra}
    </div>
  );
}

export function DecisionStudio({ result: r, selectedObjective, onSelectObjective, onApply, currentSelection }: Props) {
  const ps = r.packages;
  if (!ps) {
    return (
      <section className="section" id="studio" aria-labelledby="studio-title">
        <div className="page"><EmptyState title="Package search not included in this scenario" /></div>
      </section>
    );
  }
  const byId = new Map(ps.packages.map((p) => [p.package_id, p]));
  const picks = ps.featured.map((f) => ({ f, p: f.package_id ? byId.get(f.package_id) : undefined }));
  const shown = picks.map((x) => x.p).filter((p): p is PackageResult => !!p);
  const maxCarbon = Math.max(0, ...shown.map((p) => Math.abs(p.carbon_saving_kg ?? 0)));
  const maxCost = Math.max(0, ...shown.map((p) => p.cost_gbp ?? 0));
  const maxGas = Math.max(0, ...shown.map((p) => Math.abs(p.gas_saving_kwh ?? 0)));
  const maxElec = Math.max(0, ...shown.map((p) => Math.abs(p.elec_saving_kwh ?? 0)));
  const auditFeatured = new Map((r.audit.featured ?? []).map((a) => [a.objective, a]));
  const currentId = packageIdFor(currentSelection);
  const confirmedId = packageIdFor(r.measures_applied);

  return (
    <section className="section studio" id="studio" aria-labelledby="studio-title">
      <div className="page">
        <SectionHeader
          index="05" kicker="Retrofit Decision Studio" id="studio-title" title="Three plans. Three different trade-offs."
          lead={<>The engine searched <b>{fmtNumber(ps.packages.length)}</b> feasible combinations and kept three, each for a different objective. None is “best overall”: pick the trade-off that matches what you care about. Threshold: at least {fmtNumber(ps.threshold_pct)}% of baseline emissions.</>}
        />
        {ps.fallbacks.length > 0 && (
          <p className="callout callout-verify" role="note"><AlertTriangle size={16} aria-hidden="true" />{ps.fallbacks.join(' · ')}</p>
        )}

        <div className="studio-cols" role="list">
          {picks.map(({ f, p }, idx) => {
            const meta = OBJECTIVE_SHORT[f.objective];
            const surv = r.sensitivity?.survival[f.objective];
            const sv = parseSurvives(surv?.survives);
            const same = picks.findIndex((x) => x.f.package_id && x.f.package_id === f.package_id);
            const isActive = selectedObjective === f.objective;
            const isLoaded = p && p.package_id === confirmedId;
            const isDraft = p && p.package_id === currentId && !isLoaded;
            const elecDir = savingDirection(p?.elec_saving_kwh);
            return (
              <article
                key={f.objective}
                role="listitem"
                className={`plan ${isActive ? 'is-active' : ''} ${p ? '' : 'plan-empty'}`}
                aria-labelledby={`plan-${f.objective}`}
                onFocusCapture={() => onSelectObjective(f.objective)}
                onMouseEnter={() => onSelectObjective(f.objective)}
              >
                <header className="plan-head">
                  <span className="plan-letter serif" aria-hidden="true">{String.fromCharCode(65 + idx)}</span>
                  <div>
                    <p className="kicker">{meta.kicker}</p>
                    <h3 id={`plan-${f.objective}`}>{f.label}</h3>
                    <p className="small muted">{meta.question}</p>
                  </div>
                </header>

                {!p ? (
                  <div className="plan-body">
                    <p className="v-unknown">{f.message ?? 'No package qualifies for this objective.'}</p>
                    {f.alternatives.length > 0 && <p className="small">Alternatives: {f.alternatives.join(', ')}</p>}
                  </div>
                ) : (
                  <div className="plan-body">
                    <ul className="plan-measures" aria-label="Measures in this plan">
                      {p.measures.length ? p.measures.map((m) => <li key={m} className="chip">{MEASURE_SHORT[m]}</li>) : <li className="chip">No measures</li>}
                    </ul>
                    {same !== idx && same >= 0 && <p className="xsmall chip chip-gold">Same plan as {String.fromCharCode(65 + same)}</p>}

                    <p className="plan-hero serif num">{fmtKg(p.carbon_saving_kg, p.status)}</p>
                    <p className="small muted">carbon saved per year{p.carbon_saving_pct != null && <> · {fmtPct(p.carbon_saving_pct, 1)} of baseline</>}</p>

                    <div className="metrics">
                      <Metric label="Carbon saving" value={fmtKg(p.carbon_saving_kg)} pct={barPct(p.carbon_saving_kg, maxCarbon)} tone="bar-saving" />
                      <Metric label="Indicative cost" value={fmtGbp(p.cost_gbp, p.cost_status)} pct={barPct(p.cost_gbp, maxCost)} tone="bar-cost"
                        extra={!p.eligible_for_cost_comparison && <span className="xsmall muted">Excluded from cost rankings</span>} />
                      <Metric label="Gas saving" value={fmtKwh(p.gas_saving_kwh, p.status)} pct={barPct(p.gas_saving_kwh, maxGas)} tone="bar-gold" />
                      <Metric label="Electricity saving" value={fmtSigned(p.elec_saving_kwh, 'kWh/yr', p.status)} pct={barPct(p.elec_saving_kwh, maxElec)}
                        tone={elecDir === 'increase' ? 'bar-increase' : 'bar-saving'}
                        extra={elecDir !== 'unknown' && elecDir !== 'none' && <DirectionTag direction={elecDir} label={elecDir === 'increase' ? 'electricity use rises' : 'electricity use falls'} />} />
                    </div>

                    <dl className="plan-facts">
                      <div><dt>Purchased energy saving</dt><dd className="num">{fmtSigned(p.purchased_saving_kwh, 'kWh/yr', p.status)}</dd></div>
                      <div><dt>Carbon per £</dt><dd className="num">{p.carbon_per_pound_kg != null ? `${p.carbon_per_pound_kg.toFixed(3)} kg CO₂e per £` : 'Not estimated'}</dd></div>
                    </dl>

                    <div className="plan-why">
                      <p className="kicker">Why it qualifies</p>
                      <p className="small">{auditFeatured.get(f.objective)?.objective_text ?? f.label}.</p>
                    </div>

                    {!p.confirmed && (
                      <p className="plan-flag plan-flag-verify"><ShieldAlert size={14} aria-hidden="true" /> Conditional: verify {p.must_verify.join('; ')}</p>
                    )}
                    {p.unvalidated_impacts.length > 0 && (
                      <p className="plan-flag"><AlertTriangle size={14} aria-hidden="true" /> Not validated against NEED: {p.unvalidated_impacts.map((m) => MEASURE_SHORT[m as MeasureId] ?? m).join(', ')}</p>
                    )}

                    {sv && (
                      <div className="plan-stability">
                        <Ring k={sv[0]} n={sv[1]} />
                        <div>
                          <p className="small"><b>{sv[0] === sv[1] ? 'Stable' : 'Can change'}</b> in {surv!.survives} sensitivity runs</p>
                          {surv!.changed_under.length > 0 && <p className="xsmall muted">Flips under: {surv!.changed_under.join(', ').replace(/_/g, ' ')}</p>}
                        </div>
                        {sv[0] === sv[1] ? <ShieldCheck size={16} className="ok" aria-hidden="true" /> : <ShieldAlert size={16} className="warn" aria-hidden="true" />}
                      </div>
                    )}

                    <div className="plan-actions">
                      {isLoaded ? (
                        <span className="chip chip-saving"><Check size={12} aria-hidden="true" /> This is the confirmed scenario</span>
                      ) : (
                        <button className="btn btn-sm" onClick={() => { onSelectObjective(f.objective); onApply(p.measures); }} disabled={!!isDraft}>
                          <ArrowDownToLine size={14} aria-hidden="true" /> {isDraft ? 'Recalculating…' : 'Load into the lab'}
                        </button>
                      )}
                      <WhyButton build={() => costEvidence(r, p, `${meta.kicker}: indicative cost`)} label="Cost basis" />
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>

        {r.audit.main_factors && r.audit.main_factors.length > 0 && (
          <div className="tradeoff panel">
            <p className="kicker">How the plans differ (from the decision audit)</p>
            <ul>{r.audit.main_factors.map((x) => <li key={x}>{prettyText(x)}</li>)}</ul>
          </div>
        )}

        <PackageMatrix result={r} onApply={onApply} currentId={confirmedId} />
      </div>
    </section>
  );
}
