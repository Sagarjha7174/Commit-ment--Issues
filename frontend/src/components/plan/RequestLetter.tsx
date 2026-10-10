/** A ready-to-send request to the landlord or building management, built from engine figures only. */
import { useState } from 'react';
import { Copy, Download } from 'lucide-react';
import type { ScenarioResult } from '../../api/schema';
import type { Situation } from '../../hooks/useSituation';
import { fmtGbp, fmtKg, fmtKwh, isNum, shortId } from '../../utils/format';
import { measureLabel } from '../../utils/labels';
import { isFlat } from '../../utils/permissions';
import { selectionPackage } from '../../utils/scenarioDiff';

function letterText(r: ScenarioResult, s: Situation): string {
  const to = s.role === 'tenant' ? 'landlord' : 'building manager / residents’ committee';
  const rows = r.simulation.measures.filter((m) => r.measures_applied.includes(m.measure));
  const pkg = selectionPackage(r);
  const lines = rows.map((m) => {
    const parts: string[] = [];
    if (isNum(m.gas_saving_kwh) && Math.abs(m.gas_saving_kwh) >= 0.5) parts.push(`${fmtKwh(m.gas_saving_kwh)} less gas`);
    if (isNum(m.elec_saving_kwh) && Math.abs(m.elec_saving_kwh) >= 0.5) parts.push(m.elec_saving_kwh > 0 ? `${fmtKwh(m.elec_saving_kwh)} less electricity` : `${fmtKwh(-m.elec_saving_kwh)} more electricity`);
    return `  • ${measureLabel(m.measure)}${parts.length ? ` — about ${parts.join(', ')}` : m.status !== 'ok' ? ' — saving not estimated' : ''}`;
  });
  const verify = r.feasibility.filter((f) => r.measures_applied.includes(f.measure) && f.state === 'needs_verification');
  return [
    `Dear ${to},`,
    '',
    `I live at ${r.home.display_label} (property reference ${r.home.home_id}). An energy check based on the home’s EPC record suggests these improvements could make it warmer and cut energy use:`,
    '',
    ...lines,
    '',
    isNum(r.carbon.total_kg) ? `Estimated carbon saving for the whole plan: ${fmtKg(r.carbon.total_kg)}.` : 'The carbon saving could not be estimated from the available data.',
    pkg && isNum(pkg.cost_gbp) ? `Indicative cost: ${fmtGbp(pkg.cost_gbp)} (typical EPC figure, not a quote).` : '',
    verify.length ? `A survey would need to confirm: ${verify.map((f) => measureLabel(f.measure)).join(', ')}.` : '',
    '',
    s.role === 'tenant'
      ? 'Could we discuss whether you would be willing to carry out, or allow, this work?'
      : 'Could this be discussed at the next meeting, including approval and how costs would be shared?',
    '',
    `These figures are estimates from Green Home Score (scenario ${shortId(r.scenario_id)}), not quotes or guarantees.`,
    '',
    'Kind regards,',
  ].filter((l, i, a) => !(l === '' && a[i - 1] === '')).join('\n');
}

export function RequestLetter({ result, situation }: { result: ScenarioResult; situation: Situation }) {
  const [copied, setCopied] = useState(false);
  if (!result.measures_applied.length) return null;
  const needed = situation.role === 'tenant' || situation.role === 'leaseholder' || isFlat(result.home);
  if (!needed) return null;
  const text = letterText(result, situation);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'green-home-request.txt';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="plan-card">
      <h3>{situation.role === 'tenant' ? 'Ask your landlord' : 'Ask your building'}</h3>
      <p className="small muted">A ready-made message with the engine’s estimates. Edit it as you like.</p>
      <pre className="letter" aria-label="Request letter">{text}</pre>
      <div className="row">
        <button className="btn btn-sm" onClick={copy}><Copy size={14} aria-hidden="true" /> {copied ? 'Copied' : 'Copy text'}</button>
        <button className="btn btn-sm btn-ghost" onClick={download}><Download size={14} aria-hidden="true" /> Download</button>
      </div>
    </div>
  );
}
