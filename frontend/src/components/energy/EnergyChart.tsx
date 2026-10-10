/** Purchased energy by end use, today vs after the scenario (engine EndUses). Lazy-loaded: pulls in Recharts. */
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { EndUses } from '../../api/schema';
import { fmtKwh, fmtNumber } from '../../utils/format';

const SERIES: { key: keyof EndUses; label: string; color: string }[] = [
  { key: 'gas_space', label: 'Gas · space heating', color: 'var(--gas)' },
  { key: 'gas_water', label: 'Gas · hot water', color: 'var(--gas-2)' },
  { key: 'gas_other', label: 'Gas · cooking & other', color: 'var(--gas-3)' },
  { key: 'elec_base', label: 'Electricity · base use', color: 'var(--elec)' },
  { key: 'hp_elec', label: 'Electricity · heat pump', color: 'var(--elec-2)' },
  { key: 'pv_offset', label: 'Solar PV · grid import avoided', color: 'var(--pv)' },
];

export default function EnergyChart({ before, after }: { before: EndUses; after: EndUses }) {
  // PV offset reduces grid import, so it is drawn left of zero (presentational sign for the chart only).
  const row = (name: string, e: EndUses) => ({ name, ...e, pv_offset: e.pv_offset ? -e.pv_offset : 0 });
  const data = [row('Today', before), row('After', after)];
  return (
    <figure className="energy-chart">
      <div role="img" aria-label="Stacked bars of annual purchased energy by end use, today and after the scenario. Exact values in the table below.">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} layout="vertical" stackOffset="sign" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid horizontal={false} stroke="var(--line)" />
            <XAxis type="number" tickFormatter={(v: number) => fmtNumber(v)} stroke="var(--ink-muted)" fontSize={11} label={{ value: 'kWh per year', position: 'insideBottomRight', offset: -4, fontSize: 11, fill: 'var(--ink-muted)' }} />
            <YAxis type="category" dataKey="name" width={52} stroke="var(--ink-muted)" fontSize={12} />
            <ReferenceLine x={0} stroke="var(--ink)" />
            <Tooltip
              formatter={(v, name) => [fmtKwh(Math.abs(Number(v))), String(name)]}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: 6, fontSize: 12 }}
              cursor={{ fill: 'var(--surface-sunk)' }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" formatter={(v) => <span style={{ color: 'var(--ink-2)' }}>{v}</span>} />
            {SERIES.map((s) => <Bar key={s.key} dataKey={s.key} name={s.label} stackId="e" fill={s.color} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="sr-only"><table>
        <caption>Annual purchased energy by end use (kWh/yr)</caption>
        <thead><tr><th>End use</th><th>Today</th><th>After</th></tr></thead>
        <tbody>
          {SERIES.map((s) => <tr key={s.key}><th>{s.label}</th><td>{fmtKwh(before[s.key])}</td><td>{fmtKwh(after[s.key])}</td></tr>)}
        </tbody>
      </table></div>
    </figure>
  );
}
