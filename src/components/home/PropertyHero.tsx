import { AlertCircle, ArrowRight, Gauge } from 'lucide-react';
import type { MeasureId, ScenarioResult } from '../../api/schema';
import { fmtKwh, fmtNumber, humanise, missingText } from '../../utils/format';
import { CONTROLS_LABEL, HEATING_LABEL } from '../../utils/labels';
import { measureEvidence, scoreEvidence } from '../../utils/evidence';
import { KnowledgeLegend, ProvenanceChip, Val } from '../common/Knowledge';
import { WhyButton } from '../common/EvidenceDrawer';
import { useOpenEvidence } from '../common/evidenceContext';
import { Axonometric } from './Axonometric';
import { limitations } from '../../utils/limitations';
import './home.css';

interface Props {
  result: ScenarioResult;
  selected: ReadonlySet<string>;
  onToggle(m: MeasureId): void;
}

function yesNo(v: boolean | null): string | null {
  return v === null ? null : v ? 'Yes' : 'No';
}

export function PropertyHero({ result: r, selected, onToggle }: Props) {
  const h = r.home;
  const s = r.score_before;
  const prov = h.provenance;
  const openEvidence = useOpenEvidence();
  const lim = limitations(r);
  const facts: { label: string; value: string | null; provKey?: string; status?: string | null }[] = [
    { label: 'Property', value: [h.built_form, h.property_type].filter(Boolean).join(' ') || null },
    { label: 'Built', value: h.age_band },
    { label: 'Floor area', value: h.floor_area_m2 != null ? `${fmtNumber(h.floor_area_m2)} m²` : null, provKey: 'floor_area_m2' },
    { label: 'EPC rating', value: h.rating ? `${h.rating}${h.sap_score != null ? ` (SAP ${fmtNumber(h.sap_score)})` : ''}` : null, provKey: 'sap_score' },
    { label: 'Walls', value: h.walls_rating, provKey: 'walls_rating' },
    { label: 'Roof', value: h.roof_rating, provKey: 'roof_rating' },
    { label: 'Glazing', value: h.glazing ? `${humanise(h.glazing)}${h.multi_glaze_pct != null && h.glazing === 'partial' ? ` (${fmtNumber(h.multi_glaze_pct)}% multi)` : ''}` : null, provKey: 'glazing' },
    { label: 'Heating', value: h.heating_type ? `${HEATING_LABEL[h.heating_type] ?? humanise(h.heating_type)}${h.heating_rating ? ` · ${h.heating_rating}` : ''}` : null, provKey: 'heating_type' },
    { label: 'Controls', value: h.controls ? (CONTROLS_LABEL[h.controls] ?? humanise(h.controls)) : null, provKey: 'controls' },
    { label: 'Solar PV', value: yesNo(h.solar_pv), provKey: 'solar_pv' },
    { label: 'Mains gas', value: yesNo(h.mains_gas) },
    { label: 'Baseline gas', value: r.baseline.gas_kwh != null ? fmtKwh(r.baseline.gas_kwh) : null, provKey: 'baseline_gas_kwh', status: r.baseline.gas_status },
    { label: 'Baseline electricity', value: r.baseline.elec_kwh != null ? fmtKwh(r.baseline.elec_kwh) : null, provKey: 'baseline_elec_kwh', status: r.baseline.elec_status },
  ];
  const baselineProv = (k?: string) => {
    if (k === 'baseline_gas_kwh') return r.baseline.gas_provenance;
    if (k === 'baseline_elec_kwh') return r.baseline.elec_provenance;
    return k ? prov[k] : undefined;
  };

  return (
    <section className="hero" aria-labelledby="home-title">
      <div className="hero-main">
        <p className="kicker"><b>01</b>Property intelligence</p>
        <h2 id="home-title" className="hero-title">{h.display_label}</h2>
        <div className="row hero-meta">
          <span className="epc" aria-label={`EPC band ${h.rating ?? 'unknown'}`}><small>EPC</small>{h.rating ?? '?'}</span>
          <span className="mono xsmall">ID {h.home_id}</span>
          {h.postcode_outward && <span className="chip">{h.postcode_outward}</span>}
          {h.split && <span className="chip">{h.split} split</span>}
        </div>

        <div className="hero-score">
          <div className="hero-score-num">
            <Gauge size={18} aria-hidden="true" />
            {s.total != null ? (
              <>
                <span className="serif hero-big num">{s.total}</span>
                <span className="hero-out">/100</span>
              </>
            ) : (
              <span className="serif hero-big v-unknown">n/a</span>
            )}
          </div>
          <div>
            <p className="hero-class">{s.classification ?? missingText(s.status)}</p>
            <p className="small muted">
              Green Home Score · {s.completeness} parts recorded
              {s.range_low != null && s.range_high != null && s.range_low !== s.range_high && <> · range {s.range_low}–{s.range_high}</>}
            </p>
            <WhyButton build={() => scoreEvidence(r, 'before')} label="Why this score?" />
          </div>
        </div>

        {lim.length > 0 && (
          <div className="limit" role="note">
            <AlertCircle size={18} aria-hidden="true" />
            <div>
              <p className="kicker">What the data cannot tell us</p>
              <p className="limit-head">{lim[0]}</p>
              {lim.length > 1 && <ul>{lim.slice(1).map((l) => <li key={l}>{l}</li>)}</ul>}
            </div>
          </div>
        )}

        <div className="row hero-cta">
          <a className="btn" href="#studio">Compare the three plans <ArrowRight size={16} aria-hidden="true" /></a>
          <a className="btn btn-ghost" href="#lab">Change the plan or enter a meter reading</a>
        </div>
      </div>

      <div className="hero-side">
        <Axonometric
          home={h}
          scenarioId={r.scenario_id}
          buildOrder={r.simulation.measures.map((m) => m.measure)}
          isFlat={h.property_type === 'Flat' || h.property_type === 'Maisonette'}
          feasibility={r.feasibility}
          selected={selected}
          applied={new Set(r.measures_applied)}
          onToggle={onToggle}
          onExplain={(m) => openEvidence(measureEvidence(r, m))}
        />
      </div>

      <div className="hero-facts">
        <dl className="facts">
          {facts.map((f) => {
            const p = baselineProv(f.provKey) ?? (f.value === null ? 'unavailable' : undefined);
            return (
              <div key={f.label}>
                <dt>{f.label}</dt>
                <dd>
                  {f.value !== null
                    ? <Val provenance={p ?? 'observed'}>{f.value}</Val>
                    : <Val tier="unknown">{p === 'not_applicable' ? 'Not applicable' : f.status ? humanise(f.status) : 'Not recorded'}</Val>}
                  {p && <ProvenanceChip provenance={p} compact />}
                </dd>
              </div>
            );
          })}
        </dl>
        <KnowledgeLegend />
      </div>
    </section>
  );
}
