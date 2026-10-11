/**
 * The six questions every recommendation should answer (concept doc §15), answered from the confirmed
 * engine result plus the user's optional situation. Unknowns are said plainly, never filled in.
 */
import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle } from 'lucide-react';
import type { MeasureId, ScenarioResult } from '../../api/schema';
import { HORIZON_TEXT, type Situation } from '../../hooks/useSituation';
import { fmtGbp, fmtNumber, isNum } from '../../utils/format';
import { MEASURE_SHORT, measureLabel, packageIdFor, SENSITIVITY_RUN_LABEL } from '../../utils/labels';
import { permissionFor } from '../../utils/permissions';
import { selectionPackage } from '../../utils/scenarioDiff';

type Tone = 'ok' | 'attention' | 'unknown';
interface Answer { q: string; tone: Tone; headline: string; body: ReactNode }

const ICON = { ok: CheckCircle2, attention: AlertTriangle, unknown: HelpCircle };
const TONE_TEXT: Record<Tone, string> = { ok: 'Looks fine', attention: 'Needs attention', unknown: 'Not known yet' };

function planAnswers(r: ScenarioResult, s: Situation): Answer[] {
  const sel = r.measures_applied;
  const fmap = new Map(r.feasibility.map((f) => [f.measure, f]));
  const perms = sel.map((m) => ({ m, p: permissionFor(m, fmap.get(m), s.role, r.home) }));
  const survey = perms.filter((x) => x.p.state === 'needs_survey');
  const consent = perms.filter((x) => x.p.state === 'needs_consent' || x.p.state === 'needs_building_approval');
  const pkg = selectionPackage(r);
  const featured = r.packages?.featured.find((f) => f.package_id === packageIdFor(sel));
  const surv = featured ? r.sensitivity?.survival[featured.objective] : undefined;
  const scale = (r.request.assumptions.baseline_scale ?? 1);
  const unvalidated = r.simulation.measures.filter((m) => m.status === 'ok' && m.validated_impact === false);

  if (!sel.length) {
    return [{ q: 'Can I do it?', tone: 'unknown', headline: 'No improvements are selected yet.', body: 'Pick a plan in step 2 or choose improvements in step 3.' }];
  }

  const afford: Answer = (() => {
    const fin = r.finance && r.finance.status === 'ok' ? r.finance : null;
    const grants = r.request.assumptions.apply_grants && isNum(fin?.grants_gbp) ? fin!.grants_gbp! : 0;
    const cost = fin ? (grants > 0 ? fin.net_cost_gbp : fin.gross_cost_gbp) : pkg?.cost_gbp;
    if (cost == null) return { q: 'Can I afford it now?', tone: 'unknown', headline: 'No cost estimate for this selection.', body: 'The engine has no indicative cost for this combination.' };
    const bill = r.bills && r.bills.status === 'ok' ? r.bills.saving_gbp : null;
    const loan = fin?.illustrative_loan;
    const base = (
      <>
        Indicative cost <b>{fmtGbp(cost)}</b>{grants > 0 && <> after {fmtGbp(grants)} of grants, subject to eligibility (from {fmtGbp(fin!.gross_cost_gbp)})</>} (typical EPC figures for York, not a quote).{' '}
        {isNum(bill)
          ? <>Energy bills {bill >= 0 ? <>fall by about <b>{fmtGbp(bill)}</b></> : <>rise by about <b>{fmtGbp(-bill)}</b></>} a year at the price cap{isNum(fin?.payback_years) ? <>, so it pays back in about {fmtNumber(fin!.payback_years!, fin!.payback_years! < 10 ? 1 : 0)} years</> : bill <= 0 ? ', so it does not pay back through bills' : ''}.</>
          : 'Bill savings aren’t estimated without a baseline.'}
        {loan && isNum(loan.monthly_repayment_gbp) && <> An illustrative {loan.term_years}-year loan at {fmtNumber(loan.apr_pct, 1)}% would cost about {fmtGbp(loan.monthly_repayment_gbp)} a month (not a Lloyds product or offer).</>}
      </>
    );
    if (!s.budgetAnswered) return { q: 'Can I afford it now?', tone: 'unknown', headline: `About ${fmtGbp(cost)}.`, body: <>{base} Tell us your budget in “Your situation” to check the fit.</> };
    if (s.budgetGbp === null) return { q: 'Can I afford it now?', tone: 'ok', headline: `About ${fmtGbp(cost)}; you said there’s no fixed limit.`, body: base };
    const fits = cost <= s.budgetGbp;
    return {
      q: 'Can I afford it now?', tone: fits ? 'ok' : 'attention',
      headline: fits ? `About ${fmtGbp(cost)}: within your ${fmtGbp(s.budgetGbp)} budget.` : `About ${fmtGbp(cost)}: more than your ${fmtGbp(s.budgetGbp)} budget.`,
      body: <>{base}{!fits && ' Doing it in stages (cheapest first) is one option; check step 2 for a lower-cost plan.'}</>,
    };
  })();

  return [
    {
      q: 'Can I do it?',
      tone: survey.length || consent.length ? 'attention' : 'ok',
      headline: consent.length
        ? `${consent.length} of ${sel.length} need permission from ${consent[0].p.who}.`
        : survey.length ? `${survey.length} of ${sel.length} need a survey first.` : 'Every selected improvement is possible for this home on its records.',
      body: (
        <ul>
          {perms.map(({ m, p }) => <li key={m}><b>{MEASURE_SHORT[m]}</b>: {p.label}{p.who ? ` — ask ${p.who}` : ''}</li>)}
        </ul>
      ),
    },
    afford,
    {
      q: 'Will it work for me?',
      tone: r.baseline.source === 'user_provided' ? 'ok' : r.baseline.source === 'unavailable' ? 'unknown' : 'attention',
      headline: r.baseline.source === 'user_provided' ? 'Worked out from your own meter reading.'
        : r.baseline.source === 'unavailable' ? 'We don’t know this home’s energy use, so savings can’t be worked out.'
          : 'Worked out from typical homes like yours, not your own meter.',
      body: (
        <>
          {r.baseline.source !== 'user_provided' && <p>Adding your annual meter readings in step 3 makes the numbers yours.</p>}
          {scale !== 1 && <p>Includes your scenario of {scale > 1 ? 'more' : 'fewer'} people at home (energy use ×{scale}).</p>}
          {s.horizon !== 'unknown' && <p>You expect to stay {HORIZON_TEXT[s.horizon].toLowerCase()}.{s.horizon === 'lt2' && ' Permanent upgrades stay with the home, so much of the benefit may go to the next occupant.'}</p>}
        </>
      ),
    },
    {
      q: 'What if things change?',
      tone: surv ? (surv.changed_under.length ? 'attention' : 'ok') : 'unknown',
      headline: surv
        ? `This plan stays the engine’s pick in ${surv.survives.replace('/', ' of ')} “what if” tests.`
        : 'Your own mix isn’t one of the three tested plans, so its stability isn’t measured.',
      body: surv
        ? (surv.changed_under.length ? <>It could change if: {surv.changed_under.map((n) => (SENSITIVITY_RUN_LABEL[n] ?? n).toLowerCase()).join('; ')}.</> : 'It held under every tested change.')
        : 'Tests include energy use ±15%, heat-pump efficiency, the gas split and savings high or low.',
    },
    {
      q: 'How do I know it’s real?',
      tone: unvalidated.length ? 'attention' : 'ok',
      headline: 'All figures are estimates from public data, not guarantees.',
      body: (
        <>
          {unvalidated.length > 0 && <p>Savings for {unvalidated.map((m) => measureLabel(m.measure)).join(', ')} aren’t checked against measured national data (NEED) yet.</p>}
          {r.warnings.some((w) => w.includes('overestimated')) && <p>When several insulation measures are combined, the model saves more than real homes did: treat combined savings as optimistic.</p>}
          <p>Open “Expert details” to see where each number comes from.</p>
        </>
      ),
    },
    {
      q: 'What happens after installation?',
      tone: 'unknown',
      headline: `Suggested order: ${(r.install_sequence ?? r.simulation.measures.map((m) => m.measure)).map((m) => MEASURE_SHORT[m as MeasureId]).join(' → ')}.`,
      body: 'Insulate before a heat pump so it can be smaller. Maintenance, servicing and replacement costs aren’t modelled yet: keep the decision record so you can compare later.',
    },
  ];
}

/** The first three answers decide whether to go ahead; the rest are background, folded away. */
const MAIN_CHECKS = 3;

function CheckList({ answers, start }: { answers: Answer[]; start: number }) {
  return (
    <ol className="check" start={start + 1}>
      {answers.map((a, j) => {
        const i = start + j;
        const Icon = ICON[a.tone];
        return (
          <li key={a.q} className={`check-item check-${a.tone}`}>
            <Icon size={20} aria-hidden="true" className="check-icon" />
            <div>
              <p className="check-q"><span className="check-n">{i + 1}</span>{a.q} <span className="sr-only">({TONE_TEXT[a.tone]})</span></p>
              <p className="check-head">{a.headline}</p>
              <div className="check-body small">{a.body}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function PlanCheck({ result, situation }: { result: ScenarioResult; situation: Situation }) {
  const answers = planAnswers(result, situation);
  const more = answers.slice(MAIN_CHECKS);
  return (
    <>
      <CheckList answers={answers.slice(0, MAIN_CHECKS)} start={0} />
      {more.length > 0 && (
        <details className="howto check-more">
          <summary>{more.length} more checks (stability, evidence, after installation)</summary>
          <CheckList answers={more} start={MAIN_CHECKS} />
        </details>
      )}
    </>
  );
}

