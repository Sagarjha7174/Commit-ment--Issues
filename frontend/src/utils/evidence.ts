/**
 * "Why this number?" entries, assembled from fields of one scenario result.
 * Nothing is invented: when the engine does not supply a piece of evidence, the entry says so.
 */
import type { MeasureId, PackageResult, ScenarioResult } from '../api/schema';
import { fmtGbp, fmtKg, fmtKwh, fmtNumber, fmtPct, humanise, isNum, missingText, savingDirection, type Direction } from './format';
import { measureLabel, PROVENANCE_INFO, SCORE_PART_LABEL } from './labels';

export interface EvidenceInput { label: string; value: string; provenance?: string | null }

export interface EvidenceEntry {
  title: string;
  value: string;
  direction?: Direction;
  summary?: string;
  inputs: EvidenceInput[];
  method?: string;
  assumptions: string[];
  missing: string[];
  validation: string;
  limitations: string[];
  sources: string[];
  versions: Record<string, string>;
  scenarioId: string;
  dataTimestamp: string;
}

function base(r: ScenarioResult): Pick<EvidenceEntry, 'versions' | 'scenarioId' | 'dataTimestamp'> {
  return { versions: r.versions, scenarioId: r.scenario_id, dataTimestamp: r.data_timestamp };
}

function baselineInputs(r: ScenarioResult): EvidenceInput[] {
  const b = r.baseline;
  return [
    { label: 'Baseline gas', value: fmtKwh(b.gas_kwh, b.gas_status), provenance: b.gas_provenance },
    { label: 'Baseline electricity', value: fmtKwh(b.elec_kwh, b.elec_status), provenance: b.elec_provenance },
    { label: 'Baseline source', value: humanise(b.source) },
  ];
}

function emissionSources(r: ScenarioResult): string[] {
  return Object.entries(r.carbon.factors).map(([fuel, f]) => `${fuel === 'elec' ? 'Electricity' : 'Gas'}: ${f.kg_co2e_per_kwh} ${f.units} (${f.source})`);
}

function assumptionList(r: ScenarioResult): string[] {
  const a = r.assumptions as Record<string, unknown>;
  const out: string[] = [];
  if (a.heat_pump_scop != null) out.push(`Heat-pump seasonal efficiency (SCOP) ${a.heat_pump_scop}`);
  if (a.boiler_efficiency != null) out.push(`Existing boiler efficiency ${a.boiler_efficiency}`);
  if (a.space_share_of_heat_water_gas != null) out.push(`Space heating share of heating + hot-water gas ${a.space_share_of_heat_water_gas}`);
  if (a.other_gas_share != null) out.push(`Cooking / other gas share ${a.other_gas_share} (never changed by a measure)`);
  if (a.impact_level != null) out.push(`Measure impacts at catalogue ${a.impact_level} level`);
  if (a.package_threshold_pct != null) out.push(`Package threshold: at least ${a.package_threshold_pct}% of baseline emissions`);
  return out;
}

function unvalidated(r: ScenarioResult): string[] {
  return r.simulation.measures.filter((m) => m.status === 'ok' && m.validated_impact === false).map((m) => measureLabel(m.measure));
}

function validationText(r: ScenarioResult): string {
  const un = unvalidated(r);
  const parts = ['Engine arithmetic is checked by a hand-calculated reference suite and per-fuel reconciliation.'];
  if (un.length) parts.push(`Impacts for ${un.join(', ')} are not validated against NEED measured savings (brief range or assumption).`);
  if (r.warnings.some((w) => w.includes('overestimated'))) parts.push('Combined fabric savings exceed NEED measured combinations by 5.6–13.8 percentage points (simulator_vs_need.json).');
  parts.push('Not empirically validated against this home’s meter.');
  return parts.join(' ');
}

const COMMON_LIMITS = [
  'Savings are estimates, not guarantees.',
  'Occupancy, weather, installation quality and prices are not modelled.',
];

