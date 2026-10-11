/** Cost vs carbon saving for every estimable package (engine values). Lazy-loaded: pulls in Recharts. */
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import type { PackageResult } from '../../api/schema';
import { fmtGbp, fmtKg, fmtNumber } from '../../utils/format';
import { packageName } from '../../utils/labels';

interface Point { x: number; y: number; id: string; pkg: PackageResult }

export default function ParetoChart({ packages, featured, currentId, onPick }: {
  packages: PackageResult[]; featured: Map<string, string[]>; currentId: string; onPick(p: PackageResult): void;
}) {
  const pts = (pred: (p: PackageResult) => boolean): Point[] => packages
    .filter((p) => p.cost_gbp != null && p.carbon_saving_kg != null && pred(p))
    .map((p) => ({ x: p.cost_gbp!, y: p.carbon_saving_kg!, id: p.package_id, pkg: p }));
  const dominated = pts((p) => p.dominated && !featured.has(p.package_id));
  const frontier = pts((p) => !p.dominated && !featured.has(p.package_id));
  const feat = pts((p) => featured.has(p.package_id));
  const current = pts((p) => p.package_id === currentId);
  const pick = (d: unknown) => {
    const p = (d as { payload?: Point })?.payload?.pkg;
    if (p) onPick(p);
  };
  return (
    <figure className="pareto">
      <div role="img" aria-label="Scatter of package cost against annual carbon saving. Featured picks are highlighted; the table below lists every package.">
        <ResponsiveContainer width="100%" height={240}>
          <ScatterChart margin={{ top: 10, right: 16, bottom: 18, left: 4 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis type="number" dataKey="x" name="Cost" tickFormatter={(v: number) => `£${fmtNumber(v / 1000)}k`} fontSize={11} stroke="var(--ink-muted)"
              label={{ value: 'Indicative cost', position: 'insideBottom', offset: -10, fontSize: 11, fill: 'var(--ink-muted)' }} />
            <YAxis type="number" dataKey="y" name="Carbon saving" tickFormatter={(v: number) => fmtNumber(v)} fontSize={11} stroke="var(--ink-muted)" width={52}
              label={{ value: 'kg CO₂e/yr', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--ink-muted)' }} />
            <ZAxis range={[40, 40]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              content={({ payload }) => {
                const p = (payload?.[0]?.payload as Point | undefined)?.pkg;
                if (!p) return null;
                return (
                  <div className="pareto-tip">
                    <b>{packageName(p.package_id)}</b>
                    <span>{fmtGbp(p.cost_gbp)} · {fmtKg(p.carbon_saving_kg)}</span>
                    {featured.get(p.package_id)?.map((t) => <span key={t}>★ {t}</span>)}
                    {p.dominated && <span>Dominated</span>}
                    <i>Click to load into the lab</i>
                  </div>
                );
              }}
            />
            <Scatter data={dominated} fill="var(--line-strong)" onClick={pick} isAnimationActive={false} />
            <Scatter data={frontier} fill="var(--ink)" onClick={pick} isAnimationActive={false} line={{ stroke: 'var(--ink-muted)', strokeDasharray: '4 3' }} lineType="joint" />
            <Scatter data={feat} fill="var(--gold)" stroke="var(--ink)" shape="star" onClick={pick} isAnimationActive={false} />
            <Scatter data={current} fill="none" stroke="var(--saving)" strokeWidth={3} shape="circle" isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="xsmall muted pareto-legend">
        <span><i className="dot dot-ink" /> Pareto-efficient</span>
        <span><i className="dot dot-grey" /> Dominated</span>
        <span>★ Featured pick</span>
        <span><i className="dot dot-ring" /> Confirmed scenario</span>
      </figcaption>
    </figure>
  );
}
