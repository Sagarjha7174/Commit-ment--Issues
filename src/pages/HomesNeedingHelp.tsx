import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Info } from 'lucide-react';
import { usePortfolio, useTransport } from '../api/queries';
import type { PortfolioRow } from '../api/schema';
import { barPct, fmtKg, fmtNumber, fmtPct, fmtSigned, fmtTonnes, missingText } from '../utils/format';
import { packageName } from '../utils/labels';
import { EmptyState, ErrorState, LoadingBlock } from '../components/common/States';
import './pages.css';

type SortKey = 'potential' | 'score' | 'carbon';
const PAGE = 15;

function cmpNullLast(a: number | null, b: number | null, dir: 1 | -1) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return (a - b) * dir;
}

export default function HomesNeedingHelp() {
  const t = useTransport();
  const [topN, setTopN] = useState(100);
  const q = usePortfolio({ top_n: topN });
  const [search, setSearch] = useState('');
  const [cls, setCls] = useState('all');
  const [complete, setComplete] = useState('all');
  const [potential, setPotential] = useState('all');
  const [sort, setSort] = useState<SortKey>('potential');
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    const all = q.data?.homes ?? [];
    const s = search.trim().toLowerCase();
    const out = all.filter((r) =>
      (!s || r.home_id.toLowerCase().includes(s) || r.display_label.toLowerCase().includes(s) || (r.postcode_outward ?? '').toLowerCase().includes(s))
      && (cls === 'all' || r.classification === cls)
      && (complete === 'all' || (complete === 'complete' ? r.completeness === '7/7' : r.completeness !== '7/7'))
      && (potential === 'all' || (potential === 'available' ? r.improvement_potential_pct != null : r.improvement_potential_pct == null)));
    if (sort === 'potential') return out; // engine order: improvement potential, unavailable last
    return [...out].sort((a: PortfolioRow, b: PortfolioRow) =>
      sort === 'score' ? cmpNullLast(a.score, b.score, 1) : cmpNullLast(a.carbon_saving_kg, b.carbon_saving_kg, -1));
  }, [q.data, search, cls, complete, potential, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const cur = Math.min(page, pages - 1);
  const shown = rows.slice(cur * PAGE, cur * PAGE + PAGE);
  const maxPot = Math.max(0, ...rows.map((r) => r.improvement_potential_pct ?? 0));
  const sm = q.data?.summary;
  const reset = () => setPage(0);

  return (
    <div className="page">
      <header className="page-head">
        <p className="kicker"><b>York</b>Opportunity view</p>
        <h1 className="page-title">Homes needing help</h1>
        <p className="lead">Poor and Very poor homes ranked by how much purchased energy their confirmed feasible package could save. This is an opportunity view for planning support. It is <b>not</b> a lending, eligibility or credit decision.</p>
        <details className="howto">
          <summary>How to read this page</summary>
          <ul className="small">
            <li><b>Score</b> is the 0–100 Green Home Score; Poor and Very poor homes are listed.</li>
            <li><b>Improvement potential</b> is the share of bought energy the home could save with every improvement the engine thinks is possible. “Unavailable” means we lack the data, not that nothing can be done.</li>
            <li>Press <b>Open</b> to see any home step by step, the same way a homeowner would.</li>
          </ul>
        </details>
      </header>

      {q.data?.data_mode === 'demo_subset' && (
        <p className="callout callout-verify" role="note"><Info size={16} aria-hidden="true" /> {q.data.data_note} The live backend runs the same code over all York homes.</p>
      )}

      {q.isPending && <LoadingBlock label="Loading the portfolio" lines={5} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}

      {sm && (
        <>
          <div className="strip" aria-label="Portfolio summary">
            <div><span className="kicker">Homes scored</span><b className="num">{fmtNumber(sm.homes)}</b></div>
            <div><span className="kicker">Poor or Very poor</span><b className="num">{fmtNumber(sm.flagged_poor_or_very_poor)}</b></div>
            <div><span className="kicker">Median potential</span><b className="num">{fmtPct(sm.median_improvement_potential_pct, 0)}</b></div>
            <div><span className="kicker">Carbon potential</span><b className="num">{fmtTonnes(sm.total_carbon_saving_potential_t)}</b></div>
            <div><span className="kicker">Incomplete data</span><b className="num">{fmtPct(sm.share_incomplete_data_pct, 0)}</b></div>
            <div><span className="kicker">Potential unavailable</span><b className="num">{fmtNumber(sm.flagged_potential_unavailable)}</b></div>
          </div>
          <div className="panel" style={{ marginBottom: 'var(--s-5)' }}>
            <p className="kicker">Homes by score class</p>
            <div className="weights" style={{ marginTop: 8 }}>
              {Object.entries(sm.count_by_class).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <div key={k}><span>{k}</span><div className={`bar ${k === 'Poor' || k === 'Very poor' ? 'bar-increase' : ''}`}><span style={{ width: `${barPct(v, sm.homes)}%` }} /></div><span className="num small">{fmtNumber(v)}</span></div>
              ))}
            </div>
            <ul className="xsmall muted" style={{ marginTop: 8, paddingLeft: '1em' }}>{sm.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>

          <div className="filters">
            <div className="field grow">
              <label htmlFor="hs">Search ID, label or outward postcode</label>
              <input id="hs" className="input" value={search} onChange={(e) => { setSearch(e.target.value); reset(); }} placeholder="e.g. YO31" />
            </div>
            <div className="field">
              <label htmlFor="hc">Score class</label>
              <select id="hc" className="input" value={cls} onChange={(e) => { setCls(e.target.value); reset(); }}>
                <option value="all">Poor and Very poor</option><option value="Poor">Poor</option><option value="Very poor">Very poor</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="hd">Data completeness</label>
              <select id="hd" className="input" value={complete} onChange={(e) => { setComplete(e.target.value); reset(); }}>
                <option value="all">Any</option><option value="complete">Complete (7/7)</option><option value="incomplete">Incomplete</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="hp">Improvement potential</label>
              <select id="hp" className="input" value={potential} onChange={(e) => { setPotential(e.target.value); reset(); }}>
                <option value="all">Any</option><option value="available">Estimated</option><option value="unavailable">Unavailable</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="hsort">Sort</label>
              <select id="hsort" className="input" value={sort} onChange={(e) => { setSort(e.target.value as SortKey); reset(); }}>
                <option value="potential">Improvement potential (engine order)</option><option value="score">Lowest score first</option><option value="carbon">Most carbon saving</option>
              </select>
            </div>
            {t.kind === 'live' && (
              <div className="field">
                <label htmlFor="htop">Load from server</label>
                <select id="htop" className="input" value={topN} onChange={(e) => { setTopN(Number(e.target.value)); reset(); }}>
                  {[50, 100, 250, 500].map((n) => <option key={n} value={n}>Top {n}</option>)}
                </select>
              </div>
            )}
          </div>
          <p className="xsmall muted" style={{ marginBottom: 8 }}>EPC-band and property-type filters need those fields in the portfolio response (requested in docs/API_CONTRACT.md).</p>

          {shown.length === 0 ? <EmptyState title="No homes match these filters" /> : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Homes needing help, {rows.length} matching</caption>
                <thead>
                  <tr>
                    <th scope="col">Home</th><th scope="col" className="num">Score</th><th scope="col">Main issues</th>
                    <th scope="col">Improvement potential</th><th scope="col" className="num">Carbon saving</th><th scope="col" className="num">Elec. saving</th><th scope="col"><span className="sr-only">Open</span></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.home_id}>
                      <th scope="row">
                        <div><b>{r.display_label}</b></div>
                        <div className="mono xsmall muted">{r.home_id}</div>
                        <div className="xsmall">Data {r.completeness}{r.missing_parts.length > 0 && <span className="muted"> · missing {r.missing_parts.join(', ')}</span>}</div>
                      </th>
                      <td className="num"><b>{r.score ?? '—'}</b><div className="xsmall">{r.classification}</div></td>
                      <td className="issues-cell xsmall"><ul>{r.key_issues.slice(0, 3).map((k) => <li key={k}>{k}</li>)}</ul></td>
                      <td>
                        {r.improvement_potential_pct != null ? (
                          <>
                            <b className="num">{fmtPct(r.improvement_potential_pct, 1)}</b>
                            <div className="bar bar-saving pot-bar"><span style={{ width: `${barPct(r.improvement_potential_pct, maxPot)}%` }} /></div>
                            <div className="xsmall muted">{packageName(r.package_id)}</div>
                          </>
                        ) : <span className="v-unknown">{missingText(r.improvement_potential_status)}{r.improvement_potential_reason ? `: ${r.improvement_potential_reason}` : ''}</span>}
                      </td>
                      <td className="num">{fmtKg(r.carbon_saving_kg)}</td>
                      <td className="num">{fmtSigned(r.elec_saving_kwh, 'kWh')}</td>
                      <td><Link className="btn btn-sm btn-ghost" to={`/home/${r.home_id}`} aria-label={`Open ${r.display_label} in My Home`}>Open <ArrowRight size={14} aria-hidden="true" /></Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pager" role="navigation" aria-label="Pages">
            <span className="small muted">{rows.length} homes · page {cur + 1} of {pages}</span>
            <button className="btn btn-sm btn-ghost" disabled={cur === 0} onClick={() => setPage(cur - 1)}>Previous</button>
            <button className="btn btn-sm btn-ghost" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
