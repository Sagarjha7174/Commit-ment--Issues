import type { Evidence, ScenarioResult } from '../../api/schema';
import { fmtNumber, missingText } from '../../utils/format';
import { SCORE_PART_LABEL } from '../../utils/labels';
import { scoreEvidence } from '../../utils/evidence';
import { ProvenanceChip } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';
import { SectionHeader } from '../common/States';
import './score.css';

type Classes = Evidence['score']['classes'];

function ScoreScale({ r, classes }: { r: ScenarioResult; classes?: Classes }) {
  const b = r.score_before;
  const a = r.score_after;
  const bands = classes ? [...classes].sort((x, y) => x.min - y.min) : [];
  return (
    <div className="scale" aria-hidden="true">
      <div className="scale-track">
        {bands.map((c, i) => {
          const next = bands[i + 1]?.min ?? 100;
          return <span key={c.label} className="scale-band" style={{ left: `${c.min}%`, width: `${next - c.min}%` }}><em>{c.label}</em></span>;
        })}
        {b.range_low != null && b.range_high != null && b.range_low !== b.range_high && (
          <span className="scale-range" style={{ left: `${b.range_low}%`, width: `${b.range_high - b.range_low}%` }} />
        )}
        {b.total != null && <span className="scale-mark scale-now" style={{ left: `${b.total}%` }}><b>{b.total}</b><i>today</i></span>}
        {a?.total != null && <span className="scale-mark scale-after" style={{ left: `${a.total}%` }}><b>{a.total}</b><i>after</i></span>}
      </div>
      <div className="scale-ticks">{[0, 25, 50, 75, 100].map((t) => <span key={t} style={{ left: `${t}%` }}>{t}</span>)}</div>
    </div>
  );
}

export function ScorePanel({ result: r, classes }: { result: ScenarioResult; classes?: Classes }) {
  const b = r.score_before;
  const a = r.score_after;
  const afterParts = new Map((a?.parts ?? []).map((p) => [p.part, p]));
  const unchanged = (a?.parts ?? []).filter((p) => p.status === 'unchanged_epc_not_reassessed');
  const completeness = b.parts.map((p) => p.sub != null);

  return (
    <section className="section" aria-labelledby="score-title">
      <div className="page">
        <SectionHeader
          index="02" kicker="Score & diagnosis" id="score-title" title="What the score sees"
          lead="Seven parts with fixed weights. Energy use is measured per square metre, so a large home is not penalised for its size. Missing parts widen the range instead of being guessed."
        />
        <div className="score-grid">
          <div className="panel score-summary">
            <div className="row">
              <p className="kicker">Today</p><span className="spacer" />
              <WhyButton build={() => scoreEvidence(r, 'before')} />
            </div>
            <p className="score-num serif num">{b.total ?? <span className="v-unknown">n/a</span>}<small>/100</small></p>
            <p className="score-class">{b.classification ?? missingText(b.status)}</p>
            <div className="pips" role="img" aria-label={`${b.completeness} score parts recorded`}>
              {completeness.map((ok, i) => <span key={i} className={ok ? 'pip pip-ok' : 'pip pip-missing'} />)}
              <span className="small muted">{b.completeness} parts recorded</span>
            </div>
            {b.range_low != null && b.range_high != null && b.range_low !== b.range_high && (
              <p className="small">Range <b className="num">{b.range_low}–{b.range_high}</b>: missing parts could move the score anywhere in this band.</p>
            )}
            {b.notes.map((n) => <p key={n} className="xsmall muted">{n}</p>)}
            <hr className="rule" />
            <div className="row">
              <p className="kicker">After this scenario</p><span className="spacer" />
              <WhyButton build={() => scoreEvidence(r, 'after')} />
            </div>
            <p className="score-num serif num">{a?.total ?? <span className="v-unknown small">not estimated</span>}{a?.total != null && <small>/100</small>}</p>
            <p className="score-class">{a?.classification ?? ''}</p>
            {unchanged.length > 0 && (
              <p className="xsmall muted">The EPC efficiency part is not re-assessed after a retrofit, so the score cannot move as far as the carbon result in section 03. The score is never forced upward.</p>
            )}
          </div>

          <div className="panel score-parts">
            <ScoreScale r={r} classes={classes} />
            <table className="parts">
              <caption className="sr-only">Score parts: sub-score today and after the scenario, weight and points</caption>
              <thead>
                <tr><th scope="col">Part</th><th scope="col">Weight</th><th scope="col">Today</th><th scope="col">After</th></tr>
              </thead>
              <tbody>
                {b.parts.map((p) => {
                  const ap = afterParts.get(p.part);
                  return (
                    <tr key={p.part}>
                      <th scope="row">
                        <span className="part-name">{SCORE_PART_LABEL[p.part] ?? p.part}</span>
                        <span className="xsmall muted part-detail">{p.detail}</span>
                        <ProvenanceChip provenance={p.provenance} />
                      </th>
                      <td className="num">{fmtNumber(p.weight * 100)}%</td>
                      <td>
                        <div className={`bar ${p.sub == null ? 'bar-missing' : ''}`}><span style={{ width: `${p.used_sub}%` }} /></div>
                        <span className="xsmall num">{p.sub != null ? `${fmtNumber(p.sub)} · ${fmtNumber(p.points, 1)} pts` : `missing · scored ${p.used_sub}`}</span>
                      </td>
                      <td>
                        {ap ? (
                          <>
                            <div className="bar bar-saving"><span style={{ width: `${ap.used_sub}%` }} /></div>
                            <span className="xsmall num">{ap.sub != null ? `${fmtNumber(ap.sub)} · ${fmtNumber(ap.points, 1)} pts` : 'missing'}{ap.status === 'unchanged_epc_not_reassessed' ? ' · not re-assessed' : ''}</span>
                          </>
                        ) : <span className="xsmall muted">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {b.key_issues.length > 0 && (
              <div className="issues">
                <p className="kicker">Main issues</p>
                <ul>{b.key_issues.map((k) => <li key={k}>{k}</li>)}</ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
