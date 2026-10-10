/**
 * The scenario contract, mirrored one-to-one from the engine's Pydantic models
 * (backend/app/schemas/{enums,scenario,retrofit,property}.py in this repository).
 *
 * Every API response is parsed with these schemas at the boundary, so a drift between
 * backend and frontend fails loudly as a validation error instead of rendering wrong numbers.
 * Fields that the engine types as plain dicts (home, standalone, sensitivity, audit, portfolio)
 * are typed from the engine code that fills them (scenario_builder.py, sensitivity.py, audit.py,
 * portfolio.py). Missing values are null plus a status, never 0.
 */
import { z } from 'zod';

// ---------- enums (backend/app/schemas/enums.py) ----------
export const PROVENANCE = [
  'observed', 'population_benchmark', 'user_provided', 'modelled',
  'assumption', 'derived', 'unavailable', 'not_applicable',
] as const;
export const Provenance = z.enum(PROVENANCE);
export type Provenance = z.infer<typeof Provenance>;

export const FeasibilityState = z.enum(['feasible', 'infeasible', 'needs_verification']);
export type FeasibilityState = z.infer<typeof FeasibilityState>;

export const Suitability = z.enum(['High', 'Medium', 'Low']);

export const MEASURE_ORDER = [
  'loft_insulation', 'cavity_wall', 'solid_wall', 'double_glazing',
  'smart_thermostat', 'heat_pump', 'solar_pv',
] as const;
export const MeasureId = z.enum(MEASURE_ORDER);
export type MeasureId = z.infer<typeof MeasureId>;

export const ValueStatus = z.enum(['ok', 'unavailable', 'not_estimated', 'blocked']);
export type ValueStatus = z.infer<typeof ValueStatus>;

export const HeatPumpMode = z.enum(['full', 'partial', 'unknown']);
export const CombinationMode = z.enum(['engineering', 'need_calibrated']);
export const ImpactLevel = z.enum(['low', 'mid', 'high']);
export type ImpactLevel = z.infer<typeof ImpactLevel>;

export const OBJECTIVES = ['lowest_cost_meeting_threshold', 'largest_carbon_saving', 'best_carbon_per_pound'] as const;
export const Objective = z.enum(OBJECTIVES);
export type Objective = z.infer<typeof Objective>;

const num = z.number();
const nnum = z.number().nullable();
const nstr = z.string().nullable();
const strList = z.array(z.string()).default([]);

// ---------- request (schemas/scenario.py) ----------
export const Assumptions = z.object({
  impact_level: ImpactLevel.default('mid'),
  heat_pump_scop: nnum.default(null),
  space_share_of_heat_water_gas: nnum.default(null),
  other_gas_share: nnum.default(null),
  boiler_efficiency: nnum.default(null),
  heat_pump_mode: HeatPumpMode.default('full'),
  heat_pump_partial_share: nnum.default(null),
  baseline_scale: num.default(1),
  segment_impacts: z.boolean().default(true),
  /** What-if unit rates in p/kWh (D26); null = the Ofgem price cap. */
  gas_price_p: z.number().min(0).nullable().default(null),
  elec_price_p: z.number().min(0).nullable().default(null),
  /** Package selection on cost net of grants (D27). */
  apply_grants: z.boolean().default(true),
  combination_mode: CombinationMode.default('engineering'),
});
export type Assumptions = z.infer<typeof Assumptions>;

export const UserReading = z.object({
  gas_kwh: z.number().min(0).nullable().default(null),
  elec_kwh: z.number().min(0).nullable().default(null),
});
export type UserReading = z.infer<typeof UserReading>;

