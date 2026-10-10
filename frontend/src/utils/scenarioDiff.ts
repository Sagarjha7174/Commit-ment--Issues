/**
 * What changed between two confirmed scenarios. Pairs of engine values (before → after) and set
 * differences only; no new quantity is computed here.
 */
import type { MeasureId, Objective, PackageResult, ScenarioResult } from '../api/schema';
import { describeChange, draftOf } from '../hooks/useScenarioLab';
import { packageIdFor } from './labels';

export interface DiffRow {
  key: string;
  label: string;
  before: number | null;
  after: number | null;
  unit: 'kwh' | 'kg' | 'gbp' | 'pct' | 'score';
  /** "saving" rows: engine saving values, positive = reduction. "level" rows: absolute levels. */
  kind: 'saving' | 'level';
  status?: [string | null, string | null];
}

export interface ScenarioDiff {
  fromId: string;
  toId: string;
  changes: string[];
  added: MeasureId[];
  removed: MeasureId[];
  rows: DiffRow[];
  featured: { objective: Objective; label: string; before: string | null; after: string | null; changed: boolean }[];
  baselineSource: [string, string];
}

/** The engine's own estimate for exactly the selected measures (lookup by package id, no arithmetic). */
export function selectionPackage(r: ScenarioResult): PackageResult | undefined {
  return r.packages?.packages.find((p) => p.package_id === packageIdFor(r.measures_applied));
}

export function diffScenarios(prev: ScenarioResult, curr: ScenarioResult): ScenarioDiff {
  const a = new Set(prev.measures_applied);
  const b = new Set(curr.measures_applied);
  const pp = selectionPackage(prev);
  const cp = selectionPackage(curr);
  const rows: DiffRow[] = [
    { key: 'gas', label: 'Gas saving', before: prev.simulation.gas_saving_kwh, after: curr.simulation.gas_saving_kwh, unit: 'kwh', kind: 'saving' },
    { key: 'elec', label: 'Electricity saving', before: prev.simulation.elec_saving_kwh, after: curr.simulation.elec_saving_kwh, unit: 'kwh', kind: 'saving' },
    { key: 'carbon', label: 'Carbon saving', before: prev.carbon.total_kg, after: curr.carbon.total_kg, unit: 'kg', kind: 'saving' },
    { key: 'emissions', label: 'Emissions after', before: prev.carbon.after_kg, after: curr.carbon.after_kg, unit: 'kg', kind: 'level' },
    { key: 'potential', label: 'Improvement potential', before: prev.simulation.improvement_potential_pct, after: curr.simulation.improvement_potential_pct, unit: 'pct', kind: 'level',
      status: [prev.simulation.improvement_potential_status, curr.simulation.improvement_potential_status] },
    { key: 'score', label: 'Score after retrofit', before: prev.score_after?.total ?? null, after: curr.score_after?.total ?? null, unit: 'score', kind: 'level' },
    { key: 'cost', label: 'Selection cost', before: pp?.cost_gbp ?? null, after: cp?.cost_gbp ?? null, unit: 'gbp', kind: 'level' },
    { key: 'net_cost', label: 'Cost after grants', before: prev.finance?.net_cost_gbp ?? null, after: curr.finance?.net_cost_gbp ?? null, unit: 'gbp', kind: 'level' },
    { key: 'bill', label: 'Bill saving a year', before: prev.bills?.saving_gbp ?? null, after: curr.bills?.saving_gbp ?? null, unit: 'gbp', kind: 'saving',
      status: [prev.bills?.status ?? 'not_estimated', curr.bills?.status ?? 'not_estimated'] },
  ];
  const featured = (curr.packages?.featured ?? []).map((f) => {
    const before = prev.packages?.featured.find((x) => x.objective === f.objective)?.package_id ?? null;
    return { objective: f.objective, label: f.label, before, after: f.package_id, changed: before !== f.package_id };
  });
  return {
    fromId: prev.scenario_id,
    toId: curr.scenario_id,
    changes: describeChange(draftOf(prev), draftOf(curr), prev.measures_applied),
    added: curr.measures_applied.filter((m) => !a.has(m)),
    removed: prev.measures_applied.filter((m) => !b.has(m)),
    rows,
    featured,
    baselineSource: [prev.baseline.source, curr.baseline.source],
  };
}
