/**
 * Bills, grants, net cost, payback and the illustrative loan for the scenario on screen (engine D26, D27), plus the
 * Monte Carlo ranges (D28). Every number is an engine field; nothing is added or divided here.
 */
import { Banknote, PiggyBank, Receipt, Shuffle } from 'lucide-react';
import type { ScenarioResult } from '../../api/schema';
import { billsEvidence, rangeEvidence } from '../../utils/evidence';
import { fmtGbp, fmtNumber, fmtPct, isNum, missingText, savingDirection } from '../../utils/format';
import { DirectionTag, Val } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';

const RANGE_ROWS: { key: string; label: string; unit: string }[] = [
  { key: 'gas_saving_kwh', label: 'Gas saving', unit: 'kWh/yr' },
  { key: 'elec_saving_kwh', label: 'Electricity saving', unit: 'kWh/yr' },
  { key: 'carbon_saving_kg', label: 'Carbon saving', unit: 'kg CO₂e/yr' },
  { key: 'bill_saving_gbp', label: 'Bill saving', unit: '£/yr' },
];

function signedGbp(v: number | null | undefined, status?: string | null): string {
  if (!isNum(v)) return missingText(status ?? 'not_estimated');
  const s = fmtGbp(Math.abs(v));
  return Math.abs(v) < 0.5 ? s : v > 0 ? `${s} less` : `${s} more`;
}

export function YearsText({ years }: { years: number | null | undefined }) {
  if (!isNum(years)) return <>Not reached (the bill does not fall)</>;
  return <>{fmtNumber(years, years < 10 ? 1 : 0)} years</>;
}

export function MoneyPanel({ result: r }: { result: ScenarioResult }) {
  const b = r.bills;
  const f = r.finance;
  const u = r.uncertainty;
  const prov = r.request.assumptions.gas_price_p != null || r.request.assumptions.elec_price_p != null ? 'user_provided' : 'assumption';
  const loan = f?.illustrative_loan;

  return (
    <div className="panel money-panel" aria-labelledby="money-title">
      <div className="row"><p className="kicker" id="money-title">Bills, grants and payback</p><span className="spacer" /><WhyButton build={() => billsEvidence(r)} /></div>
      {!b || b.status !== 'ok' ? (
        <p className="small v-unknown">Bills are {missingText(b?.status ?? 'not_estimated').toLowerCase()}{b?.reason ? `: ${b.reason}` : ''}. The engine needs a baseline to price energy use; nothing is filled with zero.</p>
      ) : (
        <div className="money-grid">
          <div className="money-cell">
            <p className="kicker"><Receipt size={14} aria-hidden="true" /> Energy bill a year</p>
            <p className="money-value num"><Val provenance={prov}>{fmtGbp(b.before_gbp)} → {fmtGbp(b.after_gbp)}</Val></p>
            <p className="small">{signedGbp(b.saving_gbp)} a year <DirectionTag direction={savingDirection(b.saving_gbp)} label={isNum(b.saving_gbp) && b.saving_gbp < 0 ? 'bill rises' : 'bill falls'} /></p>
            <p className="xsmall muted">Gas {signedGbp(b.gas_saving_gbp)} · electricity {signedGbp(b.elec_saving_gbp)}{isNum(b.standing_saving_gbp) && Math.abs(b.standing_saving_gbp) >= 0.5 ? ` · standing charges ${signedGbp(b.standing_saving_gbp)}` : ''}</p>
            <p className="xsmall muted">At {String(b.prices.gas_p_per_kwh ?? '—')}p/kWh gas and {String(b.prices.elec_p_per_kwh ?? '—')}p/kWh electricity{prov === 'user_provided' ? ' (your tariff)' : ' (price cap)'}.</p>
          </div>
          <div className="money-cell">
            <p className="kicker"><Banknote size={14} aria-hidden="true" /> Cost of this plan</p>
            {f && f.status === 'ok' ? (
              <>
                <p className="money-value num"><Val tier="estimated">{fmtGbp(f.net_cost_gbp)}</Val></p>
                <p className="small">{isNum(f.grants_gbp) && f.grants_gbp > 0 ? <>after {fmtGbp(f.grants_gbp)} of grants (from {fmtGbp(f.gross_cost_gbp)})</> : <>no grant applies</>}</p>
                {f.grant_notes.map((n) => <p key={n} className="xsmall muted">{n}</p>)}
              </>
            ) : <p className="small v-unknown">{missingText(f?.status ?? 'not_estimated')}{f?.reason ? `: ${f.reason}` : ''}</p>}
          </div>
          <div className="money-cell">
            <p className="kicker"><PiggyBank size={14} aria-hidden="true" /> Simple payback</p>
            <p className="money-value num"><Val tier="estimated"><YearsText years={f?.payback_years} /></Val></p>
            <p className="xsmall muted">Net cost ÷ yearly bill saving, at today’s prices. Not a return on investment.</p>
            {loan && (
              <p className="small loan">
                Illustrative loan at {fmtNumber(loan.apr_pct, 1)}% over {loan.term_years} years: <b>{fmtGbp(loan.monthly_repayment_gbp)}</b> a month vs a bill saving of {fmtGbp(loan.monthly_bill_saving_gbp)} a month
                {loan.saving_covers_repayment === false ? ' (the saving does not cover the repayment)' : loan.saving_covers_repayment ? ' (the saving covers the repayment)' : ''}.
                <span className="xsmall muted"> Not a Lloyds product, rate or offer.</span>
              </p>
            )}
          </div>
        </div>
      )}

      {u && u.status === 'ok' && (
        <div className="ranges">
          <div className="row"><p className="kicker"><Shuffle size={14} aria-hidden="true" /> Ranges from {u.n_draws ?? 'many'} engine runs</p><span className="spacer" /><WhyButton build={() => rangeEvidence(r)} /></div>
          <div className="table-wrap"><table className="data-table range-table">
            <caption className="sr-only">Monte Carlo ranges: 10th, 50th and 90th percentiles</caption>
            <thead><tr><th scope="col">Result</th><th scope="col">Low (P10)</th><th scope="col">Middle (P50)</th><th scope="col">High (P90)</th></tr></thead>
            <tbody>
              {RANGE_ROWS.map(({ key, label, unit }) => {
                const q = u.percentiles[key];
                if (!q) return null;
                return (
                  <tr key={key}>
                    <th scope="row">{label} <span className="xsmall muted">{unit}</span></th>
                    <td className="num">{fmtNumber(q.p10)}</td><td className="num">{fmtNumber(q.p50)}</td><td className="num">{fmtNumber(q.p90)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
          <p className="xsmall muted">
            {isNum(u.prob_carbon_cut_ge_threshold) && <>Carbon falls by at least {fmtNumber(u.threshold_pct ?? 10)}% in {fmtPct(100 * u.prob_carbon_cut_ge_threshold)} of runs. </>}
            {isNum(u.prob_bill_falls) && <>The bill falls in {fmtPct(100 * u.prob_bill_falls)} of runs. </>}
            {u.label ? `${u.label.charAt(0).toUpperCase()}${u.label.slice(1)}.` : null}
          </p>
        </div>
      )}
    </div>
  );
}