export const ScenarioRequest = z.object({
  home_id: z.string(),
  measures: z.array(MeasureId).nullable().default(null),
  assumptions: Assumptions,
  user_reading: UserReading.nullable().default(null),
  include_packages: z.boolean().default(true),
  include_sensitivity: z.boolean().default(false),
  /** Monte Carlo ranges for the requested package (D28). */
  include_uncertainty: z.boolean().default(false),
  use_modelled_epc: z.boolean().default(false),
  use_model_baseline: z.boolean().default(false),
});
export type ScenarioRequest = z.infer<typeof ScenarioRequest>;

// ---------- result parts ----------
export const Baseline = z.object({
  gas_kwh: nnum,
  elec_kwh: nnum,
  gas_provenance: Provenance,
  elec_provenance: Provenance,
  gas_status: z.string(),
  elec_status: z.string(),
  source: z.string(),
  blocking_flags: strList,
  gas_heated: z.boolean(),
  elec_heated: z.boolean().default(false),
  elec_heat_share: nnum.default(null),
  elec_heat_share_source: z.string().default(''),
  note: z.string(),
});
export type Baseline = z.infer<typeof Baseline>;

export const PartScore = z.object({
  part: z.string(),
  sub: nnum,
  used_sub: num,
  weight: num,
  points: num,
  provenance: Provenance,
  status: z.string(),
  detail: z.string(),
});
export type PartScore = z.infer<typeof PartScore>;

/** Indicative EPC change after retrofit from the SAP model (D34); modelled, not an EPC re-assessment. */
export const EpcChange = z.object({
  status: ValueStatus,
  reason: nstr.default(null),
  sap_before: nnum.default(null),
  sap_change: nnum.default(null),
  sap_after_indicative: nnum.default(null),
  rating_before: nstr.default(null),
  rating_after_indicative: nstr.default(null),
  model_version: nstr.default(null),
  provenance: nstr.default(null),
  label: z.string().default(''),
});
export type EpcChange = z.infer<typeof EpcChange>;

export const ScoreResult = z.object({
  status: ValueStatus,
  total: z.number().int().nullable(),
  raw_total: nnum,
  classification: nstr,
  range_low: z.number().int().nullable(),
  range_high: z.number().int().nullable(),
  completeness: z.string(),
  missing_parts: strList,
  parts: z.array(PartScore),
  key_issues: strList,
  notes: strList,
  epc_change: EpcChange.nullable().default(null),
  rating_after_indicative: nstr.default(null),
});
export type ScoreResult = z.infer<typeof ScoreResult>;

/** Indicative property-value impact (M3): an association from York sales, not a causal effect. */
export const Valuation = z.object({
  status: ValueStatus,
  reason: z.string(),
  low_pct: nnum.default(null),
  mid_pct: nnum.default(null),
  high_pct: nnum.default(null),
  sap_before: nnum.default(null),
  sap_change: nnum.default(null),
  sap_after_indicative: nnum.default(null),
  rating_before: nstr.default(null),
  rating_after_indicative: nstr.default(null),
  current_value_gbp: nnum.default(null),
  current_value_low_gbp: nnum.default(null),
  current_value_high_gbp: nnum.default(null),
  potential_value_low_gbp: nnum.default(null),
  potential_value_high_gbp: nnum.default(null),
  value_status: ValueStatus.nullable().default(null),
  value_reason: nstr.default(null),
  measures: strList,
  provenance: nstr.default(null),
  basis: z.string().default(''),
  caveats: strList,
  model_versions: z.record(z.string(), z.string()).default({}),
});
export type Valuation = z.infer<typeof Valuation>;

export const FeasibilityItem = z.object({
  measure: MeasureId,
  state: FeasibilityState,
  suitability: Suitability.nullable(),
  reason_code: z.string(),
  reason_text: z.string(),
  missing_inputs: strList,
});
export type FeasibilityItem = z.infer<typeof FeasibilityItem>;

