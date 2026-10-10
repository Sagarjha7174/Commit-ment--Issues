import type { MeasureId, Objective, Provenance } from '../api/schema';

export const MEASURE_LABEL: Record<MeasureId, string> = {
  loft_insulation: 'Loft insulation',
  cavity_wall: 'Cavity-wall insulation',
  solid_wall: 'Solid-wall insulation',
  double_glazing: 'Double glazing',
  smart_thermostat: 'Smart thermostat',
  heat_pump: 'Air-source heat pump',
  solar_pv: 'Solar PV',
};

export const MEASURE_SHORT: Record<MeasureId, string> = {
  loft_insulation: 'Loft',
  cavity_wall: 'Cavity wall',
  solid_wall: 'Solid wall',
  double_glazing: 'Glazing',
  smart_thermostat: 'Thermostat',
  heat_pump: 'Heat pump',
  solar_pv: 'Solar PV',
};

export function measureLabel(id: string): string {
  return MEASURE_LABEL[id as MeasureId] ?? id.replace(/_/g, ' ');
}

/** Engine package ids are sorted measure ids joined by "+", or "none". */
export function packageMeasures(packageId: string | null | undefined): string[] {
  if (!packageId || packageId === 'none') return [];
  return packageId.split('+');
}

export function packageIdFor(measures: readonly string[]): string {
  return measures.length ? [...measures].sort().join('+') : 'none';
}

export function packageName(packageId: string | null | undefined): string {
  const ms = packageMeasures(packageId);
  return ms.length ? ms.map(measureLabel).join(' + ') : 'No measures';
}

/** Three tiers that run through the whole UI: what the system knows, estimates, or does not know. */
export type Knowledge = 'known' | 'estimated' | 'unknown';

export const PROVENANCE_INFO: Record<Provenance, { label: string; tier: Knowledge; text: string }> = {
  observed: { label: 'Observed', tier: 'known', text: 'Recorded on the EPC certificate or in the source data.' },
  user_provided: { label: 'Your reading', tier: 'known', text: 'Supplied by the homeowner (meter reading).' },
  population_benchmark: { label: 'Benchmark', tier: 'estimated', text: 'NEED median for similar homes in the region, not this home’s meter.' },
  modelled: { label: 'Modelled', tier: 'estimated', text: 'Predicted by a trained model.' },
  assumption: { label: 'Assumption', tier: 'estimated', text: 'Documented assumption or proxy from the catalogue.' },
  derived: { label: 'Derived', tier: 'estimated', text: 'Computed by the engine from other values, so it inherits their uncertainty.' },
  unavailable: { label: 'Unavailable', tier: 'unknown', text: 'Missing from the data; kept as unknown, never filled with 0.' },
  not_applicable: { label: 'Not applicable', tier: 'unknown', text: 'Does not apply to this home (e.g. no roof for a flat with a dwelling above).' },
};

export const KNOWLEDGE_TEXT: Record<Knowledge, { label: string; text: string }> = {
  known: { label: 'Known', text: 'Observed on the EPC or provided by you.' },
  estimated: { label: 'Estimated', text: 'Benchmark, model, assumption or engine calculation.' },
  unknown: { label: 'Unknown', text: 'Missing or not applicable. Never shown as zero.' },
};

export const SCORE_PART_LABEL: Record<string, string> = {
  energy_efficiency: 'EPC energy efficiency',
  energy_intensity: 'Energy use per m²',
  insulation: 'Insulation',
  heating: 'Heating system',
  windows: 'Windows & glazing',
  renewables: 'Renewables',
  smart_controls: 'Smart controls',
};

export const OBJECTIVE_SHORT: Record<Objective, { kicker: string; question: string; metric: string }> = {
  lowest_cost_meeting_threshold: { kicker: 'Lowest cost', question: 'What is the cheapest plan that still clears the carbon bar?', metric: 'cost' },
  largest_carbon_saving: { kicker: 'Largest cut', question: 'What cuts the most carbon, whatever it costs?', metric: 'carbon' },
  best_carbon_per_pound: { kicker: 'Carbon per pound', question: 'Where does each pound save the most carbon?', metric: 'carbon_per_pound' },
};

export const SENSITIVITY_RUN_LABEL: Record<string, string> = {
  baseline_minus_15pct: 'Baseline energy −15%',
  baseline_plus_15pct: 'Baseline energy +15%',
  scop_low: 'Heat-pump SCOP 2.5',
  scop_high: 'Heat-pump SCOP 3.5',
  gas_split_65_35: 'Space/water gas split 65/35',
  gas_split_85_15: 'Space/water gas split 85/15',
  other_gas_low: 'Cooking gas share halved',
  other_gas_high: 'Cooking gas share doubled',
  impacts_low: 'Measure impacts at catalogue low',
  impacts_high: 'Measure impacts at catalogue high',
};

export const HEATING_LABEL: Record<string, string> = {
  gas_boiler: 'Gas boiler',
  electric: 'Electric heating',
  heat_pump: 'Heat pump',
  oil_boiler: 'Oil boiler',
  lpg_boiler: 'LPG boiler',
  solid_fuel: 'Solid fuel',
  community: 'Community heating',
};

export const CONTROLS_LABEL: Record<string, string> = {
  none: 'No controls',
  timer: 'Timer only',
  full: 'Programmer, room stat & TRVs',
  smart: 'Time & temperature zone control',
};

const REASON_TEXT: Record<string, string> = {
  heating_not_on_gas: 'The heating is not gas-fired, so the engine’s gas-based impact does not apply.',
  no_gas_to_displace: 'There is no gas heating for a heat pump to replace.',
  baseline_gas_unavailable: 'The gas baseline is unknown, so no saving can be estimated.',
  baseline_elec_unavailable: 'The electricity baseline is unknown, so no saving can be estimated.',
};

export function reasonText(code: string | null | undefined): string {
  if (!code) return '';
  return REASON_TEXT[code] ?? code.replace(/_/g, ' ');
}

export function tierOf(p: string | null | undefined): Knowledge {
  if (!p) return 'unknown';
  return PROVENANCE_INFO[p as Provenance]?.tier ?? 'estimated';
}

const MEASURE_ID_RE = /\b(loft_insulation|cavity_wall|solid_wall|double_glazing|smart_thermostat|heat_pump|solar_pv)\b/g;

/** Replace raw measure ids inside engine-written text with their labels (display only). */
export function prettyText(s: string): string {
  const out = s.replace(MEASURE_ID_RE, (m) => MEASURE_LABEL[m as MeasureId]);
  return out.charAt(0).toUpperCase() + out.slice(1);
}
