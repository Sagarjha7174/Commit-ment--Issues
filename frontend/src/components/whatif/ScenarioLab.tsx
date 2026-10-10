import { useState, type FormEvent } from 'react';
import { History, MessageSquareText, RotateCcw, Sparkles } from 'lucide-react';
import { MEASURE_ORDER, type MeasureId, type ScenarioResult } from '../../api/schema';
import { useLlmHealth, useSnapshotManifest, useTransport } from '../../api/queries';
import { ERROR_TITLES, toApiError } from '../../api/errors';
import type { WhatIfResponse } from '../../api/schema';
import { draftOf, type ScenarioLab as Lab } from '../../hooks/useScenarioLab';
import { fmtGbp, fmtKg, fmtKwh, fmtNumber, fmtPct, fmtSigned, isNum, savingDirection, shortId } from '../../utils/format';
import { assumptionLabel, MEASURE_SHORT, measureLabel, packageName } from '../../utils/labels';
import { diffScenarios, type DiffRow } from '../../utils/scenarioDiff';
import { DirectionTag } from '../common/Knowledge';
import { ErrorState, SectionHeader } from '../common/States';
import { ScenarioIdBadge } from '../common/ScenarioIdBadge';
import './lab.css';

function fmtRow(row: DiffRow, v: number | null, status: string | null | undefined): string {
  if (row.unit === 'kwh') return row.kind === 'saving' ? fmtSigned(v, 'kWh/yr', status) : fmtKwh(v, status);
  if (row.unit === 'kg') return row.kind === 'saving' ? fmtSigned(v, 'kg/yr', status) : fmtKg(v, status);
  if (row.unit === 'gbp') return fmtGbp(v, status ?? 'not_estimated');
  if (row.unit === 'pct') return fmtPct(v, 1, status);
  return isNum(v) ? `${fmtNumber(v)}/100` : 'Not estimated';
}