export function scoreEvidence(r: ScenarioResult, which: 'before' | 'after'): EvidenceEntry {
  const s = which === 'before' ? r.score_before : r.score_after;
  if (!s) {
    return {
      ...base(r), title: 'Score after retrofit', value: 'Not estimated', inputs: [], assumptions: [], sources: [],
      missing: ['The engine only scores the after-retrofit state when the simulation succeeds.'],
      validation: 'Not applicable.', limitations: [],
    };
  }
  return {
    ...base(r),
    title: which === 'before' ? 'Green Home Score today' : 'Green Home Score after retrofit',
    value: s.total != null ? `${s.total} / 100 · ${s.classification}` : missingText(s.status),
    summary: s.range_low != null && s.range_high != null && s.range_low !== s.range_high
      ? `Range ${s.range_low}–${s.range_high} because ${s.missing_parts.length} part(s) are missing.` : undefined,
    inputs: s.parts.map((p) => ({
      label: `${SCORE_PART_LABEL[p.part] ?? p.part} · weight ${fmtNumber(p.weight * 100)}%`,
      value: p.sub != null ? `${fmtNumber(p.sub)} → ${fmtNumber(p.points, 1)} pts · ${p.detail}` : `missing (scored ${p.used_sub} for the headline) · ${p.detail}`,
      provenance: p.provenance,
    })),
    method: 'S = Σ weight × sub-score, rounded half up. Weights are fixed (score_mappings.json). Missing parts score 50 for the headline and 0/100 for the range; more than 2 missing → unavailable.',
    assumptions: s.parts.filter((p) => p.provenance === 'assumption').map((p) => `${SCORE_PART_LABEL[p.part] ?? p.part}: ${p.detail}`),
    missing: [...s.missing_parts.map((p) => `${SCORE_PART_LABEL[p] ?? p} not recorded`), ...s.notes],
    validation: which === 'after'
      ? 'After-retrofit score uses documented state effects; EPC energy efficiency is not re-assessed.'
      : 'Mappings are monotonic and unit-tested; intensity percentiles frozen on the training split.',
    limitations: ['The score is not an EPC rating.', 'Energy intensity uses benchmark baselines unless you enter a meter reading.'],
    sources: ['EPC certificate fields (MHCLG)', 'NEED benchmarks (DESNZ)', `score mappings ${r.versions.score_mappings ?? ''}`],
  };
}

export function energyEvidence(r: ScenarioResult, fuel: 'gas' | 'elec' | 'purchased'): EvidenceEntry {
  const sim = r.simulation;
  const v = fuel === 'gas' ? sim.gas_saving_kwh : fuel === 'elec' ? sim.elec_saving_kwh : sim.purchased_saving_kwh;
  const title = fuel === 'gas' ? 'Gas saving' : fuel === 'elec' ? 'Grid electricity saving' : 'Purchased energy saving';
  return {
    ...base(r),
    title,
    value: fmtKwh(v, sim.status),
    direction: savingDirection(v),
    summary: fuel === 'elec' && (v ?? 0) < 0
      ? 'Negative: electricity use rises because the heat pump moves heating from gas to electricity.' : undefined,
    inputs: [
      ...baselineInputs(r),
      ...sim.steps.map((st) => ({
        label: `Step: ${measureLabel(st.measure)}`,
        value: `gas ${fmtKwh(st.gas_saving_kwh)}, electricity ${fmtKwh(st.elec_saving_kwh)}${st.note ? ` · ${st.note}` : ''}`,
        provenance: 'derived',
      })),
    ],
    method: 'Sequential simulator: fabric → glazing → controls → heat pump → solar, on per-end-use energy; savings = before − after (negative = increase); steps reconcile to the total.',
    assumptions: assumptionList(r),
    missing: [r.baseline.note, sim.reason_code ? humanise(sim.reason_code) : ''].filter(Boolean),
    validation: validationText(r),
    limitations: [...COMMON_LIMITS, r.baseline.source === 'population_benchmark' ? 'Baseline is a NEED benchmark for similar homes, not this home’s meter.' : ''].filter(Boolean),
    sources: ['DESNZ NEED: Impact of measures 2026', 'DESNZ ECUK 2026 end-use split', `catalogue ${r.versions.catalogue ?? ''}`],
  };
}

export function carbonEvidence(r: ScenarioResult): EvidenceEntry {
  const c = r.carbon;
  return {
    ...base(r),
    title: 'Carbon saving',
    value: fmtKg(c.total_kg, c.status),
    direction: savingDirection(c.total_kg),
    inputs: [
      { label: 'From gas', value: fmtKg(c.gas_kg, c.status), provenance: 'derived' },
      { label: 'From electricity', value: fmtKg(c.elec_kg, c.status), provenance: 'derived' },
      { label: 'Emissions before', value: fmtKg(c.before_kg, c.status), provenance: 'derived' },
      { label: 'Emissions after', value: fmtKg(c.after_kg, c.status), provenance: 'derived' },
      { label: 'Share of baseline', value: fmtPct(c.saving_pct_of_baseline, 1, c.status), provenance: 'derived' },
    ],
    method: 'ΔC = ΔE_gas × EF_gas + ΔE_elec × EF_elec. A rise in electricity adds emissions.',
    assumptions: emissionSources(r),
    missing: c.reason_code ? [humanise(c.reason_code)] : [],
    validation: 'Per-fuel parts are checked to sum to the total. Emission factors are published values.',
    limitations: ['Uses annual average factors; grid carbon varies by hour and year.', ...COMMON_LIMITS],
    sources: ['DESNZ Greenhouse gas reporting: conversion factors 2026'],
  };
}

