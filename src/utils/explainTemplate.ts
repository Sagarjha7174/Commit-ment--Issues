/**
 * Deterministic explanation synthesizing physical energy, carbon, cost and finance estimates.
 * Direct, factual, engineer-verified breakdown without filler or artificial copy.
 */
import type { Explanation, ExplanationClaim, ScenarioResult } from '../api/schema';
import { fmtGbp, fmtKg, fmtKwh, fmtPct, isNum, missingText, savingDirection } from './format';
import { measureLabel, packageName, prettyText } from './labels';
import { selectionPackage } from './scenarioDiff';

type Span = ExplanationClaim['spans'][number];

function span(key: string, display: string, status = 'available', provenance: string | null = null, direction: string | null = null,
  sentiment: string | null = null): Span {
  return { key, display, status, provenance, direction, sentiment };
}

/** Good/bad for the homeowner from a saving (positive = less energy, carbon or bill). */
function savingSentiment(v: number | null | undefined): string | null {
  return !isNum(v) ? null : v > 0 ? 'good' : v < 0 ? 'bad' : 'neutral';
}

function claim(type: string, text: string, spans: Span[] = [], measures: string[] = []): ExplanationClaim {
  return { type, text, keys: spans.map((s) => s.key), measures, spans };
}

function changeSentence(fuel: string, key: string, v: number | null, status: string): ExplanationClaim {
  const dir = savingDirection(v);
  if (!isNum(v)) return claim('missing_data', `The ${fuel} change is ${missingText(status).toLowerCase()} for this selection.`, [span(key, missingText(status), status)]);
  const shown = fmtKwh(Math.abs(v));
  if (dir === 'none') return claim('statement', `Estimated ${fuel} use does not change with this selection.`, [span(key, fmtKwh(v), 'available', 'derived', 'no change', 'neutral')]);
  if (dir === 'reduction') return claim('saving', `Estimated ${fuel} use falls by ${shown}.`, [span(key, shown, 'available', 'derived', 'reduction', 'good')]);
  return claim('increase', `Estimated ${fuel} use rises by ${shown}; the engine reports this as a negative saving.`, [span(key, shown, 'available', 'derived', 'increase', 'bad')]);
}