export function Diff({ prev, curr }: { prev: ScenarioResult; curr: ScenarioResult }) {
  const d = diffScenarios(prev, curr);
  const flips = d.featured.filter((f) => f.changed);
  return (
    <div className="diff panel">
      <div className="row">
        <p className="kicker">What changed</p>
        <span className="spacer" />
        <span className="mono xsmall">{shortId(d.fromId)} → {shortId(d.toId)}</span>
      </div>
      <div className="row diff-changes">{d.changes.map((c) => <span key={c} className="chip chip-ink">{c}</span>)}</div>
      <table className="diff-table">
        <caption className="sr-only">Engine values in the previous and the new scenario</caption>
        <thead><tr><th scope="col">Result</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
        <tbody>
          {d.rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              <td className="num muted">{fmtRow(row, row.before, row.status?.[0])}</td>
              <td className="num">
                <b>{fmtRow(row, row.after, row.status?.[1])}</b>
                {row.kind === 'saving' && row.key === 'elec' && savingDirection(row.after) === 'increase' && <> <DirectionTag direction="increase" label="use rises" /></>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="diff-decision">
        <p className="kicker">Did the recommendation change?</p>
        {flips.length === 0
          ? <p className="small"><b>No.</b> All three featured picks are the same in both scenarios.</p>
          : flips.map((f) => (
            <p key={f.objective} className="small"><b>{f.label}:</b> {packageName(f.before)} → <b>{packageName(f.after)}</b></p>
          ))}
        {d.baselineSource[0] !== d.baselineSource[1] && <p className="small">Baseline source changed: {d.baselineSource[0]} → {d.baselineSource[1]}.</p>}
      </div>
    </div>
  );
}

/** Your own unit rates (D26) and whether grants count towards the cost (D27); the engine reprices everything. */
export function TariffForm({ lab, result }: { lab: Lab; result: ScenarioResult }) {
  const a = lab.state.draft.assumptions;
  const [gas, setGas] = useState(a.gas_price_p != null ? String(a.gas_price_p) : '');
  const [elec, setElec] = useState(a.elec_price_p != null ? String(a.elec_price_p) : '');
  const [err, setErr] = useState<string | null>(null);
  const t = useTransport();
  // The result's prices are the cap only when the result itself used no custom rate.
  const ra = result.request.assumptions;
  const cap = ra.gas_price_p == null && ra.elec_price_p == null ? result.bills?.prices : undefined;
  const parse = (s: string): number | null | 'bad' => {
    if (s.trim() === '') return null;
    const n = Number(s);
    return Number.isFinite(n) && n >= 0 && n < 500 ? n : 'bad';
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const g = parse(gas);
    const el = parse(elec);
    if (g === 'bad' || el === 'bad') return setErr('Enter a unit rate in pence per kWh, between 0 and 499.');
    setErr(null);
    lab.setAssumptions({ gas_price_p: g, elec_price_p: el });
  };
  const custom = a.gas_price_p != null || a.elec_price_p != null;
  return (
    <form className="lab-card" onSubmit={submit} noValidate>
      <h3>Your tariff and grants</h3>
      <p className="small muted">Blank = the Ofgem price cap{cap ? ` (${String(cap.gas_p_per_kwh)}p gas, ${String(cap.elec_p_per_kwh)}p electricity per kWh)` : ''}. A heat-pump tariff can change which plan pays back.</p>
      <div className="lab-fields">
        <div className="field">
          <label htmlFor="gas-p">Gas, pence per kWh</label>
          <input id="gas-p" className="input" inputMode="decimal" value={gas} onChange={(e) => setGas(e.target.value)} aria-describedby="tariff-err" />
        </div>
        <div className="field">
          <label htmlFor="elec-p">Electricity, pence per kWh</label>
          <input id="elec-p" className="input" inputMode="decimal" value={elec} onChange={(e) => setElec(e.target.value)} aria-describedby="tariff-err" />
        </div>
      </div>
      <p id="tariff-err" className="field-error" role={err ? 'alert' : undefined}>{err}</p>
      <div className="row">
        <button className="btn btn-sm" type="submit">Recalculate with my tariff</button>
        {custom && <button className="btn btn-sm btn-ghost" type="button" onClick={() => { setGas(''); setElec(''); lab.setAssumptions({ gas_price_p: null, elec_price_p: null }); }}>Back to the price cap</button>}
      </div>
      <div className="field">
        <span className="label" id="grants-l">Grants in the cost</span>
        <div className="seg" role="group" aria-labelledby="grants-l">
          <button type="button" aria-pressed={a.apply_grants} onClick={() => lab.setAssumptions({ apply_grants: true })}>Include (default)</button>
          <button type="button" aria-pressed={!a.apply_grants} onClick={() => lab.setAssumptions({ apply_grants: false })}>Leave out</button>
        </div>
      </div>
      {t.kind === 'fixtures' && <p className="xsmall muted">Offline snapshot: tariffs and grant settings need the live engine.</p>}
    </form>
  );
}

export function ReadingForm({ lab, homeId }: { lab: Lab; homeId: string }) {
  const current = lab.state.draft.user_reading;
  const [gas, setGas] = useState(current?.gas_kwh != null ? String(current.gas_kwh) : '');
  const [elec, setElec] = useState(current?.elec_kwh != null ? String(current.elec_kwh) : '');
  const [err, setErr] = useState<string | null>(null);
  const t = useTransport();
  const manifest = useSnapshotManifest();
  const preset = manifest.data?.homes[homeId]?.user_reading?.reading;

  const parse = (s: string): number | null | 'bad' => {
    if (s.trim() === '') return null;
    const n = Number(s.replace(/,/g, ''));
    return Number.isFinite(n) && n >= 0 && n < 1e6 ? n : 'bad';
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const g = parse(gas);
    const el = parse(elec);
    if (g === 'bad' || el === 'bad') return setErr('Enter annual kWh as a number between 0 and 999,999.');
    if (g === null && el === null) return setErr('Enter at least one annual reading.');
    setErr(null);
    lab.setReading({ gas_kwh: g, elec_kwh: el });
  };
  return (
    <form className="lab-card" onSubmit={submit} noValidate>
      <h3>Your meter reading</h3>
      <p className="small muted">Replace the benchmark with your own annual use. Everything is recalculated as <b>user-provided</b>.</p>
      <div className="lab-fields">
        <div className="field">
          <label htmlFor="gas-kwh">Gas, kWh per year</label>
          <input id="gas-kwh" className="input" inputMode="decimal" value={gas} onChange={(e) => setGas(e.target.value)} aria-describedby="reading-err" />
        </div>
        <div className="field">
          <label htmlFor="elec-kwh">Electricity, kWh per year</label>
          <input id="elec-kwh" className="input" inputMode="decimal" value={elec} onChange={(e) => setElec(e.target.value)} aria-describedby="reading-err" />
        </div>
      </div>
      <p id="reading-err" className="field-error" role={err ? 'alert' : undefined}>{err}</p>
      <div className="row">
        <button className="btn btn-sm" type="submit">Recalculate with my reading</button>
        {current && <button className="btn btn-sm btn-ghost" type="button" onClick={() => { setGas(''); setElec(''); lab.setReading(null); }}>Use the benchmark again</button>}
      </div>
      {t.kind === 'fixtures' && (
        <p className="xsmall muted">
          Offline snapshot: custom readings need the live engine.
          {preset && <> This home has one precomputed reading. <button type="button" className="btn-link" onClick={() => { setGas(String(preset.gas_kwh ?? '')); setElec(String(preset.elec_kwh ?? '')); }}>Fill it in</button></>}
        </p>
      )}
    </form>
  );
}

function WhatIfBox({ lab, result }: { lab: Lab; result: ScenarioResult }) {
  const t = useTransport();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<WhatIfResponse | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const ask = async (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await t.whatif({ homeId: result.home.home_id, measures: result.request.measures, scenarioId: result.scenario_id, question: q.trim(), request: result.request });
      setOut(res);
      const o = res.outcome;
      // The engine recalculates through POST /api/scenario; numbers never come from the LLM.
      if (res.recalculated && o.new_request && (o.kind === 'change_measures' || o.kind === 'change_assumptions')) {
        lab.applyRequest(o.new_request);
      } else if (o.kind === 'change_measures' && (o.added.length || o.removed.length)) {
        lab.setMeasures(o.new_measures as MeasureId[]);
      }
    } catch (x) {
      setErr(x);
    } finally {
      setBusy(false);
    }
  };
  const o = out?.outcome;
  return (
    <form className="lab-card" onSubmit={ask}>
      <h3><MessageSquareText size={16} aria-hidden="true" /> Ask a what-if</h3>
      <p className="small muted">The language model only turns your question into a change (measures, prices, your readings). The change is checked against feasibility and the engine’s request schema, then the engine recalculates.</p>
      <div className="row">
        <label htmlFor="whatif-q" className="sr-only">What-if question</label>
        <input id="whatif-q" className="input" style={{ flex: 1, minWidth: 200 }} placeholder="What if I add a heat pump but skip solar?" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} />
        <button className="btn btn-sm" disabled={busy || !q.trim()} type="submit"><Sparkles size={14} aria-hidden="true" />{busy ? 'Asking…' : 'Ask'}</button>
      </div>
      {err != null && <ErrorState error={err} />}
      {o && (
        <div className="small whatif-out" aria-live="polite">
          {o.kind === 'out_of_scope' && <p>The system cannot answer that: it changes the plan, prices or your readings only.</p>}
          {o.kind === 'invalid_request' && <p className="dir-increase">Not recalculated: {o.invalid_reason ?? 'the change is not valid for the engine'}.</p>}
          {o.kind === 'change_assumptions' && Object.keys(o.request_changes).length > 0 && (
            <p>Changed: {Object.entries(o.request_changes).map(([k, v]) => `${assumptionLabel(k)} ${String(v)}`).join(', ')}</p>
          )}
          {o.added.length > 0 && <p>Added: {o.added.map(measureLabel).join(', ')}</p>}
          {o.removed.length > 0 && <p>Removed: {o.removed.map(measureLabel).join(', ')}</p>}
          {o.blocked.length > 0 && <p className="dir-increase">Blocked (not suitable): {o.blocked.map(measureLabel).join(', ')}</p>}
          {o.conditional.length > 0 && <p className="chip chip-verify">Needs verification: {o.conditional.map(measureLabel).join(', ')}</p>}
          {o.unsupported.length > 0 && <p className="muted">Not supported: {o.unsupported.join('; ')}</p>}
          <p className="xsmall muted">Parsed by {o.parser}.</p>
        </div>
      )}
    </form>
  );
}