export function costEvidence(r: ScenarioResult, pkg: PackageResult | undefined, title = 'Indicative cost'): EvidenceEntry {
  return {
    ...base(r),
    title,
    value: pkg ? fmtGbp(pkg.cost_gbp, pkg.cost_status) : 'Not available',
    inputs: pkg ? pkg.measures.map((m) => ({ label: measureLabel(m), value: 'catalogue mid cost', provenance: 'assumption' })) : [],
    method: 'Sum of catalogue mid costs for the measures in the package.',
    assumptions: pkg ? [pkg.cost_provenance] : [],
    missing: pkg && !pkg.eligible_for_cost_comparison ? ['Not eligible for cost comparison (missing cost or estimate).'] : [],
    validation: 'Indicative only: EPC assessor cost ranges for York, not quotes.',
    limitations: ['Heat-pump cost comes from a single software default text in the EPC data.', 'Grants are subject to scheme eligibility.'],
    sources: ['EPC recommendations indicative_cost, City of York'],
  };
}

export function valuationEvidence(r: ScenarioResult): EvidenceEntry {
  const v = r.valuation;
  const inputs: EvidenceInput[] = [];
  if (isNum(v.sap_before)) inputs.push({ label: 'EPC (SAP) today', value: `${fmtNumber(v.sap_before)}${v.rating_before ? ` (band ${v.rating_before})` : ''}`, provenance: 'observed' });
  if (isNum(v.sap_after_indicative)) inputs.push({ label: 'Indicative EPC after', value: `${fmtNumber(v.sap_after_indicative, 1)}${v.rating_after_indicative ? ` (band ${v.rating_after_indicative})` : ''}`, provenance: 'modelled' });
  if (isNum(v.current_value_gbp)) inputs.push({ label: 'Current value (model)', value: `${fmtGbp(v.current_value_gbp)} (80% range ${fmtGbp(v.current_value_low_gbp)} to ${fmtGbp(v.current_value_high_gbp)})`, provenance: 'modelled' });
  return {
    ...base(r),
    title: 'Property value',
    value: v.status === 'ok' ? `${fmtPct(v.low_pct, 1)} to ${fmtPct(v.high_pct, 1)}` : missingText(v.status),
    summary: v.reason,
    inputs,
    method: v.basis || undefined,
    assumptions: v.value_reason ? [v.value_reason] : [],
    missing: v.status !== 'ok' ? [v.reason] : [],
    validation: 'Value model gated by a sales-match precision audit (precision 1.00) and an 80% interval coverage check on held-out test sales (D10, D38).',
    limitations: v.caveats.length ? v.caveats : ['Historical price associations are not causal.', 'Never a promise of uplift.'],
    sources: ['HM Land Registry Price Paid 2025–2026', ...Object.values(v.model_versions)],
  };
}

