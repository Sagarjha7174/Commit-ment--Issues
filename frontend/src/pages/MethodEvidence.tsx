import type { ReactNode } from 'react';
import { Clock } from 'lucide-react';
import { useEvidence, useLlmHealth } from '../api/queries';
import type { Evidence } from '../api/schema';
import { barPct, fmtGbp, fmtNumber, humanise } from '../utils/format';
import { SCORE_PART_LABEL, SENSITIVITY_RUN_LABEL } from '../utils/labels';
import { ErrorState, LoadingBlock } from '../components/common/States';
import './pages.css';

const TOC = [
  ['A', 'sources', 'Data sources'], ['B', 'score', 'Score formula'], ['C', 'simulation', 'Simulation'], ['D', 'need', 'Measured vs assumed impacts'],
  ['E', 'gap', 'Measured vs modelled energy'], ['F', 'models', 'ML models'], ['G', 'policy', 'Policy comparison'], ['H', 'regret', 'Regret & stability'],
  ['I', 'value', 'Valuation'], ['J', 'llm', 'LLM safeguards'], ['K', 'scope', 'Coverage of the product concept'],
] as const;

const SCOPE: [string, 'Engine' | 'Presentation' | 'Guidance' | 'Not modelled', string][] = [
  ['Feasibility of each measure', 'Engine', 'Catalogue rules; missing data becomes “needs verification”, never “infeasible”.'],
  ['Three plans for different objectives', 'Engine', 'Exhaustive package search, Pareto filter, featured picks.'],
  ['Occupancy (more / fewer people)', 'Engine', 'baseline_scale ×0.85 / ×1.15, recalculated by the engine.'],
  ['Your own meter reading', 'Engine', 'user_reading replaces the NEED benchmark; provenance becomes “user-provided”.'],
  ['What if things change', 'Engine', 'One-at-a-time sensitivity: does each pick survive?'],
  ['Role: tenant / owner / landlord / flat', 'Presentation', 'Changes wording, permission notes and the request letter.'],
  ['Budget and priority', 'Presentation', 'Flags plans within or over budget; highlights the engine pick for your priority.'],
  ['Stay length (horizon)', 'Presentation', 'Notes on who benefits from permanent upgrades.'],
  ['Permissions and approvals', 'Guidance', 'General UK guidance, always unverified, never “confirmed”.'],
  ['Decision record and saved plans', 'Presentation', 'Download JSON of the exact scenario; saved plans re-run the engine.'],
  ['Bills, grants and payback in £', 'Engine', 'Ofgem price cap Oct–Dec 2026, Boiler Upgrade Scheme grants, net cost and simple payback (D26, D27); your own tariff through a what-if.'],
  ['Illustrative loan', 'Engine', '7% APR over 10 years (configs/finance.json), labelled illustrative: not a Lloyds product, rate or offer.'],
  ['Ranges, not single numbers', 'Engine', 'Seeded Monte Carlo over documented input ranges (D28), shown as P10–P90.'],
  ['Indicative EPC after retrofit', 'Engine', 'SAP model (monotone LightGBM), shown next to the score, never as a new EPC (D34).'],
  ['Property value', 'Engine', 'Hedonic and gradient-boosted models, gated by a sales-match audit and an interval-coverage test (D10, D38).'],
  ['Climate hazards (flood, overheating)', 'Not modelled', 'No hazard data source is connected yet.'],
  ['Maintenance, warranties, contractor availability', 'Not modelled', 'Later expansion.'],
];

function Sec({ letter, id, title, children, lead }: { letter: string; id: string; title: string; children: ReactNode; lead?: ReactNode }) {
  return (
    <section className="section" aria-labelledby={`ev-${id}`}>
      <header className="section-head">
        <p className="kicker"><b>{letter}</b>Method & evidence</p>
        <h2 className="section-title" id={`ev-${id}`}>{title}</h2>
        {lead && <p className="lead">{lead}</p>}
      </header>
      {children}
    </section>
  );
}

function Pending({ what, detail }: { what: string; detail?: unknown }) {
  return (
    <div className="state">
      <span className="pending-badge"><Clock size={14} aria-hidden="true" /> Evaluation pending</span>
      <p className="small">{what}</p>
      {typeof detail === 'string' && <p className="xsmall muted">{detail}</p>}
    </div>
  );
}

