import { lazy, Suspense, type ReactNode } from 'react';
import { Flame, Leaf, Zap } from 'lucide-react';
import type { ScenarioResult } from '../../api/schema';
import { fmtGbp, fmtKg, fmtKwh, fmtNumber, fmtPct, fmtSigned, isNum, missingText, savingDirection } from '../../utils/format';
import { carbonEvidence, energyEvidence, valuationEvidence } from '../../utils/evidence';
import { DirectionTag, Val } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';
import { EmptyState, SectionHeader, Skeleton } from '../common/States';
import { MoneyPanel } from './MoneyPanel';
import './energy.css';

const EnergyChart = lazy(() => import('./EnergyChart'));

/** "−3,675 kWh/yr" → large number, small unit. Status text (e.g. "Unavailable") is left whole. */
function NumUnit({ text }: { text: string }) {
  const m = text.match(/^([+−-]?[\d,.]+%?)\s+(.+)$/);
  if (!m) return <>{text}</>;
  return <>{m[1]}<span className="unit">{m[2]}</span></>;
}

function Tile({ icon, title, value, sub, direction, why, tone }: {
  icon: ReactNode; title: string; value: ReactNode; sub?: ReactNode; direction?: ReturnType<typeof savingDirection>; why?: ReactNode; tone?: 'increase' | 'saving';
}) {
  return (
    <div className={`tile ${tone ? `tile-${tone}` : ''}`}>
      <div className="row tile-head">{icon}<span className="kicker">{title}</span><span className="spacer" />{why}</div>
      <p className="tile-value num">{value}</p>
      {direction && direction !== 'unknown' && <DirectionTag direction={direction} />}
      {sub && <div className="small muted">{sub}</div>}
    </div>
  );
}

/** "P10–P90 a to b" from the engine's Monte Carlo, when it ran. */
function Range({ r, k, unit }: { r: ScenarioResult; k: string; unit: string }) {
  const q = r.uncertainty?.status === 'ok' ? r.uncertainty.percentiles[k] : null;
  if (!q || !isNum(q.p10) || !isNum(q.p90)) return null;
  if (Math.abs(q.p90 - q.p10) < 0.5) return null;
  return <span className="tile-range"> · range {fmtNumber(q.p10)} to {fmtNumber(q.p90)} {unit}</span>;
}

