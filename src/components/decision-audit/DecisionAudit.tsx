/** Decision audit + uncertainty, rendered from the engine's generated audit and sensitivity blocks (never hand-written). */
import { Check, Shuffle } from 'lucide-react';
import { OBJECTIVES, type Objective, type ScenarioResult } from '../../api/schema';
import { fmtGbp, fmtKg, fmtKwh, fmtNumber, humanise, shortId } from '../../utils/format';
import { measureLabel, OBJECTIVE_SHORT, packageName, prettyText, PROVENANCE_INFO, SENSITIVITY_RUN_LABEL } from '../../utils/labels';
import { KnowledgeMark, ProvenanceChip } from '../common/Knowledge';
import { ScenarioIdBadge } from '../common/ScenarioIdBadge';
import { EmptyState, SectionHeader } from '../common/States';
import './audit.css';

function Triad({ r, objective }: { r: ScenarioResult; objective: Objective }) {
  const s = r.score_before;
  const verify = r.feasibility.filter((f) => f.state === 'needs_verification');
  const unvalidated = r.simulation.measures.filter((m) => m.status === 'ok' && m.validated_impact === false).map((m) => measureLabel(m.measure));
  const surv = r.sensitivity?.survival[objective];
  const baselineTier = PROVENANCE_INFO[r.baseline.gas_provenance]?.tier ?? 'unknown';
  return (
    <div className="triad">
      <article className="triad-card">
        <p className="kicker">1 · Data completeness</p>
        <p className="triad-big serif">{s.completeness}</p>
        <p className="small">score parts recorded{s.missing_parts.length > 0 && <>; missing: {s.missing_parts.map(humanise).join(', ')}</>}.</p>
        <p className="small">{verify.length} measure(s) need verification{verify.length > 0 && <> ({verify.map((f) => measureLabel(f.measure)).join(', ')})</>}.</p>
      </article>
      <article className="triad-card">
        <p className="kicker">2 · Model uncertainty</p>
        <p className="triad-big"><KnowledgeMark tier={baselineTier} /> <span className="serif">{humanise(r.baseline.source)}</span></p>
        <p className="small">Baseline: gas <ProvenanceChip provenance={r.baseline.gas_provenance} />, electricity <ProvenanceChip provenance={r.baseline.elec_provenance} />.</p>
        <p className="small">{unvalidated.length ? <>Impacts not validated against NEED: {unvalidated.join(', ')}.</> : 'All applied impacts come from NEED measured savings, or nothing is applied.'}</p>
        {r.warnings.some((w) => w.includes('overestimated')) && <p className="xsmall muted">Combined fabric savings exceed NEED measured combinations by 5.6–13.8 pp.</p>}
      </article>
      <article className="triad-card">
        <p className="kicker">3 · Assumption sensitivity</p>
        {surv ? (
          <>
            <p className="triad-big serif">{surv.survives}</p>
            <p className="small">runs keep the <b>{OBJECTIVE_SHORT[objective].kicker.toLowerCase()}</b> pick ({packageName(surv.base_pick)}).</p>
            {surv.changed_under.length > 0 && <p className="small">Flips under: {surv.changed_under.map((n) => SENSITIVITY_RUN_LABEL[n] ?? n).join('; ')}.</p>}
          </>
        ) : <p className="small muted">Sensitivity not run for this scenario.</p>}
        {r.sensitivity && <p className="xsmall muted">{r.sensitivity.label}</p>}
      </article>
    </div>
  );
}

