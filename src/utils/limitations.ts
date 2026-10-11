import type { ScenarioResult } from '../api/schema';
import { fmtNumber } from './format';

/** The single most important thing the data cannot tell us about this home, then the rest. */
export function limitations(r: ScenarioResult): string[] {
  const out: string[] = [];
  if (r.score_before.status !== 'ok') out.push(`The Green Home Score is unavailable: only ${r.score_before.completeness} parts are recorded.`);
  if (r.baseline.source === 'unavailable') out.push('No energy baseline: gas and electricity use are unknown, so savings cannot be estimated. A meter reading would fix this.');
  else if (r.baseline.source === 'population_benchmark') out.push('Energy use is a NEED benchmark for similar homes, not this home’s meter. Enter a reading to replace it.');
  else if (r.baseline.source === 'user_provided') out.push('Energy use comes from your meter reading.');
  if (r.home.flag_stale_epc) out.push(`The latest EPC is ${fmtNumber(r.home.epc_age_years, 1)} years old; recorded features may be out of date.`);
  const verify = r.feasibility.filter((f) => f.state === 'needs_verification');
  if (verify.length) out.push(`${verify.length} measure(s) need a survey before they can be confirmed.`);
  return out;
}