/** Annual purchased energy split by end use, kWh/year (schemas/retrofit.py EndUses). */
export const EndUses = z.object({
  gas_space: num,
  gas_water: num,
  gas_other: num,
  elec_base: num,
  elec_space: num.default(0),
  elec_water: num.default(0),
  hp_elec: num,
  pv_offset: num,
  /** Totals computed by the engine (EndUses computed fields); the UI prints them, never adds parts itself. */
  gas_total: num.optional(),
  elec_import: num.optional(),
  elec_gross: num.optional(),
  purchased: num.optional(),
});
export type EndUses = z.infer<typeof EndUses>;

export const SimStep = z.object({
  measure: MeasureId,
  status: ValueStatus,
  reason_code: nstr,
  impact_used: nnum,
  impact_basis: nstr,
  before: EndUses,
  after: EndUses,
  gas_saving_kwh: num,
  elec_saving_kwh: num,
  note: z.string(),
});

export const MeasureRow = z.object({
  measure: MeasureId,
  status: ValueStatus,
  reason_code: nstr,
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  purchased_saving_kwh: nnum,
  impact_used: nnum,
  impact_basis: nstr,
  validated_impact: z.boolean().nullable(),
  provenance: Provenance,
});
export type MeasureRow = z.infer<typeof MeasureRow>;

export const SimResult = z.object({
  status: ValueStatus,
  reason_code: nstr,
  before: EndUses.nullable(),
  after: EndUses.nullable(),
  steps: z.array(SimStep).default([]),
  measures: z.array(MeasureRow).default([]),
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  purchased_saving_kwh: nnum,
  purchased_before_kwh: nnum,
  purchased_after_kwh: nnum,
  improvement_potential_pct: nnum,
  improvement_potential_status: ValueStatus,
  improvement_potential_reason: nstr,
  warnings: strList,
  assumptions: z.record(z.string(), z.unknown()).default({}),
});
export type SimResult = z.infer<typeof SimResult>;

const EmissionFactor = z.object({
  kg_co2e_per_kwh: num,
  units: z.string(),
  source: z.string(),
  year: z.string(),
});

export const CarbonResult = z.object({
  status: ValueStatus,
  reason_code: nstr,
  gas_kg: nnum,
  elec_kg: nnum,
  total_kg: nnum,
  before_kg: nnum,
  after_kg: nnum,
  saving_pct_of_baseline: nnum,
  factors: z.record(z.string(), EmissionFactor).default({}),
});
export type CarbonResult = z.infer<typeof CarbonResult>;

export const PackageResult = z.object({
  package_id: z.string(),
  measures: z.array(MeasureId),
  confirmed: z.boolean(),
  must_verify: strList,
  cost_gbp: nnum,
  cost_provenance: z.string(),
  cost_status: ValueStatus,
  eligible_for_cost_comparison: z.boolean(),
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  purchased_saving_kwh: nnum,
  improvement_potential_pct: nnum,
  carbon_saving_kg: nnum,
  carbon_saving_pct: nnum,
  carbon_per_pound_kg: nnum,
  dominated: z.boolean(),
  dominated_by: nstr,
  unvalidated_impacts: strList,
  warnings: strList,
  sensitivity: z.record(z.string(), z.unknown()).nullable(),
  calibrated: z.record(z.string(), z.unknown()).nullable().default(null),
  /** D26/D27: grants subject to eligibility; bill saving annual, positive = bill falls. */
  grants_gbp: nnum.default(null),
  net_cost_gbp: nnum.default(null),
  bill_saving_gbp: nnum.default(null),
  payback_years: nnum.default(null),
  status: ValueStatus,
  reason_code: nstr,
});
export type PackageResult = z.infer<typeof PackageResult>;

export const FeaturedPick = z.object({
  objective: Objective,
  label: z.string(),
  package_id: nstr,
  message: nstr,
  alternatives: strList,
});
export type FeaturedPick = z.infer<typeof FeaturedPick>;