export function billsEvidence(r: ScenarioResult): EvidenceEntry {
  const b = r.bills;
  const f = r.finance;
  const p = b?.prices ?? {};
  return {
    ...base(r),
    title: 'Bills, grants and payback',
    value: b && b.status === 'ok' ? `${fmtGbp(b.saving_gbp)} a year` : missingText(b?.status ?? 'not_estimated'),
    direction: savingDirection(b?.saving_gbp),
    summary: 'Annual bill before and after at the unit rates and standing charges shown; payback = net cost ÷ annual bill saving.',
    inputs: [
      ...baselineInputs(r),
      { label: 'Gas unit rate', value: `${p.gas_p_per_kwh ?? '—'}p/kWh`, provenance: r.request.assumptions.gas_price_p != null ? 'user_provided' : 'assumption' },
      { label: 'Electricity unit rate', value: `${p.elec_p_per_kwh ?? '—'}p/kWh`, provenance: r.request.assumptions.elec_price_p != null ? 'user_provided' : 'assumption' },
      { label: 'Standing charges', value: `gas ${p.gas_standing_p_per_day ?? '—'}p/day, electricity ${p.elec_standing_p_per_day ?? '—'}p/day`, provenance: 'assumption' },
      ...(f ? [{ label: 'Cost before grants', value: fmtGbp(f.gross_cost_gbp, f.status), provenance: 'assumption' },
        { label: 'Grants', value: fmtGbp(f.grants_gbp, f.status), provenance: 'assumption' }] : []),
    ],
    method: 'Engine money module (D26 bills at the price cap; D27 grants, net cost, payback, illustrative loan).',
    assumptions: [...(b?.notes ?? []), ...(f?.grant_notes ?? [])],
    missing: b && b.status !== 'ok' ? [b.reason ?? 'Bills need a baseline.'] : [],
    validation: 'Bills use published price-cap rates; they are not compared with real bills.',
    limitations: ['Estimate at capped unit rates; not a quote.', 'Solar export is not credited.', 'The loan is illustrative: not a Lloyds product, rate or offer.'],
    sources: [String(p.source ?? 'configs/energy_prices.json'), 'configs/grants.json', 'configs/finance.json'],
  };
}

export function rangeEvidence(r: ScenarioResult): EvidenceEntry {
  const u = r.uncertainty;
  return {
    ...base(r),
    title: 'Ranges (Monte Carlo)',
    value: u && u.status === 'ok' ? `${u.n_draws ?? ''} draws` : missingText(u?.status ?? 'not_estimated'),
    summary: u?.label,
    inputs: Object.entries(u?.percentiles ?? {}).filter(([, q]) => q).map(([k, q]) => ({ label: humanise(k), value: `P10 ${fmtNumber(q!.p10)} · P50 ${fmtNumber(q!.p50)} · P90 ${fmtNumber(q!.p90)}` })),
    method: 'Seeded Monte Carlo over documented input ranges (D28); the seed comes from the scenario ID, so the same request gives the same ranges.',
    assumptions: u ? u.inputs_varied.map((x) => `Varied: ${x}`) : [],
    missing: u ? u.not_varied.map((x) => `Not varied: ${x}`) : [],
    validation: 'Shows sensitivity to inputs; it is not a confidence interval.',
    limitations: ['Occupancy, weather and installation quality are not varied.'],
    sources: ['configs/retrofit_catalogue.json', 'configs/engine_params.json'],
  };
}

export function measureEvidence(r: ScenarioResult, m: MeasureId): EvidenceEntry {
  const f = r.feasibility.find((x) => x.measure === m);
  const row = r.simulation.measures.find((x) => x.measure === m);
  const alone = r.standalone[m];
  return {
    ...base(r),
    title: measureLabel(m),
    value: f ? humanise(f.state) : 'Unknown',
    summary: f?.reason_text,
    inputs: [
      { label: 'Feasibility', value: `${f ? humanise(f.state) : '—'} (${f?.reason_code ?? '—'})` },
      ...(f?.missing_inputs.length ? [{ label: 'Missing inputs', value: f.missing_inputs.join(', '), provenance: 'unavailable' }] : []),
      ...(row ? [
        { label: 'Marginal gas saving in this plan', value: fmtKwh(row.gas_saving_kwh, row.status), provenance: row.provenance },
        { label: 'Marginal electricity saving', value: fmtKwh(row.elec_saving_kwh, row.status), provenance: row.provenance },
        { label: 'Impact used', value: row.impact_used != null ? `${fmtNumber(row.impact_used * 100, 1)}% of ${row.impact_basis}` : missingText(row.status), provenance: 'assumption' },
      ] : []),
      ...(alone ? [{ label: 'Applied on its own: carbon', value: fmtKg(alone.carbon_saving_kg, alone.status), provenance: 'derived' }] : []),
    ],
    method: 'Marginal effect at the measure’s position in the fixed order (later measures act on what is left).',
    assumptions: assumptionList(r),
    missing: row?.reason_code ? [humanise(row.reason_code)] : [],
    validation: row?.validated_impact === true ? 'Impact taken from NEED measured savings.' : row?.validated_impact === false ? 'Impact not validated against NEED (brief range / assumption).' : 'Not estimated in this scenario.',
    limitations: COMMON_LIMITS,
    sources: ['configs/retrofit_catalogue.json'],
  };
}

export function provenanceLabel(p: string | null | undefined): string {
  if (!p) return '—';
  return PROVENANCE_INFO[p as keyof typeof PROVENANCE_INFO]?.label ?? humanise(p);
}