export function EnergyBalance({ result: r }: { result: ScenarioResult }) {
  const sim = r.simulation;
  const v = r.valuation;
  const epc = r.score_after?.epc_change;
  const c = r.carbon;
  const st = sim.status;
  const gasDir = savingDirection(sim.gas_saving_kwh);
  const elecDir = savingDirection(sim.elec_saving_kwh);
  const carbonDir = savingDirection(c.total_kg);
  const prov = r.baseline.source === 'user_provided' ? 'user_provided' : 'derived';

  return (
    <section className="section" aria-labelledby="energy-title">
      <div className="page">
        <SectionHeader
          index="03" kicker="Energy & carbon" id="energy-title" title="Gas and electricity, kept apart"
          lead="Savings are before minus after, per fuel. A heat pump lowers gas and raises electricity: that rise is shown as a negative saving, never hidden inside a total."
        />
        {elecDir === 'increase' && (
          <p className="callout callout-increase" role="note">
            <Zap size={16} aria-hidden="true" /> Electricity use <b>rises</b> in this scenario ({fmtKwh(sim.elec_saving_kwh)} saving), because heating moves from gas to a heat pump. Carbon still {carbonDir === 'reduction' ? 'falls' : carbonDir === 'increase' ? 'rises' : 'changes'} overall.
          </p>
        )}
        <div className="tiles">
          <Tile icon={<Flame size={16} aria-hidden="true" />} title="Gas saving" tone={gasDir === 'increase' ? 'increase' : undefined}
            value={<Val provenance={prov}><NumUnit text={fmtSigned(sim.gas_saving_kwh, 'kWh/yr', st)} /></Val>} direction={gasDir}
            sub={<>Baseline {fmtKwh(r.baseline.gas_kwh, r.baseline.gas_status)}{isNum(sim.after?.gas_total) && <> → after {fmtKwh(sim.after!.gas_total)}</>}<Range r={r} k="gas_saving_kwh" unit="kWh" /></>}
            why={<WhyButton build={() => energyEvidence(r, 'gas')} />} />
          <Tile icon={<Zap size={16} aria-hidden="true" />} title="Grid electricity saving" tone={elecDir === 'increase' ? 'increase' : undefined}
            value={<Val provenance={prov}><NumUnit text={fmtSigned(sim.elec_saving_kwh, 'kWh/yr', st)} /></Val>} direction={elecDir}
            sub={<>Baseline {fmtKwh(r.baseline.elec_kwh, r.baseline.elec_status)}{isNum(sim.after?.elec_import) && <> → after {fmtKwh(sim.after!.elec_import)}</>}<Range r={r} k="elec_saving_kwh" unit="kWh" /></>}
            why={<WhyButton build={() => energyEvidence(r, 'elec')} />} />
          <Tile icon={<span className="tile-sym" aria-hidden="true">Σ</span>} title="Purchased energy"
            value={<Val provenance={prov}><NumUnit text={fmtKwh(sim.purchased_after_kwh, st)} /></Val>}
            sub={<>from {fmtKwh(sim.purchased_before_kwh, st)} · saving {fmtSigned(sim.purchased_saving_kwh, 'kWh/yr', st)}</>}
            why={<WhyButton build={() => energyEvidence(r, 'purchased')} />} />
          <Tile icon={<span className="tile-sym" aria-hidden="true">%</span>} title="Improvement potential"
            value={<Val provenance={sim.improvement_potential_pct == null ? 'unavailable' : prov}>{fmtPct(sim.improvement_potential_pct, 1, sim.improvement_potential_status)}</Val>}
            sub={sim.improvement_potential_reason ?? 'Share of purchased energy saved by this selection.'} />
          <Tile icon={<Leaf size={16} aria-hidden="true" />} title="Carbon saving" tone={carbonDir === 'reduction' ? 'saving' : carbonDir === 'increase' ? 'increase' : undefined}
            value={<Val provenance={prov}><NumUnit text={fmtSigned(c.total_kg, 'kg CO₂e/yr', c.status)} /></Val>} direction={carbonDir}
            sub={<>{fmtKg(c.before_kg, c.status)} → {fmtKg(c.after_kg, c.status)}{c.saving_pct_of_baseline != null && <> · {fmtPct(c.saving_pct_of_baseline, 1)} of baseline</>}<Range r={r} k="carbon_saving_kg" unit="kg" /></>}
            why={<WhyButton build={() => carbonEvidence(r)} />} />
          <Tile icon={<Leaf size={16} aria-hidden="true" />} title="Carbon by fuel"
            value={<span className="tile-split"><span>Gas {fmtSigned(c.gas_kg, 'kg', c.status)}</span><span>Elec {fmtSigned(c.elec_kg, 'kg', c.status)}</span></span>}
            sub="Positive = emissions fell. DESNZ 2026 factors." />
          <Tile icon={<span className="tile-sym" aria-hidden="true">£</span>} title="Property value"
            value={<Val tier={v.status === 'ok' ? 'estimated' : 'unknown'}>{v.status === 'ok' ? `+${fmtPct(v.low_pct, 1)} – ${fmtPct(v.high_pct, 1)}` : missingText(v.status)}</Val>}
            sub={v.status === 'ok'
              ? <>Indicative range of the value change, an association in York sales, not a promise.{isNum(v.potential_value_low_gbp) && isNum(v.potential_value_high_gbp) && <> About {fmtGbp(v.potential_value_low_gbp)} to {fmtGbp(v.potential_value_high_gbp)} after, from a modelled {fmtGbp(v.current_value_gbp)} today.</>}</>
              : v.reason}
            why={<WhyButton build={() => valuationEvidence(r)} />} />
          {epc && epc.status === 'ok' && (
            <Tile icon={<span className="tile-sym" aria-hidden="true">E</span>} title="Indicative EPC after"
              value={<Val provenance="modelled">{epc.rating_before ?? '?'} → {epc.rating_after_indicative ?? '?'}</Val>}
              sub={<>SAP {fmtNumber(epc.sap_before)} → about {fmtNumber(epc.sap_after_indicative)}. Modelled from York certificates, not an EPC re-assessment.</>} />
          )}
        </div>

        <MoneyPanel result={r} />

        <div className="panel energy-chart-panel">
          <div className="row"><p className="kicker">Purchased energy by end use</p><span className="spacer" /><span className="xsmall muted">kWh per year · engine end-use split</span></div>
          {sim.before && sim.after ? (
            <Suspense fallback={<Skeleton h={220} />}>
              <EnergyChart before={sim.before} after={sim.after} />
            </Suspense>
          ) : (
            <EmptyState title={`Energy breakdown ${missingText(st).toLowerCase()}`}>
              {r.baseline.note || sim.reason_code}. The engine does not estimate end-use energy without a baseline; nothing is filled with zero.
            </EmptyState>
          )}
        </div>
      </div>
    </section>
  );
}