export const PackageSearch = z.object({
  packages: z.array(PackageResult),
  featured: z.array(FeaturedPick),
  fallbacks: strList,
  excluded_measures: z.record(z.string(), z.string()).default({}),
  threshold_pct: num,
  budget_gbp: nnum,
  baseline_emissions_kg: nnum.default(null),
  cost_basis: z.string().optional(),
});
export type PackageSearch = z.infer<typeof PackageSearch>;

/** services/sensitivity.py run(): one-at-a-time reruns of the package search. */
export const Sensitivity = z.object({
  label: z.string(),
  runs: z.array(z.object({
    name: z.string(),
    change: z.string(),
    featured: z.record(z.string(), nstr),
    changed_objectives: strList,
  })),
  survival: z.record(z.string(), z.object({
    base_pick: nstr,
    survives: z.string(),
    changed_under: strList,
  })),
  untested: strList,
});
export type Sensitivity = z.infer<typeof Sensitivity>;

/** scenario_builder.py: standalone[measure] = the measure applied on its own. */
export const Standalone = z.object({
  status: z.string(),
  reason: nstr,
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  purchased_saving_kwh: nnum,
  carbon_saving_kg: nnum,
  suitability: nstr,
  feasibility: z.string(),
  reason_text: z.string(),
});
export type Standalone = z.infer<typeof Standalone>;

/** scenario_builder.public_home(): public fields only; never an address, full postcode or UPRN. */
export const PublicHome = z.object({
  home_id: z.string(),
  display_label: z.string(),
  postcode_outward: nstr,
  split: nstr,
  rating: nstr,
  sap_score: nnum,
  property_type: nstr,
  built_form: nstr,
  age_band: nstr,
  floor_area_m2: nnum,
  walls_rating: nstr,
  roof_rating: nstr,
  floor_rating: nstr,
  glazing: nstr,
  multi_glaze_pct: nnum,
  heating_type: nstr,
  heating_rating: nstr,
  controls: nstr,
  solar_pv: z.boolean().nullable(),
  mains_gas: z.boolean().nullable(),
  epc_age_years: nnum,
  flag_stale_epc: z.boolean(),
  provenance: z.record(z.string(), Provenance).default({}),
});
export type PublicHome = z.infer<typeof PublicHome>;

const PkgSummary = z.object({
  package_id: z.string(),
  cost_gbp: nnum,
  carbon_saving_kg: nnum,
  carbon_saving_pct: nnum,
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  purchased_saving_kwh: nnum,
});

/** services/audit.py build_audit(): generated from the computed result, never hand-written. */
export const Audit = z.object({
  scenario_id: z.string(),
  versions: z.record(z.string(), z.string()),
  baseline: z.object({
    gas_kwh: nnum,
    elec_kwh: nnum,
    gas_provenance: z.string(),
    elec_provenance: z.string(),
    source: z.string(),
    note: z.string(),
    blocking_flags: strList,
  }),
  feasibility: z.array(z.object({
    measure: z.string(),
    state: z.string(),
    reason: z.string(),
    missing_inputs: strList,
  })),
  requested_package: z.object({
    status: z.string(),
    measures: z.array(z.object({ measure: z.string(), status: z.string(), reason: nstr })),
    reason: nstr.optional(),
  }),
  packages_considered: z.object({
    count: z.number(),
    excluded_measures: z.record(z.string(), z.string()),
    dominated: z.record(z.string(), nstr),
    conditional: z.record(z.string(), z.array(z.string())),
    missing_cost: z.array(z.string()),
    threshold_pct: num,
    budget_gbp: nnum,
  }).optional(),
  featured: z.array(z.object({
    objective: z.string(),
    objective_text: z.string(),
    label: z.string(),
    package: PkgSummary.nullable(),
    message: nstr,
    alternatives: strList,
  })).optional(),
  fallbacks: strList.optional(),
  winner: z.object({ package: PkgSummary, objective: z.string() }).optional(),
  alternative: PkgSummary.nullable().optional(),
  main_factors: strList.optional(),
  sensitivity: z.object({
    label: z.string(),
    survival: Sensitivity.shape.survival,
    untested: strList,
  }).optional(),
  unknowns: strList,
  warnings: strList,
  improvement_potential: z.object({ status: z.string(), pct: nnum, reason: nstr }),
});
export type Audit = z.infer<typeof Audit>;