export function ScenarioLabSection({ lab, result }: { lab: Lab; result: ScenarioResult }) {
  const { state } = lab;
  const llm = useLlmHealth();
  const t = useTransport();
  const a = state.draft.assumptions;
  const infeasible = new Set(result.feasibility.filter((f) => f.state === 'infeasible').map((f) => f.measure));
  const selected = new Set(lab.selectedMeasures);
  const llmUp = !!llm.data?.enabled && !!llm.data?.engine_configured;

  return (
    <section className="section" id="lab" aria-labelledby="lab-title">
      <div className="page">
        <SectionHeader
          index="06" kicker="Live Scenario Lab" id="lab-title" title="Change one thing. See what changes."
          lead="Every change goes back to the engine. The numbers above stay on the last confirmed scenario until the new one arrives, then everything swaps at once: charts, score, plans, explanation and evidence share one scenario ID."
        />

        {state.failure && (
          <ErrorState error={state.failure.error} onRetry={lab.retry}>
            <p className="small">Failed change: <b>{state.failure.change.join('; ')}</b>. Still showing scenario <span className="mono">{shortId(state.confirmed?.scenario_id)}</span>.</p>
            <div className="row">
              <button className="btn btn-sm btn-ghost" onClick={lab.revert}>Discard this change</button>
              {state.failure.error.kind === 'fixture_miss' && <button className="btn btn-sm btn-ghost" onClick={() => lab.setMeasures(null)}>Reset measures to engine default</button>}
            </div>
          </ErrorState>
        )}

        <div className="lab-grid">
          <div className="lab-card">
            <h3>Plan</h3>
            <div className="lab-toggles" role="group" aria-label="Measures in the scenario">
              {MEASURE_ORDER.map((m) => (
                <button key={m} type="button" className={`ltoggle ${selected.has(m) ? 'on' : ''}`} aria-pressed={selected.has(m)} disabled={infeasible.has(m)}
                  onClick={() => lab.toggleMeasure(m)} title={infeasible.has(m) ? 'Not suitable for this home' : undefined}>
                  {MEASURE_SHORT[m]}
                </button>
              ))}
            </div>
            <div className="row">
              <button className="btn btn-sm btn-ghost" onClick={() => lab.setMeasures(null)} disabled={state.draft.measures === null}>
                <RotateCcw size={14} aria-hidden="true" /> Engine default selection
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => lab.setMeasures([])} disabled={state.draft.measures?.length === 0}>Clear all</button>
            </div>
          </div>

          <div className="lab-card">
            <h3>Assumptions</h3>
            <div className="field">
              <span className="label" id="impact-l">Measure impacts</span>
              <div className="seg" role="group" aria-labelledby="impact-l">
                {(['low', 'mid', 'high'] as const).map((v) => (
                  <button key={v} aria-pressed={a.impact_level === v} onClick={() => lab.setAssumptions({ impact_level: v })}>{v === 'mid' ? 'Mid (default)' : v[0].toUpperCase() + v.slice(1)}</button>
                ))}
              </div>
            </div>
            <div className="field">
              <span className="label" id="scop-l">Heat-pump efficiency (SCOP)</span>
              <div className="seg" role="group" aria-labelledby="scop-l">
                {[2.5, null, 3.5].map((v) => (
                  <button key={String(v)} aria-pressed={a.heat_pump_scop === v} onClick={() => lab.setAssumptions({ heat_pump_scop: v })}>{v === null ? `Catalogue (${result.assumptions.heat_pump_scop ?? '3.0'})` : v}</button>
                ))}
              </div>
            </div>
            {t.kind === 'fixtures' && <p className="xsmall muted">Offline snapshot: one assumption preset at a time, with the engine’s default selection.</p>}
          </div>

          <ReadingForm key={`${result.home.home_id}-${JSON.stringify(draftOf(result).user_reading)}`} lab={lab} homeId={result.home.home_id} />

          <TariffForm key={`${result.home.home_id}-${String(draftOf(result).assumptions.gas_price_p)}-${String(draftOf(result).assumptions.elec_price_p)}`} lab={lab} result={result} />

          {llmUp
            ? <WhatIfBox lab={lab} result={result} />
            : (
              <div className="lab-card lab-card-muted">
                <h3><MessageSquareText size={16} aria-hidden="true" /> Natural-language what-ifs</h3>
                <p className="small muted">
                  {t.kind === 'fixtures'
                    ? 'Needs the LLM service, which is not part of the offline snapshot. Use the controls instead: they drive the same engine.'
                    : `The LLM service is not available (${llm.error ? ERROR_TITLES[toApiError(llm.error).kind].toLowerCase() : 'disabled'}). The controls still recalculate everything.`}
                </p>
              </div>
            )}
        </div>

        {state.previous && state.confirmed ? <Diff prev={state.previous} curr={state.confirmed} /> : (
          <p className="small muted diff-empty">Make a change to see a before-and-after comparison of the two scenarios.</p>
        )}

        {state.history.length > 1 && (
          <div className="history">
            <p className="kicker"><History size={13} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px' }} /> Scenario timeline</p>
            <ol>
              {state.history.map((h, i) => (
                <li key={h.scenarioId} className={i === 0 ? 'is-current' : ''}>
                  <ScenarioIdBadge id={h.scenarioId} label={i === 0 ? 'Now' : `−${i}`} />
                  <span className="xsmall">{h.change.join('; ')}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  );
}
