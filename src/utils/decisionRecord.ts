/**
 * Versioned decision record (concept doc §17): what was recommended, from which facts and assumptions,
 * what is still unknown. Built only from the confirmed engine result plus the user's optional situation.
 */
import type { MeasureId, ScenarioResult } from '../api/schema';
import type { Situation } from '../hooks/useSituation';
import { permissionFor } from './permissions';
import { packageIdFor } from './labels';

export function buildDecisionRecord(r: ScenarioResult, situation: Situation) {
  const pkg = r.packages?.packages.find((p) => p.package_id === packageIdFor(r.measures_applied));
  return {
    record_version: 'decision-record-v1',
    created_at: new Date().toISOString(),
    scenario_id: r.scenario_id,
    data_timestamp: r.data_timestamp,
    versions: r.versions,
    property: { home_id: r.home.home_id, display_label: r.home.display_label, postcode_outward: r.home.postcode_outward, epc_rating: r.home.rating },
    situation_user_provided: situation,
    request: r.request,
    baseline: r.baseline,
    selected_measures: r.measures_applied,
    feasibility: r.feasibility.map((f) => ({
      measure: f.measure, state: f.state, reason: f.reason_text, missing_inputs: f.missing_inputs,
      permission_guidance: permissionFor(f.measure as MeasureId, f, situation.role, r.home).label,
    })),
    outcomes_estimated: {
      score_before: r.score_before.total, score_after: r.score_after?.total ?? null,
      gas_saving_kwh: r.simulation.gas_saving_kwh, elec_saving_kwh: r.simulation.elec_saving_kwh,
      carbon_saving_kg: r.carbon.total_kg, indicative_cost_gbp: pkg?.cost_gbp ?? null,
      cost_provenance: pkg?.cost_provenance ?? null,
    },
    featured_packages: r.packages?.featured ?? [],
    sensitivity: r.sensitivity ? { label: r.sensitivity.label, survival: r.sensitivity.survival, untested: r.sensitivity.untested } : null,
    unknowns: r.audit.unknowns,
    warnings: r.warnings,
    not_modelled: ['energy bills and payback in £', 'climate hazards (flood, heat)', 'legal permissions', 'maintenance and replacement costs'],
  };
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