/** Annual bills at the price cap (or the what-if tariff), per fuel (D26). Positive saving = bill falls. */
export const Bills = z.object({
  status: ValueStatus,
  reason: nstr.optional(),
  before_gbp: nnum.default(null),
  after_gbp: nnum.default(null),
  saving_gbp: nnum.default(null),
  gas_saving_gbp: nnum.default(null),
  elec_saving_gbp: nnum.default(null),
  standing_saving_gbp: nnum.default(null),
  prices: z.record(z.string(), z.union([z.number(), z.string(), z.null()])).default({}),
  notes: strList,
});
export type Bills = z.infer<typeof Bills>;

/** Gross and net cost, grants, payback and an illustrative loan (D27). Not a Lloyds product or offer. */
export const Finance = z.object({
  status: ValueStatus,
  reason: nstr.optional(),
  gross_cost_gbp: nnum.default(null),
  grants_gbp: nnum.default(null),
  net_cost_gbp: nnum.default(null),
  cost_provenance: z.string().default(''),
  grant_notes: strList,
  annual_bill_saving_gbp: nnum.default(null),
  payback_years: nnum.default(null),
  illustrative_loan: z.object({
    apr_pct: num,
    term_years: num,
    status: z.string(),
    monthly_repayment_gbp: nnum,
    monthly_bill_saving_gbp: nnum,
    saving_covers_repayment: z.boolean().nullable(),
  }).nullable().default(null),
});
export type Finance = z.infer<typeof Finance>;

const Pctl = z.object({ p10: nnum, p50: nnum, p90: nnum });
/** Monte Carlo ranges over documented input ranges (D28); not a confidence interval. */
export const Uncertainty = z.object({
  status: ValueStatus,
  reason: nstr.optional(),
  label: z.string().default(''),
  n_draws: num.optional(),
  percentiles: z.record(z.string(), Pctl.nullable()).default({}),
  threshold_pct: nnum.optional(),
  prob_carbon_cut_ge_threshold: nnum.optional(),
  prob_bill_falls: nnum.optional(),
  inputs_varied: strList,
  not_varied: strList,
});
export type Uncertainty = z.infer<typeof Uncertainty>;

/** Assessor-relevance priority of feasible measures (M5); install order stays the engine's physical order. */
export const RecommendationRank = z.object({
  measure: MeasureId,
  assessor_relevance_prob: nnum,
  basis: z.string(),
  feasibility: z.string(),
  verify: z.boolean(),
  carbon_per_pound_kg: nnum.default(null),
  bill_saving_gbp: nnum.default(null),
  rank: num,
  label: z.string(),
});
export type RecommendationRank = z.infer<typeof RecommendationRank>;

export const ScenarioResult = z.object({
  scenario_id: z.string().min(1),
  home: PublicHome,
  request: ScenarioRequest,
  baseline: Baseline,
  feasibility: z.array(FeasibilityItem),
  measures_applied: z.array(MeasureId),
  measures_blocked: z.record(z.string(), z.string()),
  simulation: SimResult,
  standalone: z.record(z.string(), Standalone),
  carbon: CarbonResult,
  score_before: ScoreResult,
  score_after: ScoreResult.nullable(),
  packages: PackageSearch.nullable(),
  sensitivity: Sensitivity.nullable(),
  valuation: Valuation,
  combination_check: z.record(z.string(), z.unknown()).nullable().default(null),
  bills: Bills.nullable().default(null),
  finance: Finance.nullable().default(null),
  uncertainty: Uncertainty.nullable().default(null),
  recommendation_ranking: z.array(RecommendationRank).nullable().default(null),
  install_sequence: z.array(MeasureId).nullable().default(null),
  audit: Audit,
  assumptions: z.record(z.string(), z.unknown()),
  warnings: strList,
  versions: z.record(z.string(), z.string()),
  data_timestamp: z.string(),
});
export type ScenarioResult = z.infer<typeof ScenarioResult>;