function StabilityMatrix({ r }: { r: ScenarioResult }) {
  const sens = r.sensitivity;
  if (!sens) return <EmptyState title="Sensitivity analysis not included" />;
  return (
    <div className="table-wrap">
      <table className="data-table stability">
        <caption className="sr-only">For each sensitivity run, whether each featured pick stays the same</caption>
        <thead>
          <tr>
            <th scope="col">Tested change</th>
            {OBJECTIVES.map((o) => <th key={o} scope="col">{OBJECTIVE_SHORT[o].kicker}</th>)}
          </tr>
        </thead>
        <tbody>
          <tr className="stability-base">
            <th scope="row">Base pick</th>
            {OBJECTIVES.map((o) => <td key={o} className="small">{packageName(sens.survival[o]?.base_pick)}</td>)}
          </tr>
          {sens.runs.map((run) => (
            <tr key={run.name}>
              <th scope="row">{SENSITIVITY_RUN_LABEL[run.name] ?? run.change}<span className="xsmall muted"> · {run.change}</span></th>
              {OBJECTIVES.map((o) => {
                const base = sens.survival[o]?.base_pick ?? null;
                const now = run.featured[o] ?? null;
                const same = base === now;
                return (
                  <td key={o} className={same ? 'cell-same' : 'cell-flip'}>
                    {same
                      ? <span className="row"><Check size={14} aria-hidden="true" /><span>Same</span></span>
                      : <span className="row"><Shuffle size={14} aria-hidden="true" /><span>{packageName(now)}</span></span>}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <th scope="row">Survives</th>
            {OBJECTIVES.map((o) => <td key={o}><b>{sens.survival[o]?.survives ?? '—'}</b></td>)}
          </tr>
        </tbody>
      </table>
      <p className="xsmall muted stability-untested">Not tested: {sens.untested.join('; ')}.</p>
    </div>
  );
}

export function DecisionAudit({ result: r, objective }: { result: ScenarioResult; objective: Objective }) {
  const a = r.audit;
  const pc = a.packages_considered;
  return (
    <section className="section" id="audit" aria-labelledby="audit-title">
      <div className="page">
        <SectionHeader
          index="08" kicker="Decision audit" id="audit-title" title="Why this plan, and when it would change"
          lead="Generated automatically from the same scenario result as everything above. Three kinds of uncertainty are kept apart: what is missing, what is modelled, and which assumptions could flip the decision."
          aside={<div className="row"><ScenarioIdBadge id={a.scenario_id} label="Audit of" /></div>}
        />
        <Triad r={r} objective={objective} />

        <h3 className="audit-h">Decision stability under tested assumptions</h3>
        <StabilityMatrix r={r} />

        <div className="audit-grid">
          <details className="audit-block" open>
            <summary>Winner and the main alternative</summary>
            {a.winner ? (
              <div className="stack small">
                <p><b>{packageName(a.winner.package.package_id)}</b> for “{OBJECTIVE_SHORT[a.winner.objective as Objective]?.kicker ?? a.winner.objective}”: {fmtGbp(a.winner.package.cost_gbp)}, {fmtKg(a.winner.package.carbon_saving_kg)}.</p>
                {a.alternative && <p>Alternative: <b>{packageName(a.alternative.package_id)}</b>: {fmtGbp(a.alternative.cost_gbp)}, {fmtKg(a.alternative.carbon_saving_kg)}.</p>}
                {a.main_factors && <ul>{a.main_factors.map((f) => <li key={f}>{prettyText(f)}</li>)}</ul>}
              </div>
            ) : <p className="small muted">No winning package: {(a.fallbacks ?? []).join('; ') || 'none could be estimated'}.</p>}
          </details>

          <details className="audit-block" open>
            <summary>Objectives behind each featured plan</summary>
            <ul className="small stack">
              {(a.featured ?? []).map((f) => (
                <li key={f.objective}><b>{f.label}</b>: {f.objective_text}. {f.package ? <>Pick: {packageName(f.package.package_id)}.</> : <span className="muted">{f.message}</span>}</li>
              ))}
            </ul>
          </details>

          <details className="audit-block">
            <summary>Baseline and its provenance</summary>
            <dl className="audit-dl small">
              <div><dt>Gas</dt><dd>{fmtKwh(a.baseline.gas_kwh)} <ProvenanceChip provenance={a.baseline.gas_provenance} /></dd></div>
              <div><dt>Electricity</dt><dd>{fmtKwh(a.baseline.elec_kwh)} <ProvenanceChip provenance={a.baseline.elec_provenance} /></dd></div>
              <div><dt>Source</dt><dd>{humanise(a.baseline.source)}</dd></div>
              {a.baseline.note && <div><dt>Note</dt><dd>{a.baseline.note}</dd></div>}
            </dl>
          </details>

          <details className="audit-block">
            <summary>Feasibility of every measure</summary>
            <ul className="small stack">
              {a.feasibility.map((f) => (
                <li key={f.measure}><b>{measureLabel(f.measure)}</b>: {humanise(f.state)} ({f.reason}){f.missing_inputs.length > 0 && <>; missing {f.missing_inputs.join(', ')}</>}</li>
              ))}
            </ul>
          </details>

          <details className="audit-block">
            <summary>Packages considered and excluded</summary>
            {pc ? (
              <ul className="small stack">
                <li>{fmtNumber(pc.count)} packages evaluated; threshold {fmtNumber(pc.threshold_pct)}% of baseline emissions{pc.budget_gbp != null ? `, budget ${fmtGbp(pc.budget_gbp)}` : ', no budget limit'}.</li>
                <li>{Object.keys(pc.dominated).length} dominated (another package is cheaper and saves more).</li>
                <li>{Object.keys(pc.conditional).length} conditional on verification.</li>
                <li>{pc.missing_cost.length} without a usable cost (kept out of cost rankings).</li>
                {Object.entries(pc.excluded_measures).map(([m, why]) => <li key={m}>{measureLabel(m)} excluded: {why}</li>)}
              </ul>
            ) : <p className="small muted">Package search not included.</p>}
          </details>

          <details className="audit-block">
            <summary>Unknowns that could change the decision</summary>
            {a.unknowns.length ? <ul className="small stack">{a.unknowns.map((u) => <li key={u}>{prettyText(u)}</li>)}</ul> : <p className="small muted">None reported.</p>}
          </details>

          <details className="audit-block">
            <summary>Warnings</summary>
            <ul className="small stack">{a.warnings.map((w) => <li key={w}>{prettyText(w)}</li>)}</ul>
          </details>

          <details className="audit-block">
            <summary>Versions and identifiers</summary>
            <dl className="audit-dl small">
              {Object.entries(a.versions).map(([k, v]) => <div key={k}><dt>{humanise(k)}</dt><dd className="mono">{v}</dd></div>)}
              <div><dt>Scenario</dt><dd className="mono" title={a.scenario_id}>{shortId(a.scenario_id, 16)}…</dd></div>
            </dl>
          </details>
        </div>
      </div>
    </section>
  );
}
