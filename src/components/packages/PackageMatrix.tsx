import { lazy, Suspense, useMemo, useState } from 'react';
import type { MeasureId, PackageResult, ScenarioResult } from '../../api/schema';
import { barPct, fmtGbp, fmtKg, fmtPct, fmtSigned, savingDirection } from '../../utils/format';
import { MEASURE_SHORT, OBJECTIVE_SHORT } from '../../utils/labels';
import { Skeleton } from '../common/States';

const ParetoChart = lazy(() => import('./ParetoChart'));

type Sort = 'cost' | 'carbon' | 'per_pound';

export function PackageMatrix({ result: r, onApply, currentId }: { result: ScenarioResult; onApply(m: readonly MeasureId[]): void; currentId: string }) {
  const [showDominated, setShowDominated] = useState(false);
  const [sort, setSort] = useState<Sort>('cost');
  const [limit, setLimit] = useState(12);
  const ps = r.packages!;
  const featuredBy = useMemo(() => {
    const m = new Map<string, string[]>();
    ps.featured.forEach((f) => f.package_id && m.set(f.package_id, [...(m.get(f.package_id) ?? []), OBJECTIVE_SHORT[f.objective].kicker]));
    return m;
  }, [ps]);
  const estimable = ps.packages.filter((p) => p.status === 'ok' && p.measures.length > 0);
  const dominatedCount = estimable.filter((p) => p.dominated).length;
  const rows = estimable
    .filter((p) => showDominated || !p.dominated)
    .sort((a, b) => {
      const key = (p: PackageResult) => (sort === 'cost' ? p.cost_gbp ?? Infinity : sort === 'carbon' ? -(p.carbon_saving_kg ?? -Infinity) : -(p.carbon_per_pound_kg ?? -Infinity));
      return key(a) - key(b) || a.package_id.localeCompare(b.package_id);
    });
  const maxCost = Math.max(0, ...rows.map((p) => p.cost_gbp ?? 0));
  const maxCarbon = Math.max(0, ...rows.map((p) => Math.abs(p.carbon_saving_kg ?? 0)));

  if (estimable.length === 0) return null;

  return (
    <div className="matrix">
      <div className="matrix-head">
        <div>
          <p className="kicker">Every package the engine searched</p>
          <h3 className="serif matrix-title">The frontier behind the three picks</h3>
          <p className="small muted">{estimable.length - dominatedCount} Pareto-efficient packages (no other package is cheaper <i>and</i> saves more carbon), {dominatedCount} dominated.</p>
        </div>
        <Suspense fallback={<Skeleton h={240} />}>
          <ParetoChart packages={estimable} featured={featuredBy} currentId={currentId} onPick={(p) => onApply(p.measures)} />
        </Suspense>
      </div>
      <div className="row matrix-controls">
        <div className="seg" role="group" aria-label="Sort packages">
          {(['cost', 'carbon', 'per_pound'] as Sort[]).map((s) => (
            <button key={s} aria-pressed={sort === s} onClick={() => setSort(s)}>{s === 'cost' ? 'Cheapest first' : s === 'carbon' ? 'Most carbon' : 'Carbon per £'}</button>
          ))}
        </div>
        <label className="row small"><input type="checkbox" checked={showDominated} onChange={(e) => setShowDominated(e.target.checked)} /> Show dominated ({dominatedCount})</label>
      </div>
      <div className="table-wrap">
        <table className="data-table matrix-table">
          <caption className="sr-only">Packages with cost, carbon saving, electricity change and status</caption>
          <thead>
            <tr>
              <th scope="col">Package</th>
              <th scope="col">Cost</th>
              <th scope="col">Carbon saving</th>
              <th scope="col" className="num">Elec. saving</th>
              <th scope="col">Status</th>
              <th scope="col"><span className="sr-only">Action</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((p) => {
              const tags = featuredBy.get(p.package_id);
              const elecDir = savingDirection(p.elec_saving_kwh);
              return (
                <tr key={p.package_id} className={p.package_id === currentId ? 'is-current' : p.dominated ? 'is-dominated' : ''}>
                  <th scope="row">
                    <div className="matrix-measures">{p.measures.map((m) => <span key={m} className="chip">{MEASURE_SHORT[m]}</span>)}</div>
                    {tags && <div className="matrix-tags">{tags.map((t) => <span key={t} className="chip chip-gold">★ {t}</span>)}</div>}
                  </th>
                  <td><span className="num">{fmtGbp(p.cost_gbp, p.cost_status)}</span><div className="bar bar-cost"><span style={{ width: `${barPct(p.cost_gbp, maxCost)}%` }} /></div></td>
                  <td><span className="num">{fmtKg(p.carbon_saving_kg)}</span> <span className="xsmall muted">{fmtPct(p.carbon_saving_pct)}</span><div className="bar bar-saving"><span style={{ width: `${barPct(p.carbon_saving_kg, maxCarbon)}%` }} /></div></td>
                  <td className={`num dir-${elecDir}`}>{fmtSigned(p.elec_saving_kwh, 'kWh')}</td>
                  <td>
                    <div className="matrix-status">
                      {!p.confirmed && <span className="chip chip-verify" title={p.must_verify.join('; ')}>Conditional</span>}
                      {p.dominated && <span className="chip chip-blocked" title={`Dominated by ${p.dominated_by}`}>Dominated</span>}
                      {!p.eligible_for_cost_comparison && <span className="chip chip-blocked">No cost</span>}
                      {p.confirmed && !p.dominated && p.eligible_for_cost_comparison && <span className="chip">Efficient</span>}
                    </div>
                  </td>
                  <td>
                    {p.package_id === currentId
                      ? <span className="xsmall muted">Current</span>
                      : <button className="btn btn-sm btn-ghost" onClick={() => onApply(p.measures)} aria-label={`Load package ${p.measures.join(', ')} into the lab`}>Load</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.length > limit && <button className="btn btn-link small matrix-more" onClick={() => setLimit((l) => l + 24)}>Show more ({rows.length - limit} remaining)</button>}
    </div>
  );
}