// ---------- other endpoints ----------
export const DemoHome = z.object({
  home_id: z.string(),
  case: z.string(),
  display_label: z.string(),
  why_chosen: z.string(),
  rating: nstr,
  property_type: nstr,
  postcode_outward: nstr,
});
export const DemoHomes = z.array(DemoHome);
export type DemoHome = z.infer<typeof DemoHome>;

/** services/portfolio.py portfolio(): Poor / Very poor homes ranked by improvement potential. */
export const PortfolioRow = z.object({
  home_id: z.string(),
  display_label: z.string(),
  postcode_outward: nstr,
  score: z.number().int().nullable(),
  classification: z.string(),
  completeness: z.string(),
  missing_parts: strList,
  key_issues: strList,
  package_id: z.string(),
  improvement_potential_pct: nnum,
  improvement_potential_status: z.string(),
  improvement_potential_reason: nstr,
  gas_saving_kwh: nnum,
  elec_saving_kwh: nnum,
  carbon_saving_kg: nnum,
  floor_area_m2: nnum,
  heat_pump_in_package: z.boolean().optional(),
  fabric_improvement_potential_pct: nnum.optional(),
  gross_cost_gbp: nnum.optional(),
  grants_gbp: nnum.optional(),
  net_cost_gbp: nnum.optional(),
  bill_saving_gbp: nnum.optional(),
  payback_years: nnum.optional(),
  carbon_per_pound_kg: nnum.optional(),
});
export type PortfolioRow = z.infer<typeof PortfolioRow>;

export const Portfolio = z.object({
  summary: z.object({
    homes: z.number(),
    count_by_class: z.record(z.string(), z.number()),
    flagged_poor_or_very_poor: z.number(),
    flagged_with_potential_available: z.number(),
    flagged_potential_unavailable: z.number(),
    median_improvement_potential_pct: nnum,
    total_carbon_saving_potential_t: nnum,
    share_incomplete_data_pct: nnum,
    rank_by: z.string().optional(),
    total_net_cost_gbp: nnum.optional(),
    homes_with_bill_falling: z.number().optional(),
    notes: strList,
  }),
  homes: z.array(PortfolioRow),
  data_mode: z.string().optional(),
  data_note: z.string().optional(),
});
export type Portfolio = z.infer<typeof Portfolio>;

const EvalBlock = z.object({ status: z.string(), detail: z.unknown().optional() });