export function templateExplanation(r: ScenarioResult, reason: string | null = null): Explanation {
  const s = r.score_before;
  const sections: Explanation['sections'] = [];

  sections.push({
    id: 'score', title: 'Green Home Score',
    claims: s.status === 'ok' && isNum(s.total)
      ? [claim('statement', `This home scores ${s.total} out of 100 (${s.classification}), with ${s.completeness} assessment factors recorded.`,
          [span('score_before.total', String(s.total)), span('score_before.completeness', s.completeness)])]
      : [claim('missing_data', `Green Home Score currently pending: ${s.notes.join('; ') || `only ${s.completeness} factors recorded`}.`,
          [span('score_before.completeness', s.completeness, 'unavailable')])],
  });

  if (s.key_issues.length) {
    sections.push({ id: 'issues', title: 'Priority efficiency bottlenecks', claims: [claim('statement', `Key bottlenecks: ${s.key_issues.join('; ')}.`)] });
  }

  const plan = r.measures_applied;
  sections.push({
    id: 'plan', title: 'Selected retrofits',
    claims: [plan.length
      ? claim('recommendation', `Applied measures (in optimal installation sequence): ${plan.map(measureLabel).join(', ')}.`, [], plan)
      : claim('statement', 'No measures selected in this scenario.')],
  });

  const sim = r.simulation;
  sections.push({
    id: 'energy', title: 'Energy demand impact',
    claims: [
      changeSentence('gas', 'simulation.gas_saving_kwh', sim.gas_saving_kwh, sim.status),
      changeSentence('grid electricity', 'simulation.elec_saving_kwh', sim.elec_saving_kwh, sim.status),
      ...(isNum(sim.improvement_potential_pct)
        ? [claim('statement', `Total purchased energy improvement potential: ${fmtPct(sim.improvement_potential_pct)}.`, [span('simulation.improvement_potential_pct', fmtPct(sim.improvement_potential_pct))])]
        : [claim('missing_data', `Improvement potential is ${missingText(sim.improvement_potential_status).toLowerCase()}${sim.improvement_potential_reason ? `: ${sim.improvement_potential_reason}` : ''}.`)]),
    ],
  });

  const c = r.carbon;
  const cdir = savingDirection(c.total_kg);
  sections.push({
    id: 'carbon', title: 'Carbon footprint impact',
    claims: [isNum(c.total_kg)
      ? claim(cdir === 'increase' ? 'increase' : 'saving',
          cdir === 'increase'
            ? `Estimated emissions increase by ${fmtKg(Math.abs(c.total_kg))}.`
            : `Estimated emissions fall by ${fmtKg(c.total_kg)} (from ${fmtKg(c.before_kg)} to ${fmtKg(c.after_kg)}).`,
          [span('carbon.total_kg', fmtKg(c.total_kg), 'available', 'derived', cdir, savingSentiment(c.total_kg))])
      : claim('missing_data', `Carbon change calculation: ${missingText(c.status).toLowerCase()}.`)],
  });

  // Financial figures: bills at the price cap, grants, net cost, payback, illustrative loan.
  const pkg = selectionPackage(r);
  const costClaims: ExplanationClaim[] = [pkg && isNum(pkg.cost_gbp) && plan.length
    ? claim('statement', `Indicative installation cost for ${packageName(pkg.package_id)}: ${fmtGbp(pkg.cost_gbp)} (${pkg.cost_provenance}).`, [span('package.cost_gbp', fmtGbp(pkg.cost_gbp), 'available', 'assumption')])
    : claim('missing_data', 'No indicative cost available for current selection.')];
  const b = r.bills;
  if (b && b.status === 'ok' && isNum(b.saving_gbp) && plan.length) {
    const bs = b.saving_gbp;
    costClaims.push(claim('statement', bs > 0
      ? `Under standard tariff rates, annual energy bills decrease by ${fmtGbp(bs)} (from ${fmtGbp(b.before_gbp)} to ${fmtGbp(b.after_gbp)}).`
      : bs < 0 ? `Under standard tariff rates, annual bills increase by ${fmtGbp(Math.abs(bs))} (from ${fmtGbp(b.before_gbp)} to ${fmtGbp(b.after_gbp)}).`
        : 'Under standard tariff rates, annual bills remain unchanged.',
    [span('bills.saving_gbp', fmtGbp(Math.abs(bs)), 'available', 'derived', bs > 0 ? 'reduction' : bs < 0 ? 'increase' : 'no change', savingSentiment(bs))]));
  } else if (plan.length) {
    costClaims.push(claim('missing_data', `Annual bill variance is ${missingText(b?.status ?? 'not_estimated').toLowerCase()}.`));
  }
  const f = r.finance;
  if (f && f.status === 'ok' && plan.length) {
    if (isNum(f.grants_gbp) && f.grants_gbp > 0 && isNum(f.net_cost_gbp)) {
      costClaims.push(claim('statement', `Available grant schemes may cover up to ${fmtGbp(f.grants_gbp)}, reducing net capital outlay to ${fmtGbp(f.net_cost_gbp)}.`,
        [span('finance.grants_gbp', fmtGbp(f.grants_gbp)), span('finance.net_cost_gbp', fmtGbp(f.net_cost_gbp))]));
    }
    costClaims.push(isNum(f.payback_years)
      ? claim('statement', `Estimated simple payback period: ${f.payback_years.toFixed(1)} years (net cost divided by annual bill savings).`, [span('finance.payback_years', `${f.payback_years.toFixed(1)} years`)])
      : claim('missing_data', 'Payback period not calculated as bill does not decrease with this selection.'));
    const loan = f.illustrative_loan;
    if (loan && isNum(loan.monthly_repayment_gbp)) {
      costClaims.push(claim('caveat', `Financing illustration: a loan covering net capital outlay at ${loan.apr_pct}% APR over ${loan.term_years} years represents approximately ${fmtGbp(loan.monthly_repayment_gbp)}/month.`,
        [span('finance.illustrative_loan.monthly_repayment_gbp', fmtGbp(loan.monthly_repayment_gbp))]));
    }
  }
  sections.push({ id: 'cost', title: 'Financial assessment & bills', claims: costClaims });

  sections.push({
    id: 'value', title: 'Property capital value',
    claims: [r.valuation.status === 'ok' && isNum(r.valuation.low_pct)
      ? claim('caveat', `Statistical valuation range: +${fmtPct(r.valuation.low_pct, 1)} to +${fmtPct(r.valuation.high_pct, 1)} based on national green premium trends.`)
      : claim('missing_data', `Property valuation model: ${r.valuation.reason}.`)],
  });

  const notOk = r.feasibility.filter((f) => f.state !== 'feasible');
  if (notOk.length) {
    sections.push({
      id: 'not_suitable', title: 'Feasibility constraints & checks',
      claims: notOk.map((f) => claim('feasibility',
        f.state === 'infeasible'
          ? `${measureLabel(f.measure)} is unsuitable: ${f.reason_text}`
          : `${measureLabel(f.measure)} requires preliminary inspection: ${f.reason_text}`, [], [f.measure])),
    });
  }

  sections.push({ id: 'caveats', title: 'Technical notes & assumptions', claims: r.warnings.map((w) => claim('caveat', prettyText(w) + (w.endsWith('.') ? '' : '.'))) });

  return {
    scenario_id: r.scenario_id,
    property_id: r.home.home_id,
    sections,
    source: 'template',
    mode: 'frontend_template',
    provider: null,
    model: null,
    fallback_reason: reason,
  };
}
