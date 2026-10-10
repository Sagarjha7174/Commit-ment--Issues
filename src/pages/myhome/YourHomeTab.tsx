import { AlertCircle, Flame, Leaf, MapPin, Zap } from 'lucide-react';
import type { Evidence, ScenarioResult } from '../../api/schema';
import type { ScenarioLab } from '../../hooks/useScenarioLab';
import { fmtKg, fmtKwh, missingText } from '../../utils/format';
import { prettyText } from '../../utils/labels';
import { limitations } from '../../utils/limitations';
import { measureEvidence, scoreEvidence } from '../../utils/evidence';
import { Blueprint } from '../../components/home/Blueprint';
import { ProvenanceChip } from '../../components/common/Knowledge';
import { WhyButton } from '../../components/common/EvidenceDrawer';
import { useOpenEvidence } from '../../components/common/evidenceContext';
import { Term } from '../../components/common/Term';
import { isFlat } from '../../utils/permissions';
import { NextButton, type TabId } from './StepBar';

type Classes = Evidence['score']['classes'];

/** "Poor: 30–49 out of 100", from the engine's own class bands. */
function classMeaning(label: string | null, classes?: Classes): string | null {
  if (!label || !classes) return null;
  const sorted = [...classes].sort((a, b) => a.min - b.min);
  const i = sorted.findIndex((c) => c.label === label);
  if (i < 0) return null;
  const hi = sorted[i + 1] ? sorted[i + 1].min - 1 : 100;
  return `Homes scoring ${sorted[i].min}–${hi} are classed ${label.toLowerCase()}.`;
}

/** Engine key issues read "insulation (walls Poor, roof Very Poor)": keep the plain part. */
function plainIssue(s: string): string {
  return prettyText(s.replace(/\s*\(.*\)\s*$/, '').replace(/^EPC /, 'official EPC '));
}

export function YourHomeTab({ r, lab, classes, onTab }: { r: ScenarioResult; lab: ScenarioLab; classes?: Classes; onTab(t: TabId): void }) {
  const s = r.score_before;
  const openEvidence = useOpenEvidence();
  const lim = limitations(r);
  const meaning = classMeaning(s.classification, classes);
  const factor = r.carbon.factors;
  return (
    <div className="tab-grid">
      <div className="tab-main">
        <div className="scorecard">
          <div className="scorecard-num">
            {s.total != null ? <><span className="big">{s.total}</span><span className="out">/100</span></> : <span className="big v-unknown">?</span>}
          </div>
          <div>
            <p className="scorecard-class">{s.classification ?? 'Score not available'}</p>
            <p className="small">{meaning ?? (s.total == null ? `Only ${s.completeness} parts of the home are recorded, so we can’t score it fairly.` : '')}</p>
            <p className="xsmall muted"><Term k="Green Home Score">Green Home Score</Term> · higher is better · {s.completeness} parts known</p>
            <WhyButton build={() => scoreEvidence(r, 'before')} label="How is this worked out?" />
          </div>
        </div>

        <div className="facts3">
          <div>
            <Flame size={18} aria-hidden="true" />
            <span className="facts3-label">Gas a year</span>
            <b>{fmtKwh(r.baseline.gas_kwh, r.baseline.gas_status)}</b>
            <ProvenanceChip provenance={r.baseline.gas_provenance} />
          </div>
          <div>
            <Zap size={18} aria-hidden="true" />
            <span className="facts3-label">Electricity a year</span>
            <b>{fmtKwh(r.baseline.elec_kwh, r.baseline.elec_status)}</b>
            <ProvenanceChip provenance={r.baseline.elec_provenance} />
          </div>
          <div>
            <Leaf size={18} aria-hidden="true" />
            <span className="facts3-label">Carbon a year (<Term k="CO₂e">CO₂e</Term>)</span>
            <b>{fmtKg(r.carbon.before_kg, r.carbon.status)}</b>
            <span className="xsmall muted">{r.carbon.before_kg == null ? missingText(r.carbon.status) : 'estimate'}</span>
          </div>
        </div>

        {s.key_issues.length > 0 && (
          <div className="issues-plain">
            <p className="kicker">What lets it down most</p>
            <ul>{s.key_issues.slice(0, 4).map((k) => <li key={k}>{plainIssue(k)}</li>)}</ul>
          </div>
        )}

        {lim.length > 0 && (
          <div className="limit" role="note">
            <AlertCircle size={18} aria-hidden="true" />
            <div>
              <p className="limit-head">{lim[0]}</p>
              {lim.length > 1 && <ul>{lim.slice(1, 3).map((l) => <li key={l}>{l}</li>)}</ul>}
            </div>
          </div>
        )}
      </div>

      <aside className="tab-side">
        <Blueprint
          isFlat={isFlat(r.home)}
          feasibility={r.feasibility}
          selected={new Set(lab.selectedMeasures)}
          applied={new Set(r.measures_applied)}
          onToggle={lab.toggleMeasure}
          onExplain={(m) => openEvidence(measureEvidence(r, m))}
        />
        <p className="xsmall muted">Tap a number to add or remove that improvement. Green = in the current plan.</p>
        <div className="location">
          <p className="kicker"><MapPin size={12} aria-hidden="true" /> Location & climate</p>
          <dl>
            <div><dt>Area</dt><dd>{r.home.postcode_outward ?? 'York'}, City of York, UK</dd></div>
            <div><dt>Climate</dt><dd>Cool, heating-led: the engine models space heating, hot water and grid electricity</dd></div>
            <div><dt>Carbon factors</dt><dd>{factor.gas ? `Gas ${factor.gas.kg_co2e_per_kwh}, electricity ${factor.elec?.kg_co2e_per_kwh} kg CO₂e/kWh (${factor.gas.source.split(':')[0]})` : 'Not available'}</dd></div>
            <div><dt>Flood / overheating risk</dt><dd className="v-unknown">Not checked yet</dd></div>
          </dl>
        </div>
      </aside>

      <div className="tab-foot"><NextButton to="options" label="See your options" onTab={onTab} /></div>
    </div>
  );
}