/** Method & Evidence: engine configs and validation files, served verbatim. */
export const Evidence = z.object({
  versions: z.record(z.string(), z.string()),
  sources: z.array(z.object({ id: z.string(), title: z.string(), body: z.string() })),
  score: z.object({
    weights: z.record(z.string(), num),
    classes: z.array(z.object({ min: num, label: z.string() })),
    missing: z.record(z.string(), z.unknown()),
    rating_points: z.record(z.string(), num),
    parts: z.record(z.string(), z.record(z.string(), z.unknown())),
    intensity_params: z.record(z.string(), z.unknown()),
  }),
  catalogue: z.object({
    version: z.string(),
    global: z.record(z.string(), z.unknown()),
    measures: z.array(z.object({
      id: MeasureId,
      label: z.string(),
      /** low/mid/high fractions for most measures; scop_low/mid/high for the heat pump. */
      impact: z.record(z.string(), z.number().nullable()).nullable(),
      impact_units: nstr.optional(),
      impact_method: nstr.optional(),
      impact_basis: nstr.optional(),
      target_end_use: nstr.optional(),
      conversion_method: nstr.optional(),
      household_dispersion: z.record(z.string(), z.unknown()).nullable().optional(),
      source: nstr.optional(),
      source_table: nstr.optional(),
      validated: z.boolean().nullable(),
      cost: z.record(z.string(), z.unknown()).nullable(),
      dependencies: z.array(z.string()).default([]),
      applicability_rules: z.record(z.string(), z.unknown()).nullable().optional(),
    })),
  }),
  emission_factors: z.record(z.string(), EmissionFactor),
  simulator_vs_need: z.object({
    source: z.string(),
    basis: z.string(),
    tolerance_pp: num,
    catalogue: z.string(),
    rows: z.array(z.object({
      combination: z.string(),
      measures: z.array(z.string()),
      need_n: num,
      need_median_pct: num,
      need_mean_pct: nnum.optional(),
      simulated_pct: num,
      gap_pp_vs_median: num,
      within_tolerance: z.boolean(),
    })),
  }).loose(),
  value_gate: z.record(z.string(), z.unknown()),
  energy_prices: z.record(z.string(), z.unknown()).optional(),
  grants: z.record(z.string(), z.unknown()).optional(),
  finance: z.record(z.string(), z.unknown()).optional(),
  models: EvalBlock,
  policy_comparison: EvalBlock,
  llm_evaluation: EvalBlock,
});
export type Evidence = z.infer<typeof Evidence>;

export const Health = z.object({
  status: z.string(),
  data_mode: z.string(),
  versions: z.record(z.string(), z.string()).default({}),
});
export type Health = z.infer<typeof Health>;

// ---------- LLM layer (backend/app/llm/{api,render,explain,whatif}.py) ----------
export const Span = z.object({
  key: z.string(),
  display: z.string(),
  status: z.string(),
  provenance: nstr,
  direction: nstr.optional(),
});
export const ExplanationClaim = z.object({
  type: z.string(),
  text: z.string(),
  keys: strList,
  measures: strList,
  spans: z.array(Span).default([]),
});
export type ExplanationClaim = z.infer<typeof ExplanationClaim>;

export const Explanation = z.object({
  scenario_id: z.string(),
  property_id: nstr.optional(),
  markdown: z.string().optional(),
  sections: z.array(z.object({ id: z.string(), title: z.string(), claims: z.array(ExplanationClaim) })),
  source: z.string(),
  mode: z.string().optional(),
  provider: nstr.optional(),
  model: nstr.optional(),
  fallback_reason: nstr.optional(),
});
export type Explanation = z.infer<typeof Explanation>;

export const ExplainResponse = z.object({ explanation: Explanation }).loose();

export const LlmHealth = z.object({
  engine_configured: z.boolean(),
  enabled: z.boolean(),
  providers: z.array(z.object({ provider: z.string(), key_set: z.boolean() }).loose()).default([]),
});
export type LlmHealth = z.infer<typeof LlmHealth>;

export const WhatIfResponse = z.object({
  outcome: z.object({
    kind: z.enum(['change_measures', 'change_assumptions', 'question_about_current', 'out_of_scope', 'invalid_request']),
    parser: z.string(),
    requested_add: strList,
    requested_remove: strList,
    unsupported: strList,
    added: strList,
    removed: strList,
    blocked: strList,
    conditional: strList,
    new_measures: strList,
    /** Validated changes to the engine request (tariff, readings, heat-pump mode, ...) and why a change was refused. */
    request_changes: z.record(z.string(), z.unknown()).default({}),
    invalid_reason: nstr.default(null),
    /** The validated ScenarioRequest; the UI applies it through POST /api/scenario. */
    new_request: ScenarioRequest.nullable().default(null),
  }).loose(),
  scenario_id: nstr,
  recalculated: z.boolean(),
  explanation: Explanation,
}).loose();
export type WhatIfResponse = z.infer<typeof WhatIfResponse>;