function clean(md: string): string {
  return md.replace(/\*\*/g, '').replace(/`/g, '').replace(/^- /gm, '• ');
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${fmtNumber(v * 100, 1)}%`);

type ModelRow = { name: string; version: string | null; shipped: boolean; gates: Record<string, boolean>; headline_val: Record<string, number> };

function ModelsTable({ detail }: { detail: unknown }) {
  const d = (detail ?? {}) as { models?: ModelRow[]; model_switch?: { use_model_baseline?: boolean; rule?: string }; report?: string };
  const rows = d.models ?? [];
  return (
    <>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="sr-only">Models, validation gates and headline validation metrics</caption>
          <thead><tr><th scope="col">Model</th><th scope="col">Shipped</th><th scope="col">Gates (validation)</th><th scope="col">Headline (validation)</th></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.name}>
                <th scope="row">{m.name}<div className="xsmall muted mono">{m.version ?? '—'}</div></th>
                <td><span className={`chip ${m.shipped ? 'chip-saving' : 'chip-blocked'}`}>{m.shipped ? 'Yes' : 'No'}</span></td>
                <td className="small">{Object.entries(m.gates).map(([g, ok]) => <div key={g}>{ok ? '✓' : '✗'} {g.replace(/_/g, ' ')}</div>)}</td>
                <td className="small num">{Object.entries(m.headline_val).map(([k, v]) => <div key={k}>{k.replace(/_/g, ' ')}: {fmtNumber(v, Math.abs(v) < 10 ? 3 : 1)}</div>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="xsmall muted">
        A model ships only if it beats its baseline on validation; the test split was scored once, after every choice was frozen.
        {d.model_switch && <> Modelled baseline energy: <b>{d.model_switch.use_model_baseline ? 'on' : 'off'}</b> ({d.model_switch.rule}).</>} {d.report}
      </p>
    </>
  );
}

type LlmRun = { mode: string; label: string; date: string | null; n: number | null; groundedness: number | null; factual_accuracy: number | null; unsupported_claim_rate: number | null; whatif_success: number | null; refusal_correctness: number | null; items_all_checks_passed: number | null };

function LlmEvalTable({ detail }: { detail: unknown }) {
  const d = (detail ?? {}) as { runs?: LlmRun[]; note?: string | null; targets?: Record<string, number> };
  return (
    <>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="sr-only">LLM evaluation runs on the real engine</caption>
          <thead><tr><th scope="col">Run</th><th scope="col" className="num">n</th><th scope="col" className="num">Groundedness</th><th scope="col" className="num">Factual accuracy</th><th scope="col" className="num">Unsupported claims</th><th scope="col" className="num">What-if success</th><th scope="col" className="num">All checks</th></tr></thead>
          <tbody>
            {(d.runs ?? []).map((r) => (
              <tr key={r.mode}>
                <th scope="row">{r.label}<div className="xsmall muted">{r.date}</div></th>
                <td className="num">{r.n ?? '—'}</td><td className="num">{pct(r.groundedness)}</td><td className="num">{pct(r.factual_accuracy)}</td>
                <td className="num">{pct(r.unsupported_claim_rate)}</td><td className="num">{pct(r.whatif_success)}</td><td className="num">{pct(r.items_all_checks_passed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="xsmall muted">Targets: groundedness ≥ 90%, factual accuracy ≥ 90%, unsupported claims &lt; 5%. {d.note}</p>
    </>
  );
}

function Score({ ev }: { ev: Evidence }) {
  const s = ev.score;
  const miss = s.missing as { rule?: string };
  return (
    <div className="ev-grid">
      <div className="ev-card">
        <h3>Seven fixed weights</h3>
        <div className="weights">
          {Object.entries(s.weights).map(([k, w]) => (
            <div key={k}><span>{SCORE_PART_LABEL[k] ?? k}</span><div className="bar"><span style={{ width: `${barPct(w, 0.25)}%` }} /></div><span className="num">{fmtNumber(w * 100)}%</span></div>
          ))}
        </div>
        <p className="xsmall muted">S = Σ weight × sub-score (0–100), rounded half up. {ev.versions.score_mappings}.</p>
      </div>
      <div className="ev-card">
        <h3>Classes</h3>
        <ul className="small">{[...s.classes].sort((a, b) => b.min - a.min).map((c) => <li key={c.label}><b>{c.label}</b>: {c.min}+</li>)}</ul>
        <h3>Missing data</h3>
        <p className="small">{miss.rule ?? 'See score_mappings.json'}</p>
      </div>
      <div className="ev-card">
        <h3>Sub-score rules</h3>
        <ul className="small stack">
          {Object.entries(s.parts).map(([k, v]) => (
            <li key={k}><b>{SCORE_PART_LABEL[k] ?? k}</b>: {String((v as { rule?: string }).rule ?? (v as { input?: string }).input ?? JSON.stringify(v).slice(0, 140))}</li>
          ))}
        </ul>
        <p className="xsmall muted">Energy intensity percentiles p10 {String(s.intensity_params.p10)} and p90 {String(s.intensity_params.p90)} kWh/m²/yr, frozen on the training split (n = {String(s.intensity_params.n)}).</p>
      </div>
    </div>
  );
}

function Simulation({ ev }: { ev: Evidence }) {
  const g = ev.catalogue.global as Record<string, { value?: unknown; status?: string; note?: string; definition?: string } | unknown>;
  const row = (k: string) => g[k] as { value?: unknown; status?: string; note?: string; definition?: string } | undefined;
  return (
    <>
      <div className="ev-grid">
        {['boiler_efficiency', 'other_gas_share', 'space_share_of_heat_water_gas', 'heat_pump_scop'].map((k) => {
          const v = row(k);
          const val = k === 'heat_pump_scop' ? Object.entries((g[k] ?? {}) as Record<string, number>).map(([a, b]) => `${a} ${b}`).join(' · ') : String(v?.value ?? '—');
          return (
            <div key={k} className="ev-card">
              <h3>{humanise(k)}</h3>
              <p className="serif" style={{ fontSize: '1.6rem' }}>{val}</p>
              {v?.status && <span className="chip">{humanise(v.status)}</span>}
              <p className="xsmall muted">{v?.definition ?? v?.note ?? ''}</p>
            </div>
          );
        })}
      </div>
      <div className="table-wrap" style={{ marginTop: 'var(--s-4)' }}>
        <table className="data-table">
          <caption className="sr-only">Retrofit catalogue {ev.catalogue.version}</caption>
          <thead><tr><th scope="col">Measure</th><th scope="col">Impact low / mid / high</th><th scope="col">Basis</th><th scope="col">Evidence</th><th scope="col">Cost (low / mid / high)</th><th scope="col">Feasibility rule</th></tr></thead>
          <tbody>
            {ev.catalogue.measures.map((m) => {
              const c = (m.cost ?? {}) as Record<string, number | string | null>;
              const rules = (m.applicability_rules ?? {}) as { text?: string };
              return (
                <tr key={m.id}>
                  <th scope="row">{m.label}{m.dependencies.length > 0 && <div className="xsmall muted">after {m.dependencies.map(humanise).join(', ')}</div>}</th>
                  <td className="num">
                    {m.impact && 'scop_mid' in m.impact
                      ? <>SCOP {m.impact.scop_low} / {m.impact.scop_mid} / {m.impact.scop_high}</>
                      : <>{pct(m.impact?.low)} / {pct(m.impact?.mid)} / {pct(m.impact?.high)}</>}
                    {m.impact_units && <div className="xsmall muted">{m.impact_units}</div>}
                  </td>
                  <td className="small">{humanise(m.impact_basis)}<div className="xsmall muted">{m.target_end_use ? `targets ${humanise(m.target_end_use)}` : ''}</div></td>
                  <td>{m.validated ? <span className="chip chip-saving">NEED measured</span> : <span className="chip chip-verify">Assumption / brief range</span>}<div className="xsmall muted">{m.source}</div></td>
                  <td className="num small">{fmtGbp(c.low as number)} / {fmtGbp(c.mid as number)} / {fmtGbp(c.high as number)}{c.note && <div className="xsmall muted">{String(c.note)}</div>}</td>
                  <td className="xsmall">{rules.text ?? '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>Order: loft → cavity wall → solid wall → double glazing → smart thermostat → heat pump → solar PV. Reductions multiply, so overlapping measures are not double-counted; every step reconciles per fuel.</p>
    </>
  );
}

function Gap({ ev }: { ev: Evidence }) {
  const v = ev.simulator_vs_need;
  const max = Math.max(...v.rows.map((r) => Math.max(r.need_median_pct, r.simulated_pct)));
  return (
    <>
      <p className="small" style={{ marginBottom: 12 }}>{v.source}. Basis: {v.basis}. Tolerance ±{v.tolerance_pp} pp.</p>
      <div className="ev-grid">
        {v.rows.map((r) => (
          <div key={r.combination} className="ev-card">
            <h3>{r.combination}</h3>
            <div className="gap-bar" aria-hidden="true">
              <span className="gap-sim" style={{ left: 0, width: `${barPct(r.simulated_pct, max)}%` }} />
              <span className="gap-need" style={{ left: 0, width: `${barPct(r.need_median_pct, max)}%`, height: '50%', top: '25%' }} />
            </div>
            <p className="small">NEED measured median <b>{fmtNumber(r.need_median_pct, 1)}%</b> (n = {fmtNumber(r.need_n)}) · simulated <b>{fmtNumber(r.simulated_pct, 1)}%</b></p>
            <p className={`small ${r.within_tolerance ? 'dir-reduction' : 'dir-increase'}`}>Gap {fmtNumber(r.gap_pp_vs_median, 1)} pp · {r.within_tolerance ? 'within' : 'outside'} tolerance</p>
          </div>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>The simulator overestimates combined fabric savings. This is reported, not tuned away, and every scenario that combines fabric measures carries a warning.</p>
    </>
  );
}

export default function MethodEvidence() {
  const q = useEvidence();
  const llm = useLlmHealth();
  const ev = q.data;
  const vg = (ev?.value_gate ?? {}) as Record<string, unknown>;
  return (
    <div className="page">
      <header className="page-head">
        <p className="kicker"><b>Method</b>How every number is made</p>
        <h1 className="page-title">Method & evidence</h1>
        <p className="lead">What the engine knows, what it assumes, what has been checked against measured data, and what has not been evaluated yet. Figures on this page are read from the engine’s configuration and validation files.</p>
        <details className="howto">
          <summary>In one minute</summary>
          <ul className="small">
            <li>The score and savings come from public data: EPC certificates, national measured savings (NEED) and official carbon factors.</li>
            <li>Where data is missing we say so and never guess zero. Where we assume, we label it.</li>
            <li>The AI only explains results in words; it never produces a number.</li>
          </ul>
        </details>
      </header>
      <nav className="toc" aria-label="Sections">{TOC.map(([l, id, t]) => <a key={id} href={`#ev-${id}`}>{l} · {t}</a>)}</nav>
      {q.isPending && <LoadingBlock label="Loading evidence" lines={6} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {ev && (
        <>
          <Sec letter="A" id="sources" title="Data sources, licences and limits" lead="All open government data for the City of York. Addresses are never exposed: only an outward postcode and a display label.">
            <div className="ev-grid">
              {ev.sources.map((s) => (
                <div key={s.id} className="ev-card"><h3>{s.id} · {s.title}</h3><div className="ev-body">{clean(s.body)}</div></div>
              ))}
            </div>
          </Sec>
          <Sec letter="B" id="score" title="Green Home Score formula"><Score ev={ev} /></Sec>
          <Sec letter="C" id="simulation" title="Retrofit simulation and feasibility" lead={`Catalogue ${ev.catalogue.version}. A missing input makes a measure “needs verification”, never “infeasible”.`}><Simulation ev={ev} /></Sec>
          <Sec letter="D" id="need" title="NEED measured impacts vs assumptions">
            <div className="ev-grid">
              <div className="ev-card"><h3>From NEED measured savings</h3><ul className="small">{ev.catalogue.measures.filter((m) => m.validated).map((m) => <li key={m.id}>{m.label}: {m.impact_method}</li>)}</ul></div>
              <div className="ev-card"><h3>Brief ranges or assumptions (not validated)</h3><ul className="small">{ev.catalogue.measures.filter((m) => !m.validated).map((m) => <li key={m.id}>{m.label}: {m.impact_method ?? m.source}</li>)}</ul></div>
            </div>
          </Sec>
          <Sec letter="E" id="gap" title="Measured vs modelled energy" lead={String(ev.score.intensity_params.note ?? 'Baselines are NEED population benchmarks unless a meter reading is entered.')}><Gap ev={ev} /></Sec>
          <Sec letter="F" id="models" title="ML models vs their baselines">
            {ev.models.status === 'pending'
              ? <Pending what="No trained model has been switched in. The engine uses the NEED benchmark baseline, which is the fallback any model must beat." detail={ev.models.detail} />
              : <ModelsTable detail={ev.models.detail} />}
          </Sec>
          <Sec letter="G" id="policy" title="Fixed checklist vs greedy vs full package search" lead="Three policies run through the same engine with the same objective and budget (£5k, £15k, unlimited).">
            {ev.policy_comparison.status === 'pending' ? <Pending what="Policy A/B/C results have not been saved by the evaluation pipeline." detail={ev.policy_comparison.detail} /> : <pre className="ev-body">{JSON.stringify(ev.policy_comparison.detail, null, 2)}</pre>}
          </Sec>
          <Sec letter="H" id="regret" title="Regret, feasibility violations and stability">
            <Pending what="Regret and feasibility-violation rates come from the policy comparison above." />
            <div className="ev-card" style={{ marginTop: 12 }}>
              <h3>Per-home stability (live in every scenario)</h3>
              <p className="small">Each featured pick is rerun under {Object.keys(SENSITIVITY_RUN_LABEL).length} one-at-a-time changes and reported as “survives k/10”. See the decision audit on any home.</p>
              <ul className="small">{Object.values(SENSITIVITY_RUN_LABEL).map((l) => <li key={l}>{l}</li>)}</ul>
            </div>
          </Sec>
          <Sec letter="I" id="value" title="Property valuation">
            <div className="ev-grid">
              <div className="ev-card">
                <h3>Sales-match audit</h3>
                <p className="small">Status <b>{String(vg.status ?? '—')}</b>: {String(vg.correct ?? '—')}/{String(vg.n_audited ?? '—')} hand-checked matches correct (precision {String(vg.precision ?? '—')}).</p>
                <p className="xsmall muted">{String(vg.uncertainty_note ?? '')}</p>
              </div>
              <div className="ev-card">
                <h3>Value range</h3>
                {(() => {
                  const cc = (vg.coverage_check ?? null) as { result?: string; empirical_coverage?: number; nominal?: number; n_test?: number; accept_range?: number[] } | string | null;
                  return cc && typeof cc === 'object'
                    ? <p className="small">Coverage check <b>{cc.result}</b>: the {pct(cc.nominal)} interval covered {pct(cc.empirical_coverage)} of {cc.n_test} held-out test sales (accepted {cc.accept_range?.map((x) => pct(x)).join('–')}). Status <b>{String(vg.status ?? '—')}</b>: scenarios show an indicative range. Price associations are never presented as causal uplift.</p>
                    : <p className="small">Coverage check: {String(cc ?? 'pending')}. Until a value model passes it, every scenario reports value as “not estimated”. Price associations are never presented as causal uplift.</p>;
                })()}
              </div>
            </div>
          </Sec>
          <Sec letter="J" id="llm" title="LLM safeguards">
            <div className="ev-grid">
              <div className="ev-card"><h3>It cannot write a number</h3><p className="small">The model writes placeholders; code fills every figure from the scenario result. A checker rejects stray digits, wrong directions (calling a rise a saving), unsupported comparisons and infeasible recommendations.</p></div>
              <div className="ev-card"><h3>Bound to one scenario</h3><p className="small">Explanations carry the scenario ID and are discarded if it does not match the one on screen (HTTP 409 for stale requests).</p></div>
              <div className="ev-card"><h3>Deterministic fallback</h3><p className="small">Any failure falls back to a template. This app renders every number without the LLM, and has a template-mode switch.</p></div>
              <div className="ev-card">
                <h3>Status here</h3>
                <p className="small">{llm.data ? `LLM service reachable; generation ${llm.data.enabled ? 'enabled' : 'disabled'}.` : 'LLM service not connected: explanations use the template.'}</p>
                {ev.llm_evaluation.status === 'pending' && <Pending what="LLM evaluation on the real engine and York demo homes." detail={ev.llm_evaluation.detail} />}
              </div>
            </div>
            {ev.llm_evaluation.status !== 'pending' && <div style={{ marginTop: 12 }}><LlmEvalTable detail={ev.llm_evaluation.detail} /></div>}
          </Sec>
          <Sec letter="K" id="scope" title="Coverage of the product concept" lead="How each idea from the product concept (roles, horizons, budgets, permissions, climate, occupancy, the decision record) is handled today. Nothing marked “not modelled” is ever shown as a number.">
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th scope="col">Concept</th><th scope="col">Status</th><th scope="col">How</th></tr></thead>
                <tbody>
                  {SCOPE.map(([c, st, how]) => (
                    <tr key={c}><th scope="row">{c}</th><td><span className={`chip ${st === 'Engine' ? 'chip-saving' : st === 'Guidance' ? 'chip-verify' : st === 'Not modelled' ? 'chip-blocked' : ''}`}>{st}</span></td><td className="small">{how}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Sec>
        </>
      )}
    </div>
  );
}
