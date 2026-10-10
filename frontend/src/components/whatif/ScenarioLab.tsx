import { useState, type FormEvent } from 'react';
import { History, MessageSquareText, RotateCcw, Sparkles } from 'lucide-react';
import { MEASURE_ORDER, type MeasureId, type ScenarioResult } from '../../api/schema';
import { useLlmHealth, useSnapshotManifest, useTransport } from '../../api/queries';
import { ERROR_TITLES, toApiError } from '../../api/errors';
import type { WhatIfResponse } from '../../api/schema';
import { draftOf, type ScenarioLab as Lab } from '../../hooks/useScenarioLab';
import { fmtGbp, fmtKg, fmtKwh, fmtNumber, fmtPct, fmtSigned, isNum, savingDirection, shortId } from '../../utils/format';
import { MEASURE_SHORT, measureLabel, packageName } from '../../utils/labels';
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
      const res = await t.whatif({ homeId: result.home.home_id, measures: result.request.measures, scenarioId: result.scenario_id, question: q.trim() });
      setOut(res);
      if (res.outcome.kind === 'change_measures' && (res.outcome.added.length || res.outcome.removed.length)) {
        lab.setMeasures(res.outcome.new_measures as MeasureId[]); // the engine recalculates; numbers never come from the LLM
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
      <p className="small muted">The language model only turns your question into a measure change. The change is checked against feasibility, then the engine recalculates.</p>
      <div className="row">
        <label htmlFor="whatif-q" className="sr-only">What-if question</label>
        <input id="whatif-q" className="input" style={{ flex: 1, minWidth: 200 }} placeholder="What if I add a heat pump but skip solar?" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} />
        <button className="btn btn-sm" disabled={busy || !q.trim()} type="submit"><Sparkles size={14} aria-hidden="true" />{busy ? 'Asking…' : 'Ask'}</button>
      </div>
      {err != null && <ErrorState error={err} />}
      {o && (
        <div className="small whatif-out" aria-live="polite">
          {o.kind === 'out_of_scope' && <p>The system cannot answer that: it only changes the measure set.</p>}
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
